"""Activity catalogue endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.models import ActivitiesResponse, ActivityOut, DestinationOut, DestinationsResponse, PartnerOut
from agent.partner_context import build_greeting_reply
from services.data_loader import data_loader

router = APIRouter(tags=["activities"])


@router.get("/activities", response_model=ActivitiesResponse)
async def list_activities(
    destination: str | None = Query(None, description="Nom de la destination (ex: Paris)"),
    destination_id: int | None = Query(None, description="ID destination B2B"),
    budget: float | None = Query(None, ge=0, description="Budget maximum par personne (€)"),
    profil: str | None = Query(None, description="Profil voyageur (famille, couple, solo…)"),
    q: str | None = Query(None, description="Recherche texte dans titre / description"),
    limit: int = Query(20, ge=1, le=100),
) -> ActivitiesResponse:
    rows = data_loader.search_activities(
        destination_id=destination_id,
        destination_name=destination,
        budget_max=budget,
        profil=profil,
        query=q,
        limit=limit,
    )
    items = [ActivityOut.model_validate(row) for row in rows]
    return ActivitiesResponse(total=len(items), items=items)


@router.get("/activities/{activity_id}", response_model=ActivityOut)
async def get_activity(activity_id: str) -> ActivityOut:
    row = data_loader.get_activity_by_id(activity_id)
    if not row:
        raise HTTPException(status_code=404, detail="Activité introuvable")
    return ActivityOut.model_validate(row)


@router.get("/destinations", response_model=DestinationsResponse)
async def list_destinations() -> DestinationsResponse:
    rows = data_loader.load_destinations()
    items = [DestinationOut.model_validate(row) for row in rows]
    return DestinationsResponse(total=len(items), items=items)


@router.get("/partners/{partner_id}", response_model=PartnerOut)
async def get_partner(partner_id: str) -> PartnerOut:
    row = data_loader.get_partner_by_id(partner_id)
    if not row:
        raise HTTPException(status_code=404, detail="Partenaire introuvable")
    name = (row.get("nom_agence") or row.get("nom_complet") or "").strip()
    return PartnerOut(
        id=str(row.get("id", partner_id)),
        nom_agence=name,
        pays=row.get("pays", "") or "",
        greeting_message=build_greeting_reply(name) if name else "",
    )
