"""Détection d'intention — structure prête pour enrichissement LLM."""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    ACTIVITY_SEARCH = "activity_search"
    TUNNEL_QUALIFY = "tunnel_qualify"
    QUOTE = "quote"
    ORDER = "order"
    FAQ = "faq"
    SUPPORT = "support"
    GENERAL = "general"


ORDER_RE = re.compile(r"\b([A-Z]{2,}-\d{3,})\b", re.I)
GREETINGS = frozenset({"bonjour", "bonsoir", "salut", "hello", "hi", "coucou"})
FAQ_HINTS = ("commission", "annulation", "paiement", "facture", "remboursement")
SUPPORT_HINTS = ("remboursement", "réclamation", "reclamation", "litige", "insatisfait", "plainte")
QUOTE_HINTS = ("devis", "quote", "proposition", "générer le pdf")
PLAN_HINTS = ("plan", "propose", "proposition", "à ton choix", "a ton choix", "choisis", "sélection")
ACTIVITY_HINTS = (
    "activit", "expérience", "experience", "recherche", "catalogue",
    "montagne", "plage", "mer", "sahara", "désert", "aventure", "destination",
)


def detect_intent(message: str, *, escalated: bool = False) -> Intent:
    text = message.strip()
    lower = text.casefold()

    if escalated:
        return Intent.SUPPORT

    if ORDER_RE.search(text):
        return Intent.ORDER

    normalized = lower.rstrip("!.? ")
    if normalized in GREETINGS or (len(text) < 15 and normalized.split()[0] in GREETINGS):
        return Intent.GREETING

    if any(h in lower for h in SUPPORT_HINTS):
        return Intent.SUPPORT

    if any(h in lower for h in QUOTE_HINTS):
        return Intent.QUOTE

    if "?" in text and any(h in lower for h in FAQ_HINTS):
        return Intent.FAQ

    if any(h in lower for h in PLAN_HINTS):
        return Intent.ACTIVITY_SEARCH

    if any(h in lower for h in ACTIVITY_HINTS):
        return Intent.ACTIVITY_SEARCH

    if len(text) < 60:
        return Intent.TUNNEL_QUALIFY

    return Intent.GENERAL
