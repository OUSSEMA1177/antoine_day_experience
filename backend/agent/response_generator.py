"""Post-traitement des réponses LLM."""

from __future__ import annotations

import re

FORBIDDEN_PHRASES = (
    "tunnel antoine",
    "tunnel conversationnel",
    "étape 1",
    "étape 2",
    "processus en",
    "simuler la génération",
    "je vais simuler",
    "ne peux pas accéder à l'outil",
    "ne peut pas accéder",
    "generate_quote réel",
    "outil generate_quote",
    "vous envoyer le devis par e-mail",
    "envoyer le devis par email",
    "devis généré !",
    "un conseiller vous contactera rapidement",
    "un conseiller vous contactera",
    "demande a été transmise à notre équipe",
    "demande a ete transmise a notre equipe",
    "transmise à notre équipe",
)


def sanitize_response(text: str) -> str:
    if not text:
        return "Je n'ai pas pu formuler de réponse. Pouvez-vous reformuler ?"
    cleaned = text.strip()
    for phrase in FORBIDDEN_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    # Style pro : pas de gras markdown **texte**
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()
