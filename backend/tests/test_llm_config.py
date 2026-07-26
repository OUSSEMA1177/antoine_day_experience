"""Tests configuration LLM payant et optimisation tokens."""

import pytest

from agent.orchestrator import Orchestrator
from app.config import Settings
from search.catalog_search import CatalogSearchResult


def test_settings_llm_defaults_optimized() -> None:
    s = Settings()
    assert s.llm_max_tokens == 512
    assert s.llm_history_limit == 8
    assert s.llm_catalog_inject_limit == 4
    assert s.llm_compact_prompt is True
    assert s.llm_retry_max == 1


def test_anthropic_requires_api_key() -> None:
    from agent.orchestrator import AgentConfigurationError

    orch = Orchestrator()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "agent.orchestrator.get_settings",
            lambda: Settings(
                llm_model="anthropic/claude-sonnet-4-5",
                anthropic_api_key="",
            ),
        )
        with pytest.raises(AgentConfigurationError) as exc:
            orch._ensure_configured()
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_catalog_search_limited() -> None:
    result = CatalogSearchResult(
        activities=[{"id": str(i), "titre": f"A{i}", "prix": "10"} for i in range(10)],
        scores=list(range(10)),
    )
    trimmed = result.limited(4)
    assert trimmed.count == 4
    block = trimmed.to_prompt_block()
    assert block.count('"id"') == 4


def test_should_not_use_tools_during_qualification() -> None:
    from agent.intent_detector import Intent
    from agent.planner import Action, Plan

    orch = Orchestrator()
    plan = Plan(Action.ASK_PROFIL, "test")
    assert orch._should_use_tools(plan, Intent.TUNNEL_QUALIFY) is False

    plan_present = Plan(Action.PRESENT_RESULTS, "test", one_question_only=False)
    assert orch._should_use_tools(plan_present, Intent.ACTIVITY_SEARCH) is False
