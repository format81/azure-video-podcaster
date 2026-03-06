"""
Azure Video Podcaster
Generates 5-minute avatar video podcasts from text input using Azure AI Speech TTS Avatar (Batch Synthesis API).
"""

import os
import uuid
import time
import logging
import requests
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.identity import DefaultAzureCredential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("video-podcaster")

app = FastAPI(
    title="Azure Video Podcaster",
    description="Generate 5-minute avatar video podcasts from text input",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Configuration ───────────────────────────────────────────────────────────

SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "westeurope")  # westeurope, westus2, southeastasia
SPEECH_ENDPOINT = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com"
API_VERSION = "2024-08-01"

# Storage for generated videos (optional - for persistent download links)
STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "podcast-videos")

# Default avatar settings
DEFAULT_AVATAR_CHARACTER = os.getenv("AVATAR_CHARACTER", "lisa")
DEFAULT_AVATAR_STYLE = os.getenv("AVATAR_STYLE", "casual-sitting")
DEFAULT_VOICE = os.getenv("TTS_VOICE", "it-IT-ElsaNeural")  # Italian voice
DEFAULT_LANGUAGE = os.getenv("TTS_LANGUAGE", "it-IT")

# Available standard avatars (as of 2025)
STANDARD_AVATARS = {
    "lisa": ["casual-sitting", "graceful-sitting", "graceful-standing", "technical-sitting", "technical-standing"],
    "harry": ["business", "casual", "youthful"],
    "jeff": ["business", "casual", "formal"],
    "max": ["business", "casual", "formal"],
    "lori": ["casual", "formal", "graceful"],
}

# Available voices for Italian
ITALIAN_VOICES = [
    "it-IT-ElsaNeural",
    "it-IT-IsabellaNeural",
    "it-IT-DiegoNeural",
    "it-IT-GiuseppeNeural",
    "it-IT-BenignoNeural",
    "it-IT-CalimeroNeural",
    "it-IT-CataldoNeural",
    "it-IT-FabiolaNeural",
    "it-IT-FiammaNeural",
    "it-IT-GianniNeural",
    "it-IT-ImeldaNeural",
    "it-IT-IrmaNeural",
    "it-IT-LisandroNeural",
    "it-IT-PalmiraNeural",
    "it-IT-PierinaNeural",
    "it-IT-RinaldoNeural",
]

# ─── Models ──────────────────────────────────────────────────────────────────

class PodcastRequest(BaseModel):
    """Request to generate a video podcast."""
    text: str = Field(..., description="The podcast script text (plain text or SSML)")
    title: Optional[str] = Field(None, description="Podcast episode title")
    voice: Optional[str] = Field(None, description="Azure TTS voice name (e.g., it-IT-ElsaNeural)")
    language: Optional[str] = Field(None, description="Language code (e.g., it-IT)")
    avatar_character: Optional[str] = Field(None, description="Avatar character (e.g., lisa, harry, jeff)")
    avatar_style: Optional[str] = Field(None, description="Avatar style (e.g., casual-sitting)")
    background_color: Optional[str] = Field("#FFFFFFFF", description="Background color (hex ARGB)")
    subtitle: Optional[bool] = Field(True, description="Enable embedded subtitles")
    video_format: Optional[str] = Field("mp4", description="Video format: mp4 or webm")
    video_codec: Optional[str] = Field("h264", description="Video codec: h264, hevc, av1, vp9")
    input_kind: Optional[str] = Field("PlainText", description="Input kind: PlainText or SSML")

class PodcastStatus(BaseModel):
    """Status of a podcast generation job."""
    job_id: str
    status: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    video_url: Optional[str] = None
    duration_ms: Optional[int] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None

class PodcastListResponse(BaseModel):
    """List of podcast jobs."""
    jobs: list[PodcastStatus]
    total: int


# ─── In-memory job tracker ──────────────────────────────────────────────────

jobs_tracker: dict[str, dict] = {}


# ─── Helper Functions ────────────────────────────────────────────────────────

def _get_auth_headers() -> dict:
    """Get authentication headers for Azure Speech API."""
    return {
        "Ocp-Apim-Subscription-Key": SPEECH_KEY,
        "Content-Type": "application/json",
    }


def _estimate_speech_duration_seconds(text: str, words_per_minute: int = 130) -> int:
    """Estimate speech duration from text. Italian speech ~130 WPM."""
    word_count = len(text.split())
    return int((word_count / words_per_minute) * 60)


