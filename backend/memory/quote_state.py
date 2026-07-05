"""État devis session — activités proposées, sélection, bouton PDF."""

from __future__ import annotations

import re
import unicodedata

from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from search.geo import resolve_destination_name
from services.data_loader import data_loader

REJECT_RE = re.compile(
    r"(pas\s+aime|n['\u2019]?aime\s+pas|pas\s+bien|retir|enlev|supprim|"
    r"met\s+de\s+c[oô]t[eé]|c['\u2019]est\s+non|je\s+n['\u2019]?aime\s+pas)",
    re.I,
)
SELECT_RE = re.compile(
    r"(j['\u2019]?ai\s+aime|j\s+ai\s+aime|je\s+choisis|je\s+prends|je\s+veux|"
    r"cette\s+option|celle[- ]l[aà]|valid|parfait|super|top)",
    re.I,
)
QUOTE_CONFIRM_RE = re.compile(
    r"^(oui|ok|d['\u2019]accord|dacord|daccord|valid[eé]?|parfait|"
    r"top|super|go|yes|pr[eê]t)\b",
    re.I,
)
SELECT_ALL_RE = re.compile(
    r"(toutes?\s+les?\s+activit|tous?\s+les?\s+activit|activit.*discut|"
    r"les\s+\d+\s+activit|qu['\u2019]?on\s+a\s+(?:pas\s+)?discut|"
    r"tout\s+inclure|inclure\s+tout)",
    re.I,
)
NUMBERED_ITEM_RE = re.compile(r"(?:^|\s)(\d+)\.\s+")
TITLE_MATCH_MIN_SCORE = 20


