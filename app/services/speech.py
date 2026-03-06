"""Azure Speech Service integration for TTS Avatar batch synthesis."""

import logging
import time
import uuid
from typing import Optional

import requests
from fastapi import HTTPException

from app.config import (
    API_VERSION,
    DEFAULT_AVATAR_CHARACTER,
    DEFAULT_AVATAR_STYLE,
    DEFAULT_LANGUAGE,
    DEFAULT_VOICE,
    SPEECH_ENDPOINT,
    SPEECH_KEY,
)
from app.models import PodcastRequest

logger = logging.getLogger("video-podcaster")


def get_auth_headers() -> dict[str, str]:
    """Get authentication headers for Azure Speech API."""
    return {
        "Ocp-Apim-Subscription-Key": SPEECH_KEY,
        "Content-Type": "application/json",
    }


def estimate_speech_duration_seconds(text: str, words_per_minute: int = 130) -> int:
    """Estimate speech duration from text. Italian speech ~130 WPM."""
    word_count = len(text.split())
    return int((word_count / words_per_minute) * 60)


def build_single_ssml(text: str, voice: str, language: str) -> str:
    """Build a single SSML document from plain text."""
    paragraphs = text.split("\n\n")
    ssml_body = '<break time="800ms"/>'.join(
        [p.strip() for p in paragraphs if p.strip()]
    )
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">'
        f'<voice name="{voice}">'
        f'<prosody rate="0%">{ssml_body}</prosody>'
        f'</voice></speak>'
    )


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"podcast-{uuid.uuid4().hex[:12]}"


def submit_avatar_synthesis(job_id: str, request: PodcastRequest) -> dict:
    """Submit a batch avatar synthesis job to Azure Speech Service."""
    voice = request.voice or DEFAULT_VOICE
    language = request.language or DEFAULT_LANGUAGE
    avatar_character = request.avatar_character or DEFAULT_AVATAR_CHARACTER
    avatar_style = request.avatar_style or DEFAULT_AVATAR_STYLE

    if request.input_kind == "SSML":
        input_kind = "SSML"
        content = request.text
    else:
        input_kind = "SSML"
        content = build_single_ssml(request.text, voice, language)

    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses/{job_id}?api-version={API_VERSION}"

    payload = {
        "inputKind": input_kind,
        "inputs": [{"content": content}],
        "synthesisConfig": {"voice": voice},
        "avatarConfig": {
            "talkingAvatarCharacter": avatar_character,
            "talkingAvatarStyle": avatar_style,
            "videoFormat": request.video_format or "mp4",
            "videoCodec": request.video_codec or "h264",
            "subtitleType": "soft_embedded" if request.subtitle else "none",
            "backgroundColor": request.background_color or "#FFFFFFFF",
            "videoBitrate": 2000000,
        },
        "properties": {"timeToLiveInHours": 48},
    }

    logger.info(f"Submitting avatar synthesis job: {job_id}")
    response = requests.put(url, json=payload, headers=get_auth_headers())

    if response.status_code >= 400:
        error_detail = response.text
        logger.error(f"Avatar synthesis submission failed: {response.status_code} - {error_detail}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Azure Speech API error: {error_detail}",
        )

    return response.json()


def get_synthesis_status(job_id: str) -> dict:
    """Get the status of a batch avatar synthesis job."""
    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses/{job_id}?api-version={API_VERSION}"
    response = requests.get(url, headers=get_auth_headers())

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to get job status: {response.text}",
        )

    return response.json()


def delete_synthesis_job(job_id: str) -> bool:
    """Delete a batch avatar synthesis job."""
    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses/{job_id}?api-version={API_VERSION}"
    response = requests.delete(url, headers=get_auth_headers())
    return response.status_code < 400


def list_synthesis_jobs() -> list[dict]:
    """List all batch synthesis jobs from Azure."""
    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses?api-version={API_VERSION}"
    response = requests.get(url, headers=get_auth_headers())

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Failed to list jobs")

    return response.json().get("value", [])


async def poll_and_track_job(
    job_id: str,
    jobs_tracker: dict[str, dict],
    title: Optional[str] = None,
    on_complete: Optional[callable] = None,
) -> None:
    """Background task to poll job status until completion."""
    max_polls = 120
    poll_interval = 10

    for i in range(max_polls):
        try:
            result = get_synthesis_status(job_id)
            status = result.get("status", "Unknown")

            jobs_tracker[job_id] = {
                "job_id": job_id,
                "status": status,
                "title": title,
                "created_at": result.get("createdDateTime"),
                "last_updated": result.get("lastActionDateTime"),
                "video_url": None,
                "download_url": None,
                "duration_ms": None,
                "size_bytes": None,
                "error": None,
            }

            if status == "Succeeded":
                props = result.get("properties", {})
                outputs = result.get("outputs", {})
                video_url = outputs.get("result", "")

                jobs_tracker[job_id].update({
                    "video_url": video_url,
                    "duration_ms": props.get("durationInMilliseconds"),
                    "size_bytes": props.get("sizeInBytes"),
                })
                logger.info(f"Job {job_id} completed. Video URL: {video_url}")

                if on_complete and video_url:
                    try:
                        on_complete(job_id, video_url, jobs_tracker)
                    except Exception as e:
                        logger.error(f"Post-completion callback failed for {job_id}: {e}")
                return

            elif status == "Failed":
                props = result.get("properties", {})
                error = props.get("error", {})
                jobs_tracker[job_id]["error"] = error.get("message", "Unknown error")
                logger.error(f"Job {job_id} failed: {jobs_tracker[job_id]['error']}")
                return

            logger.info(f"Job {job_id} status: {status} (poll {i + 1}/{max_polls})")

        except Exception as e:
            logger.error(f"Error polling job {job_id}: {e}")

        time.sleep(poll_interval)

    jobs_tracker[job_id]["status"] = "Timeout"
    jobs_tracker[job_id]["error"] = "Job polling timed out after 20 minutes"
