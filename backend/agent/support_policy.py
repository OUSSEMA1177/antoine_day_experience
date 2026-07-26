"""Escalade support — hors chat, orientation e-mail (pas de conseiller in-app)."""

from __future__ import annotations

import re

from memory.memory_manager import memory_manager

# Placeholder démo — à remplacer par l'adresse support réelle plus tard
DEFAULT_SUPPORT_EMAIL = "support@day-experience-demo.com"

SUPPORT_REQUEST_RE = re.compile(
    r"\b("
    r"rembours|"
    r"r[eé]clamation|"
    r"reclamation|"
    r"litige|"
    r"plainte|"
    r"insatisfait|"
    r"m[eé]content|"
    r"refund|"
    r"claim|"
    r"complaint|"
    r"modifier\s+(?:ma|la)\s+commande|"
    r"annuler\s+(?:ma|la)\s+commande|"
    r"sav\b|"
    r"service\s+client"
    r")",
    re.I,
)

# « c'est quoi votre e-mail ? » / « comment contacter le support »
SUPPORT_EMAIL_ASK_RE = re.compile(
    r"(?:"
    r"(?:c['\u2019]?est\s+quoi|quelle\s+est|quel\s+est|donnez?[ -]?moi|donne[rz]?|"
    r"avez[- ]vous|vous\s+avez|besoin\s+de|je\s+(?:veux|voudrais|cherche))\s+"
    r".{0,40}?\b(?:e[ -]?mails?|mails?|courriels?)\b|"
    r"\b(?:votre|vos)\s+(?:e[ -]?mails?|mails?|adresse\s+(?:e[ -]?mail|mail|courriel))\b|"
    r"\badresse\s+(?:e[ -]?mail|mail|courriel|support)\b|"
    r"\b(?:contact|contacter)\s+(?:par\s+)?(?:e[ -]?mail|mail)\b|"
    r"\b(?:comment|comment\s+faire\s+(?:pour|a|à))\s+.{0,40}?\b(?:contact|contacter|joindre)\b|"
    r"\b(?:contacter?|joindre)\s+(?:le\s+|l['\u2019]?)?(?:support|sav|service\s+client)\b|"
    r"\b(?:contacter?|joindre)\s+(?:vous|day\s+experience)\b|"
    r"\bhow\s+(?:can\s+i\s+|to\s+)?contact\b|"
    r"\bsupport\s+e[ -]?mail\b|"
    r"\be[ -]?mail\s+(?:de\s+)?support\b|"
    r"\b(?:num[eé]ro|coordonn[eé]es)\s+(?:du\s+|de\s+)?support\b"
    r")",
    re.I,
)


def support_email() -> str:
    try:
        from app.config import get_settings

        email = (get_settings().support_email or "").strip()
        return email or DEFAULT_SUPPORT_EMAIL
    except Exception:
        return DEFAULT_SUPPORT_EMAIL


def is_support_request(message: str) -> bool:
    return bool(SUPPORT_REQUEST_RE.search(message or ""))


def is_support_email_inquiry(message: str) -> bool:
    """Demande l'adresse e-mail / contact — pas forcément une escalade dossier."""
    return bool(SUPPORT_EMAIL_ASK_RE.search(message or ""))


def build_support_contact_reply() -> str:
    """Réponse courte : donner l'e-mail support (0 token)."""
    email = support_email()
    return (
        f"Notre adresse support est {email}. "
        "Pour un remboursement, une réclamation ou un litige, "
        "écrivez-nous en indiquant la référence de commande : un conseiller vous répondra par e-mail."
    )


def build_support_email_reply(*, reason: str | None = None) -> str:
    """Réponse déterministe : orienter vers l'e-mail, sans promettre un rappel chat."""
    email = support_email()
    motif = (reason or "").strip()
    extra = f" (motif : {motif})" if motif else ""
    return (
        f"Cette demande{extra} ne peut pas être traitée dans le chat. "
        f"Merci d'écrire à {email} en indiquant la référence de commande "
        f"et les détails de votre demande. Un conseiller vous répondra par e-mail."
    )


def escalate_session(session_id: str, reason: str = "") -> dict[str, str]:
    """Marque la session et renvoie le payload tool / API."""
    memory_manager.mark_escalated(session_id)
    email = support_email()
    return {
        "status": "escalated_to_email",
        "support_email": email,
        "reason": reason or "",
        "message": build_support_email_reply(reason=reason),
        "instruction": (
            "Ne pas dire qu'un conseiller contactera via le chat. "
            f"Indiquer uniquement d'écrire à {email}."
        ),
    }