def _split_text_for_ssml(text: str, voice: str, language: str, max_chars: int = 9000) -> list[str]:
    """
    Split long text into SSML segments for batch synthesis.
    Azure batch synthesis supports up to 500KB payload, but we split for readability.
    Each segment gets wrapped in SSML tags.
    """
    paragraphs = text.split("\n\n")
    segments = []
    current_segment = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Add a natural pause between paragraphs
        para_with_pause = f'{para}<break time="800ms"/>'

        if len(current_segment) + len(para_with_pause) > max_chars:
            if current_segment:
                segments.append(current_segment)
            current_segment = para_with_pause
        else:
            current_segment += "\n" + para_with_pause if current_segment else para_with_pause

    if current_segment:
        segments.append(current_segment)

    # Wrap each segment in SSML
    ssml_segments = []
    for seg in segments:
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">'
            f'<voice name="{voice}">'
            f'<prosody rate="0%">{seg}</prosody>'
            f'</voice></speak>'
        )
        ssml_segments.append(ssml)

    return ssml_segments


def _build_single_ssml(text: str, voice: str, language: str) -> str:
    """Build a single SSML document from plain text."""
    # Add paragraph breaks as pauses
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


def submit_avatar_synthesis(job_id: str, request: PodcastRequest) -> dict:
    """Submit a batch avatar synthesis job to Azure Speech Service."""

    voice = request.voice or DEFAULT_VOICE
    language = request.language or DEFAULT_LANGUAGE
    avatar_character = request.avatar_character or DEFAULT_AVATAR_CHARACTER
    avatar_style = request.avatar_style or DEFAULT_AVATAR_STYLE

    # Build SSML or use plain text
    if request.input_kind == "SSML":
        input_kind = "SSML"
        content = request.text
    else:
        input_kind = "SSML"  # We always convert to SSML for better control
        content = _build_single_ssml(request.text, voice, language)

    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses/{job_id}?api-version={API_VERSION}"

    payload = {
        "inputKind": input_kind,
        "inputs": [
            {"content": content}
        ],
        "synthesisConfig": {
            "voice": voice,
        },
        "avatarConfig": {
            "talkingAvatarCharacter": avatar_character,
            "talkingAvatarStyle": avatar_style,
            "videoFormat": request.video_format or "mp4",
            "videoCodec": request.video_codec or "h264",
            "subtitleType": "soft_embedded" if request.subtitle else "none",
            "backgroundColor": request.background_color or "#FFFFFFFF",
            "videoBitrate": 2000000,
        },
        "properties": {
            "timeToLiveInHours": 48,
        },
    }

    logger.info(f"Submitting avatar synthesis job: {job_id}")
    response = requests.put(url, json=payload, headers=_get_auth_headers())

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
    response = requests.get(url, headers=_get_auth_headers())

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to get job status: {response.text}",
        )

    return response.json()


def delete_synthesis_job(job_id: str) -> bool:
    """Delete a batch avatar synthesis job."""
    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses/{job_id}?api-version={API_VERSION}"
    response = requests.delete(url, headers=_get_auth_headers())
    return response.status_code < 400


async def poll_and_track_job(job_id: str, title: Optional[str] = None):
    """Background task to poll job status until completion."""
    max_polls = 120  # Max ~20 minutes of polling
    poll_interval = 10  # seconds

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
                "duration_ms": None,
                "size_bytes": None,
                "error": None,
            }

            if status == "Succeeded":
                props = result.get("properties", {})
                # The output video URL is in the outputs
                outputs = result.get("outputs", {})
                video_url = outputs.get("result", "")

                jobs_tracker[job_id].update({
                    "video_url": video_url,
                    "duration_ms": props.get("durationInMilliseconds"),
                    "size_bytes": props.get("sizeInBytes"),
                })
                logger.info(f"Job {job_id} completed successfully. Video URL: {video_url}")
                return

            elif status == "Failed":
                props = result.get("properties", {})
                error = props.get("error", {})
                jobs_tracker[job_id]["error"] = error.get("message", "Unknown error")
                logger.error(f"Job {job_id} failed: {jobs_tracker[job_id]['error']}")
                return

            logger.info(f"Job {job_id} status: {status} (poll {i+1}/{max_polls})")

        except Exception as e:
            logger.error(f"Error polling job {job_id}: {e}")

        time.sleep(poll_interval)

    # Timeout
    jobs_tracker[job_id]["status"] = "Timeout"
    jobs_tracker[job_id]["error"] = "Job polling timed out after 20 minutes"


# ─── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "Azure Video Podcaster",
        "version": "1.0.0",
        "description": "Generate 5-minute avatar video podcasts from text",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "region": SPEECH_REGION}


@app.get("/avatars")
async def list_avatars():
    """List available standard avatar characters and styles."""
    return {
        "avatars": STANDARD_AVATARS,
        "voices": {
            "italian": ITALIAN_VOICES,
            "default": DEFAULT_VOICE,
        },
        "note": "For a full voice list, see: https://learn.microsoft.com/azure/ai-services/speech-service/language-support",
    }


