"""Azure Blob Storage integration for persistent video storage."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import requests as http_requests

from app.config import SAS_EXPIRY_HOURS, STORAGE_CONNECTION_STRING, STORAGE_CONTAINER

if TYPE_CHECKING:
    from azure.storage.blob import BlobServiceClient

logger = logging.getLogger("video-podcaster")


def is_storage_configured() -> bool:
    """Check if Azure Blob Storage is configured."""
    return bool(STORAGE_CONNECTION_STRING)


def get_blob_service_client() -> BlobServiceClient:
    """Create a BlobServiceClient from connection string."""
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)


def upload_video_from_url(job_id: str, video_url: str) -> str:
    """Download video from Azure Speech temporary URL and upload to Blob Storage.

    Returns the blob name.
    """
    client = get_blob_service_client()
    container_client = client.get_container_client(STORAGE_CONTAINER)

    # Ensure container exists
    try:
        container_client.create_container()
    except Exception:
        pass  # Container already exists

    blob_name = f"{job_id}.mp4"
    blob_client = container_client.get_blob_client(blob_name)

    logger.info(f"Downloading video from temporary URL for job {job_id}")
    response = http_requests.get(video_url, stream=True)
    response.raise_for_status()

    blob_client.upload_blob(response.content, overwrite=True, content_settings={
        "content_type": "video/mp4",
    })
    logger.info(f"Uploaded video to blob: {blob_name}")

    return blob_name


def generate_sas_url(blob_name: str) -> str:
    """Generate a SAS URL for downloading a video blob."""
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions

    client = get_blob_service_client()
    account_name = client.account_name

    # Extract account key from connection string
    parts = dict(part.split("=", 1) for part in STORAGE_CONNECTION_STRING.split(";") if "=" in part)
    account_key = parts.get("AccountKey", "")

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=STORAGE_CONTAINER,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=SAS_EXPIRY_HOURS),
    )

    return f"https://{account_name}.blob.core.windows.net/{STORAGE_CONTAINER}/{blob_name}?{sas_token}"


def persist_video_on_complete(job_id: str, video_url: str, jobs_tracker: dict[str, dict]) -> None:
    """Callback to persist video to Blob Storage when synthesis completes."""
    if not is_storage_configured():
        return

    try:
        blob_name = upload_video_from_url(job_id, video_url)
        download_url = generate_sas_url(blob_name)
        jobs_tracker[job_id]["download_url"] = download_url
        logger.info(f"Video persisted for job {job_id}: {download_url}")
    except Exception as e:
        logger.error(f"Failed to persist video for job {job_id}: {e}")
