"""Tests for agent intent and planner."""

from agent.intent_detector import Intent, detect_intent
from agent.orchestrator import Orchestrator
from agent.partner_context import build_greeting_reply, resolve_agency_name, sync_partner_from_id
from agent.planner import Action, plan_next


def test_greeting_intent() -> None:
    assert detect_intent("Bonjour") == Intent.GREETING


def test_activity_intent_montagne() -> None:
    assert detect_intent("montagne aventure") == Intent.ACTIVITY_SEARCH


def test_plan_ask_destination() -> None:
    plan = plan_next(Intent.GREETING, {}, has_catalog_results=False, escalated=False)
    assert plan.action == Action.ASK_DESTINATION


def test_skip_catalog_during_qualification() -> None:
    orch = Orchestrator()
    plan = plan_next(
        Intent.GENERAL,
        {"destination": "Dubaï", "profil_voyageur": "couple"},
        has_catalog_results=True,
        escalated=False,
    )
    assert plan.action == Action.ASK_ENVIES
    assert orch._should_inject_catalog(plan, Intent.GENERAL) is False


def test_inject_catalog_for_results() -> None:
    orch = Orchestrator()
    plan = plan_next(
        Intent.GENERAL,
        {"destination": "Dubaï", "profil_voyageur": "couple", "envies": "aventure"},
        has_catalog_results=True,
        escalated=False,
    )
    assert plan.action == Action.PRESENT_RESULTS
    assert orch._should_inject_catalog(plan, Intent.GENERAL) is True


def test_build_greeting_reply() -> None:
    msg = build_greeting_reply("TUI España Turismo, S.L.U")
    assert "Bonjour TUI España Turismo, S.L.U" in msg
    assert "destination" in msg.lower()


def test_sync_partner_from_id() -> None:
    session = "test-partner-sync"
    name = sync_partner_from_id(session, "1")
    assert name == "TUI España Turismo, S.L.U"
    assert resolve_agency_name(session) == "TUI España Turismo, S.L.U"
