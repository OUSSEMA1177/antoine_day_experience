"""Tests list_destinations (continents + outil)."""

import json
from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator
from search.geo import (
    detect_country_query,
    list_catalog_destinations_for_region,
    list_destinations,
)
from tools.registry import execute_tool


def test_asia_detect_and_list() -> None:
    assert detect_country_query("je veux des pays asiatique") == "asie"
    assert detect_country_query("donner moi des pays asiatiques") == "asie"
    cities = list_catalog_destinations_for_region("asie")
    assert "Bali" in cities
    assert "Tokyo" in cities
    assert "Pékin" in cities
    assert "Paris" not in cities


def test_other_destinations_lists_all() -> None:
    assert detect_country_query("il ya pas dautre destinations ?") == "all"
    cities = list_catalog_destinations_for_region("all")
    assert len(cities) >= 30
    assert "Bali" in cities
    assert "Marrakech" in cities


def test_list_destinations_tool_filter() -> None:
    raw = execute_tool("s1", "list_destinations", {"continent": "asie"})
    data = json.loads(raw)
    assert data["count"] >= 3
    names = {d["nom"] for d in data["destinations"]}
    assert "Bali" in names
    assert "Tokyo" in names


def test_list_destinations_by_pays() -> None:
    result = list_destinations(pays="Japon")
    names = [d["nom"] for d in result["destinations"]]
    assert names == ["Tokyo"]


@patch("agent.orchestrator.get_settings")
def test_asia_orchestrator_zero_llm(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_log_usage=False,
    )
    with patch("agent.orchestrator.litellm.completion") as mock_completion:
        reply, _, meta = orchestrator.chat("asia-session", "je veux des pays asiatique")
        mock_completion.assert_not_called()
    assert "Bali" in reply
    assert "Tokyo" in reply
    assert meta.get("llm_used") is False


@patch("agent.orchestrator.get_settings")
def test_other_destinations_orchestrator(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_log_usage=False,
    )
    reply, _, meta = orchestrator.chat("all-dest-session", "il ya pas dautre destinations ?")
    assert "catalogue" in reply.casefold()
    assert "Bali" in reply or "Indonésie" in reply or "autre(s) pays" in reply
    assert meta.get("llm_used") is False
