"""Tests logs structurés chat (JSONL)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.chat_logger import LOGS_DIR, resolve_path
from agent.orchestrator import orchestrator
from memory.session_store import session_store


def test_resolve_path_matrix() -> None:
    assert resolve_path(llm_used=False, nlu_ran=False, dialog_ran=False) == "deterministic"
    assert resolve_path(llm_used=True, nlu_ran=True, dialog_ran=False) == "nlu"
    assert resolve_path(llm_used=True, nlu_ran=False, dialog_ran=True) == "dialog"
    assert resolve_path(llm_used=True, nlu_ran=True, dialog_ran=True) == "nlu+dialog"


def _settings():
    return MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
        support_email="support@test.com",
    )


@patch("agent.orchestrator.get_settings")
def test_chat_writes_jsonl_deterministic(mock_settings, tmp_path, monkeypatch) -> None:
    mock_settings.return_value = _settings()
    # Rediriger les logs vers un dossier temp
    import agent.chat_logger as chat_logger

    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)

    session = "log-jsonl-demo"
    session_store.clear(session)
    with patch("litellm.completion"):
        reply, tools, meta = orchestrator.chat(session, "Espagne")

    files = list(tmp_path.glob("chat_*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip().splitlines()[-1]
    import json

    event = json.loads(line)
    assert event["path"] == "deterministic"
    assert event["session_id"] == session
    assert event["total_tokens"] == 0
    assert event["nlu_ran"] is False
    assert "latency_ms" in event
    assert "Espagne" in event["user_msg_preview"] or event["user_msg_len"] > 0
