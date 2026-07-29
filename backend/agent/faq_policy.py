"""FAQ dans le chat — réponses déterministes depuis data/faq.csv (0 token).

Le partenaire peut poser une question FAQ directement dans la conversation
(« quel est le taux de commission ? », « comment fonctionne la réservation ? »).
Gate regex (question métier) puis meilleure entrée via data_loader.search_faq.
"""

from __future__ import annotations

import re

# Mot interrogatif / tournure de question
FAQ_QUESTION_RE = re.compile(
    r"\b("
    r"comment|combien|pourquoi|"
    r"quel(?:le)?s?|"
    r"est[- ]il|est[- ]ce|sont[- ]ils?|sont[- ]elles?|"
    r"qui\s+est|qui\s+[eê]tes|"
    r"c['\u2019]?est\s+quoi"
    r")\b",
    re.I,
)

# Sujets couverts par la FAQ partenaires (pas le catalogue d'activités)
FAQ_TOPIC_RE = re.compile(
    r"\b("
    r"commissions?|"
    r"factur\w*|"
    r"paiements?|"
    r"annulations?|"
    r"modifications?|"
    r"vouchers?|"
    r"day\s*experience|"
    r"prix\s+garant\w*|"
    r"garant\w*|"
    r"revend\w*|"
    r"je\s+gagne|gagner?|"
    r"r[eé]serv\w*|"
    r"suivi\s+du\s+voyageur|"
    r"supports?|"
    r"apst|"
    r"centrale|"
    r"atouts?|"
    r"avantages?|"
    r"avant\s+le\s+d[eé]part"
    r")\b",
    re.I,
)

# Sujets assez spécifiques pour matcher même sans mot interrogatif
FAQ_STRONG_TOPIC_RE = re.compile(
    r"\b("
    r"taux\s+de\s+commission|commissions?|"
    r"facturation|"
    r"vouchers?|"
    r"apst|"
    r"politique\s+d['\u2019]?annulation|"
    r"prix\s+garant\w*"
    r")\b",
    re.I,
)


def is_faq_inquiry(message: str) -> bool:
    """Question métier FAQ — pas une demande catalogue/destination."""
    text = (message or "").strip()
    if not text:
        return False
    if FAQ_STRONG_TOPIC_RE.search(text):
        return True
    return bool(FAQ_QUESTION_RE.search(text) and FAQ_TOPIC_RE.search(text))


def find_faq_answer(message: str) -> dict[str, str] | None:
    """Meilleure entrée FAQ pour le message, None si rien de pertinent."""
    if not is_faq_inquiry(message):
        return None
    from services.data_loader import data_loader

    rows = data_loader.search_faq(message, limit=1)
    return rows[0] if rows else None


def build_faq_reply(row: dict[str, str]) -> str:
    question = (row.get("question") or "").strip()
    answer = (row.get("reponse") or "").strip()
    return (
        f"{question}\n\n{answer}\n\n"
        "D'autres questions ? L'onglet FAQ du widget regroupe toutes les réponses."
    )