@app.post("/podcast/generate", response_model=PodcastStatus)
async def generate_podcast(request: PodcastRequest, background_tasks: BackgroundTasks):
    """
    Generate a video podcast from text input.

    The text will be synthesized into a video with a speaking avatar.
    For a ~5 minute podcast, provide approximately 650-700 words of text.

    The job runs asynchronously. Use the returned job_id to check status.
    """
    if not SPEECH_KEY:
        raise HTTPException(status_code=500, detail="AZURE_SPEECH_KEY not configured")

    # Validate avatar
    avatar_char = request.avatar_character or DEFAULT_AVATAR_CHARACTER
    avatar_style = request.avatar_style or DEFAULT_AVATAR_STYLE

    if avatar_char in STANDARD_AVATARS:
        if avatar_style not in STANDARD_AVATARS[avatar_char]:
            raise HTTPException(
                status_code=400,
                detail=f"Style '{avatar_style}' not available for avatar '{avatar_char}'. "
                       f"Available: {STANDARD_AVATARS[avatar_char]}",
            )

    # Estimate duration
    estimated_seconds = _estimate_speech_duration_seconds(request.text)
    if estimated_seconds > 1200:  # 20 min max
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Estimated duration: {estimated_seconds//60}min. Max is 20 minutes. "
                   f"Reduce text to ~2600 words for 20min or ~650 words for 5min.",
        )

    # Generate job ID
    job_id = f"podcast-{uuid.uuid4().hex[:12]}"

    # Submit synthesis
    try:
        result = submit_avatar_synthesis(job_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit synthesis: {str(e)}")

    # Track job
    jobs_tracker[job_id] = {
        "job_id": job_id,
        "status": "Submitted",
        "title": request.title,
        "created_at": datetime.utcnow().isoformat(),
        "last_updated": None,
        "video_url": None,
        "duration_ms": None,
        "size_bytes": None,
        "error": None,
        "estimated_duration_seconds": estimated_seconds,
    }

    # Start background polling
    background_tasks.add_task(poll_and_track_job, job_id, request.title)

    return PodcastStatus(
        job_id=job_id,
        status="Submitted",
        title=request.title,
        created_at=jobs_tracker[job_id]["created_at"],
    )


@app.get("/podcast/{job_id}", response_model=PodcastStatus)
async def get_podcast_status(job_id: str):
    """Get the status of a podcast generation job."""
    # Check local tracker first
    if job_id in jobs_tracker:
        return PodcastStatus(**{k: v for k, v in jobs_tracker[job_id].items()
                               if k in PodcastStatus.model_fields})

    # Fallback: query Azure directly
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


@app.get("/podcast", response_model=PodcastListResponse)
async def list_podcasts():
    """List all podcast generation jobs (from Azure)."""
    url = f"{SPEECH_ENDPOINT}/avatar/batchsyntheses?api-version={API_VERSION}"
    response = requests.get(url, headers=_get_auth_headers())

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Failed to list jobs")

    data = response.json()
    jobs = []
    for item in data.get("value", []):
        props = item.get("properties", {})
        outputs = item.get("outputs", {})
        jobs.append(PodcastStatus(
            job_id=item.get("id", ""),
            status=item.get("status", "Unknown"),
            created_at=item.get("createdDateTime"),
            last_updated=item.get("lastActionDateTime"),
            video_url=outputs.get("result"),
            duration_ms=props.get("durationInMilliseconds"),
            size_bytes=props.get("sizeInBytes"),
        ))

    return PodcastListResponse(jobs=jobs, total=len(jobs))


@app.delete("/podcast/{job_id}")
async def delete_podcast(job_id: str):
    """Delete a podcast generation job."""
    success = delete_synthesis_job(job_id)
    if success:
        jobs_tracker.pop(job_id, None)
        return {"message": f"Job {job_id} deleted successfully"}
    raise HTTPException(status_code=404, detail="Job not found or already deleted")


@app.post("/podcast/generate-script")
async def generate_script_template():
    """
    Returns a template/guide for writing a 5-minute podcast script.
    ~650 words at natural Italian speaking pace (~130 WPM).
    """
    return {
        "guide": {
            "target_duration": "5 minutes",
            "target_word_count": "600-700 words",
            "speaking_rate": "~130 words per minute (Italian)",
            "structure": [
                "Introduzione (30 sec, ~65 parole): Saluto, presentazione del tema",
                "Contesto (1 min, ~130 parole): Background e perché è importante",
                "Corpo principale (2.5 min, ~325 parole): Analisi dettagliata, punti chiave",
                "Implicazioni (45 sec, ~100 parole): Cosa significa per il pubblico",
                "Conclusione (15 sec, ~30 parole): Recap e call-to-action",
            ],
        },
        "ssml_tips": {
            "pause": '<break time="500ms"/> per pause tra sezioni',
            "emphasis": "<emphasis>parola importante</emphasis>",
            "speed": '<prosody rate="-10%">testo più lento</prosody>',
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
