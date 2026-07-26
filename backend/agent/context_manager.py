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
    "mer": re.compile(
        r"\b(plages?|mers?|oc[eé]ans?|c[oô]tes?|lagons?|snorkeling|plong[eé]e|baln[eé]aire)\b",
        re.I,
    ),
    "montagne": re.compile(
        r"\b(montagnes?|alpes|volcans?|randonn[eé]e|treks?|trekking)\b",
        re.I,
    ),
    "foret": re.compile(r"\b(for[eê]ts?|jungles?|tropicale?s?)\b", re.I),
    "sahara": re.compile(r"\b(sahara|d[eé]serts?|dunes?)\b", re.I),
    "aventure": re.compile(r"\baventure\b", re.I),
    "culture": re.compile(r"\bculture\b", re.I),
    "gastronomie": re.compile(r"\b(gastronomie|cuisine)\b", re.I),
    "nature": re.compile(r"\b(nature|cascades?|safari)\b", re.I),
    "détente": re.compile(r"\b(d[eé]tente|relax|spa|wellness)\b", re.I),
    "croisiere": re.compile(r"\b(croisi[eè]res?|catamaran)\b", re.I),
}

DUREE_RE = re.compile(r"\b(\d{1,3})\s*jours?\b", re.I)
GROUP_RE = re.compile(r"\b(\d{1,3})\s*pers+onnes?\b", re.I)
BUDGET_RE = re.compile(
    r"(?:"
    r"\bj['\u2019]?\s*ai\s+(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)\b|"
    r"\bj\s+ai\s+(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)\b|"
    r"\b(?:budget|budjet|max(?:imum)?)\s*(?:de\s+|à\s+|a\s+)?(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)?\b|"
    r"\b(?:jusqu['\u2019]?[aà]|moins\s+de)\s+(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)\b|"
    r"\b(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)\b"
    r")",
    re.I,
)
PLAN_REQUEST_RE = re.compile(r"\b(plan|propose|proposition|à ton choix|a ton choix|choisis)\b", re.I)
AGENCY_RE = re.compile(
    r"^[a-zàâäéèêëïîôùûüç0-9\s\-']{3,50}(?:voyage|travel|tours?|agence|trips?)\s*$",
    re.I,
)

DEFAULT_PLAN_DESTINATIONS = ("Marrakech", "Paris", "Rome")

TUNNEL_SLOT_RE = re.compile(
    r"^(une\s+famille|en\s+famille|famille|en\s+couple|couple|solo|seul|seule|"
    r"groupe|s[eé]minaire|plage|mer|culture|aventure|gastronomie|d[eé]tente|"
    r"montagne|for[eê]t|jungle|nature|sahara|d[eé]sert|croisi[eè]re|"
    r"g[eé]n[eé]rale?|g[eé]n[eé]ral|general|"
    r"tous|tout|un\s+peu\s+de\s+tout|mix\s+de\s+tout|un\s+mix|"
    r"un\s+peu\s+de\s+chaque|de\s+tout)\s*[?.!,]*$",
    re.I,
)

MIX_ALL_RE = re.compile(
    r"\b(mix\s+de\s+tout|un\s+peu\s+de\s+tout|un\s+mix|de\s+tout|"
    r"un\s+peu\s+de\s+chaque|tout\s+un\s+peu|un\s+peu\s+tout)\b",
    re.I,
)


def is_tunnel_slot_message(message: str) -> bool:
    """Message de qualification tunnel (profil/envies) — pas une requête produit."""
    return bool(TUNNEL_SLOT_RE.match(message.strip()))


def is_qualification_message(message: str) -> bool:
    """Profil, envies ou réponse tunnel — ne jamais traiter comme une destination."""
    text = message.strip()
    if not text or len(text) > 100:
        return False
    if is_tunnel_slot_message(text):
        return True
    if MIX_ALL_RE.search(text):
        return True
    lower = text.casefold()
    if lower in ("tous", "tout", "un peu de tout", "tous les", "mix de tout", "un mix"):
        return True
    for pattern in PROFIL_MAP.values():
        if pattern.search(text):
            return True
    for pattern in ENVIE_PATTERNS.values():
        if pattern.search(text) and len(text.split()) <= 8:
            return True
    return False


def parse_budget_from_message(message: str) -> str | None:
    """Extrait un budget numérique (ex. « 200 euro », « budget 150 € »)."""
    match = BUDGET_RE.search(message or "")
    if not match:
        return None
    raw = next((g for g in match.groups() if g), None)
    if not raw:
        return None
    try:
        value = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if value < 5 or value > 100_000:
        return None
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def sync_slots_from_message(session_id: str, message: str) -> dict[str, str]:
    """Met à jour la mémoire depuis signaux évidents (pas de NLU lourde)."""
    updates: dict[str, str] = {}
    slots = memory_manager.get_slots(session_id)
    lower = message.strip().casefold()

    dest = detect_destination_in_message(message)
    if dest:
        updates["destination"] = dest
        updates["destination_demandee"] = ""

    for name, pattern in PROFIL_MAP.items():
        if pattern.search(message):
            updates["profil_voyageur"] = name
            break

    if MIX_ALL_RE.search(message) or lower.strip() in (
        "tous", "tout", "un peu de tout", "tous les", "mix de tout", "un mix",
    ):
        updates["envies"] = "culture, gastronomie, aventure, nature, détente"
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

    budget = parse_budget_from_message(message)
    if budget:
        updates["budget"] = budget

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
