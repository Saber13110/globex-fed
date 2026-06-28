"""Tests API assistant routes (ingestion sans Ollama)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from jarvis.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_assistant_ingest_txt(client: TestClient) -> None:
    data = b"Contenu test API ingestion"
    files = {"file": ("demo.txt", io.BytesIO(data), "text/plain")}
    resp = client.post("/api/assistant/ingest", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "demo.txt"
    assert "Contenu test" in body["extracted_preview"]
    assert body["char_count"] == len(data)


def test_api_assistant_ask_visual_rejected(client: TestClient) -> None:
    data = b"fake"
    files = {"file": ("img.png", io.BytesIO(data), "image/png")}
    resp = client.post(
        "/api/assistant/ask-with-file",
        files=files,
        data={"question": "Décris cette image en détail"},
    )
    assert resp.status_code == 200
    assert "llama3.2:3b" in resp.json()["reply"]
