"""Shared test fixtures."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _env_setup():
    """Set test environment variables."""
    env = {
        "AZURE_SPEECH_KEY": "test-key-12345",
        "AZURE_SPEECH_REGION": "westeurope",
        "API_KEY": "",
        "RATE_LIMIT_REQUESTS": "0",
    }
    with patch.dict(os.environ, env):
        yield


@pytest.fixture
def client():
    """Create a test client with fresh app instance."""
    # Re-import to pick up patched env
    from app.main import app
    return TestClient(app)


@pytest.fixture
def sample_text():
    """Sample podcast script text."""
    return "Benvenuti al nostro podcast settimanale. " * 50  # ~350 words
