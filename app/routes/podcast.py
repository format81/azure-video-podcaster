"""Podcast generation and management routes."""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import (
    DEFAULT_AVATAR_CHARACTER,
    DEFAULT_AVATAR_STYLE,
    MAX_TEXT_LENGTH,
    MAX_VIDEO_DURATION_SECONDS,
    MIN_TEXT_LENGTH,
    SPEECH_KEY,
    STANDARD_AVATARS,
)
from app.middleware import check_rate_limit, verify_api_key
from app.models import PodcastListResponse, PodcastRequest, PodcastStatus, TopicRequest
from app.services.openai import generate_script, is_openai_configured
from app.services.speech import (
    delete_synthesis_job,
    estimate_speech_duration_seconds,
    generate_job_id,
    get_synthesis_status,
    list_synthesis_jobs,
    poll_and_track_job,
    submit_avatar_synthesis,
)
from app.services.storage import (
    generate_sas_url,
    is_storage_configured,
    persist_video_on_complete,
)

logger = logging.getLogger("video-podcaster")

router = APIRouter(prefix="/podcast", tags=["Podcast"])

# In-memory job tracker
jobs_tracker: dict[str, dict] = {}


def _validate_text(text: str) -> None:
    """Validate input text for length and content."""
    if len(text.strip()) < MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text too short. Minimum {MIN_TEXT_LENGTH} characters required.",
        )
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Maximum {MAX_TEXT_LENGTH} characters allowed.",
        )


def _validate_avatar(avatar_char: str, avatar_style: str) -> None:
    """Validate avatar character and style combination."""
    if avatar_char in STANDARD_AVATARS:
        if avatar_style not in STANDARD_AVATARS[avatar_char]:
            raise HTTPException(
                status_code=400,
                detail=f"Style '{avatar_style}' not available for avatar '{avatar_char}'. "
                       f"Available: {STANDARD_AVATARS[avatar_char]}",
            )


@router.post("/generate", response_model=PodcastStatus)
async def generate_podcast(
    request: PodcastRequest,
    background_tasks: BackgroundTasks,
    req: Request = None,
    _key: str | None = Depends(verify_api_key),
):
    """Generate a video podcast from text input.

    The text will be synthesized into a video with a speaking avatar.
    For a ~5 minute podcast, provide approximately 650-700 words.
    The job runs asynchronously - use the returned job_id to check status.
    """
    if req:
        check_rate_limit(req)

    if not SPEECH_KEY:
        raise HTTPException(status_code=500, detail="AZURE_SPEECH_KEY not configured")

    _validate_text(request.text)

    avatar_char = request.avatar_character or DEFAULT_AVATAR_CHARACTER
    avatar_style = request.avatar_style or DEFAULT_AVATAR_STYLE
    _validate_avatar(avatar_char, avatar_style)

    estimated_seconds = estimate_speech_duration_seconds(request.text)
    if estimated_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Estimated duration: {estimated_seconds // 60}min. Max is 20 minutes. "
                   f"Reduce text to ~2600 words for 20min or ~650 words for 5min.",
        )

    job_id = generate_job_id()

    try:
        submit_avatar_synthesis(job_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit synthesis: {str(e)}")

    created_at = datetime.now(timezone.utc).isoformat()
    jobs_tracker[job_id] = {
        "job_id": job_id,
        "status": "Submitted",
        "title": request.title,
        "created_at": created_at,
        "last_updated": None,
        "video_url": None,
        "download_url": None,
        "duration_ms": None,
        "size_bytes": None,
        "error": None,
        "estimated_duration_seconds": estimated_seconds,
    }

    on_complete = persist_video_on_complete if is_storage_configured() else None
    background_tasks.add_task(poll_and_track_job, job_id, jobs_tracker, request.title, on_complete)

    return PodcastStatus(
        job_id=job_id,
        status="Submitted",
        title=request.title,
        created_at=created_at,
    )


@router.post("/generate-from-topic", response_model=PodcastStatus)
async def generate_from_topic(
    request: TopicRequest,
    background_tasks: BackgroundTasks,
    req: Request = None,
    _key: str | None = Depends(verify_api_key),
):
    """Generate a podcast from a topic using Azure OpenAI to create the script.

    Requires Azure OpenAI to be configured (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT).
    """
    if req:
        check_rate_limit(req)

    if not is_openai_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT.",
        )

    if not SPEECH_KEY:
        raise HTTPException(status_code=500, detail="AZURE_SPEECH_KEY not configured")

    language = request.language or "it-IT"
    script = generate_script(request.topic, language)

    podcast_request = PodcastRequest(
        text=script,
        title=request.title or f"Podcast: {request.topic[:50]}",
        voice=request.voice,
        language=language,
        avatar_character=request.avatar_character,
        avatar_style=request.avatar_style,
        background_color=request.background_color,
        subtitle=request.subtitle,
        video_format=request.video_format,
        video_codec=request.video_codec,
    )

    return await generate_podcast(podcast_request, background_tasks, req)


