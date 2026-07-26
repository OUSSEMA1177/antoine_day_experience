"""Politique destinations hors catalogue — réponses déterministes."""

from __future__ import annotations

import re

from agent.context_manager import is_qualification_message, is_tunnel_slot_message
from memory.memory_manager import memory_manager
from memory.quote_state import (
    _prune_wrong_destination,
    detect_destination_in_message,
    is_confirmation_message,
    session_has_activity_context,
)
from search.geo import (
    REGION_ALIASES,
    _has_catalog_question_hint,
    _norm,
    detect_country_query,
    find_catalog_destination_in_message,
    resolve_destination_name,
)
from services.data_loader import data_loader

ACTIVITY_SLOT_KEYS = (
    "activites_proposees",
    "activites_selectionnees",
    "activites_rejetees",
    "activites_discutees",
    "devis_ref",
)

GREETING_RE = re.compile(
    r"^(bonjour|salut|hello|hi|hey|coucou|merci|oui|non|ok|d['\u2019]accord|"
    r"parfait|super|top|yes|go|bienvenue)\s*[!.?]*$",
    re.I,
)
CONFIRMATION_LEXICON_RE = re.compile(
    r"\b(oui|ok|d['\u2019]?accord|parfait|super|top|bon|nickel|devis|"
    r"valid[eé]|confirm|please|svp|merci)\b",
    re.I,
)
HERE_RE = re.compile(r"\b(l[aà]\s*-?\s*b[aà]s|ici|sur\s+place)\b", re.I)
PLACE_TOKEN_RE = re.compile(r"^[\wàâäéèêëïîôùûüç'-]+$", re.I)
CONVERSATIONAL_QUESTION_RE = re.compile(
    r"\b(il\s*y\s*a|ily|y\s*a|est[- ]ce\s+qu|que|quoi|uniquement|seulement|"
    r"juste|autre|autres|avez|avons)\b",
    re.I,
)


def is_catalog_destination(name: str) -> bool:
    return resolve_destination_name(name.strip(), data_loader) is not None


def detect_catalog_destination_request(message: str) -> str | None:
    """Destination présente dans le catalogue (ex. Bali, Paris)."""
    return detect_destination_in_message(message)


def _clear_activity_slots(session_id: str) -> None:
    for key in ACTIVITY_SLOT_KEYS:
        memory_manager.clear_slot(session_id, key)


def activate_catalog_destination(session_id: str, name: str) -> str | None:
    """Enregistre une destination catalogue et efface tout blocage précédent."""
    dest_id = data_loader.resolve_destination_id(destination_name=name.strip())
    if not dest_id:
        return None
    row = data_loader.get_destination_by_id(dest_id) or {}
    resolved = (row.get("nom") or name.strip()).strip()
    if not resolved:
        return None
    slots = memory_manager.get_slots(session_id)
    previous = str(slots.get("destination", "") or "").strip()
    memory_manager.update_slots(session_id, destination=resolved)
    memory_manager.clear_slot(session_id, "destination_demandee")
    memory_manager.clear_slot(session_id, "region_interest")
    from agent.destination_confirm import clear_pending_city

    clear_pending_city(session_id)
    if previous and previous != resolved:
        _clear_activity_slots(session_id)
    _prune_wrong_destination(session_id, resolved)
    return resolved


def activate_unavailable_destination(session_id: str, place: str) -> None:
    """Mémorise une ville hors catalogue demandée.

    Non destructif : si une destination catalogue + une sélection sont en cours,
    on note seulement la demande (le refus est répondu) sans détruire la session.
    Ne fait rien si l'état interdit un changement de destination (ask devis, ajout).
    """
    from agent.conversation_state import allows_destination_change, derive_state

    slots = memory_manager.get_slots(session_id)
    if not allows_destination_change(derive_state(slots)):
        return
    label = _normalize_place_label(place)
    if not label:
        return
    dest = str(slots.get("destination", "") or "").strip()
    selected = str(slots.get("activites_selectionnees", "") or "").strip()
    if dest and is_catalog_destination(dest) and selected:
        # Session engagée : refuser le lieu sans effacer destination/sélection
        memory_manager.update_slots(session_id, destination_demandee=label)
        return
    memory_manager.clear_slot(session_id, "destination")
    memory_manager.update_slots(session_id, destination_demandee=label)
    _clear_activity_slots(session_id)


def destination_has_activities(name: str) -> bool:
    resolved = resolve_destination_name(name.strip(), data_loader)
    if not resolved:
        return False
    return bool(
        data_loader.search_activities(destination_name=resolved, limit=1)
    )


FRENCH_CITY_HINTS = {
    "toulouse", "lille", "nantes", "strasbourg", "rennes", "nice", "bordeaux",
    "lyon", "marseille", "montpellier", "grenoble",
}


def _normalize_place_label(text: str) -> str:
    cleaned = text.strip().rstrip("?.!,;:").strip()
    if not cleaned:
        return ""
    return cleaned.title()


