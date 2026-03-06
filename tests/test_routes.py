"""Tests for API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Azure Video Podcaster"
    assert "version" in data


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "region" in data


def test_list_avatars(client):
    response = client.get("/avatars")
    assert response.status_code == 200
    data = response.json()
    assert "avatars" in data
    assert "lisa" in data["avatars"]
    assert "voices" in data


@patch("app.routes.podcast.SPEECH_KEY", "test-key")
@patch("app.routes.podcast.submit_avatar_synthesis")
@patch("app.routes.podcast.poll_and_track_job")
def test_generate_podcast(mock_poll, mock_submit, client):
    mock_submit.return_value = {"status": "Accepted"}

    response = client.post("/podcast/generate", json={
        "text": "Benvenuti al nostro podcast. " * 30,
        "title": "Test Episode",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Submitted"
    assert data["job_id"].startswith("podcast-")
    assert data["title"] == "Test Episode"
    mock_submit.assert_called_once()


@patch("app.routes.podcast.SPEECH_KEY", "test-key")
def test_generate_podcast_text_too_short(client):
    response = client.post("/podcast/generate", json={
        "text": "short",
    })
    assert response.status_code == 400
    assert "too short" in response.json()["detail"].lower()


@patch("app.routes.podcast.SPEECH_KEY", "test-key")
def test_generate_podcast_invalid_avatar_style(client):
    response = client.post("/podcast/generate", json={
        "text": "Benvenuti al nostro podcast. " * 30,
        "avatar_character": "lisa",
        "avatar_style": "nonexistent-style",
    })
    assert response.status_code == 400
    assert "not available" in response.json()["detail"]


@patch("app.routes.podcast.SPEECH_KEY", "")
def test_generate_podcast_no_key(client):
    response = client.post("/podcast/generate", json={
        "text": "Benvenuti al nostro podcast. " * 30,
    })
    assert response.status_code == 500
    assert "AZURE_SPEECH_KEY" in response.json()["detail"]


def test_get_podcast_status_not_found(client):
    response = client.get("/podcast/nonexistent-id")
    assert response.status_code == 404


def test_generate_script_template(client):
    response = client.post("/podcast/generate-script")
    assert response.status_code == 200
    data = response.json()
    assert "guide" in data
    assert "ssml_tips" in data


@patch("app.routes.podcast.list_synthesis_jobs")
def test_list_podcasts(mock_list, client):
    """List podcasts returns results from Azure."""
    mock_list.return_value = [
        {
            "id": "podcast-abc123",
            "status": "Succeeded",
            "createdDateTime": "2026-01-01T00:00:00Z",
            "lastActionDateTime": "2026-01-01T00:05:00Z",
            "properties": {},
            "outputs": {"result": "https://example.com/video.mp4"},
        }
    ]
    response = client.get("/podcast")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["jobs"][0]["job_id"] == "podcast-abc123"
