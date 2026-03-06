"""Pydantic models for request/response schemas."""

from typing import Optional

from pydantic import BaseModel, Field


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
    download_url: Optional[str] = None
    duration_ms: Optional[int] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


class PodcastListResponse(BaseModel):
    """List of podcast jobs."""
    jobs: list[PodcastStatus]
    total: int


class TopicRequest(BaseModel):
    """Request to generate a podcast from a topic."""
    topic: str = Field(..., description="The podcast topic or bullet points")
    title: Optional[str] = Field(None, description="Podcast episode title")
    voice: Optional[str] = Field(None, description="Azure TTS voice name")
    language: Optional[str] = Field(None, description="Language code (e.g., it-IT)")
    avatar_character: Optional[str] = Field(None, description="Avatar character")
    avatar_style: Optional[str] = Field(None, description="Avatar style")
    background_color: Optional[str] = Field("#FFFFFFFF", description="Background color")
    subtitle: Optional[bool] = Field(True, description="Enable embedded subtitles")
    video_format: Optional[str] = Field("mp4", description="Video format")
    video_codec: Optional[str] = Field("h264", description="Video codec")
