"""Tests suivi usage LLM par message."""

from unittest.mock import MagicMock, patch

from agent.llm_usage import attach_llm_usage, empty_llm_usage, record_llm_usage
from agent.orchestrator import orchestrator


def test_record_llm_usage_accumulates() -> None:
    usage = empty_llm_usage()
    response = MagicMock()
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=40, total_tokens=140)

    from agent import llm_usage

    token = llm_usage._llm_usage_ctx.set(usage)
    try:
        record_llm_usage(response, "anthropic/claude-haiku-4-5", log=False)
    finally:
        llm_usage._llm_usage_ctx.reset(token)

    assert usage["llm_used"] is True
    assert usage["total_tokens"] == 140
    assert usage["llm_model"] == "anthropic/claude-haiku-4-5"


def test_attach_llm_usage_on_meta() -> None:
    meta = attach_llm_usage({"quote_ready": False})
    assert meta["llm_used"] is False
    assert meta["total_tokens"] == 0


@patch("agent.orchestrator.get_settings")
def test_country_reply_reports_zero_tokens(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        groq_api_key="",
        gemini_api_key="",
        anthropic_api_key="test",
        openai_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_log_usage=False,
    )
    _, _, meta = orchestrator.chat("usage-maroc", "maroc")
    assert meta["llm_used"] is False
    assert meta["total_tokens"] == 0


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_llm_reply_reports_tokens(mock_completion, mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        groq_api_key="",
        gemini_api_key="",
        anthropic_api_key="test",
        openai_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_log_usage=False,
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
    )
    mock_completion.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content="Parfait pour Bali ! Votre client voyage en couple, en famille, en groupe ?",
                    tool_calls=[],
                    model_dump=MagicMock(return_value={"role": "assistant", "content": "..."}),
                )
            )
        ],
        usage=MagicMock(prompt_tokens=320, completion_tokens=28, total_tokens=348),
    )

    _, _, meta = orchestrator.chat("usage-bali", "bali")
    assert meta["llm_used"] is True
    assert meta["total_tokens"] == 348
    assert meta["prompt_tokens"] == 320
    assert meta["completion_tokens"] == 28
    assert "haiku" in str(meta["llm_model"]).casefold()
