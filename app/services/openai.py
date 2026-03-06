"""Azure OpenAI integration for script generation."""

import logging

import requests
from fastapi import HTTPException

from app.config import AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY

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


def is_openai_configured() -> bool:
    """Check if Azure OpenAI is configured."""
    return bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY)


def generate_script(topic: str, language: str = "it-IT") -> str:
    """Generate a podcast script from a topic using Azure OpenAI.

    Args:
        topic: The topic or bullet points to generate a script from.
        language: Language code for the script.

    Returns:
        Generated script text.
    """
    if not is_openai_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, and AZURE_OPENAI_DEPLOYMENT.",
        )

    lang_name = "Italian" if language.startswith("it") else "English"
    user_prompt = f"Write a podcast script in {lang_name} about the following topic:\n\n{topic}"

    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-10-21"

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY,
    }

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
