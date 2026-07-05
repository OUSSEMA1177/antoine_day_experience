"""Résolution nom agence partenaire (White Label) depuis partner_id ou slots."""

from __future__ import annotations

from memory.memory_manager import memory_manager
from services.data_loader import data_loader


def resolve_agency_name(session_id: str) -> str | None:
    """Nom affichable agence : nom_agence slot, sinon lookup partner_id."""
    slots = memory_manager.get_slots(session_id)
    nom = str(slots.get("nom_agence", "") or "").strip()
    if nom:
        return nom

    partner_id = str(slots.get("partner_id", "") or "").strip()
    if not partner_id:
        return None

    partner = data_loader.get_partner_by_id(partner_id)
    if not partner:
        return None

    return (partner.get("nom_agence") or partner.get("nom_complet") or "").strip() or None


def sync_partner_from_id(session_id: str, partner_id: str) -> str | None:
    """Enregistre partner_id + nom_agence en mémoire. Retourne le nom agence."""
    pid = partner_id.strip()
    if not pid:
        return None

    memory_manager.update_slots(session_id, partner_id=pid)
    partner = data_loader.get_partner_by_id(pid)
    if not partner:
        return None

    name = (partner.get("nom_agence") or partner.get("nom_complet") or "").strip()
    if name:
        memory_manager.update_slots(session_id, nom_agence=name)
    return name or None


def build_greeting_reply(agency_name: str) -> str:
    return (
        f"Bonjour {agency_name} ! "
        "Votre client a choisi sa destination ? Dites-moi où il va — "
        "je vous montre ce qu'il peut y vivre."
    )
