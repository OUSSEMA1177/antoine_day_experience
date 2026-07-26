"""Taxonomie thématique B2B — plage, montagne, forêt, etc. + matching mot entier."""

from __future__ import annotations

import re
import unicodedata

# Alias utilisateur / NLU → clé canonique
THEME_ALIASES: dict[str, str] = {
    "plage": "mer",
    "plages": "mer",
    "beach": "mer",
    "beaches": "mer",
    "ocean": "mer",
    "océan": "mer",
    "oceans": "mer",
    "mer": "mer",
    "mers": "mer",
    "cote": "mer",
    "côte": "mer",
    "cotes": "mer",
    "côtes": "mer",
    "balneaire": "mer",
    "balnéaire": "mer",
    "lagon": "mer",
    "lagons": "mer",
    "snorkeling": "mer",
    "plongee": "mer",
    "plongée": "mer",
    "montagne": "montagne",
    "montagnes": "montagne",
    "mountain": "montagne",
    "mountains": "montagne",
    "alpes": "montagne",
    "volcan": "montagne",
    "volcans": "montagne",
    "randonnee": "montagne",
    "randonnée": "montagne",
    "trek": "montagne",
    "trekking": "montagne",
    "foret": "foret",
    "forêt": "foret",
    "forets": "foret",
    "forêts": "foret",
    "forest": "foret",
    "jungle": "foret",
    "jungles": "foret",
    "tropicale": "foret",
    "tropical": "foret",
    "nature": "nature",
    "parc": "nature",
    "safari": "nature",
    "cascade": "nature",
    "cascades": "nature",
    "sahara": "sahara",
    "desert": "sahara",
    "désert": "sahara",
    "dune": "sahara",
    "dunes": "sahara",
    "aventure": "aventure",
    "culture": "culture",
    "culturel": "culture",
    "gastronomie": "gastronomie",
    "gastro": "gastronomie",
    "cuisine": "gastronomie",
    "detente": "détente",
    "détente": "détente",
    "relax": "détente",
    "spa": "détente",
    "wellness": "détente",
    "croisiere": "croisiere",
    "croisière": "croisiere",
    "cruise": "croisiere",
    "bateau": "croisiere",
}

# Termes de recherche / scoring par thème (catalogue mondial, pas seulement Maroc)
ENVIE_TERMS: dict[str, list[str]] = {
    "mer": [
        "plage",
        "plages",
        "lagon",
        "lagons",
        "snorkeling",
        "snorkel",
        "plongée",
        "plongee",
        "beach",
        "sandbank",
        "seminyak",
        "paje",
        "nakupenda",
        "anakena",
        "comporta",
        "jumeirah",
        "comino",
        "mtende",
        "balnéaire",
        "balneaire",
        "océan",
        "ocean",
        "bord de mer",
        "water sports",
        "watersports",
    ],
    "montagne": [
        "montagne",
        "montagnes",
        "alpes",
        "atlas",
        "volcan",
        "volcans",
        "fuji",
        "hajar",
        "kintamani",
        "torres del paine",
        "vésuve",
        "vesuve",
        "randonnée",
        "randonnee",
        "trek",
        "trekking",
        "mountain",
        "grand canyon",
        "mont fuji",
    ],
    "foret": [
        "forêt",
        "foret",
        "forest",
        "jungle",
        "tijuca",
        "jozani",
        "tropicale",
        "tropical",
        "patagonie",
    ],
    "nature": [
        "nature",
        "cascade",
        "cascades",
        "parc national",
        "safari",
        "kruger",
        "ouzoud",
        "iguacu",
        "iguazú",
        "iguazu",
        "ourika",
        "vallée",
        "vallee",
    ],
    "sahara": [
        "sahara",
        "désert",
        "desert",
        "merzouga",
        "agafay",
        "dune",
        "dunes",
        "chameau",
        "dromadaire",
        "campement",
    ],
    "aventure": [
        "quad",
        "4x4",
        "buggy",
        "montgolfière",
        "montgolfiere",
        "safari",
        "rafting",
        "parachute",
        "tyrolienne",
        "sensations",
        "aventure",
    ],
    "culture": [
        "médina",
        "medina",
        "souk",
        "palais",
        "musée",
        "musee",
        "monument",
        "temple",
        "culture",
        "historique",
        "patrimoine",
    ],
    "gastronomie": [
        "dîner",
        "diner",
        "restaurant",
        "gastronom",
        "dégustation",
        "degustation",
        "cuisine",
        "repas",
        "food",
    ],
    "détente": [
        "spa",
        "massage",
        "jardin",
        "relax",
        "détente",
        "detente",
        "wellness",
        "bain de fleurs",
    ],
    "croisiere": [
        "croisière",
        "croisiere",
        "cruise",
        "catamaran",
        "bateau",
        "voilier",
        "ferry",
    ],
}

