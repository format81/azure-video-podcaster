"""Tests for service modules."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.speech import (
    build_single_ssml,
    estimate_speech_duration_seconds,
    generate_job_id,
)


def test_estimate_speech_duration():
    text = " ".join(["word"] * 130)  # 130 words
    duration = estimate_speech_duration_seconds(text)
    assert duration == 60  # 1 minute at 130 WPM


def test_estimate_speech_duration_short():
    text = "just a few words"
    duration = estimate_speech_duration_seconds(text)
    assert duration >= 0


def test_build_single_ssml():
    ssml = build_single_ssml("Hello world", "en-US-JennyNeural", "en-US")
    assert 'xml:lang="en-US"' in ssml
    assert 'name="en-US-JennyNeural"' in ssml
    assert "Hello world" in ssml


def test_build_single_ssml_with_paragraphs():
    text = "First paragraph.\n\nSecond paragraph."
    ssml = build_single_ssml(text, "it-IT-ElsaNeural", "it-IT")
    assert '<break time="800ms"/>' in ssml
    assert "First paragraph." in ssml
    assert "Second paragraph." in ssml


def test_generate_job_id():
    job_id = generate_job_id()
    assert job_id.startswith("podcast-")
    assert len(job_id) == 20  # "podcast-" + 12 hex chars


@patch("app.services.speech.requests.put")
def test_submit_avatar_synthesis(mock_put):
    from app.models import PodcastRequest
    from app.services.speech import submit_avatar_synthesis

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"status": "Accepted"}
    mock_put.return_value = mock_response

    request = PodcastRequest(text="Test text for podcast generation.")
    result = submit_avatar_synthesis("test-job-1", request)

    assert result["status"] == "Accepted"
    mock_put.assert_called_once()


@patch("app.services.speech.requests.put")
def test_submit_avatar_synthesis_error(mock_put):
    from fastapi import HTTPException
    from app.models import PodcastRequest
    from app.services.speech import submit_avatar_synthesis

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_put.return_value = mock_response

    request = PodcastRequest(text="Test text.")
    with pytest.raises(HTTPException) as exc_info:
        submit_avatar_synthesis("test-job-2", request)
    assert exc_info.value.status_code == 400


@patch("app.services.speech.requests.get")
def test_get_synthesis_status(mock_get):
    from app.services.speech import get_synthesis_status

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "Running"}
    mock_get.return_value = mock_response

    result = get_synthesis_status("test-job-1")
    assert result["status"] == "Running"


@patch("app.services.speech.requests.delete")
def test_delete_synthesis_job(mock_delete):
    from app.services.speech import delete_synthesis_job

    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_delete.return_value = mock_response

    assert delete_synthesis_job("test-job-1") is True


def test_openai_not_configured():
    from app.services.openai import is_openai_configured
    # Without env vars set, should return False
    assert is_openai_configured() is False


def test_storage_not_configured():
    from app.services.storage import is_storage_configured
    assert is_storage_configured() is False
