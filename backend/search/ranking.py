"""Scoring et classement des activités catalogue."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.data_loader import DataLoader

ENVIE_TERMS: dict[str, list[str]] = {
    "mer": ["mer", "essaouira", "mogador", "bateau", "plage", "côte", "cote", "atlantique"],
    "sahara": ["sahara", "désert", "desert", "merzouga", "agafay", "dune", "chameau"],
    "aventure": ["quad", "4x4", "buggy", "montgolfière", "safari", "sensations"],
    "culture": ["médina", "medina", "souk", "palais", "musée", "musee", "monument"],
    "gastronomie": ["dîner", "diner", "restaurant", "gastronom", "spectacle"],
    "détente": ["spa", "jardin", "calèche", "relax"],
    "nature": ["atlas", "ouzoud", "cascade", "montagne", "alpes", "mont fuji", "hajar"],
}

STOPWORDS = frozenset(
    {
        "je", "tu", "il", "nous", "vous", "les", "des", "une", "pour", "avec", "dans",
        "pas", "que", "qui", "est", "son", "ses", "mon", "mes", "donner", "donne",
        "moi", "tes", "nos", "vos", "bonjour", "hello", "client", "voyage",
        "choisi", "choisit", "destination", "activites", "activité", "devis",
        "veux", "veut", "voulez", "avoir", "faire", "aller", "être", "ete",
    }
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[a-zàâäéèêëïîôùûüçœæ0-9'-]{3,}", _norm(text))
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 3]


def activity_haystack(loader: Any, row: dict[str, str]) -> str:
    dest = loader.get_destination_by_id(row.get("destination_id", ""))
    return _norm(
        " ".join(
            [
                row.get("titre", ""),
                row.get("description", ""),
                row.get("categorie", ""),
                row.get("profil_cible", ""),
                dest.get("nom", "") if dest else "",
                dest.get("pays", "") if dest else "",
            ]
        )
    )


def score_activity(
    loader: Any,
    row: dict[str, str],
    *,
    query_tokens: list[str],
    profil: str | None = None,
    themes: list[str] | None = None,
) -> int:
    haystack = activity_haystack(loader, row)
    score = 0

    for token in query_tokens:
        if token in haystack:
            score += 5 if len(token) >= 6 else 3

    profil_norm = _norm(profil) if profil else ""
    row_profil = _norm(row.get("profil_cible"))
    if profil_norm:
        if profil_norm in row_profil:
            score += 4
        elif row_profil in ("", "general"):
            score += 2

    for theme in themes or []:
        key = _norm(theme)
        terms = ENVIE_TERMS.get(key, [key])
        if any(_norm(t) in haystack for t in terms):
            score += 4

    return score


def rank_activities(
    loader: Any,
    rows: list[dict[str, str]],
    *,
    query: str | None = None,
    profil: str | None = None,
    themes: list[str] | None = None,
    limit: int = 20,
) -> list[tuple[int, dict[str, str]]]:
    tokens = tokenize_query(query or "")
    scored = [
        (
            score_activity(loader, row, query_tokens=tokens, profil=profil, themes=themes),
            row,
        )
        for row in rows
    ]
    scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    if tokens or profil or themes:
        positive = [(s, r) for s, r in scored if s > 0]
        pool = positive if positive else scored
    else:
        pool = scored
    return pool[:limit]