def _numbered_chunks(text: str) -> list[str]:
    matches = list(NUMBERED_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []
    chunks: list[str] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip(" .")
        if chunk:
            chunks.append(chunk)
    return chunks


def _count_numbered_items(text: str) -> int:
    return len(NUMBERED_ITEM_RE.findall(text))


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def _parse_id_list(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if not raw:
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _join_ids(ids: list[str]) -> str:
    return ",".join(dict.fromkeys(ids))


def _destination_id(name: str | None) -> str | None:
    if not name:
        return None
    return data_loader.resolve_destination_id(destination_name=name)


def detect_destination_in_message(message: str) -> str | None:
    """Extrait une destination catalogue depuis le message (ex. « j'ai aimé Zanzibar »)."""
    lower = _norm(message)
    if not lower:
        return None

    best: tuple[int, str] | None = None
    for row in data_loader.load_destinations():
        nom = (row.get("nom") or "").strip()
        if not nom:
            continue
        key = _norm(nom)
        if len(key) < 3:
            continue
        if key in lower:
            score = len(key)
            if best is None or score > best[0]:
                best = (score, nom)

    if best:
        resolved = resolve_destination_name(best[1], data_loader)
        return resolved or best[1]

    for token in re.findall(r"[\wàâäéèêëïîôùûüç'-]+", message, re.I):
        if len(token) < 4:
            continue
        resolved = resolve_destination_name(token, data_loader)
        if resolved:
            return resolved
    return None


def _filter_rows_by_destination(
    rows: list[dict[str, str]],
    destination: str | None,
) -> list[dict[str, str]]:
    if not destination:
        return rows
    dest_id = _destination_id(destination)
    if not dest_id:
        return rows
    return [r for r in rows if str(r.get("destination_id", "")).strip() == dest_id]


def _title_tokens(titre: str) -> set[str]:
    stop = {
        "de", "la", "le", "les", "du", "des", "et", "en", "au", "à", "a", "d", "l",
        "une", "un", "sur", "pour", "avec", "the", "visite", "journée", "journee",
    }
    tokens = set()
    for word in re.findall(r"[\wàâäéèêëïîôùûüç'-]+", titre, re.I):
        w = _norm(word)
        if len(w) >= 4 and w not in stop:
            tokens.add(w)
    return tokens


def _score_title_match(titre: str, text: str) -> int:
    titre_norm = _norm(re.sub(r"\*+", "", titre))
    text_norm = _norm(re.sub(r"\*+", "", text))
    if not titre_norm or not text_norm:
        return 0
    if titre_norm in text_norm:
        return len(titre_norm) + 100
    tokens = _title_tokens(titre)
    if not tokens:
        return 0
    hits = sum(1 for t in tokens if t in text_norm)
    if hits >= 4:
        return hits * 20
    if hits >= 3:
        return hits * 15
    if hits >= 2:
        return hits * 10
    return 0


def _text_chunks(text: str) -> list[str]:
    chunks = [text]
    parts = re.split(r"(?:^|\n)\s*\d+\.\s*", text)
    chunks.extend(p.strip() for p in parts if p.strip())
    return chunks


def match_activities_by_titles(
    text: str,
    destination: str | None,
    *,
    rejected: set[str] | None = None,
    min_score: int = TITLE_MATCH_MIN_SCORE,
) -> list[str]:
    """Associe des titres cités dans le texte aux activités catalogue d'une destination."""
    rejected = rejected or set()
    if not text or not destination:
        return []
    dest_id = _destination_id(destination)
    if not dest_id:
        return []

    catalog: list[tuple[str, dict[str, str]]] = []
    for row in data_loader.load_activities():
        if str(row.get("destination_id", "")).strip() != dest_id:
            continue
        aid = str(row.get("id", "")).strip()
        if aid and aid not in rejected:
            catalog.append((aid, row))

    if _count_numbered_items(text) >= 2:
        chunks = _numbered_chunks(text)
        picked: list[str] = []
        used: set[str] = set()
        for chunk in chunks:
            best_id: str | None = None
            best_score = min_score - 1
            for aid, row in catalog:
                if aid in used:
                    continue
                score = _score_title_match(row.get("titre", "") or "", chunk)
                if score > best_score:
                    best_score = score
                    best_id = aid
            if best_id:
                picked.append(best_id)
                used.add(best_id)
        if picked:
            return picked

    scored: dict[str, int] = {}
    for aid, row in catalog:
        titre = row.get("titre", "") or ""
        best = max((_score_title_match(titre, chunk) for chunk in _text_chunks(text)), default=0)
        if best >= min_score:
            scored[aid] = best

    ordered = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return [aid for aid, _ in ordered]


def _known_activity_rows(session_id: str) -> list[tuple[str, dict[str, str]]]:
    slots = memory_manager.get_slots(session_id)
    ids: set[str] = set()
    for key in ("activites_discutees", "activites_proposees", "activites_selectionnees"):
        ids.update(_parse_id_list(slots.get(key)))
    rows: list[tuple[str, dict[str, str]]] = []
    for aid in ids:
        row = data_loader.get_activity_by_id(aid)
        if row:
            rows.append((aid, row))
    return rows


def _match_activities_in_text(text: str, candidates: list[tuple[str, dict[str, str]]]) -> list[str]:
    if not text or not candidates:
        return []
    matched: list[tuple[int, str]] = []
    for aid, row in candidates:
        titre = row.get("titre", "") or ""
        best = max((_score_title_match(titre, chunk) for chunk in _text_chunks(text)), default=0)
        if best >= TITLE_MATCH_MIN_SCORE:
            matched.append((best, aid))
    matched.sort(key=lambda x: x[0], reverse=True)
    return [aid for _, aid in matched]


def _last_assistant_message(session_id: str) -> str:
    history = conversation_manager.get_history(session_id, limit=10)
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            return str(msg.get("content", "") or "")
    return ""


def _conversation_text(session_id: str, limit: int = 30) -> str:
    parts: list[str] = []
    for msg in conversation_manager.get_history(session_id, limit=limit):
        parts.append(str(msg.get("content", "") or ""))
    return "\n".join(parts)


def _merge_discussed(session_id: str, new_ids: list[str]) -> None:
    if not new_ids:
        return
    slots = memory_manager.get_slots(session_id)
    discussed = _parse_id_list(slots.get("activites_discutees"))
    merged = _join_ids(discussed + new_ids)
    memory_manager.update_slots(session_id, activites_discutees=merged)


def record_discussed_activities_from_text(session_id: str, text: str) -> list[str]:
    """Enregistre les activités mentionnées dans un message (souvent réponse bot)."""
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    ids = match_activities_by_titles(text, destination, rejected=rejected)
    if ids:
        _merge_discussed(session_id, ids)
    return ids


def sync_discussed_from_history(session_id: str) -> None:
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    if not destination:
        return
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    collected: list[str] = []
    for msg in conversation_manager.get_history(session_id, limit=30):
        if msg.get("role") != "assistant":
            continue
        text = str(msg.get("content", "") or "")
        if not text.strip():
            continue
        if _count_numbered_items(text) >= 2:
            collected.extend(match_activities_by_titles(text, destination, rejected=rejected))
        else:
            ids = match_activities_by_titles(text, destination, rejected=rejected, min_score=35)
            collected.extend(ids[:4])
    if collected:
        _merge_discussed(session_id, collected)


def _prune_wrong_destination(session_id: str, destination: str) -> None:
    dest_id = _destination_id(destination)
    if not dest_id:
        return
    slots = memory_manager.get_slots(session_id)
    for key in (
        "activites_proposees",
        "activites_selectionnees",
        "activites_rejetees",
        "activites_discutees",
    ):
        ids = _parse_id_list(slots.get(key))
        kept = []
        for aid in ids:
            row = data_loader.get_activity_by_id(aid)
            if row and str(row.get("destination_id", "")).strip() == dest_id:
                kept.append(aid)
        if kept:
            memory_manager.update_slots(session_id, **{key: _join_ids(kept)})
        else:
            memory_manager.clear_slot(session_id, key)


def sync_activity_feedback_from_message(session_id: str, message: str) -> None:
    """Met à jour sélection / rejet depuis le message utilisateur."""
    sync_discussed_from_history(session_id)
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    selected = _parse_id_list(slots.get("activites_selectionnees"))
    proposed = _parse_id_list(slots.get("activites_proposees"))
    discussed = _parse_id_list(slots.get("activites_discutees"))
    candidates = _known_activity_rows(session_id)

    numbered_count = _count_numbered_items(message)
    catalog_picks = match_activities_by_titles(message, destination, rejected=rejected)

    if SELECT_ALL_RE.search(message):
        pool = discussed or proposed
        picks = [x for x in pool if x not in rejected]
        if picks:
            memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))
        return

    if numbered_count >= 2 and catalog_picks:
        memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(catalog_picks))
        return

    if REJECT_RE.search(message):
        reject_ids = _match_activities_in_text(message, candidates)
        for aid in reject_ids:
            rejected.add(aid)
            selected = [x for x in selected if x != aid]
            proposed = [x for x in proposed if x != aid]
            discussed = [x for x in discussed if x != aid]
        if reject_ids:
            memory_manager.update_slots(
                session_id,
                activites_rejetees=_join_ids(list(rejected)),
                activites_selectionnees=_join_ids(selected),
                activites_proposees=_join_ids(proposed),
                activites_discutees=_join_ids(discussed),
            )
        return

    if SELECT_RE.search(message):
        pick = _match_activities_in_text(message, candidates)
        if not pick:
            last = _last_assistant_message(session_id)
            pick = _match_activities_in_text(last, candidates)
        if not pick:
            last = _last_assistant_message(session_id)
            pick = match_activities_by_titles(last, destination, rejected=rejected)[:1]
        if pick and re.search(r"\b(ca|ça|celle)\b", message, re.I):
            pick = pick[:1]
        if pick:
            for aid in pick:
                if aid not in rejected and aid not in selected:
                    selected.append(aid)
            memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(selected))
        return

    if re.search(r"c['\u2019]est\s+bon|cest\s+bon", message, re.I) and "?" not in message:
        if not re.search(r"\bautre", message, re.I):
            pool = discussed or proposed
            picks = [x for x in pool if x not in rejected]
            if picks and not selected:
                memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))


