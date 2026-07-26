"""Destination pas encore choisie — aide 0 token, skip NLU."""

from unittest.mock import MagicMock, patch

from agent.destination_policy import (
    build_destination_help_reply,
    is_destination_not_chosen_yet,
)
from agent.nlu_extractor import should_run_nlu
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager


def test_is_destination_not_chosen_patterns() -> None:
    assert is_destination_not_chosen_yet("non pas encore") is True
    assert is_destination_not_chosen_yet("non il n a pas chosit") is True
    assert is_destination_not_chosen_yet("il n'a pas choisi") is True
    assert is_destination_not_chosen_yet("pas encore") is True
    assert is_destination_not_chosen_yet("non") is True
    assert is_destination_not_chosen_yet("je ne sais pas") is True
    assert is_destination_not_chosen_yet("Bali") is False
    assert is_destination_not_chosen_yet("plage en Asie") is False


def test_should_run_nlu_skips_not_chosen() -> None:
    assert should_run_nlu("non pas encore") is False
    assert should_run_nlu("non il n a pas chosit") is False
    assert should_run_nlu("Bali plage") is True


def test_help_reply_offers_alternatives() -> None:
    reply = build_destination_help_reply()
    assert "Pas de souci" in reply
    assert "Asie" in reply or "région" in reply.casefold()
    assert "plage" in reply.casefold()


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
def test_orchestrator_not_chosen_zero_token_help(mock_nlu, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "dest-not-chosen"
    memory_manager.update_slots(session, partner_id="1", nom_agence="Japanticket Inc.")

    reply, _tools, _meta = orchestrator.chat(session, "non pas encore")
    assert "Pas de souci" in reply
    assert "Votre client a choisi sa destination ?" not in reply
    mock_nlu.assert_not_called()


@patch("agent.orchestrator.get_settings")
@patch("agent.nlu_extractor.litellm.completion")
def test_orchestrator_typo_chosit(mock_nlu, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "dest-chosit"
    memory_manager.update_slots(session, partner_id="1", nom_agence="Japanticket Inc.")

    reply, _, _ = orchestrator.chat(session, "non il n a pas chosit")
    assert "Pas de souci" in reply
    mock_nlu.assert_not_called()
