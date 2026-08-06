"""Tests API /api/logs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent import chat_logger
from main import app

client = TestClient(app)


def test_logs_endpoint_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    # Rebind routes module LOGS_DIR via import used in routes.logs
    import routes.logs as logs_route

    monkeypatch.setattr(logs_route, "LOGS_DIR", tmp_path)

    res = client.get("/api/logs")
    assert res.status_code == 200
    data = res.json()
    assert "date" in data
    assert data["stats"]["total"] == 0
    assert data["events"] == []


def test_logs_endpoint_reads_jsonl(tmp_path: Path, monkeypatch) -> None:
    import routes.logs as logs_route

    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(logs_route, "LOGS_DIR", tmp_path)

    day = "2026-08-05"
    path = tmp_path / f"chat_{day}.jsonl"
    events = [
        {
            "ts": "2026-08-05T10:00:00+00:00",
            "path": "deterministic",
            "intent": "greeting",
            "destination": "",
            "total_tokens": 0,
            "latency_ms": 12,
            "llm_used": False,
            "user_msg_preview": "bonjour",
        },
        {
            "ts": "2026-08-05T10:01:00+00:00",
            "path": "nlu+dialog",
            "intent": "unknown",
            "destination": "Paris",
            "total_tokens": 1200,
            "latency_ms": 800,
            "llm_used": True,
            "user_msg_preview": "c est qui tu ?",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
        encoding="utf-8",
    )

    res = client.get("/api/logs", params={"date": day})
    assert res.status_code == 200
    data = res.json()
    assert data["date"] == day
    assert data["stats"]["total"] == 2
    assert data["stats"]["deterministic"] == 1
    assert data["stats"]["nlu_dialog"] == 1
    assert data["stats"]["total_tokens"] == 1200
    assert len(data["events"]) == 2
    assert day in data["available_dates"]

    filtered = client.get("/api/logs", params={"date": day, "path": "deterministic"})
    assert filtered.status_code == 200
    fdata = filtered.json()
    assert fdata["stats"]["total"] == 1
    assert fdata["events"][0]["path"] == "deterministic"


def test_logs_page_served() -> None:
    res = client.get("/logs")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert b"Chat Logs" in res.content
