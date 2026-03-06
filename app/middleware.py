"""Middleware for rate limiting and API key authentication."""

import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import API_KEY, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger("video-podcaster")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Simple in-memory rate limiter
_request_log: dict[str, list[float]] = defaultdict(list)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str | None:
    """Verify API key if authentication is enabled."""
    if not API_KEY:
        return None  # Auth disabled
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


def check_rate_limit(request: Request) -> None:
    """Check rate limit for the requesting client."""
    if RATE_LIMIT_REQUESTS <= 0:
        return

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Clean old entries
    _request_log[client_ip] = [t for t in _request_log[client_ip] if t > window_start]

    if len(_request_log[client_ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds.",
        )

    _request_log[client_ip].append(now)
