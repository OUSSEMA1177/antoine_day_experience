"""« 1 est ok + autres activités » — select_and_add avant search."""

from unittest.mock import MagicMock, patch

from agent.intent_router import RouteKind, classify_route
from agent.orchestrator import orchestrator
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import is_wants_another_activity, parse_presentation_indices
from memory.session_store import session_store


def test_parse_one_est_ok() -> None:
    assert parse_presentation_indices("1 est ok") == [1]
    assert parse_presentation_indices("1 est ok vous avez d autre activite ?") == [1]
    assert parse_presentation_indices("2 ok") == [2]


def test_wants_another_variants() -> None:
    assert is_wants_another_activity("vous avez d autre activite ?")
    assert is_wants_another_activity("1 est ok vous avez d autre activite ?")
    assert is_wants_another_activity("d autres activites")
    assert is_wants_another_activity("1 est ok dautrre a ctivite ?")
    assert is_wants_another_activity("qu est ce que vous avez dans bali d autres activites")


def test_router_select_and_add_before_search() -> None:
    slots = {"destination": "Bali"}
    decision = classify_route(
        "1 est ok vous avez d autre activite ?", slots
    )
    assert decision.kind == RouteKind.PURE_SELECTION
    assert decision.reason == "select_and_add"

    # Autre activité seule → pas SEARCH
    alone = classify_route("d autres activites", slots)
    assert alone.kind != RouteKind.SEARCH_ACTIVITIES


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


@patch("agent.orchestrator.get_settings")
def test_scenario_one_est_ok_autre_asks_theme(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-1-est-ok-autre"
    session_store.clear(session)
    memory_manager.update_slots(
        session,
        destination="Bali",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test",
        activites_proposees="14650,62826,63644,62843",
        activites_discutees="14650,62826,63644,62843",
    )
    conversation_manager.add_turn(
        session,
        "bali",
        "1. **Act A** — 10 €\n2. **Act B** — 20 €\n3. **Act C** — 30 €\n4. **Act D** — 40 €",
    )
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(
            session, "1 est ok vous avez d autre activite ?"
        )

    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert "14650" in selected
    assert memory_manager.get_slots(session).get("awaiting_add_activity") == "1"
    assert "thématique" in reply.casefold() or "gastronomie" in reply.casefold()
    assert "choisi sa destination" not in reply.casefold()
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True
