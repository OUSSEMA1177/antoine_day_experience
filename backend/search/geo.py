"""Résolution géographique catalogue (villes/régions) — pas de NLU conversationnel."""

from __future__ import annotations

import re
import unicodedata

REGION_ALIASES: dict[str, dict[str, list[str]]] = {
    "maroc": {
        "aliases": ["maroc", "morocco", "marocain", "marocaine"],
        "catalog_keywords": [
            "marrakech", "agafay", "essaouira", "merzouga", "ouarzazate", "ouzoud", "ourika", "zagora",
        ],
    },
    "france": {
        "aliases": ["france", "francais", "français"],
        "catalog_keywords": ["paris", "lyon", "marseille", "nice", "bordeaux"],
    },
    "espagne": {
        "aliases": ["espagne", "spain", "espagnol"],
        "catalog_keywords": ["barcelone", "madrid", "seville", "séville"],
    },
    "italie": {
        "aliases": ["italie", "italy", "italien"],
        "catalog_keywords": ["rome", "milan", "venise", "florence", "duomo"],
    },
    "egypte": {
        "aliases": ["egypte", "egypt", "égypte"],
        "catalog_keywords": ["caire", "louxor"],
    },
    "grece": {
        "aliases": ["grece", "grèce", "greece", "grec"],
        "catalog_keywords": ["athenes", "athènes", "santorin"],
    },
    "emirats": {
        "aliases": ["emirats", "émirats", "uae", "dubai"],
        "catalog_keywords": ["dubai", "dubaï"],
    },
    "suisse": {
        "aliases": ["suisse", "switzerland", "swiss", "alpes suisses"],
        "catalog_keywords": ["milan", "lugano", "bernina", "st moritz"],
    },
}

LANDMARK_QUERIES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"tour\s+eiffel|eiffel", re.I), "Paris", "tour eiffel"),
    (re.compile(r"\blouvre\b", re.I), "Paris", "louvre"),
    (re.compile(r"versailles", re.I), "Paris", "versailles"),
    (re.compile(r"sagrada|gaudi", re.I), "Barcelone", "sagrada"),
    (re.compile(r"\bcolisee\b|\bcolisée\b", re.I), "Rome", "colisée"),
    (re.compile(r"burj", re.I), "Dubaï", "burj"),
    (re.compile(r"pyramide", re.I), "Le Caire", "pyramide"),
]


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def expand_to_keywords(place: str) -> list[str]:
    needle = _norm(place)
    if not needle:
        return []
    keywords: list[str] = [place.strip()]
    for region in REGION_ALIASES.values():
        aliases = [_norm(a) for a in region["aliases"]]
        if needle in aliases or any(needle in a or a in needle for a in aliases):
            keywords.extend(region["catalog_keywords"])
            break
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        key = _norm(kw)
        if key and key not in seen:
            seen.add(key)
            unique.append(kw)
    return unique


def resolve_destination_name(name: str, loader) -> str | None:
    """Retourne le nom catalogue si la destination existe."""
    if loader.resolve_destination_id(destination_name=name):
        return name.strip()
    for kw in expand_to_keywords(name):
        if loader.resolve_destination_id(destination_name=kw):
            return kw
    return None


def detect_landmark(text: str) -> tuple[str, str] | None:
    for pattern, destination, query in LANDMARK_QUERIES:
        if pattern.search(text):
            return destination, query
    return None
