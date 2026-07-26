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
    r"met\s+de\s+c[oô]t[eé]|c['\u2019]est\s+non|je\s+n['\u2019]?aime\s+pas|"
    r"je\s+veux\s+pas|veux\s+pas|d[eé]sol[eé].{0,40}pas)",
    re.I,
)
REMOVE_SELECTION_RE = re.compile(
    r"(?:"
    r"d[eé]sol[eé]|"
    r"je\s+veux\s+pas|"
    r"veux\s+pas|"
    r"pas\s+(?:la|le|les)\b|"
    r"enlever|retirer|supprim|"
    r"sans\s+(?:la|le)\b|"
    r"sauf\s+(?:la|le)\b|"
    r"plut[oô]t\s+pas"
    r")",
    re.I,
)
WANTS_ANOTHER_ACTIVITY_RE = re.compile(
    r"(?:"
    r"autre\s+activit|"
    r"autres?\s+activit|"
    r"d['\u2019]?\s*autres?\s+activit|"
    r"une\s+autre(?:\s+activit)?|"
    r"encore\s+(?:une\s+)?(?:autre\s+)?activit|"
    r"en\s+plus|"
    r"avec\s+(?:elle|celle[- ]?ci|ça|ca)\b|"
    r"ajouter\s+(?:une\s+)?autre|"
    r"je\s+veux\s+(?:encore\s+)?une\s+autre|"
    r"avez[- ]vous\s+(?:d['\u2019]?\s*)?autres?\s+activit|"
    r"vous\s+avez\s+(?:d['\u2019]?\s*)?autres?\s+activit|"
    r"dautres?\s+activit|"
    r"dautr+\w*\s+a?\s*ctivit|"  # typos : dautrre a ctivite
    r"plus\s+d['\u2019]?\s*(?:autres?\s+)?activit"
    r")",
    re.I,
)
# Remplacer la liste / voir autre chose — ≠ « ajouter une activité »
WANTS_OTHER_OPTIONS_RE = re.compile(
    r"(?:"
    r"autres?\s+options?|"
    r"autre\s+option|"
    r"d['\u2019]?\s*autres?\s+options?|"
    r"autres?\s+propositions?|"
    r"autre\s+(?:liste|choix|proposition)|"
    r"autres?\s+choix|"
    r"montre[rz]?\s+(?:moi\s+)?(?:autre|d['\u2019]autres?)|"
    r"propose[rz]?\s+(?:moi\s+)?(?:autre|d['\u2019]autres?)|"
    r"autre\s+chose(?!\s+a\s+ajouter)"
    r")",
    re.I,
)
# Refus de la liste présentée (sans avoir choisi d'indices)
REJECT_PRESENTED_LIST_RE = re.compile(
    r"(?:"
    r"j['\u2019]?\s*ai\s+pas\s+aim[eé]|"
    r"(?:je\s+)?n['\u2019]?aime\s+pas|"
    r"j['\u2019]?aime\s+pas|"
    r"pas\s+aim[eé](?:\s+(?:du\s+tout|vraiment))?$|"
    r"rien\s+ne\s+(?:me\s+)?pla[iî]t|"
    r"aucune?\s+(?:ne\s+)?(?:me\s+)?pla[iî]t|"
    r"pas\s+(?:ces|les)\s+activit|"
    r"pas\s+int[eé]ress[eé]"
    r")",
    re.I,
)

