"""Tous les pays catalogue (CSV) — pas seulement les 8 hardcodés."""

from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator
from search.geo import (
    detect_catalog_country_query,
    detect_country_query,
    list_catalog_destinations_for_region,
    resolve_catalog_country_key,
)


def test_bresil_not_amerique() -> None:
    assert detect_country_query("bresil") == "bresil"
    assert detect_country_query("juste brezil") == "bresil"
    assert resolve_catalog_country_key("brezil") == "bresil"
    cities = list_catalog_destinations_for_region("bresil")
    assert "Rio de Janeiro" in cities
    assert "Foz do Iguaçu" in cities
    assert "Miami" not in cities
    assert "Montréal" not in cities
    assert "Grand Canyon" not in cities


def test_chili_china_canada() -> None:
    assert detect_catalog_country_query("chili") == "chili"
    assert detect_country_query("chine") == "chine"
    assert detect_country_query("canada") == "canada"
    chili = list_catalog_destinations_for_region("chili")
    assert "Santiago" in chili
    assert "Rio de Janeiro" not in chili
    chine = list_catalog_destinations_for_region("chine")
    assert chine == ["Pékin"]


def test_continent_amerique_still_works() -> None:
    assert detect_country_query("en Amérique") == "amerique"
    cities = list_catalog_destinations_for_region("amerique")
    assert "Rio de Janeiro" in cities
    assert "Miami" in cities


def test_france_still_works() -> None:
    assert detect_country_query("france") == "france"
    assert list_catalog_destinations_for_region("france") == ["Paris"]


def _mock_settings():
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
    )


@patch("agent.orchestrator.get_settings")
@patch("agent.nlu_extractor.litellm.completion")
def test_orchestrator_bresil_zero_token(mock_nlu, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    reply, _, _ = orchestrator.chat("bresil-zero", "bresil")
    assert "Rio" in reply or "Foz" in reply
    assert "Amériques" not in reply
    assert "Miami" not in reply
    mock_nlu.assert_not_called()


@patch("agent.orchestrator.get_settings")
@patch("agent.nlu_extractor.litellm.completion")
def test_orchestrator_juste_brezil(mock_nlu, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    reply, _, _ = orchestrator.chat("brezil-typo", "juste brezil")
    assert "Rio" in reply or "Foz" in reply
    assert "Miami" not in reply
    mock_nlu.assert_not_called()
