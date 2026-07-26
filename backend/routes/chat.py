"""Chat endpoint — agent conversationnel."""

from fastapi import APIRouter, HTTPException

from app.models import ChatRequest, ChatResponse
from agent.partner_context import sync_partner_from_id
from memory.memory_manager import memory_manager
from services.agent import AgentConfigurationError, AgentError, agent_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        if payload.partner_id and payload.partner_id.strip():
            sync_partner_from_id(payload.session_id, payload.partner_id.strip())
        reply, tools_used, meta = agent_service.chat(payload.session_id, payload.message)
        return ChatResponse(
            session_id=payload.session_id,
            reply=reply,
            tools_used=tools_used,
            quote_url=meta.get("quote_url"),
            devis_ref=meta.get("devis_ref"),
            quote_ready=bool(meta.get("quote_ready")),
            quote_activities=meta.get("quote_activities") or [],
            destination=meta.get("destination"),
            nom_agence=meta.get("nom_agence"),
            llm_used=bool(meta.get("llm_used")),
            llm_model=meta.get("llm_model"),
            prompt_tokens=int(meta.get("prompt_tokens") or 0),
            completion_tokens=int(meta.get("completion_tokens") or 0),
            total_tokens=int(meta.get("total_tokens") or 0),
        )
    except AgentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/session/{session_id}")
async def clear_session(session_id: str) -> dict[str, str]:
    """Reset mémoire + historique (nouvelle conversation QA)."""
    from memory.session_store import session_store

    session_store.clear(session_id)
    return {"status": "cleared", "session_id": session_id}