# « 1 est ok », « 2 ok », « la 1 est bonne »
INDEX_OK_RE = re.compile(
    r"(?<![\d,.])([1-9]|10)\s*(?:est\s+)?(?:ok|bonne?|parfait|bien|nickel)\b",
    re.I,
)
ADD_THIS_ACTIVITY_RE = re.compile(
    r"(?:"
    r"ajoute(?:r|z)?\s+(?:ceci|cela|ça|ca|celle|cette|la|le)\b|"
    r"oui\s*,?\s*ajoute|"
    r"ajoute(?:r|z)?\s+(?:aussi|avec)|"
    r"je\s+(?:la\s+|le\s+)?(?:prends?|garde)\s+(?:aussi|avec|celle)|"
    r"ajoute(?:r|z)?\s+(?:la|le)\s+(?:\d+|premier|premiere|deuxieme|troisieme)|"
    # « ajouter 6 », « ajoute la 6 », « ajouter l'activité 6 », « ajouter lactivite 6 »
    r"(?:je\s+veux\s+)?ajoute(?:r|z)?\s+"
    r"(?:(?:l['\u2019]?|la\s+|le\s+)?activit[eé]s?\s+|lactivit[eé]s?\s+)?"
    r"(?:(?:la|le)\s+)?"
    r"(?:\d+|premier|premiere|deuxieme|troisieme|quatrieme|cinquieme|sixieme)\b"
    r")",
    re.I,
)
SELECT_RE = re.compile(
    r"(j['\u2019]?ai\s+aime|j\s+ai\s+aime|je\s+choisis|je\s+prends|"
    r"je\s+veux\s+(?!le\s+devis|un\s+devis|mon\s+devis|pas)|"
    r"cette\s+option|celle[- ]l[aà])",
    re.I,
)
QUOTE_CONFIRM_RE = re.compile(
    r"^(?:oui+|ouais|ouai|ui+|ok|d['\u2019]accord|dacord|daccord|valid[eé]?|parfait|"
    r"top|super|go|yes|pr[eê]t|wesh\s+ok)"
    r"(?:\s*[!.]*)?$",
    re.I,
)
# « le devis », « devis pdf », « génère le devis »
DEVIS_REQUEST_RE = re.compile(
    r"(?:"
    r"^(?:le\s+)?devis\b|"
    r"\b(?:g[eé]n[eé]r(?:e|er|ez)|donne[rz]?|pr[eé]par(?:e|er|ez)|envoyer?)\s+(?:le\s+)?devis\b|"
    r"\bdevis\s+(?:pdf|white\s*label|s['\u2019]?il|svp|please)\b"
    r")",
    re.I,
)
ACTIVITY_OK_RE = re.compile(
    r"(c\s+est\s+bon|c['\u2019]est\s+bon|c\s+est\s+parfait|c['\u2019]est\s+parfait|"
    r"ça\s+me\s+va|ca\s+me\s+va|c\s+est\s+nickel|c['\u2019]est\s+nickel|"
    r"j['\u2019]?ai\s+dit.{0,60}(bon|valid|oui|parfait)|"
    r"^oui+\b.{0,50}(bon|parfait|valid|devis|nickel)|"
    r"^ok\b|"
    r"(je\s+veux|donne[rz]?|donner|envoyer|g[eé]n[eé]rer).{0,20}\bdevis\b|"
    r"\bdevis\b.{0,20}(pdf|please|s['\u2019]?il|svp))",
    re.I,
)
SELECT_ALL_RE = re.compile(
    r"(toutes?\s+les?\s+activit|tous?\s+les?\s+activit|activit.*discut|"
    r"les\s+\d+\s+activit|"
    r"qu['\u2019]?on\s+a\s+(?:pas\s+)?discut|"
    r"tout\s+inclure|inclure\s+tout|je\s+prends\s+tout|prendre\s+tout|"
    r"\btoutes?\b(?:\s+c['\u2019]?est\s+bon)?|"
    r"\btous\b(?:\s+c['\u2019]?est\s+(?:bon|parfait|ok))?|"
    r"devis\s+(?:des?\s+|avec\s+les\s+)?(?:trois|\d+)\s*activit|"
    r"(?:je\s+)?veux\s+les\s+(trois|deux|quatre|\d+)(?:\s+activit)?\b|"
    r"non\s+je\s+veux\s+les\s+(trois|deux|quatre)(?:\s+activit)?\b)",
    re.I,
)
# « les deux » / « les 3 » sans ordinaux nommés → N premières de la présentation
LES_COUNT_RE = re.compile(
    r"\bles\s+(deux|trois|quatre|cinq|six|[1-6])\b",
    re.I,
)
LES_COUNT_WORDS: dict[str, int] = {
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
}
CORRECTION_RE = re.compile(
    r"\b(?:non\s+)?(?:juste|seulement|uniquement)\b|"
    r"\bnon\b.{0,40}\bj['\u2019]?\s*ai\s+dit\b",
    re.I,
)
# Question factuelle (lieu, « est-ce que ») — ne jamais confirmer / sélectionner
CLARIFYING_QUESTION_RE = re.compile(
    r"(?:"
    r"\?|"
    r"\best[- ]ce\s+qu|"
    r"\bestce\s+qu|"
    r"\bc['\u2019]?est\s+(?:a|à|bien\s+a|bien\s+à)\b|"
    r"\bcette\s+activit.{0,40}\b(?:a|à|dans)\b|"
    r"\b(?:premier[e]?|1er|deuxi[eè]me|troisi[eè]me).{0,50}\b(?:c['\u2019]?est|est)\b.{0,25}\b(?:a|à|dans)\b"
    r")",
    re.I,
)
SOFT_CONFIRM_WITH_Q_RE = re.compile(
    r"c['\u2019]?est\s+(bon|parfait|nickel)|"
    r"j['\u2019]?\s*ai\s+dit.{0,50}(bon|oui|parfait|valid)|"
    r"\b(oui|ok).{0,30}(devis|parfait|bon)\b",
    re.I,
)
PRICE_RE = re.compile(r"\d+[,.]\d+\s*€")
NUMBERED_ITEM_RE = re.compile(r"(?:^|\s)(\d+)\.\s+")
TITLE_MATCH_MIN_SCORE = 20