VALID_THEMES = frozenset(ENVIE_TERMS.keys())

THEME_LABELS_FR: dict[str, str] = {
    "mer": "plage / mer",
    "montagne": "montagne",
    "foret": "forêt / jungle",
    "nature": "nature",
    "sahara": "désert / sahara",
    "aventure": "aventure",
    "culture": "culture",
    "gastronomie": "gastronomie",
    "détente": "détente",
    "croisiere": "croisière",
}

# Patterns de détection dans un message libre
_THEME_DETECT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("mer", re.compile(
        r"\b(plages?|beach(es)?|mers?|oc[eé]ans?|c[oô]tes?|lagons?|"
        r"snorkeling|plong[eé]e|baln[eé]aire|bord\s+de\s+mer)\b",
        re.I,
    )),
    ("montagne", re.compile(
        r"\b(montagnes?|mountains?|alpes|volcans?|randonn[eé]e|treks?|trekking)\b",
        re.I,
    )),
    ("foret", re.compile(
        r"\b(for[eê]ts?|forests?|jungles?|tropicale?s?)\b",
        re.I,
    )),
    ("nature", re.compile(
        r"\b(nature|cascades?|parcs?\s+nationaux?|safari)\b",
        re.I,
    )),
    ("sahara", re.compile(r"\b(sahara|d[eé]serts?|dunes?)\b", re.I)),
    ("aventure", re.compile(r"\baventure\b", re.I)),
    ("culture", re.compile(r"\b(culture|culturel)\b", re.I)),
    ("gastronomie", re.compile(r"\b(gastronomie|gastro|cuisine)\b", re.I)),
    ("détente", re.compile(r"\b(d[eé]tente|relax|spa|wellness)\b", re.I)),
    ("croisiere", re.compile(r"\b(croisi[eè]res?|cruises?|catamaran)\b", re.I)),
]


def _norm(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def canonicalize_theme(name: str | None) -> str | None:
    """Normalise un libellé envie/thème vers une clé ENVIE_TERMS."""
    if not name:
        return None
    key = _norm(name).replace("é", "e")
    # Ré-essayer avec accents d'origine via aliases
    raw = _norm(name)
    if raw in THEME_ALIASES:
        return THEME_ALIASES[raw]
    if key in THEME_ALIASES:
        return THEME_ALIASES[key]
    if raw in VALID_THEMES:
        return raw
    if name.strip() in VALID_THEMES:
        return name.strip()
    # détente avec accent
    if raw in ("detente", "détente"):
        return "détente"
    return None


def term_in_text(term: str, haystack: str) -> bool:
    """
    Matching mot entier pour termes courts.
    « mer » matche « la mer » / « étoiles de mer », pas « Merzouga ».
    """
    t = _norm(term)
    h = _norm(haystack)
    if not t or not h:
        return False
    if " " in t:
        return t in h
    if len(t) >= 5:
        return t in h
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", h))


def detect_themes_from_text(text: str | None) -> list[str]:
    """Détecte les thèmes B2B dans un message libre."""
    if not text or not text.strip():
        return []
    found: list[str] = []
    for theme, pattern in _THEME_DETECT_PATTERNS:
        if pattern.search(text) and theme not in found:
            found.append(theme)
    return found


def expand_theme_search_terms(
    raw_query: str | None = None,
    themes: list[str] | None = None,
) -> list[str]:
    """Termes à utiliser pour constituer le pool catalogue (sans faux positifs courts)."""
    terms: list[str] = []
    canon_themes: list[str] = []

    for theme in themes or []:
        key = canonicalize_theme(theme) or _norm(theme)
        if key and key not in canon_themes:
            canon_themes.append(key)
        terms.extend(ENVIE_TERMS.get(key, [theme]))

    detected = detect_themes_from_text(raw_query or "")
    for theme in detected:
        if theme not in canon_themes:
            canon_themes.append(theme)
        terms.extend(ENVIE_TERMS.get(theme, []))

    # Ne jamais chercher le token « mer » seul (Merzouga) — déjà retiré de ENVIE_TERMS["mer"]
    # Dédupliquer en gardant l'ordre
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = _norm(term)
        if key and key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def theme_matches_activity(haystack: str, theme: str) -> bool:
    key = canonicalize_theme(theme) or _norm(theme)
    terms = ENVIE_TERMS.get(key, [theme])
    return any(term_in_text(t, haystack) for t in terms)


def themes_label(themes: list[str]) -> str:
    labels = [THEME_LABELS_FR.get(canonicalize_theme(t) or t, t) for t in themes]
    return ", ".join(labels)
