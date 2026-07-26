"""Confirmation / choix de ville après une offre pays (0 token).

Quand le bot dit « Souhaitez-vous explorer Parc Kruger ? » ou liste
Barcelone / Séville, on pose des slots awaiting_* pour que « oui » /
le nom de ville ne retombe pas sur ASK_DESTINATION.
"""

from __future__ import annotations

import re

from memory.memory_manager import memory_manager
from memory.quote_state import parse_presentation_indices
from search.geo import _norm, resolve_destination_name
from services.data_loader import data_loader

AFFIRM_RE = re.compile(
    r"^(?:oui+|ouais|ouai|ui+|ok|d['\u2019]?accord|dacord|parfait|super|top|yes|go|vas[- ]y|"
    r"volontiers|avec\s+plaisir|bien\s+s[uû]r|carr[eé]ment|"
    r"explorons|allez|je\s+veux\s+bien|c['\u2019]?est\s+bon)"
    r"(?:\s*[!.]*)?$",
    re.I,
)
NEGATE_RE = re.compile(
    r"^(?:non|nan|nope|pas\s+(?:ça|ca|maintenant)|autre\s+chose)"
    r"(?:\s*[!.]*)?$",
    re.I,
)


def is_affirmative_short(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 60:
        return False
    # Ne pas confondre avec « oui ajoute ceci » / sélection
    from memory.quote_state import is_add_this_activity, parse_presentation_indices

    if is_add_this_activity(text) or parse_presentation_indices(text):
        return False
    return bool(AFFIRM_RE.match(text))


def is_negative_short(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 60:
        return False
    return bool(NEGATE_RE.match(text))


def clear_pending_city(session_id: str) -> None:
    memory_manager.clear_slot(session_id, "awaiting_city_confirm")
    memory_manager.clear_slot(session_id, "awaiting_city_pick")
    memory_manager.clear_slot(session_id, "pending_destination")
    memory_manager.clear_slot(session_id, "pending_cities")


def remember_city_offer(
    session_id: str,
    cities: list[str],
    *,
    region_key: str = "",
) -> None:
    """Après build_country_catalog_reply : 1 ville = confirm, N villes = pick."""
    clean = [c.strip() for c in cities if (c or "").strip()]
    if not clean:
        clear_pending_city(session_id)
        return
    if region_key and region_key != "all":
        memory_manager.update_slots(session_id, region_interest=region_key)
    if len(clean) == 1:
        memory_manager.update_slots(
            session_id,
            awaiting_city_confirm="1",
            pending_destination=clean[0],
        )
        memory_manager.clear_slot(session_id, "awaiting_city_pick")
        memory_manager.clear_slot(session_id, "pending_cities")
        return
    # Multi-villes (ex. Espagne) — pas pour le dump « all » trop long
    if region_key == "all" or len(clean) > 25:
        clear_pending_city(session_id)
        return
    memory_manager.update_slots(
        session_id,
        awaiting_city_pick="1",
        pending_cities="|".join(clean),
    )
    memory_manager.clear_slot(session_id, "awaiting_city_confirm")
    memory_manager.clear_slot(session_id, "pending_destination")


def _pending_city_list(slots: dict) -> list[str]:
    raw = str(slots.get("pending_cities", "") or "").strip()
    if raw:
        return [p.strip() for p in raw.split("|") if p.strip()]
    pending = str(slots.get("pending_destination", "") or "").strip()
    return [pending] if pending else []


def resolve_pending_city_choice(session_id: str, message: str) -> str | None:
    """Retourne le nom de ville catalogue à activer, ou None."""
    slots = memory_manager.get_slots(session_id)
    awaiting_confirm = str(slots.get("awaiting_city_confirm", "") or "").strip()
    awaiting_pick = str(slots.get("awaiting_city_pick", "") or "").strip()
    if not awaiting_confirm and not awaiting_pick:
        return None

    text = (message or "").strip()
    if not text:
        return None

    pending = str(slots.get("pending_destination", "") or "").strip()
    cities = _pending_city_list(slots)

    if awaiting_confirm and pending:
        if is_affirmative_short(text):
            return pending
        if is_negative_short(text):
            clear_pending_city(session_id)
            return None
        # « Parc Kruger » / « kruger » au lieu de oui
        if _norm(pending) in _norm(text) or _norm(text) in _norm(pending):
            return pending
        resolved = resolve_destination_name(text, data_loader)
        if resolved and _norm(resolved) == _norm(pending):
            return pending

    if awaiting_pick and cities:
        if is_negative_short(text):
            clear_pending_city(session_id)
            return None
        indices = parse_presentation_indices(text)
        if len(indices) == 1 and 1 <= indices[0] <= len(cities):
            return cities[indices[0] - 1]
        # Match nom / alias
        needle = _norm(text)
        for city in cities:
            if _norm(city) == needle or _norm(city) in needle or needle in _norm(city):
                return city
        resolved = resolve_destination_name(text, data_loader)
        if resolved:
            for city in cities:
                if _norm(city) == _norm(resolved):
                    return city

    return None