# Indices 1-based vers la dernière présentation bot
ORDINAL_INDEX: dict[str, int] = {
    "premier": 1,
    "premiere": 1,
    "premiers": 1,
    "premieres": 1,
    "1er": 1,
    "1ere": 1,
    "rpemier": 1,  # typo fréquente
    "premie": 1,
    "deuxieme": 2,
    "2e": 2,
    "2eme": 2,
    "second": 2,
    "seconde": 2,
    "deusieme": 2,  # typos fréquentes
    "deuixieme": 2,
    "deuixeme": 2,
    "dexieme": 2,
    "troisieme": 3,
    "3e": 3,
    "3eme": 3,
    "troisiem": 3,
    "trosieme": 3,
    "troisiemme": 3,
    "quatrieme": 4,
    "4e": 4,
    "4eme": 4,
    "quatriem": 4,
    "cinquieme": 5,
    "5e": 5,
    "5eme": 5,
    "sixieme": 6,
    "6e": 6,
    "6eme": 6,
}
# Fuzzy typos : deusieme, troisiem…
ORDINAL_FUZZY: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bpremie?r[e]?s?\b", re.I), 1),
    (re.compile(r"\bdeu[sx]?i[eè]?m+e?s?\b", re.I), 2),
    (re.compile(r"\bseconde?s?\b", re.I), 2),
    (re.compile(r"\btroi?si[eè]?m+e?s?\b", re.I), 3),
    (re.compile(r"\bquatri[eè]?m+e?s?\b", re.I), 4),
]
# Chiffres dans un contexte de choix (pas les prix 90,30)
INDEX_DIGIT_RE = re.compile(
    r"(?:(?:^|[^\d])|^)"
    r"(?:le|la|les|n[°o]|num(?:ero|éro)|activit[eé]s?)?\s*"
    r"([1-9]|10)"
    r"(?!\s*[,.]\d)"  # pas une décimale
    r"(?!\s*€)",
    re.I,
)


def _numbered_chunks(text: str) -> list[str]:
    matches = list(NUMBERED_ITEM_RE.finditer(text))
    if not matches:
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


def is_clarifying_question(message: str) -> bool:
    """True si le partenaire pose une question factuelle (pas une sélection / devis)."""
    text = (message or "").strip()
    if not text:
        return False
    if SOFT_CONFIRM_WITH_Q_RE.search(text):
        return False
    if SELECT_ALL_RE.search(text) and "?" not in text:
        return False
    if re.search(r"\b(je\s+prends|je\s+choisis|j['\u2019]?aime)\b", text, re.I):
        return False
    # « 1 est ok … ? » / « 1 et 2 ok ? » = sélection, pas clarification lieu
    if INDEX_OK_RE.search(text):
        return False
    if re.search(r"\b\d\s*(et|ou|,)\s*\d", text) and WANTS_ANOTHER_ACTIVITY_RE.search(text):
        return False
    if re.search(r"(?<![\d,.])([1-9]|10)\b", text) and WANTS_ANOTHER_ACTIVITY_RE.search(text):
        return False
    return bool(CLARIFYING_QUESTION_RE.search(text))


def parse_les_count(message: str) -> int | None:
    """« les deux » / « les 3 » → nombre N (sans ordinaux nommés)."""
    m = LES_COUNT_RE.search(message or "")
    if not m:
        return None
    raw = m.group(1).casefold()
    if raw.isdigit():
        n = int(raw)
        return n if 1 <= n <= 6 else None
    return LES_COUNT_WORDS.get(raw)


