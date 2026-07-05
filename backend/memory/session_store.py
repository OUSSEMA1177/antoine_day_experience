"""In-memory session storage (MVP)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    slots: dict[str, str | list[str]] = field(default_factory=dict)
    escalated: bool = False


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


session_store = SessionStore()
