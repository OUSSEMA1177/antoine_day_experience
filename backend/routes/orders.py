"""Order lookup endpoints."""

from fastapi import APIRouter, HTTPException

from app.models import OrderOut
from services.data_loader import data_loader

router = APIRouter(tags=["orders"])


@router.get("/orders/{reference}", response_model=OrderOut)
async def get_order(reference: str) -> OrderOut:
    row = data_loader.get_order_by_reference(reference)
    if not row:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return OrderOut.model_validate(row)