def parse_presentation_indices(message: str) -> list[int]:
    """Extrait les indices de choix (1-based) : « premier », « 1 et 4 », « le quatrième »."""
    if not message or not message.strip():
        return []
    # « la première activité c'est à Istanbul ? » ≠ sélection
    if is_clarifying_question(message):
        return []

    text = _norm(message)
    hits: list[tuple[int, int]] = []  # (position, index)

    for word, idx in ORDINAL_INDEX.items():
        for m in re.finditer(rf"\b{re.escape(word)}\b", text):
            hits.append((m.start(), idx))

    # Fuzzy typos (deusieme, troisiem…) si pas déjà couvert
    covered_spans = [(s, s + 4) for s, _ in hits]
    for pattern, idx in ORDINAL_FUZZY:
        for m in pattern.finditer(text):
            if any(abs(m.start() - s) < 3 for s, _ in covered_spans):
                continue
            hits.append((m.start(), idx))
            covered_spans.append((m.start(), m.end()))

    for match in re.finditer(
        r"(?<![\d,.])([1-9]|10)(?!\s*[,.]\d)(?!\s*€)(?!\d)",
        message,
    ):
        idx = int(match.group(1))
        # « 2 jours » / « 3 personnes » ≠ indice de présentation
        right = message[match.end() : match.end() + 16]
        if re.match(r"\s*(jours?|personnes?|euros?|eur|€|nuits?|semaines?)\b", right, re.I):
            continue
        # « devis des 3 activités » / « les 3 activités » = SELECT_ALL, pas l'indice 3
        left = message[max(0, match.start() - 12) : match.start()]
        if re.search(r"(?:des?|les)\s*$", left, re.I) and re.match(
            r"\s*activit", right, re.I
        ):
            continue
        start = max(0, match.start() - 24)
        window = _norm(message[start : match.end() + 8])
        # Mots-clés avec frontières (évite « ou » dans « pour »)
        if re.search(
            r"\b(aime|choisi|prend|veux|juste|seulement|uniquement|et|ou|"
            r"numero|activit|option|bonne|bonnes|aussi|ok)\b|"
            r"\bajoute",
            window,
            re.I,
        ) or re.search(r"\b(le|la)\s+\d", message[max(0, match.start() - 4) : match.end() + 1], re.I):
            hits.append((match.start(), idx))
        elif re.match(
            r"\s*(?:est\s+)?(?:ok|bonne?|parfait|bien|nickel)\b",
            right,
            re.I,
        ):
            # « 1 est ok », « 2 ok »
            hits.append((match.start(), idx))
        elif re.search(r"\b(et|ou)\b", message, re.I) and re.search(
            r"\b(premier|deuxieme|1|2|3|4|5|6|7|8|9|10)\b", _norm(message)
        ):
            # « 1 et 3 » / « 1 et 6 » uniquement si contexte choix
            if re.search(r"\b\d\s*(et|ou|,)\s*\d", message, re.I):
                hits.append((match.start(), idx))

    # « 1 est ok vous avez d autres… » — filet si le chiffre n'a pas encore matché
    if not hits:
        for m in INDEX_OK_RE.finditer(message):
            hits.append((m.start(), int(m.group(1))))

    if not hits:
        bare = list(
            re.finditer(r"(?<![\d,.])([1-9]|10)(?!\s*[,.]\d)(?!\s*€)(?!\d)", message)
        )
        if bare and re.search(r"\b(et|ou)\b", message, re.I):
            for m in bare:
                idx = int(m.group(1))
                left = message[max(0, m.start() - 12) : m.start()]
                right = message[m.end() : m.end() + 16]
                if re.search(r"(?:des?|les)\s*$", left, re.I) and re.match(
                    r"\s*activit", right, re.I
                ):
                    continue
                hits.append((m.start(), idx))

    hits.sort(key=lambda x: x[0])
    found: list[int] = []
    for _, idx in hits:
        if idx not in found:
            found.append(idx)

    n = parse_les_count(message)
    # « les deux premiers » → [1, 2] (pas seulement l'ordinal « premiers » = 1)
    if found and n:
        if all(i <= n for i in found) and re.search(
            r"\bpremier", _norm(message)
        ):
            return list(range(1, n + 1))
        return sorted(found)

    # Ordinaux nommés / chiffres prioritaires
    if found:
        return sorted(found)

    # « 1 » / « 2. » seul → indice de la dernière présentation
    bare_only = re.fullmatch(
        r"(?:n[°o]\s*)?([1-9]|10)\.?",
        message.strip(),
        re.I,
    )
    if bare_only:
        return [int(bare_only.group(1))]

    # « les deux » / « les trois » / « je veux les trois » → N premières
    if n:
        return list(range(1, n + 1))

    # « devis des 3 activités » / « toutes les activités » → SELECT_ALL
    if SELECT_ALL_RE.search(message):
        return []

    return []


