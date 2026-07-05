"""Conversation history per session."""

from __future__ import annotations

from memory.session_store import session_store


class ConversationManager:
    def get_history(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        session = session_store.get(session_id)
        return session.messages[-limit:]

    def add_turn(self, session_id: str, user_message: str, assistant_reply: str) -> None:
        session = session_store.get(session_id)
        session.messages.append({"role": "user", "content": user_message})
        session.messages.append({"role": "assistant", "content": assistant_reply})


conversation_manager = ConversationManager()
