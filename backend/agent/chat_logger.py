"""Logs structurés par tour de chat — JSONL pour stats / coûts / qualité.

Fichiers : backend/logs/chat_YYYY-MM-DD.jsonl (une ligne JSON par message).
Voir backend/logs/README.md.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

_turn_ctx: ContextVar[dict[str, Any] | None] = ContextVar("chat_turn", default=None)


def _empty_turn() -> dict[str, Any]:
    return {
        "t0": time.perf_counter(),
        "session_id": "",
        "partner_id": "",
        "conv_state": "",
        "route_kind": "",
        "route_reason": "",
        "intent": "",
        "nlu_ran": False,
        "nlu_intent": None,
        "dialog_ran": False,
        "user_msg_len": 0,
        "user_msg_preview": "",
        "error": None,
    }


def start_chat_turn(
    *,
    session_id: str,
    user_message: str,
    partner_id: str = "",
) -> Token:
    """Démarre le contexte d'un tour (appeler en tête de chat())."""
    turn = _empty_turn()
    turn["session_id"] = session_id
    turn["partner_id"] = (partner_id or "").strip()
    turn["user_msg_len"] = len(user_message or "")
    turn["user_msg_preview"] = (user_message or "")[:80]
    return _turn_ctx.set(turn)


def reset_chat_turn(token: Token) -> None:
    _turn_ctx.reset(token)


def current_turn() -> dict[str, Any] | None:
    return _turn_ctx.get()


def update_turn(**fields: Any) -> None:
    turn = _turn_ctx.get()
    if turn is None:
        return
    turn.update(fields)


def mark_nlu(intent: str | None = None) -> None:
    """Appelé quand l'extract NLU LLM a vraiment tourné."""
    update_turn(nlu_ran=True, nlu_intent=intent or None)


def mark_dialog() -> None:
    """Appelé quand le dialogue LLM (tool loop) démarre."""
    update_turn(dialog_ran=True)


def resolve_path(*, llm_used: bool, nlu_ran: bool, dialog_ran: bool) -> str:
    if dialog_ran and nlu_ran:
        return "nlu+dialog"
    if dialog_ran:
        return "dialog"
    if nlu_ran:
        return "nlu"
    if not llm_used:
        return "deterministic"
    # LLM usage (ex. NLU seul déjà couvert) — filet
    return "nlu" if nlu_ran else "dialog"


def finish_chat_turn(
    *,
    tools_used: list[str] | None = None,
    reply: str = "",
    meta: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    """Finalise le tour, écrit une ligne JSONL, log console enrichi."""
    turn = _turn_ctx.get()
    if turn is None:
        return None

    usage = usage or {}
    meta = meta or {}
    tools_used = tools_used or []

    llm_used = bool(usage.get("llm_used"))
    nlu_ran = bool(turn.get("nlu_ran"))
    dialog_ran = bool(turn.get("dialog_ran"))
    path = resolve_path(llm_used=llm_used, nlu_ran=nlu_ran, dialog_ran=dialog_ran)

    latency_ms = int((time.perf_counter() - float(turn["t0"])) * 1000)
    event: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": turn.get("session_id") or "",
        "partner_id": turn.get("partner_id") or meta.get("partner_id") or "",
        "path": path,
        "conv_state": turn.get("conv_state") or "",
        "route_kind": turn.get("route_kind") or "",
        "route_reason": turn.get("route_reason") or "",
        "intent": turn.get("intent") or "",
        "nlu_ran": nlu_ran,
        "nlu_intent": turn.get("nlu_intent"),
        "dialog_ran": dialog_ran,
        "llm_used": llm_used,
        "llm_model": usage.get("llm_model") if llm_used else None,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "tools": list(tools_used),
        "destination": meta.get("destination") or turn.get("destination") or "",
        "quote_ready": bool(meta.get("quote_ready")),
        "devis_ref": meta.get("devis_ref") or meta.get("quote_devis_ref") or "",
        "latency_ms": latency_ms,
        "user_msg_len": turn.get("user_msg_len") or 0,
        "user_msg_preview": turn.get("user_msg_preview") or "",
        "reply_len": len(reply or ""),
        "error": error or turn.get("error"),
    }

    _append_jsonl(event)
    logger.info(
        "chat.event path=%s session=%s state=%s route=%s/%s intent=%s "
        "nlu=%s dialog=%s llm=%s tokens=%s latency_ms=%s tools=%s dest=%s",
        event["path"],
        event["session_id"],
        event["conv_state"] or "-",
        event["route_kind"] or "-",
        event["route_reason"] or "-",
        event["intent"] or "-",
        event["nlu_ran"],
        event["dialog_ran"],
        event["llm_model"] or "0-token",
        event["total_tokens"],
        event["latency_ms"],
        ",".join(event["tools"]) or "-",
        event["destination"] or "-",
    )
    return event


def _append_jsonl(event: dict[str, Any]) -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = LOGS_DIR / f"chat_{day}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Impossible d'écrire le log chat JSONL : %s", exc)