def pick_activities_by_presentation_indices(
    session_id: str,
    indices: list[int],
    *,
    rejected: set[str] | None = None,
) -> list[str]:
    """Mappe des indices 1-based sur la dernière liste numérotée / proposees."""
    rejected = rejected or set()
    last = _last_presentation_activities(session_id)
    slots = memory_manager.get_slots(session_id)
    proposed = [
        x for x in _parse_id_list(slots.get("activites_proposees")) if x not in rejected
    ]
    # Si un indice dépasse la dernière « présentation » (souvent 1 ligne LLM),
    # utiliser proposees (vraie liste Miami 1..6).
    max_idx = max(indices) if indices else 0
    pool = last
    if max_idx > len(pool) and len(proposed) >= max_idx:
        pool = proposed
    elif not pool:
        pool = proposed

    picks: list[str] = []
    for idx in indices:
        if 1 <= idx <= len(pool):
            aid = pool[idx - 1]
            if aid not in rejected and aid not in picks:
                picks.append(aid)
    return picks


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
        candidates = [nom] + [a.strip() for a in (row.get("aliases") or "").split("|") if a.strip()]
        for label in candidates:
            key = _norm(label)
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

    if _count_numbered_items(text) >= 1:
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


def _is_activity_presentation(text: str) -> bool:
    """Message assistant qui présente des activités (liste numérotée ou prix catalogue)."""
    if _count_numbered_items(text) >= 1:
        return True
    return bool(PRICE_RE.search(text))


CONFIRMATION_MAX_ACTIVITIES = 4
# Liste affichée peut aller jusqu'à 6–10 ; le cap 4 ne s'applique qu'au devis final
PRESENTATION_LIST_MAX = 10

# Message bot type confirmation / ask devis — pas une liste à indexer
_CONFIRMATION_STYLE_RE = re.compile(
    r"(?:"
    r"activit[eé]\s+s[eé]lectionn|"
    r"bien\s+not[eé].{0,40}activit|"
    r"je\s+pr[eé]pare\s+le\s+devis|"
    r"souhaitez[- ]vous\s+que\s+je\s+pr[eé]pare|"
    r"c['\u2019]?est\s+bon\s+pour\s+vous"
    r")",
    re.I,
)


def _presentation_activities_from_text(
    text: str,
    destination: str,
    *,
    rejected: set[str] | None = None,
) -> list[str]:
    """Extrait les activités d'un message de présentation (pas qualification / envies)."""
    if not text or not destination or not _is_activity_presentation(text):
        return []
    rejected = rejected or set()
    numbered = _count_numbered_items(text)
    min_score = TITLE_MATCH_MIN_SCORE if numbered >= 1 else 55
    picks = match_activities_by_titles(text, destination, rejected=rejected, min_score=min_score)
    if numbered >= 1:
        return picks[:numbered]
    # Présentation non numérotée : au plus 1–2 matches forts (évite 40 pyramides)
    return picks[:2]


def _last_presentation_activities(session_id: str) -> list[str]:
    """Activités de la dernière liste numérotée assistant (ordre = indices 1..N).

    Ignore les messages « activité sélectionnée / préparer le devis » qui
    écrasaient la liste Miami après un « 1 » passé par le LLM.
    Cap 4 = devis seulement ; ici on garde toute la liste affichée.
    """
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    proposed = [
        x for x in _parse_id_list(slots.get("activites_proposees")) if x not in rejected
    ]

    numbered_hit: list[str] = []
    soft_hit: list[str] = []

    for msg in reversed(conversation_manager.get_history(session_id, limit=20)):
        if msg.get("role") != "assistant":
            continue
        text = str(msg.get("content", "") or "")
        if not _is_activity_presentation(text):
            continue
        # Confirmation LLM (1 titre) ≠ liste à indexer
        if _CONFIRMATION_STYLE_RE.search(text) and _count_numbered_items(text) < 2:
            continue

        numbered = _count_numbered_items(text)
        picks: list[str] = []
        if destination:
            picks = _presentation_activities_from_text(
                text, destination, rejected=rejected
            )
        if numbered >= 2 and len(picks) < numbered and proposed:
            batch = proposed[-numbered:] if len(proposed) >= numbered else proposed
            if len(picks) < len(batch):
                picks = batch
        if not picks:
            continue
        if numbered >= 2:
            numbered_hit = picks[:PRESENTATION_LIST_MAX]
            break
        if not soft_hit:
            soft_hit = picks[:CONFIRMATION_MAX_ACTIVITIES]

    if numbered_hit:
        return numbered_hit
    if soft_hit:
        return soft_hit
    # Filet : dernières proposées session (écrasées à chaque search)
    if proposed:
        return proposed[:PRESENTATION_LIST_MAX]
    return []