def is_quote_confirmation(message: str) -> bool:
    text = message.strip()
    if not text or len(text) > 60:
        return False
    if "?" in text or re.search(r"\b(autre|non|pas)\b", text, re.I):
        return False
    if REJECT_RE.search(text) or SELECT_RE.search(text):
        return False
    if SELECT_ALL_RE.search(text):
        return False
    if _count_numbered_items(text) >= 2:
        return False
    if re.search(r"\b(activit|option|choisis|prends)\b", text, re.I):
        return False
    return bool(QUOTE_CONFIRM_RE.search(text))


def pick_proposed_activities(
    activities: list[dict[str, str]],
    slots: dict[str, str | list[str]],
    *,
    limit: int = 4,
) -> list[dict[str, str]]:
    """Top activités catalogue, filtrées par destination et préférence."""
    destination = str(slots.get("destination", "") or "").strip()
    rows = _filter_rows_by_destination(list(activities), destination or None)

    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    rows = [r for r in rows if str(r.get("id", "")).strip() not in rejected]

    pref = str(slots.get("preference", "") or "").casefold()
    if "priv" in pref:
        private = [
            r
            for r in rows
            if "priv" in (r.get("titre", "") or "").casefold()
            or r.get("profil_cible", "") in ("solo", "couple")
        ]
        if private:
            seen = {r.get("id") for r in private}
            rows = private + [r for r in rows if r.get("id") not in seen]
    return rows[:limit]


