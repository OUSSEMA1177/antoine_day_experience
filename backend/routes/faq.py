"""FAQ partenaires — liste et recherche."""

from fastapi import APIRouter, Query

from app.models import FaqItemOut, FaqResponse
from services.data_loader import data_loader

router = APIRouter(tags=["faq"])


@router.get("/faq", response_model=FaqResponse)
async def list_faq(
    q: str | None = Query(None, description="Recherche dans question / réponse / catégorie"),
    limit: int = Query(50, ge=1, le=100),
) -> FaqResponse:
    query = (q or "").strip()
    if query:
        rows = data_loader.search_faq(query, limit=limit)
    else:
        rows = data_loader.load_faq()[:limit]
    items = [
        FaqItemOut(
            id=str(row.get("id", "")),
            question=row.get("question", "") or "",
            reponse=row.get("reponse", "") or "",
            categorie=row.get("categorie", "") or "",
        )
        for row in rows
    ]
    return FaqResponse(total=len(items), items=items)
