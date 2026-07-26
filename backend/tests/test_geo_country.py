"""Tests requêtes pays/région et qualification tunnel."""

from unittest.mock import MagicMock, patch

from agent.context_manager import is_qualification_message
from agent.destination_policy import detect_unknown_place_request
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager
from search.geo import (
    build_country_catalog_reply,
    detect_country_query,
    list_catalog_destinations_for_region,
)


def test_en_couple_not_a_place() -> None:
    assert is_qualification_message("en couple")
    assert is_qualification_message("en famille")
    assert is_qualification_message("generale")
    assert detect_unknown_place_request("en couple") is None
    assert detect_unknown_place_request("en famille") is None
    assert detect_unknown_place_request("generale") is None


def test_france_country_query() -> None:
    assert detect_country_query("que vous avez dans france ?") == "france"
    assert detect_country_query("est ce qu il ya d autres place en france") == "france"
    cities = list_catalog_destinations_for_region("france")
    assert cities == ["Paris"]
    reply = build_country_catalog_reply("france", cities)
    assert "Paris" in reply
    assert "uniquement" in reply.casefold()


def test_italy_lists_catalog_cities() -> None:
    cities = list_catalog_destinations_for_region("italie")
    assert "Rome" in cities
    assert "Venise" in cities


def test_maroc_followup_via_city_question() -> None:
    assert detect_country_query("ily a que marrakch ?") == "maroc"
    assert detect_country_query("il y a que marrakech ?") == "maroc"
    assert detect_unknown_place_request("ily a que marrakch ?") is None
    cities = list_catalog_destinations_for_region("maroc")
    reply = build_country_catalog_reply("maroc", cities)
    assert "Marrakech" in reply
    assert "uniquement" in reply.casefold()


@patch("agent.orchestrator.get_settings")
def test_maroc_followup_orchestrator(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "maroc-followup-v2"
    memory_manager.update_slots(session, destination="", region_interest="")
    memory_manager.clear_slot(session, "destination")
    orchestrator.chat(session, "maroc")
    reply, _, _ = orchestrator.chat(session, "ily a que marrakch ?")
    assert "Marrakech" in reply
    assert "Ily A Que Marrakch" not in reply
    assert "pas d'activités à Ily" not in reply
    assert "uniquement" in reply.casefold() or "catalogue" in reply.casefold()


def _mock_settings():
    return MagicMock(
        llm_model="groq/llama-3.3-70b-versatile",
        groq_api_key="test-key",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=False,
        llm_log_usage=False,
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
    )


@patch("agent.orchestrator.get_settings")
def test_france_catalog_reply_orchestrator(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "france-query"
    reply, _, _ = orchestrator.chat(session, "que vous avez dans france ?")
    assert "Paris" in reply
    assert "catalogue" in reply.casefold()


@patch("agent.orchestrator.get_settings")
def test_bali_then_en_couple_not_blocked(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "bali-couple"

    with patch("agent.orchestrator.litellm.completion") as mock_completion:
        mock_completion.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content="Bali ! Votre client voyage en couple, en famille, en groupe, en solo ou en séminaire ?",
                        tool_calls=[],
                        role="assistant",
                        model_dump=MagicMock(return_value={"role": "assistant", "content": "..."}),
                    )
                )
            ]
        )
        orchestrator.chat(session, "bali")

    reply, _, meta = orchestrator.chat(session, "en couple")
    slots = memory_manager.get_slots(session)

    assert slots.get("destination") == "Bali"
    assert slots.get("profil_voyageur") == "couple"
    assert "destination_demandee" not in slots
    assert "En Couple" not in reply
    assert "pas d'activités" not in reply.casefold()
    assert "culture" in reply.casefold() or "gastronomie" in reply.casefold()
    assert meta["quote_ready"] is False