def save_proposed_activities(session_id: str, activities: list[dict[str, str]]) -> list[str]:
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    filtered = _filter_rows_by_destination(activities, destination or None)
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    new_ids = [
        str(r.get("id", "")).strip()
        for r in filtered
        if r.get("id") and str(r.get("id", "")).strip() not in rejected
    ]
    if not new_ids:
        return []

    existing = _parse_id_list(slots.get("activites_proposees"))
    discussed = _parse_id_list(slots.get("activites_discutees"))
    memory_manager.update_slots(
        session_id,
        activites_proposees=_join_ids(existing + new_ids),
        activites_discutees=_join_ids(discussed + new_ids),
    )
    return new_ids


def confirm_proposed_activities(session_id: str) -> list[str]:
    """Confirme les activités déjà sélectionnées, ou la proposition si une seule."""
    slots = memory_manager.get_slots(session_id)
    proposed = _parse_id_list(slots.get("activites_proposees"))
    selected = _parse_id_list(slots.get("activites_selectionnees"))
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))

    if selected:
        ids = [x for x in selected if x not in rejected]
    elif len(proposed) == 1:
        ids = [proposed[0]] if proposed[0] not in rejected else []
    else:
        ids = []

    if ids:
        memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(ids))
    return ids


def activity_previews(activity_ids: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for aid in activity_ids:
        row = data_loader.get_activity_by_id(aid)
        if not row:
            continue
        items.append(
            {
                "id": row.get("id", ""),
                "titre": row.get("titre", ""),
                "prix_net": row.get("prix", "") or row.get("prix_public", ""),
                "duree": row.get("duree", "") or "—",
            }
        )
    return items


def compute_quote_state(session_id: str) -> dict:
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    profil = str(slots.get("profil_voyageur", "") or "").strip()
    nom_agence = str(slots.get("nom_agence", "") or "").strip()
    partner_id = str(slots.get("partner_id", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))

    if not nom_agence and partner_id:
        partner = data_loader.get_partner_by_id(partner_id)
        if partner:
            nom_agence = partner.get("nom_agence") or partner.get("nom_complet") or ""

    selected_ids = [
        aid for aid in _parse_id_list(slots.get("activites_selectionnees")) if aid not in rejected
    ]

    if destination:
        dest_id = _destination_id(destination)
        if dest_id:
            filtered = []
            for aid in selected_ids:
                row = data_loader.get_activity_by_id(aid)
                if row and str(row.get("destination_id", "")).strip() == dest_id:
                    filtered.append(aid)
            selected_ids = filtered

    activities = activity_previews(selected_ids)
    missing: list[str] = []
    if not destination:
        missing.append("destination")
    if not profil:
        missing.append("profil")
    if not activities:
        missing.append("activites")
    if not nom_agence and not partner_id:
        missing.append("agence")

    quote_ready = not missing

    return {
        "quote_ready": quote_ready,
        "missing": missing,
        "destination": destination or None,
        "nom_agence": nom_agence or None,
        "activity_ids": selected_ids,
        "activities": activities,
    }
