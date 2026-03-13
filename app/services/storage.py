"""Azure Blob Storage integration for persistent video storage."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import requests as http_requests

from app.config import (
    MANAGED_IDENTITY_CLIENT_ID,
    SAS_EXPIRY_HOURS,
    STORAGE_ACCOUNT_NAME,
    STORAGE_BACKGROUNDS_CONTAINER,
    STORAGE_CONNECTION_STRING,
    STORAGE_CONTAINER,
)

if TYPE_CHECKING:
    from azure.storage.blob import BlobServiceClient

logger = logging.getLogger("video-podcaster")


def is_storage_configured() -> bool:
    """Check if Azure Blob Storage is configured (connection string or account name)."""
    return bool(STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME)


def get_blob_service_client() -> BlobServiceClient:
    """Create a BlobServiceClient.

    Uses connection string if available, otherwise Managed Identity.
    """
    from azure.storage.blob import BlobServiceClient

    if STORAGE_CONNECTION_STRING:
        return BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)

    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    if MANAGED_IDENTITY_CLIENT_ID:
        credential = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
    else:
        credential = DefaultAzureCredential()

    account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=credential)


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

    from azure.storage.blob import ContentSettings

    blob_client.upload_blob(
        response.content,
        overwrite=True,
        content_settings=ContentSettings(content_type="video/mp4"),
    )
    logger.info(f"Uploaded video to blob: {blob_name}")

    return blob_name


def generate_sas_url(blob_name: str, container_name: str | None = None, expiry_hours: int | None = None) -> str:
    """Generate a SAS URL for downloading a blob.

    Uses user delegation key via Managed Identity (recommended, no shared keys needed).
    Falls back to account key from connection string if configured.

    Managed Identity requires the 'Storage Blob Delegator' role on the storage account.
    """
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    container = container_name or STORAGE_CONTAINER
    hours = expiry_hours or SAS_EXPIRY_HOURS
    client = get_blob_service_client()
    account_name = client.account_name

    if not STORAGE_CONNECTION_STRING:
        # Use user delegation key (Managed Identity) - no shared keys needed
        logger.info("Generating user delegation SAS (Managed Identity)")
        start_time = datetime.now(timezone.utc)
        expiry_time = start_time + timedelta(hours=hours)
        delegation_key = client.get_user_delegation_key(start_time, expiry_time)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
            start=start_time,
        )
    else:
        # Fallback: extract account key from connection string
        logger.info("Generating account-key SAS (connection string)")
        parts = dict(part.split("=", 1) for part in STORAGE_CONNECTION_STRING.split(";") if "=" in part)
        account_key = parts.get("AccountKey", "")

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=hours),
        )

    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"


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


def upload_background(file_content: bytes, filename: str, content_type: str) -> str:
    """Upload a background image or video to blob storage.

    Returns the blob_name. The caller is responsible for building
    the public URL (proxy endpoint or SAS).
    """
    import uuid

    from azure.storage.blob import ContentSettings

    client = get_blob_service_client()
    container_client = client.get_container_client(STORAGE_BACKGROUNDS_CONTAINER)

    # Ensure container exists
    try:
        container_client.create_container()
    except Exception:
        pass  # Container already exists

    blob_name = f"backgrounds/{uuid.uuid4().hex[:8]}-{filename}"
    blob_client = container_client.get_blob_client(blob_name)

    blob_client.upload_blob(
        file_content,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    logger.info(f"Uploaded background: {blob_name} ({content_type})")

    return blob_name


def download_background_blob(blob_name: str) -> tuple[bytes, str]:
    """Download a background blob and return (content, content_type).

    Uses Managed Identity / connection string — no SAS needed.
    """
    client = get_blob_service_client()
    blob_client = client.get_blob_client(STORAGE_BACKGROUNDS_CONTAINER, blob_name)
    download = blob_client.download_blob()
    content_type = download.properties.content_settings.content_type or "application/octet-stream"
    return download.readall(), content_type