def _confirmation_selection_pool(
    session_id: str,
    discussed: list[str],
    proposed: list[str],
    rejected: set[str],
) -> list[str]:
    """Pool de confirmation STRICT : dernière présentation ou petite sélection / proposition.

    Ne jamais confirmer tout activites_discutees (évite devis à 40+ activités).
    """
    slots = memory_manager.get_slots(session_id)
    selected = [x for x in _parse_id_list(slots.get("activites_selectionnees")) if x not in rejected]
    last = _last_presentation_activities(session_id)
    proposed_ok = [x for x in proposed if x not in rejected]

    # Petite sélection explicite OK ; grosse sélection = bug → préférer last / proposed
    if selected and len(selected) <= CONFIRMATION_MAX_ACTIVITIES:
        return selected
    if last:
        return [x for x in last if x not in rejected][:CONFIRMATION_MAX_ACTIVITIES]
    if proposed_ok and len(proposed_ok) <= CONFIRMATION_MAX_ACTIVITIES:
        return proposed_ok
    if selected:
        return selected[:CONFIRMATION_MAX_ACTIVITIES]
    _ = discussed
    return []


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
    """Enregistre les activités mentionnées dans un message de présentation (réponse bot)."""
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    ids = _presentation_activities_from_text(text, destination, rejected=rejected)
    if ids:
        _merge_discussed(session_id, ids)
    return ids


def sync_discussed_from_history(session_id: str) -> None:
    """Reconstruit activites_discutees depuis les présentations assistant uniquement."""
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
        picks = _presentation_activities_from_text(text, destination, rejected=rejected)
        if picks:
            collected.extend(picks)
    if collected:
        memory_manager.update_slots(session_id, activites_discutees=_join_ids(collected))


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
    # Question factuelle : ne pas toucher à la sélection
    if is_clarifying_question(message):
        return

    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    selected = _parse_id_list(slots.get("activites_selectionnees"))
    proposed = _parse_id_list(slots.get("activites_proposees"))
    discussed = _parse_id_list(slots.get("activites_discutees"))
    candidates = _known_activity_rows(session_id)

    numbered_count = _count_numbered_items(message)
    catalog_picks = match_activities_by_titles(message, destination, rejected=rejected)

    # Retrait / correction (« pas la première », « enlever Moulin Rouge ») AVANT indices
    if REMOVE_SELECTION_RE.search(message) or REJECT_RE.search(message):
        remove_ids: list[str] = []
        # Ordinaux dans un contexte de refus → retirer de la sélection / présentation
        rm_indices = parse_presentation_indices(message)
        if rm_indices:
            from_pres = pick_activities_by_presentation_indices(
                session_id, rm_indices, rejected=set()
            )
            remove_ids.extend(from_pres)
            # Aussi indices sur la sélection courante (1 = première sélectionnée)
            for idx in rm_indices:
                if 1 <= idx <= len(selected):
                    remove_ids.append(selected[idx - 1])
        # Match titres cités
        title_hits = _match_activities_in_text(message, candidates) or []
        remove_ids.extend(title_hits)
        title_catalog = match_activities_by_titles(
            message, destination, rejected=set(), min_score=30
        )
        remove_ids.extend(title_catalog)
        remove_ids = list(dict.fromkeys(remove_ids))
        if remove_ids:
            for aid in remove_ids:
                rejected.add(aid)
            had_selection = bool(selected)
            selected = [x for x in selected if x not in rejected]
            # Si on avait une sélection et qu'elle est vide : garder le reste de la présentation
            if had_selection and not selected:
                last = _last_presentation_activities(session_id)
                pool = last or proposed or discussed
                selected = [x for x in pool if x not in rejected]
            memory_manager.update_slots(
                session_id,
                activites_rejetees=_join_ids(list(rejected)),
                activites_selectionnees=_join_ids(selected) if selected else "",
            )
            if not selected:
                memory_manager.clear_slot(session_id, "activites_selectionnees")
            return

    # « ajoute ceci » / « oui ajoute » → append à la sélection (ne remplace pas)
    if is_add_this_activity(message):
        picks: list[str] = []
        add_indices = parse_presentation_indices(message)
        if add_indices:
            picks = pick_activities_by_presentation_indices(
                session_id, add_indices, rejected=rejected
            )
        if not picks and not add_indices:
            # Sans indice explicite (« ajoute ceci ») → 1re de la dernière liste
            last = _last_presentation_activities(session_id)
            picks = last[:1] if last else []
        if not picks and catalog_picks:
            picks = catalog_picks[:1]
        if picks:
            for aid in picks:
                if aid not in rejected and aid not in selected:
                    selected.append(aid)
            selected = selected[:CONFIRMATION_MAX_ACTIVITIES]
            memory_manager.update_slots(
                session_id, activites_selectionnees=_join_ids(selected)
            )
            return

    # « le premier et le quatrième » / « 1 et 4 » → indices sur la dernière présentation
    indices = parse_presentation_indices(message)
    if indices:
        picks = pick_activities_by_presentation_indices(
            session_id, indices, rejected=rejected
        )
        if picks:
            awaiting_add = str(slots.get("awaiting_add_activity", "") or "").strip()
            # Liste 2+ : append si on ajoute une activité (ne pas écraser la liste 1)
            if awaiting_add and not CORRECTION_RE.search(message):
                for aid in picks:
                    if aid not in rejected and aid not in selected:
                        selected.append(aid)
                selected = selected[:CONFIRMATION_MAX_ACTIVITIES]
                memory_manager.update_slots(
                    session_id, activites_selectionnees=_join_ids(selected)
                )
            else:
                memory_manager.update_slots(
                    session_id, activites_selectionnees=_join_ids(picks)
                )
            return

    if CORRECTION_RE.search(message):
        picks = catalog_picks or match_activities_by_titles(
            message, destination, rejected=rejected, min_score=35
        )
        if picks:
            if not _count_numbered_items(message) and len(picks) > 1:
                picks = picks[:1]
            memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))
            return

    # « les trois » / « devis des 3 activités » → dernière présentation exacte
    # Ne pas écraser si des ordinaux précis sont déjà présents (« 2 et 3 », « les deux la 2e… »)
    if SELECT_ALL_RE.search(message) and not parse_presentation_indices(message):
        last = _last_presentation_activities(session_id)
        pool = last or discussed or proposed
        picks = [x for x in pool if x not in rejected]
        if picks:
            memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))
        return

    if (ACTIVITY_OK_RE.search(message) or is_quote_confirmation(message)) and (discussed or proposed):
        # Garder une sélection explicite raisonnable (ex. 3) — ne pas élargir à 4.
        # Sélection pathologique (40 IDs) → normaliser via le pool (cap / last).
        if selected and len(selected) <= CONFIRMATION_MAX_ACTIVITIES:
            return
        picks = _confirmation_selection_pool(session_id, discussed, proposed, rejected)
        if picks:
            memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))
        return

    if numbered_count >= 1 and catalog_picks:
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
        # Sans indices : matcher le texte, sinon la dernière présentation (1 item si « ça »)
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
            if re.search(r"\b(choisis|prends|aime)\b", message, re.I):
                memory_manager.update_slots(
                    session_id, activites_selectionnees=_join_ids(pick)
                )
            else:
                for aid in pick:
                    if aid not in rejected and aid not in selected:
                        selected.append(aid)
                memory_manager.update_slots(
                    session_id, activites_selectionnees=_join_ids(selected)
                )
        return

    if re.search(r"c['\u2019]est\s+bon|cest\s+bon", message, re.I) and "?" not in message:
        if not re.search(r"\bautre", message, re.I) and not selected:
            picks = _confirmation_selection_pool(session_id, discussed, proposed, rejected)
            if picks:
                memory_manager.update_slots(session_id, activites_selectionnees=_join_ids(picks))


