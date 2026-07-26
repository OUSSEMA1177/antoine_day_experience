"""Suivi tokens LLM par requête /chat (contexte async-safe)."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any

logger = logging.getLogger(__name__)

_llm_usage_ctx: ContextVar[dict[str, Any] | None] = ContextVar("llm_usage", default=None)


def empty_llm_usage() -> dict[str, Any]:
    return {
        "llm_used": False,
        "llm_model": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def start_llm_usage_tracking() -> Token:
    return _llm_usage_ctx.set(empty_llm_usage())


def reset_llm_usage_tracking(token: Token) -> None:
    _llm_usage_ctx.reset(token)


def current_llm_usage() -> dict[str, Any]:
    return _llm_usage_ctx.get() or empty_llm_usage()


def record_llm_usage(response: Any, model: str, *, log: bool = True) -> None:
    usage_state = _llm_usage_ctx.get()
    if usage_state is None:
        return

    usage = getattr(response, "usage", None)
    if not usage:
        return

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0) or (prompt_tokens + completion_tokens)

    usage_state["llm_used"] = True
    usage_state["llm_model"] = model
    usage_state["prompt_tokens"] += prompt_tokens
    usage_state["completion_tokens"] += completion_tokens
    usage_state["total_tokens"] += total_tokens

    if log:
        logger.info(
            "LLM usage model=%s prompt=%s completion=%s total=%s",
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )


def attach_llm_usage(meta: dict[str, Any]) -> dict[str, Any]:
    meta.update(current_llm_usage())
    return meta