def _has_place_like_spelling(word: str) -> bool:
    """Rejette le gibberish (ex. dfgbdfgdfg) — les toponymes ont des voyelles."""
    w = _norm(word)
    if len(w) <= 2:
        return True
    vowels = set("aeiouyàâäéèêëïîôùûü")
    if not any(c in vowels for c in w):
        return False
    consonant_run = 0
    for ch in w:
        if ch in vowels or not ch.isalpha():
            consonant_run = 0
        else:
            consonant_run += 1
            if consonant_run > 4:
                return False
    return True


def suggest_alternatives(requested: str, *, limit: int = 4) -> list[str]:
    """Destinations catalogue proches géographiquement (pas d'autres pays au hasard)."""
    needle = _norm(_normalize_place_label(requested))
    catalog_names = [
        (row.get("nom") or "").strip()
        for row in data_loader.load_destinations()
        if (row.get("nom") or "").strip()
    ]

    if needle in FRENCH_CITY_HINTS:
        picks = [
            nom
            for nom in catalog_names
            if any(
                _norm(kw) in _norm(nom)
                for kw in REGION_ALIASES["france"]["catalog_keywords"]
            )
        ]
        if picks:
            return picks[:limit]

    for region in REGION_ALIASES.values():
        aliases = [_norm(a) for a in region["aliases"]]
        keywords = [_norm(k) for k in region["catalog_keywords"]]
        region_match = any(
            needle in a or a in needle for a in aliases
        ) or any(needle in k or k in needle for k in keywords)
        if not region_match:
            continue
        picks = [
            nom
            for nom in catalog_names
            if any(_norm(kw) in _norm(nom) for kw in region["catalog_keywords"])
        ]
        if picks:
            return picks[:limit]

    return catalog_names[:limit]


# « non pas encore », « il n'a pas choisi » — destination inconnue / pas décidé
DESTINATION_NOT_CHOSEN_RE = re.compile(
    r"("
    r"pas\s+encore"
    r"|n['\u2019]?\s*a\s+pas\s+cho\w*"
    r"|na\s+pas\s+cho\w*"
    r"|pas\s+(?:encore\s+)?cho\w*"
    r"|aucune?\s+destination"
    r"|pas\s+de\s+destination"
    r"|pas\s+d['\u2019]?id[eé]e"
    r"|je\s+ne\s+sais\s+pas"
    r"|on\s+ne\s+sait\s+pas"
    r"|pas\s+(?:encore\s+)?d[eé]cid[eé]"
    r"|not\s+yet"
    r"|no\s+destination"
    r"|hasn'?t\s+chosen"
    r")",
    re.I,
)
SHORT_DESTINATION_NO_RE = re.compile(r"^(non|no)\s*[.!?]*$", re.I)


def is_destination_not_chosen_yet(message: str) -> bool:
    """Partenaire indique que la destination n'est pas (encore) connue."""
    text = (message or "").strip()
    if not text:
        return False
    if SHORT_DESTINATION_NO_RE.match(text):
        return True
    return bool(DESTINATION_NOT_CHOSEN_RE.search(text))


def build_destination_help_reply() -> str:
    """Aide 0 token quand le client n'a pas encore de destination."""
    catalog_names = [
        (row.get("nom") or "").strip()
        for row in data_loader.load_destinations()
        if (row.get("nom") or "").strip()
    ]
    preferred = ("Paris", "Bali", "Marrakech", "Rome", "Barcelone", "Istanbul")
    examples: list[str] = []
    catalog_norm = {_norm(n): n for n in catalog_names}
    for name in preferred:
        hit = catalog_norm.get(_norm(name))
        if hit and hit not in examples:
            examples.append(hit)
        if len(examples) >= 4:
            break
    if len(examples) < 3:
        for nom in catalog_names:
            if nom not in examples:
                examples.append(nom)
            if len(examples) >= 4:
                break
    alt_text = ", ".join(examples[:4]) if examples else "Paris, Bali, Marrakech, Rome"
    return (
        "Pas de souci. On peut avancer autrement : une région (Asie, Afrique, Europe…), "
        "un thème (plage, culture, gastronomie, montagne…), ou une ville du catalogue. "
        f"Exemples : {alt_text}. Qu'est-ce qui vous aide le plus ?"
    )


def build_destination_unavailable_reply(place: str) -> str:
    alts = suggest_alternatives(place)
    alt_text = ", ".join(alts) if alts else "Paris, Rome, Barcelone, Bali"
    return (
        f"Nous n'avons malheureusement pas {place} dans notre catalogue Day Experience "
        f"(ni d'activités associées). Je ne peux pas remplacer par un autre pays ou continent "
        f"sans votre accord. Souhaitez-vous explorer par exemple : {alt_text} ?"
    )


