"""Azure OpenAI integration for script generation using Managed Identity."""

from __future__ import annotations

import logging

import requests
from fastapi import HTTPException

from app.config import (
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    MANAGED_IDENTITY_CLIENT_ID,
)

logger = logging.getLogger("video-podcaster")

SYSTEM_PROMPT = """You are an expert podcast scriptwriter. Write engaging, natural-sounding podcast scripts in Italian.

Guidelines:
- Write approximately 650 words (for a ~5 minute episode at 130 WPM)
- Use a conversational, professional tone
- Structure: Introduction (65 words) -> Context (130 words) -> Main body (325 words) -> Implications (100 words) -> Conclusion (30 words)
- Use natural paragraph breaks (double newlines) between sections
- Do NOT include SSML tags, stage directions, or speaker labels
- Write as continuous spoken text that sounds natural when read aloud
- Include smooth transitions between sections
"""

# Cognitive Services token scope
_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def is_openai_configured() -> bool:
    """Check if Azure OpenAI is configured (endpoint is sufficient for Managed Identity auth)."""
    return bool(AZURE_OPENAI_ENDPOINT)


def _get_entra_token() -> str:
    """Get an Entra ID (AAD) access token for Cognitive Services.

    Uses ManagedIdentityCredential when running in Azure (Container Apps),
    falls back to DefaultAzureCredential for local dev (az login, VS Code, etc.).
    """
    try:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

        if MANAGED_IDENTITY_CLIENT_ID:
            credential = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
        else:
            credential = DefaultAzureCredential()

        token = credential.get_token(_COGNITIVE_SCOPE)
        return token.token
    except Exception as e:
        logger.error(f"Failed to acquire Entra ID token: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to acquire Entra ID token for Azure OpenAI. "
                   f"Ensure Managed Identity or 'az login' is configured. Error: {e}",
        )


def _get_auth_headers() -> dict[str, str]:
    """Build authentication headers. Prefers API key if set, otherwise uses Entra ID token."""
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if AZURE_OPENAI_KEY:
        # API key auth (if tenant allows it)
        headers["api-key"] = AZURE_OPENAI_KEY
    else:
        # Managed Identity / Entra ID auth
        token = _get_entra_token()
        headers["Authorization"] = f"Bearer {token}"

    return headers


def generate_script(topic: str, language: str = "it-IT") -> str:
    """Generate a podcast script from a topic using Azure OpenAI.

    Auth: Uses Managed Identity (Entra ID) by default. Falls back to API key
    if AZURE_OPENAI_KEY is set.

    Args:
        topic: The topic or bullet points to generate a script from.
        language: Language code for the script.

    Returns:
        Generated script text.
    """
    if not is_openai_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT "
                   "(and optionally AZURE_OPENAI_DEPLOYMENT). "
                   "Auth via Managed Identity (no API key needed).",
        )

    lang_name = "Italian" if language.startswith("it") else "English"
    user_prompt = f"Write a podcast script in {lang_name} about the following topic:\n\n{topic}"

    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-10-21"
    )

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    headers = _get_auth_headers()

    logger.info(f"Generating script for topic: {topic[:100]}...")
    response = requests.post(url, json=payload, headers=headers, timeout=60)

    if response.status_code >= 400:
        logger.error(f"Azure OpenAI error: {response.status_code} - {response.text}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Azure OpenAI error: {response.text}",
        )

    data = response.json()
    script = data["choices"][0]["message"]["content"].strip()
    logger.info(f"Script generated: {len(script.split())} words")
    return script
