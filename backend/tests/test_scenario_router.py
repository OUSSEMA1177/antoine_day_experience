"""Scénarios critiques — matrice routeur (anti whack-a-mole)."""

from unittest.mock import MagicMock, patch

from agent.destination_policy import detect_unknown_place_request
from agent.intent_router import RouteKind, classify_route, is_raise_budget_request
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


def test_router_matrix_priority() -> None:
    assert classify_route("c est quoi votre email").kind == RouteKind.SUPPORT_EMAIL
    assert classify_route("je veux un remboursement").kind == RouteKind.SUPPORT
    assert classify_route("non pas encore").kind == RouteKind.NOT_CHOSEN_YET
    assert classify_route("AUGMENTEZ BUDJET").kind == RouteKind.RAISE_BUDGET
    assert is_raise_budget_request("augmentez le budget")
    assert detect_unknown_place_request("AUGMENTEZ BUDJET") is None

    need = classify_route(
        "DE BUDGET DE 400 EURO DONNE MOI DES ACTIVITES", {}
    )
    assert need.kind == RouteKind.NEED_PLACE_FOR_SEARCH

    with_place = classify_route(
        "DE BUDGET DE 400 EURO DONNE MOI DES ACTIVITES",
        {"region_interest": "afrique", "budget": "400"},
    )
    assert with_place.kind == RouteKind.SEARCH_ACTIVITIES

    assert classify_route("AFRIQUE").kind == RouteKind.COUNTRY_OR_CONTINENT
    assert classify_route("juste les deux premiers").kind == RouteKind.PURE_SELECTION


@patch("agent.orchestrator.get_settings")
def test_scenario_budget_alone_asks_place_zero_token(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-budget-alone"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(
            session, "DE BUDGET DE 400 EURO DONNE MOI DES ACTIVITES"
        )
    assert memory_manager.get_slots(session).get("budget") == "400"
    assert "destination" in reply.casefold() or "ville" in reply.casefold() or "zone" in reply.casefold()
    assert "choisi sa destination" not in reply.casefold()
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True


@patch("agent.orchestrator.get_settings")
def test_scenario_afrique_budget_then_raise(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-afrique-raise"
    session_store.clear(session)
    memory_manager.update_slots(session, budget="400")

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply1, _, meta1 = orchestrator.chat(session, "AFRIQUE")
        reply2, _, meta2 = orchestrator.chat(session, "AUGMENTEZ BUDJET")

    assert "Augmentez" not in reply2 and "Budjet" not in reply2
    assert "catalogue" not in reply2.casefold() or "activités" in reply2.casefold() or "budget" in reply2.casefold()
    # Soit liste 1. soit message budget élargi
    assert (
        "1." in reply2
        or "élargi" in reply2.casefold()
        or "elargi" in reply2.casefold()
        or "moins chères" in reply1.casefold()
        or "1." in reply1
        or "marrakech" in reply1.casefold()
        or "caire" in reply1.casefold()
    )
    assert not memory_manager.get_slots(session).get("budget")  # plafond levé
    mock_nlu.assert_not_called()
    assert meta1.get("llm_used") is not True
    assert meta2.get("llm_used") is not True


@patch("agent.orchestrator.get_settings")
def test_scenario_espagne_budget_lists_activities(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-espagne"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(
            session,
            "j ai 200 euro je veux des activite en espagne pour un couple pour 2 jours",
        )
    assert memory_manager.get_slots(session).get("budget") == "200"
    assert memory_manager.get_slots(session).get("profil_voyageur") == "couple"
    assert "1." in reply or "barcelone" in reply.casefold() or "séville" in reply.casefold()
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True