def is_wants_other_options(message: str) -> bool:
    """« autre option » / « autres options » — remplacer la liste, pas ajouter."""
    text = message or ""
    if not text.strip():
        return False
    if WANTS_OTHER_OPTIONS_RE.search(text):
        return True
    return False


def is_reject_presented_list(message: str) -> bool:
    """« j'ai pas aimé » sans indice précis → refus de la liste proposée."""
    text = (message or "").strip()
    if not text:
        return False
    if parse_presentation_indices(text):
        return False
    if is_wants_other_options(text):
        return True
    return bool(REJECT_PRESENTED_LIST_RE.search(text))


def reject_presented_list(session_id: str) -> list[str]:
    """Marque les activités proposées / présentées comme rejetées ; vide la sélection."""
    slots = memory_manager.get_slots(session_id)
    proposed = _parse_id_list(slots.get("activites_proposees"))
    last = _last_presentation_activities(session_id)
    pool = list(dict.fromkeys((last or []) + proposed))
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))
    rejected.update(pool)
    memory_manager.update_slots(
        session_id,
        activites_rejetees=_join_ids(list(rejected)),
        activites_selectionnees="",
    )
    memory_manager.clear_slot(session_id, "activites_selectionnees")
    memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
    memory_manager.clear_slot(session_id, "awaiting_add_activity")
    return pool


