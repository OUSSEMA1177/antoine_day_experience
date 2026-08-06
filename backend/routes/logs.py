"""API lecture des logs chat JSONL (dashboard démo / LinkedIn)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent.chat_logger import LOGS_DIR

router = APIRouter(tags=["logs"])

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LogsStats(BaseModel):
    total: int = 0
    deterministic: int = 0
    nlu: int = 0
    dialog: int = 0
    nlu_dialog: int = 0
    llm_turns: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0
    errors: int = 0


class LogsResponse(BaseModel):
    date: str
    available_dates: list[str] = Field(default_factory=list)
    stats: LogsStats
    events: list[dict[str, Any]] = Field(default_factory=list)


def _list_log_dates() -> list[str]:
    if not LOGS_DIR.is_dir():
        return []
    dates: list[str] = []
    for path in LOGS_DIR.glob("chat_*.jsonl"):
        day = path.stem.removeprefix("chat_")
        if _DAY_RE.match(day):
            dates.append(day)
    dates.sort(reverse=True)
    return dates


def _read_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    # Plus récents en premier pour l'UI
    rows.reverse()
    return rows[:limit]


def _compute_stats(events: list[dict[str, Any]]) -> LogsStats:
    stats = LogsStats(total=len(events))
    latencies: list[int] = []
    for ev in events:
        path = str(ev.get("path") or "")
        if path == "deterministic":
            stats.deterministic += 1
        elif path == "nlu":
            stats.nlu += 1
        elif path == "dialog":
            stats.dialog += 1
        elif path == "nlu+dialog":
            stats.nlu_dialog += 1
        if ev.get("llm_used"):
            stats.llm_turns += 1
        stats.total_tokens += int(ev.get("total_tokens") or 0)
        if ev.get("error"):
            stats.errors += 1
        try:
            latencies.append(int(ev.get("latency_ms") or 0))
        except (TypeError, ValueError):
            pass
    if latencies:
        stats.avg_latency_ms = round(sum(latencies) / len(latencies), 1)
    return stats


@router.get("/api/logs", response_model=LogsResponse)
async def get_chat_logs(
    date: str | None = Query(None, description="YYYY-MM-DD (UTC), défaut = aujourd'hui"),
    limit: int = Query(100, ge=1, le=500),
    path: str | None = Query(None, description="Filtrer par path: deterministic|nlu|dialog|nlu+dialog"),
) -> LogsResponse:
    available = _list_log_dates()
    day = (date or "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not _DAY_RE.match(day):
        raise HTTPException(status_code=400, detail="date invalide (attendu YYYY-MM-DD)")

    file_path = LOGS_DIR / f"chat_{day}.jsonl"
    events = _read_jsonl(file_path, limit=limit)

    filter_path = (path or "").strip()
    if filter_path:
        events = [e for e in events if str(e.get("path") or "") == filter_path]

    # Stats sur le fichier complet (avant filtre path) pour KPIs honnêtes
    all_for_day = _read_jsonl(file_path, limit=5000) if filter_path else events
    stats_source = all_for_day if filter_path else events
    # Si filtre actif, stats sur le sous-ensemble affiché
    if filter_path:
        stats_source = events

    return LogsResponse(
        date=day,
        available_dates=available,
        stats=_compute_stats(stats_source),
        events=events,
    )
