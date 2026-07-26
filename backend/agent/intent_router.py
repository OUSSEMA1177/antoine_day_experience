"""Routeur d'intentions — matrice fermée avant chemins catalogue / NLU / LLM.

Objectif : une intention dominante par message, ordre de priorité stable.
Évite le whack-a-mole (faux lieux, greeting répété, budget ignoré).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from agent.context_manager import parse_budget_from_message
from agent.destination_policy import is_destination_not_chosen_yet
from agent.nlu_extractor import is_pure_selection_or_confirm_message
from agent.support_policy import is_support_email_inquiry, is_support_request
from memory.quote_state import is_quote_confirmation, parse_presentation_indices
from search.geo import detect_country_query


class RouteKind(str, Enum):
    SUPPORT = "support"
    SUPPORT_EMAIL = "support_email"
    # Question métier partenaire (commission, facturation, annulation…) → faq.csv
    FAQ = "faq"
    # « oui » après « explorer Parc Kruger ? » / choix ville
    CITY_CONFIRM = "city_confirm"
    NOT_CHOSEN_YET = "not_chosen_yet"
    RAISE_BUDGET = "raise_budget"
    # Budget / « donne activités » sans lieu connu → demander zone (0 token)
    NEED_PLACE_FOR_SEARCH = "need_place_for_search"
    # Lieu (ville ou region_interest) connu + demande activités/budget → search
    SEARCH_ACTIVITIES = "search_activities"
    PURE_SELECTION = "pure_selection"
    COUNTRY_OR_CONTINENT = "country_or_continent"
    UNKNOWN_PLACE = "unknown_place"
    CONTINUE = "continue"  # NLU / planner / LLM


RAISE_BUDGET_RE = re.compile(
    r"(?:"
    r"augment\w*.{0,25}bud[gj]|"
    r"bud[gj]\w*.{0,25}augment|"
    r"(?:plus|davantage)\s+(?:de\s+)?bud[gj]|"
    r"enlever\s+(?:le\s+)?bud[gj]|"
    r"sans\s+(?:le\s+)?bud[gj]|"
    r"pas\s+de\s+(?:limite|plafond)"
    r")",
    re.I,
)

WANTS_ACTIVITIES_RE = re.compile(
    r"\b("
    r"activit|"
    r"exp[eé]riences?|"
    r"excursions?|"
    r"donne[rz]?\s+moi|"
    r"propose[rz]?|"
    r"montre[rz]?|"
    r"cherche|"
    r"besoin\s+d"
    r")",
    re.I,
)

# Messages type « DE BUDGET DE 400… » sans toponyme
HAS_BUDGET_SIGNAL_RE = re.compile(
    r"\b(budg|€|euros?|eur)\b|\d{2,5}\s*(?:€|euros?|eur)\b",
    re.I,
)


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    reason: str = ""


def is_raise_budget_request(message: str) -> bool:
    return bool(RAISE_BUDGET_RE.search(message or ""))


def wants_activity_listing(message: str) -> bool:
    return bool(WANTS_ACTIVITIES_RE.search(message or ""))


def _filled(slots: dict, key: str) -> bool:
    return bool(str(slots.get(key, "") or "").strip())


def has_search_place(slots: dict) -> bool:
    """Ville catalogue ou région/pays déjà en session."""
    return _filled(slots, "destination") or _filled(slots, "region_interest")


def classify_route(message: str, slots: dict | None = None) -> RouteDecision:
    """Une intention dominante — ordre = priorité orchestrateur."""
    text = (message or "").strip()
    slots = slots or {}

    if not text:
        return RouteDecision(RouteKind.CONTINUE, "empty")

    if is_support_email_inquiry(text):
        return RouteDecision(RouteKind.SUPPORT_EMAIL, "ask_email")
    if is_support_request(text):
        return RouteDecision(RouteKind.SUPPORT, "escalation")

    # FAQ métier (commission, réservation, annulation…) — avant budget/activités
    from agent.faq_policy import is_faq_inquiry

    if is_faq_inquiry(text) and not detect_country_query(text):
        return RouteDecision(RouteKind.FAQ, "faq_inquiry")

    # Confirmation / pick ville en attente (avant « oui » devis)
    awaiting_city = _filled(slots, "awaiting_city_confirm") or _filled(
        slots, "awaiting_city_pick"
    )
    if awaiting_city and not _filled(slots, "awaiting_quote_confirm"):
        from agent.destination_confirm import is_affirmative_short, is_negative_short

        if is_affirmative_short(text) or is_negative_short(text):
            return RouteDecision(RouteKind.CITY_CONFIRM, "pending_city")

    if is_destination_not_chosen_yet(text):
        return RouteDecision(RouteKind.NOT_CHOSEN_YET, "destination_unknown")

    if is_raise_budget_request(text):
        return RouteDecision(RouteKind.RAISE_BUDGET, "raise_budget")

    from memory.quote_state import (
        is_add_this_activity,
        is_reject_presented_list,
        is_wants_another_activity,
        is_wants_other_options,
    )

    # Ordinal + autre activité / « oui ajoute ceci » → quote_state 0 token (pas search)
    if is_add_this_activity(text):
        return RouteDecision(RouteKind.PURE_SELECTION, "add_this")
    if parse_presentation_indices(text) and is_wants_another_activity(text):
        return RouteDecision(RouteKind.PURE_SELECTION, "select_and_add")
    # « autre option » / refus liste → search / re-list (pas thème add)
    if is_wants_other_options(text) or is_reject_presented_list(text):
        if has_search_place(slots):
            return RouteDecision(RouteKind.SEARCH_ACTIVITIES, "other_options")
        return RouteDecision(RouteKind.CONTINUE, "other_options")
    # « autre activité » / « d'autres activités » → pas SEARCH (garde sélection + ask thème)
    if is_wants_another_activity(text):
        return RouteDecision(RouteKind.CONTINUE, "wants_another")

    # Sélection / oui devis purs — avant faux lieu (pas si demande d'activités / pays / budget)
    if is_pure_selection_or_confirm_message(text) or (
        parse_presentation_indices(text) and not wants_activity_listing(text)
    ):
        if (
            not wants_activity_listing(text)
            and not parse_budget_from_message(text)
            and not detect_country_query(text)
            and not HAS_BUDGET_SIGNAL_RE.search(text)
        ):
            return RouteDecision(RouteKind.PURE_SELECTION, "selection_or_confirm")
        # « 1 est ok » + mots activités → quand même sélection (pas search)
        if parse_presentation_indices(text) and not parse_budget_from_message(text):
            return RouteDecision(RouteKind.PURE_SELECTION, "selection_with_ok")

    country = detect_country_query(text)
    if country:
        return RouteDecision(RouteKind.COUNTRY_OR_CONTINENT, country)

    budget_in_msg = parse_budget_from_message(text) or bool(HAS_BUDGET_SIGNAL_RE.search(text))
    wants_acts = wants_activity_listing(text)

    if (budget_in_msg or wants_acts) and has_search_place(slots):
        return RouteDecision(RouteKind.SEARCH_ACTIVITIES, "context_search")

    if (budget_in_msg or wants_acts) and not has_search_place(slots):
        # Évite greeting LLM / faux lieu
        return RouteDecision(RouteKind.NEED_PLACE_FOR_SEARCH, "budget_or_activities_no_place")

    # Faux lieux gérés plus bas dans orchestrator (après ce filtre)
    return RouteDecision(RouteKind.CONTINUE, "default")


def build_need_place_reply(slots: dict) -> str:
    budget = str(slots.get("budget", "") or "").strip()
    prefix = f"Budget ~{budget} € noté. " if budget else ""
    return (
        f"{prefix}"
        "Pour proposer des activités du catalogue, indiquez une ville ou une zone "
        "(ex. Espagne, Afrique, Paris, Marrakech, Bali). "
        "Quelle destination pour votre client ?"
    )