@router.get("/{job_id}", response_model=PodcastStatus)
async def get_podcast_status(job_id: str, _key: str | None = Depends(verify_api_key)):
    """Get the status of a podcast generation job."""
    if job_id in jobs_tracker:
        return PodcastStatus(**{k: v for k, v in jobs_tracker[job_id].items()
                                if k in PodcastStatus.model_fields})

    try:
        result = get_synthesis_status(job_id)
        props = result.get("properties", {})
        outputs = result.get("outputs", {})

        return PodcastStatus(
            job_id=job_id,
            status=result.get("status", "Unknown"),
            created_at=result.get("createdDateTime"),
            last_updated=result.get("lastActionDateTime"),
            video_url=outputs.get("result"),
            duration_ms=props.get("durationInMilliseconds"),
            size_bytes=props.get("sizeInBytes"),
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {str(e)}")


@router.get("/{job_id}/download")
async def download_podcast(job_id: str, _key: str | None = Depends(verify_api_key)):
    """Get a download URL (SAS) for a completed podcast video.

    Requires Azure Blob Storage to be configured.
    """
    if not is_storage_configured():
        # Fallback to direct video URL
        if job_id in jobs_tracker and jobs_tracker[job_id].get("video_url"):
            return {"download_url": jobs_tracker[job_id]["video_url"]}
        raise HTTPException(status_code=503, detail="Azure Blob Storage is not configured")

    if job_id in jobs_tracker:
        download_url = jobs_tracker[job_id].get("download_url")
        if download_url:
            return {"download_url": download_url}
        if jobs_tracker[job_id].get("status") != "Succeeded":
            raise HTTPException(status_code=400, detail=f"Job is not complete. Status: {jobs_tracker[job_id].get('status')}")

    # Try to generate a new SAS URL for existing blob
    try:
        blob_name = f"{job_id}.mp4"
        sas_url = generate_sas_url(blob_name)
        return {"download_url": sas_url}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Video not found in storage: {str(e)}")


@router.get("/{job_id}/subtitle")
async def get_subtitle(job_id: str, format: str = "vtt", _key: str | None = Depends(verify_api_key)):
    """Get subtitles for a completed podcast.

    The subtitle URL is extracted from the Azure Speech synthesis outputs.
    Supported formats: vtt, srt (Azure provides WebVTT by default).
    """
    if job_id in jobs_tracker:
        if jobs_tracker[job_id].get("status") != "Succeeded":
            raise HTTPException(status_code=400, detail="Job is not complete yet")

    try:
        result = get_synthesis_status(job_id)
        if result.get("status") != "Succeeded":
            raise HTTPException(status_code=400, detail=f"Job status: {result.get('status')}")

        outputs = result.get("outputs", {})
        # Azure provides subtitle in the outputs
        subtitle_url = outputs.get("subtitle")
        if not subtitle_url:
            raise HTTPException(status_code=404, detail="No subtitles available for this job. Ensure subtitle was enabled during generation.")

        return {
            "job_id": job_id,
            "format": format,
            "subtitle_url": subtitle_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to get subtitles: {str(e)}")


@router.get("", response_model=PodcastListResponse)
async def list_podcasts(_key: str | None = Depends(verify_api_key)):
    """List all podcast generation jobs."""
    items = list_synthesis_jobs()
    jobs = []
    for item in items:
        props = item.get("properties", {})
        outputs = item.get("outputs", {})
        job_id = item.get("id", "")
        download_url = jobs_tracker.get(job_id, {}).get("download_url")
        jobs.append(PodcastStatus(
            job_id=job_id,
            status=item.get("status", "Unknown"),
            created_at=item.get("createdDateTime"),
            last_updated=item.get("lastActionDateTime"),
            video_url=outputs.get("result"),
            download_url=download_url,
            duration_ms=props.get("durationInMilliseconds"),
            size_bytes=props.get("sizeInBytes"),
        ))

    return PodcastListResponse(jobs=jobs, total=len(jobs))


@router.delete("/{job_id}")
async def delete_podcast(job_id: str, _key: str | None = Depends(verify_api_key)):
    """Delete a podcast generation job."""
    success = delete_synthesis_job(job_id)
    if success:
        jobs_tracker.pop(job_id, None)
        return {"message": f"Job {job_id} deleted successfully"}
    raise HTTPException(status_code=404, detail="Job not found or already deleted")


@router.post("/generate-script")
async def generate_script_template(_key: str | None = Depends(verify_api_key)):
    """Returns a template/guide for writing a 5-minute podcast script."""
    return {
        "guide": {
            "target_duration": "5 minutes",
            "target_word_count": "600-700 words",
            "speaking_rate": "~130 words per minute (Italian)",
            "structure": [
                "Introduzione (30 sec, ~65 parole): Saluto, presentazione del tema",
                "Contesto (1 min, ~130 parole): Background e perche' e' importante",
                "Corpo principale (2.5 min, ~325 parole): Analisi dettagliata, punti chiave",
                "Implicazioni (45 sec, ~100 parole): Cosa significa per il pubblico",
                "Conclusione (15 sec, ~30 parole): Recap e call-to-action",
            ],
        },
        "ssml_tips": {
            "pause": '<break time="500ms"/> per pause tra sezioni',
            "emphasis": "<emphasis>parola importante</emphasis>",
            "speed": '<prosody rate="-10%">testo piu lento</prosody>',
        },
        "example_request": {
            "text": "Benvenuti al nostro podcast settimanale sulla cybersecurity...",
            "title": "Episodio 1 - Threat Landscape Q1 2026",
            "voice": "it-IT-DiegoNeural",
            "avatar_character": "jeff",
            "avatar_style": "business",
            "subtitle": True,
        },
    }
