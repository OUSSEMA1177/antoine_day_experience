"""Synchronisation légère des slots depuis le message (complément LLM)."""

from __future__ import annotations

import re

from memory.memory_manager import memory_manager
from memory.quote_state import (
    detect_destination_in_message,
    sync_activity_feedback_from_message,
    _prune_wrong_destination,
)

PROFIL_MAP = {
    "famille": re.compile(r"\bfamill", re.I),
    "couple": re.compile(r"\b(en\s+)?couples?\b", re.I),
    "solo": re.compile(r"\b(solo|seul|seule)\b", re.I),
    "groupe_amis": re.compile(r"\bgroupe\s+d[''']?\s*amis\b|\bentre\s+amis\b", re.I),
    "groupe": re.compile(r"\bgroupes?\b", re.I),
    "seminaire": re.compile(r"\b(séminaire|seminaire)\b", re.I),
}

ENVIE_PATTERNS = {
    "mer": re.compile(r"\b(plage|mers?|océan|ocean|côte)\b", re.I),
    "sahara": re.compile(r"\b(sahara|désert|desert)\b", re.I),
    "aventure": re.compile(r"\baventure\b", re.I),
    "culture": re.compile(r"\bculture\b", re.I),
    "gastronomie": re.compile(r"\bgastronomie\b", re.I),
    "nature": re.compile(r"\b(montagne|nature|alpes)\b", re.I),
    "détente": re.compile(r"\b(détente|detente|relax)\b", re.I),
}

DUREE_RE = re.compile(r"\b(\d{1,3})\s*jours?\b", re.I)
GROUP_RE = re.compile(r"\b(\d{1,3})\s*pers+onnes?\b", re.I)
PLAN_REQUEST_RE = re.compile(r"\b(plan|propose|proposition|à ton choix|a ton choix|choisis)\b", re.I)
AGENCY_RE = re.compile(
    r"^[a-zàâäéèêëïîôùûüç0-9\s\-']{3,50}(?:voyage|travel|tours?|agence|trips?)\s*$",
    re.I,
)

DEFAULT_PLAN_DESTINATIONS = ("Marrakech", "Paris", "Rome")

TUNNEL_SLOT_RE = re.compile(
    r"^(une\s+famille|famille|couple|solo|seul|seule|groupe|s[eé]minaire|"
    r"plage|mer|culture|aventure|gastronomie|d[eé]tente|montagne|nature|"
    r"sahara|d[eé]sert|tous|tout|un\s+peu\s+de\s+tout)\s*[?.!,]*$",
    re.I,
)


def is_tunnel_slot_message(message: str) -> bool:
    """Message de qualification tunnel (profil/envies) — pas une requête produit."""
    return bool(TUNNEL_SLOT_RE.match(message.strip()))


def sync_slots_from_message(session_id: str, message: str) -> dict[str, str]:
    """Met à jour la mémoire depuis signaux évidents (pas de NLU lourde)."""
    updates: dict[str, str] = {}
    slots = memory_manager.get_slots(session_id)
    lower = message.strip().casefold()

    dest = detect_destination_in_message(message)
    if dest:
        updates["destination"] = dest

    for name, pattern in PROFIL_MAP.items():
        if pattern.search(message):
            updates["profil_voyageur"] = name
            break

    if lower.strip() in ("tous", "tout", "un peu de tout", "tous les"):
        updates["envies"] = "culture, gastronomie, aventure, détente"
    else:
        envies: list[str] = []
        for name, pattern in ENVIE_PATTERNS.items():
            if pattern.search(message):
                envies.append(name)
        if envies:
            updates["envies"] = ", ".join(envies)

    duree = DUREE_RE.search(message)
    if duree:
        updates["duree"] = f"{duree.group(1)} jours"

    group = GROUP_RE.search(message)
    if group:
        size = int(group.group(1))
        if 2 <= size <= 500:
            updates["taille_groupe"] = str(size)

    if re.search(r"\bprivée?s?\b", message, re.I):
        updates["preference"] = "privé"

    if PLAN_REQUEST_RE.search(message):
        if not str(slots.get("destination", "") or "").strip():
            updates["destination"] = DEFAULT_PLAN_DESTINATIONS[0]
        if "couple" in lower and "profil_voyageur" not in updates:
            updates["profil_voyageur"] = "couple"

    stripped = message.strip()
    if AGENCY_RE.match(stripped) and "?" not in message:
        updates["nom_agence"] = stripped.title()

    if updates:
        memory_manager.update_slots(session_id, **updates)

    if updates.get("destination"):
        _prune_wrong_destination(session_id, updates["destination"])

    sync_activity_feedback_from_message(session_id, message)

    return updates