def build_no_activities_reply(place: str) -> str:
    alts = suggest_alternatives(place)
    alt_text = ", ".join(alts) if alts else "Paris, Rome, Barcelone"
    return (
        f"Aucune activité n'est disponible dans notre catalogue pour {place}. "
        f"Je ne peux pas vous proposer d'alternatives dans d'autres villes ou pays sans votre accord. "
        f"Souhaitez-vous choisir une autre destination ? Par exemple : {alt_text}."
    )


def _looks_like_place_name(text: str) -> bool:
    """Heuristique stricte : 1–2 tokens type ville, jamais une phrase conversationnelle."""
    cleaned = text.strip().rstrip("?.!,;:")
    if len(cleaned) < 3 or len(cleaned) > 40:
        return False
    if GREETING_RE.match(cleaned):
        return False
    if is_tunnel_slot_message(cleaned):
        return False
    if is_confirmation_message(cleaned):
        return False
    if is_qualification_message(cleaned):
        return False
    # Multi-mots avec lexique conversationnel → laisser le LLM
    if CONFIRMATION_LEXICON_RE.search(cleaned) and len(cleaned.split()) >= 2:
        return False
    if re.search(r"\d", cleaned):
        return False
    lower = _norm(cleaned)
    if _has_catalog_question_hint(text, lower) and (
        CONVERSATIONAL_QUESTION_RE.search(cleaned) or find_catalog_destination_in_message(text)
    ):
        return False
    words = cleaned.split()
    # Plus de 2 mots = presque jamais une ville seule → LLM
    if len(words) > 2:
        return False
    if len(words) > 1 and CONVERSATIONAL_QUESTION_RE.search(cleaned):
        return False
    # Mots fonctionnels français (pas des toponymes)
    stop = {
        "mix", "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou",
        "tout", "tous", "peu", "plus", "avec", "sans", "pour", "dans", "sur",
        "budget", "budjet", "euro", "euros", "activite", "activites",
        "augmentez", "augmenter", "augmente", "donnez", "donne", "moi",
    }
    if any(_norm(w) in stop for w in words):
        return False
    if not all(PLACE_TOKEN_RE.match(w) for w in words):
        return False
    return all(_has_place_like_spelling(w) for w in words)


def detect_unknown_place_request(message: str, session_id: str | None = None) -> str | None:
    """Ville/pays demandé mais absent du catalogue (ex. Toulouse, Monaco).

    Whitelist stricte :
    1. l'état de la session doit autoriser un changement de destination
       (jamais pendant ask devis / ajout d'activité — typo « ouii » ≠ lieu) ;
    2. AUCUNE intention métier connue ne doit matcher (`matches_known_intent`) ;
    3. le message doit ressembler à un toponyme isolé (1–2 tokens).

    Règle d'architecture : ne jamais inventer une destination depuis une phrase,
    ni élargir à un continent (Monaco ≠ Europe).
    """
    text = message.strip()
    if not text or HERE_RE.search(text):
        return None

    from agent.conversation_state import (
        allows_destination_change,
        derive_state,
        matches_known_intent,
    )

    # Gate 1 — état conversationnel
    if session_id:
        if not allows_destination_change(derive_state(memory_manager.get_slots(session_id))):
            return None

    # Gate 2 — intention métier connue → jamais un lieu
    if matches_known_intent(text):
        return None

    # Gate 3 — le message doit ressembler à un toponyme isolé
    # Ne stripper que « juste / seulement » — pas « les » (casse « les deux premiers »)
    cleaned = text.rstrip("?.!,;:").strip()
    cleaned = re.sub(
        r"^(?:juste|seulement|uniquement)\s+",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    if not _looks_like_place_name(cleaned):
        return None
    if is_catalog_destination(cleaned):
        return None

    return _normalize_place_label(cleaned)


def detect_gibberish_destination_attempt(message: str) -> bool:
    """Texte court non reconnu (ex. dfgbdfgdfg) — pas une vraie destination."""
    cleaned = message.strip().rstrip("?.!,;:")
    if not cleaned or len(cleaned) > 35:
        return False
    if is_confirmation_message(cleaned) or is_qualification_message(cleaned):
        return False
    if detect_country_query(message) or is_catalog_destination(cleaned):
        return False
    if detect_destination_in_message(message):
        return False
    words = cleaned.split()
    if len(words) > 3:
        return False
    return not all(_has_place_like_spelling(w) for w in words)


def refers_to_previous_place(message: str) -> bool:
    return bool(HERE_RE.search(message))


def invalid_destination_in_slots(slots: dict) -> str | None:
    dest = str(slots.get("destination", "") or "").strip()
    if dest and not is_catalog_destination(dest):
        return dest
    return None


def unavailable_place_from_slots(slots: dict) -> str | None:
    """Lieu hors catalogue mémorisé — ignoré si une destination catalogue est active."""
    dest = str(slots.get("destination", "") or "").strip()
    if dest and is_catalog_destination(dest):
        return None
    invalid = invalid_destination_in_slots(slots)
    if invalid:
        return invalid
    demandee = str(slots.get("destination_demandee", "") or "").strip()
    if demandee and not is_catalog_destination(demandee):
        return demandee
    return None
