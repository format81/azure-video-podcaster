"""Admin and utility routes."""

from fastapi import APIRouter, Depends

from app.config import (
    DEFAULT_AVATAR_CHARACTER,
    DEFAULT_AVATAR_STYLE,
    DEFAULT_VOICE,
    ITALIAN_VOICES,
    SPEECH_REGION,
    STANDARD_AVATARS,
)
from app.middleware import verify_api_key
from app.services.openai import is_openai_configured
from app.services.storage import is_storage_configured

router = APIRouter(tags=["Admin"])


@router.get("/")
async def root():
    """Service information."""
    return {
        "service": "Azure Video Podcaster",
        "version": "2.0.0",
        "description": "Generate avatar video podcasts from text",
        "docs": "/docs",
        "frontend": "/static/index.html",
    }


@router.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "region": SPEECH_REGION,
        "storage_configured": is_storage_configured(),
        "openai_configured": is_openai_configured(),
    }


@router.get("/avatars")
async def list_avatars(_key: str | None = Depends(verify_api_key)):
    """List available standard avatar characters, styles, and voices."""
    return {
        "avatars": STANDARD_AVATARS,
        "voices": {
            "italian": ITALIAN_VOICES,
            "default": DEFAULT_VOICE,
        },
        "defaults": {
            "avatar_character": DEFAULT_AVATAR_CHARACTER,
            "avatar_style": DEFAULT_AVATAR_STYLE,
            "voice": DEFAULT_VOICE,
        },
        "note": "For a full voice list, see: https://learn.microsoft.com/azure/ai-services/speech-service/language-support",
    }
