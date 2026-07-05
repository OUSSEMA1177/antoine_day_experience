"""Devis PDF — génération et téléchargement."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models import QuoteRequest, QuoteResponse, QuoteSessionRequest, QuoteStateResponse
from memory.memory_manager import memory_manager
from memory.quote_state import compute_quote_state
from pdf.quote_generator import OUTPUT_DIR, generate_quote_for_session

router = APIRouter(tags=["quote"])


@router.get("/session/{session_id}/quote-state", response_model=QuoteStateResponse)
async def get_quote_state(session_id: str) -> QuoteStateResponse:
    state = compute_quote_state(session_id)
    return QuoteStateResponse(
        session_id=session_id,
        quote_ready=state["quote_ready"],
        missing=state["missing"],
        destination=state["destination"],
        nom_agence=state["nom_agence"],
        activities=state["activities"],
    )


@router.post("/quote/from-session", response_model=QuoteResponse)
async def create_quote_from_session(payload: QuoteSessionRequest) -> QuoteResponse:
    if payload.partner_id and payload.partner_id.strip():
        memory_manager.update_slots(payload.session_id, partner_id=payload.partner_id.strip())

    state = compute_quote_state(payload.session_id)
    if not state["quote_ready"]:
        missing = ", ".join(state["missing"]) or "informations"
        raise HTTPException(
            status_code=400,
            detail=f"Devis incomplet — manque : {missing}",
        )

    try:
        result = generate_quote_for_session(
            session_id=payload.session_id,
            destination=state["destination"] or "",
            activity_ids=state["activity_ids"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur génération PDF : {exc}") from exc

    return QuoteResponse(
        session_id=payload.session_id,
        devis_ref=result["devis_ref"],
        pdf_url=result["pdf_url"],
        destination=result["destination"],
        activity_count=int(result["activity_count"]),
        total_net=result["total_net"],
        valid_until=result["valid_until"],
    )


@router.post("/quote", response_model=QuoteResponse)
async def create_quote(payload: QuoteRequest) -> QuoteResponse:
    if payload.partner_id and payload.partner_id.strip():
        memory_manager.update_slots(
            payload.session_id,
            partner_id=payload.partner_id.strip(),
        )
    if not payload.activity_ids:
        raise HTTPException(status_code=400, detail="Au moins une activité est requise.")

    try:
        result = generate_quote_for_session(
            session_id=payload.session_id,
            destination=payload.destination,
            activity_ids=payload.activity_ids,
            devis_ref=payload.devis_ref,
            validite_jours=payload.validite_jours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur génération PDF : {exc}") from exc

    return QuoteResponse(
        session_id=payload.session_id,
        devis_ref=result["devis_ref"],
        pdf_url=result["pdf_url"],
        destination=result["destination"],
        activity_count=int(result["activity_count"]),
        total_net=result["total_net"],
        valid_until=result["valid_until"],
    )


@router.get("/quotes/{filename}", include_in_schema=True)
async def download_quote(filename: str) -> FileResponse:
    safe = Path(filename).name
    if not safe.endswith(".pdf") or ".." in safe:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    path = OUTPUT_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Devis introuvable.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=safe,
        headers={"Content-Disposition": f'inline; filename="{safe}"'},
    )
