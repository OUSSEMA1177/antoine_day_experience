"""Pays + budget + activités — réponse enrichie 0 token."""

from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager


@patch("agent.orchestrator.get_settings")
def test_espagne_budget_couple_proposes_activities(mock_settings) -> None:
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
        llm_nlu_extract=True,
        llm_log_usage=False,
    )
    session = "espagne-budget-couple"
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(
            session,
            "j ai 200 euro je veux des activite en espagne pour un couple pour 2 jours",
        )

    slots = memory_manager.get_slots(session)
    assert slots.get("budget") == "200"
    assert slots.get("profil_voyageur") == "couple"
    assert slots.get("duree") == "2 jours"
    assert slots.get("region_interest") == "espagne"

    lower = reply.casefold()
    assert "200" in reply or "budget" in lower
    assert "couple" in lower or "2 jours" in lower or "€" in reply
    # Soit liste numérotée d'activités, soit message budget/villes
    assert (
        "1." in reply
        or "barcelone" in lower
        or "séville" in lower
        or "seville" in lower
        or "grenade" in lower
    )
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True
    assert "search_catalog" in tools or "1." in reply