def is_wants_another_activity(message: str) -> bool:
    """« je veux une autre activité », « avec elle », etc. — pas un oui devis."""
    text = message or ""
    # « autre option » ≠ ajouter une activité supplémentaire
    if is_wants_other_options(text) and not re.search(r"autre\s+activit", text, re.I):
        return False
    return bool(WANTS_ANOTHER_ACTIVITY_RE.search(text))


def is_add_this_activity(message: str) -> bool:
    """« ajoute ceci », « oui ajoute » — append à la sélection existante."""
    return bool(ADD_THIS_ACTIVITY_RE.search(message or ""))


def is_quote_confirmation(message: str) -> bool:
    text = message.strip()
    if not text or len(text) > 140:
        return False
    if is_clarifying_question(text):
        # « le devis ? » reste une confirmation
        if DEVIS_REQUEST_RE.search(text) and not parse_presentation_indices(text):
            return True
        return False
    # Ajout / autre activité ≠ confirmation devis (sauf devis explicite)
    if is_add_this_activity(text) or is_wants_another_activity(text):
        if not re.search(r"\bdevis\b", text, re.I):
            return False
    # Choix par indices (« premier et quatrième ») ≠ confirmation globale
    if parse_presentation_indices(text):
        return False
    # Confirmations explicites d'abord (évite le conflit SELECT_RE / « parfait »)
    if ACTIVITY_OK_RE.search(text):
        return True
    if DEVIS_REQUEST_RE.search(text):
        return True
    if REJECT_RE.search(text):
        return False
    if SELECT_RE.search(text):
        return False
    if SELECT_ALL_RE.search(text):
        return False
    if _count_numbered_items(text) >= 2:
        return False
    if "?" in text and re.search(r"\b(activit|devis)\b", text, re.I):
        return bool(re.search(r"c['\u2019]?est\s+(bon|parfait)|oui+\b", text, re.I))
    if "?" in text or re.search(r"\b(autre|non|pas)\b", text, re.I):
        return False
    if re.search(r"\b(choisis|prends)\b", text, re.I):
        return False
    return bool(QUOTE_CONFIRM_RE.search(text))


def is_confirmation_message(message: str) -> bool:
    """Confirmation d'activités / devis — ne pas traiter comme une destination."""
    return is_quote_confirmation(message.strip())


def session_has_activity_context(session_id: str) -> bool:
    """True si une destination catalogue + activités sont déjà en discussion."""
    slots = memory_manager.get_slots(session_id)
    destination = str(slots.get("destination", "") or "").strip()
    if not destination:
        return False
    if not resolve_destination_name(destination, data_loader):
        return False
    for key in ("activites_discutees", "activites_proposees", "activites_selectionnees"):
        if str(slots.get(key, "") or "").strip():
            return True
    return False


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
    """Enregistre la dernière liste proposée (écrase proposees ; merge discussees).

    `activites_proposees` = dernière présentation seulement → indices 1..N corrects.
    """
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

    discussed = _parse_id_list(slots.get("activites_discutees"))
    memory_manager.update_slots(
        session_id,
        activites_proposees=_join_ids(new_ids),
        activites_discutees=_join_ids(discussed + new_ids),
    )
    return new_ids


def confirm_proposed_activities(session_id: str) -> list[str]:
    """Confirme les activités déjà sélectionnées, ou le pool de présentation / propositions."""
    slots = memory_manager.get_slots(session_id)
    proposed = _parse_id_list(slots.get("activites_proposees"))
    discussed = _parse_id_list(slots.get("activites_discutees"))
    rejected = set(_parse_id_list(slots.get("activites_rejetees")))

    ids = _confirmation_selection_pool(session_id, discussed, proposed, rejected)
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
    # Sélection faite mais en attente du « oui » devis
    awaiting = str(slots.get("awaiting_quote_confirm", "") or "").strip().casefold()
    if awaiting in ("1", "true", "oui", "pending"):
        quote_ready = False
        if "confirmation_devis" not in missing:
            missing.append("confirmation_devis")
    # En train d'ajouter une activité → pas encore prêt pour le PDF
    awaiting_add = str(slots.get("awaiting_add_activity", "") or "").strip().casefold()
    if awaiting_add in ("1", "true", "oui", "pending"):
        quote_ready = False
        if "activite_supplementaire" not in missing:
            missing.append("activite_supplementaire")

    return {
        "quote_ready": quote_ready,
        "missing": missing,
        "destination": destination or None,
        "nom_agence": nom_agence or None,
        "activity_ids": selected_ids,
        "activities": activities,
    }
