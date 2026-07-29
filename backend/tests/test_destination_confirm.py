"""Confirmation ville après offre pays (Afrique du Sud → oui → Parc Kruger)."""

from unittest.mock import MagicMock, patch

from agent.destination_confirm import (
    clear_pending_city,
    is_affirmative_short,
    remember_city_offer,
    resolve_pending_city_choice,
)
from agent.intent_router import RouteKind, classify_route
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager
from memory.session_store import session_store


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
        support_email="support@day-experience-demo.com",
    )


def test_affirmative_helpers() -> None:
    assert is_affirmative_short("oui")
    assert is_affirmative_short("ok")
    assert is_affirmative_short("vas-y")
    assert not is_affirmative_short("oui ajoute ceci")


def test_remember_and_resolve_single_city() -> None:
    session = "city-confirm-unit"
    session_store.clear(session)
    remember_city_offer(session, ["Parc Kruger"], region_key="afrique_du_sud")
    slots = memory_manager.get_slots(session)
    assert slots.get("awaiting_city_confirm") == "1"
    assert slots.get("pending_destination") == "Parc Kruger"
    assert resolve_pending_city_choice(session, "oui") == "Parc Kruger"
    clear_pending_city(session)
    remember_city_offer(session, ["Parc Kruger"], region_key="afrique_du_sud")
    assert resolve_pending_city_choice(session, "Parc Kruger") == "Parc Kruger"


def test_remember_multi_city_pick() -> None:
    session = "city-pick-unit"
    session_store.clear(session)
    remember_city_offer(
        session, ["Barcelone", "Grenade", "Séville"], region_key="espagne"
    )
    assert memory_manager.get_slots(session).get("awaiting_city_pick") == "1"
    assert resolve_pending_city_choice(session, "1") == "Barcelone"
    assert resolve_pending_city_choice(session, "Séville") == "Séville"


def test_router_city_confirm_before_pure_selection() -> None:
    slots = {
        "awaiting_city_confirm": "1",
        "pending_destination": "Parc Kruger",
    }
    assert classify_route("oui", slots).kind == RouteKind.CITY_CONFIRM
    assert classify_route("oui", {}).kind == RouteKind.PURE_SELECTION


@patch("agent.orchestrator.get_settings")
def test_scenario_afrique_du_sud_oui_sets_kruger(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-afrique-sud-oui"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply1, _, meta1 = orchestrator.chat(session, "Afrique du Sud")
        assert "Parc Kruger" in reply1
        assert memory_manager.get_slots(session).get("awaiting_city_confirm") == "1"

        reply2, tools, meta2 = orchestrator.chat(session, "oui")

    dest = memory_manager.get_slots(session).get("destination")
    assert dest == "Parc Kruger"
    assert "destination ?" not in reply2.casefold() or "activités" in reply2.casefold()
    assert "choisi sa destination" not in reply2.casefold()
    assert "1." in reply2 or "activités" in reply2.casefold() or "Parc Kruger" in reply2
    assert "city_confirm" in tools or "search" in str(tools).casefold() or "1." in reply2
    mock_nlu.assert_not_called()
    assert meta1.get("llm_used") is not True
    assert meta2.get("llm_used") is not True
    assert not memory_manager.get_slots(session).get("awaiting_city_confirm")


@patch("agent.orchestrator.get_settings")
def test_scenario_espagne_then_city_name(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-espagne-pick"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply1, _, _ = orchestrator.chat(session, "Espagne")
        assert "Barcelone" in reply1 or "Séville" in reply1
        reply2, _, meta = orchestrator.chat(session, "Barcelone")

    assert memory_manager.get_slots(session).get("destination") == "Barcelone"
    assert "choisi sa destination" not in reply2.casefold()
    assert "1." in reply2 or "Barcelone" in reply2
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True


def test_seville_is_not_country_query() -> None:
    """« Séville » ne doit PAS matcher le hint « ville » (sous-chaîne)."""
    from search.geo import detect_country_query

    assert detect_country_query("Séville") is None
    assert detect_country_query("Seville") is None
    assert detect_country_query("oui Séville") is None
    assert detect_country_query("je veux Séville") is None
    assert detect_country_query("quelles villes en Espagne") == "espagne"


@patch("agent.orchestrator.get_settings")
def test_espagne_seville_pick_activates_city(mock_settings) -> None:
    """Espagne → Séville → activités Séville (pas re-liste pays)."""
    mock_settings.return_value = _settings()
    session = "scen-espagne-seville"
    session_store.clear(session)
    with patch("litellm.completion") as mock_llm:
        r1, _, _ = orchestrator.chat(session, "Espagne")
        assert "Séville" in r1
        r2, tools, _ = orchestrator.chat(session, "Séville")

    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Séville"
    assert not slots.get("awaiting_city_pick")
    assert "Voici des activités" in r2 or "1." in r2
    assert "city_confirm" in tools
    mock_llm.assert_not_called()


@patch("agent.orchestrator.get_settings")
def test_city_pick_works_despite_stale_quote_confirm(mock_settings) -> None:
    """Même si awaiting_quote_confirm est resté collé, le choix de ville gagne."""
    mock_settings.return_value = _settings()
    session = "scen-stale-quote-seville"
    session_store.clear(session)
    remember_city_offer(
        session, ["Barcelone", "Grenade", "Séville"], region_key="espagne"
    )
    memory_manager.update_slots(session, awaiting_quote_confirm="1", partner_id="1")

    with patch("litellm.completion") as mock_llm:
        reply, tools, _ = orchestrator.chat(session, "Séville")

    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Séville"
    assert not slots.get("awaiting_quote_confirm")
    assert "1." in reply
    assert "city_confirm" in tools
    mock_llm.assert_not_called()


@patch("agent.orchestrator.get_settings")
def test_espagne_grenade_and_oui_seville(mock_settings) -> None:
    """Autres formulations : Grenade, « oui Séville »."""
    mock_settings.return_value = _settings()
    with patch("litellm.completion"):
        session = "scen-espagne-grenade"
        session_store.clear(session)
        orchestrator.chat(session, "Espagne")
        r1, _, _ = orchestrator.chat(session, "Grenade")
        assert memory_manager.get_slots(session).get("destination") == "Grenade"
        assert "1." in r1

        session2 = "scen-espagne-oui-sev"
        session_store.clear(session2)
        orchestrator.chat(session2, "Espagne")
        r2, _, _ = orchestrator.chat(session2, "oui Séville")
        assert memory_manager.get_slots(session2).get("destination") == "Séville"
        assert "1." in r2
