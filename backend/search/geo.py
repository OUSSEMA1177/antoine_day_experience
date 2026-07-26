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
    """Retourne le nom catalogue canonique si la destination existe."""
    if hasattr(loader, "resolve_destination_name"):
        resolved = loader.resolve_destination_name(name)
        if resolved:
            return resolved
    if loader.resolve_destination_id(destination_name=name):
        return name.strip()
    for kw in expand_to_keywords(name):
        if loader.resolve_destination_id(destination_name=kw):
            dest = loader.get_destination_by_name(kw)
            return (dest.get("nom") if dest else kw) or kw
    return None


def detect_landmark(text: str) -> tuple[str, str] | None:
    for pattern, destination, query in LANDMARK_QUERIES:
        if pattern.search(text):
            return destination, query
    return None


REGION_LABELS: dict[str, str] = {
    "maroc": "le Maroc",
    "france": "la France",
    "espagne": "l'Espagne",
    "italie": "l'Italie",
    "egypte": "l'Égypte",
    "grece": "la Grèce",
    "emirats": "les Émirats",
    "suisse": "la Suisse",
    "asie": "l'Asie",
    "europe": "l'Europe",
    "afrique": "l'Afrique",
    "amerique": "les Amériques",
    "moyen_orient": "le Moyen-Orient",
    "all": "notre catalogue",
}

REGION_PAYS: dict[str, str] = {
    "maroc": "Maroc",
    "france": "France",
    "espagne": "Espagne",
    "italie": "Italie",
    "egypte": "Égypte",
    "grece": "Grèce",
    "emirats": "Émirats arabes unis",
    "suisse": "Suisse",
}

# Alias supplémentaires (typos / anglais) → slug pays catalogue
EXTRA_COUNTRY_ALIASES: dict[str, list[str]] = {
    "bresil": ["bresil", "brésil", "brazil", "brasil", "brezil", "bresille"],
    "chili": ["chili", "chile", "chiliens"],
    "canada": ["canada", "canadien", "canadienne"],
    "chine": ["chine", "china", "chinois", "chinoise"],
    "indonesie": ["indonesie", "indonésie", "indonesia", "indonesien"],
    "japon": ["japon", "japan", "japonais", "japonaise"],
    "mexique": ["mexique", "mexico", "mexicain", "mexicaine"],
    "etats-unis": [
        "etats-unis", "états-unis", "etats unis", "états unis", "usa", "u.s.a",
        "united states", "etatsunis",
    ],
    "afrique_du_sud": [
        "afrique du sud", "afrique-du-sud", "south africa", "afrique dusud",
        "afrique de sud", "afrique de sude", "afrique dusude", "afrique sud",
        "afrique d sud", "rsa",
    ],
    "tanzanie": ["tanzanie", "tanzania"],
    "turquie": ["turquie", "turkey", "turc", "turque"],
    "jordanie": ["jordanie", "jordan"],
    "autriche": ["autriche", "austria", "autrichien"],
    "hongrie": ["hongrie", "hungary", "hongrois"],
    "pologne": ["pologne", "poland", "polonais"],
    "portugal": ["portugal", "portugais", "portugaise"],
    "royaume-uni": [
        "royaume-uni", "royaume uni", "uk", "angleterre", "england",
        "grande bretagne", "britain",
    ],
    "pays-bas": ["pays-bas", "pays bas", "netherlands", "hollande", "dutch"],
    "malte": ["malte", "malta"],
}

# Préfixes usuels avant un nom de pays (« juste bresil », « en chili »)
COUNTRY_PREFIX_RE = re.compile(
    r"^(?:juste|seulement|uniquement|au|aux|en|le|la|les|du|de\s+la|des|"
    r"dans|pour|vers|sur|au\s+sujet\s+d(?:e|u)|c['\u2019]est)\s+",
    re.I,
)

_catalog_countries_cache: dict[str, dict[str, object]] | None = None


def _pays_slug(pays: str) -> str:
    return _norm(pays).replace(" ", "_")


def _label_article(pays_label: str) -> str:
    """Forme courte pour l'affichage (« le Brésil », « la France »)."""
    p = pays_label.strip()
    if not p:
        return p
    for key, label in REGION_PAYS.items():
        if _norm(label) == _norm(p) and key in REGION_LABELS:
            return REGION_LABELS[key]
    n = _norm(p)
    if n.startswith(("etats", "emirats", "pays")):
        return f"les {p}"
    masculine = {
        "bresil", "canada", "chili", "japon", "mexique", "portugal",
        "royaume-uni", "maroc", "luxembourg",
    }
    feminine = {
        "france", "espagne", "italie", "grece", "suisse", "chine",
        "turquie", "jordanie", "pologne", "hongrie", "autriche", "tanzanie",
        "indonesie", "afrique_du_sud", "afrique du sud",
    }
    if n in masculine:
        return f"le {p}"
    if n in feminine:
        return f"la {p}"
    if p[:1].casefold() in "aeiouéèêàâîôùüy":
        return f"l'{p}"
    if n.endswith("e"):
        return f"la {p}"
    return f"le {p}"


def invalidate_catalog_countries_cache() -> None:
    global _catalog_countries_cache
    _catalog_countries_cache = None


def get_catalog_countries(loader=None) -> dict[str, dict[str, object]]:
    """
    Registry pays catalogue (CSV + aliases).
    key (slug) → {label, aliases: list[str], pays_norm: str}
    """
    global _catalog_countries_cache
    if _catalog_countries_cache is not None and loader is None:
        return _catalog_countries_cache

    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader
    registry: dict[str, dict[str, object]] = {}

    def _ensure(key: str, label: str) -> dict[str, object]:
        entry = registry.get(key)
        if entry is None:
            entry = {"label": label, "aliases": [], "pays_norm": _norm(label)}
            registry[key] = entry
        return entry

    def _add_alias(entry: dict[str, object], alias: str) -> None:
        aliases = entry["aliases"]
        assert isinstance(aliases, list)
        a = alias.strip()
        if not a:
            return
        if _norm(a) not in {_norm(x) for x in aliases}:
            aliases.append(a)

    # 1) Pays hardcodés (rétrocompat)
    for key, label in REGION_PAYS.items():
        entry = _ensure(key, label)
        _add_alias(entry, label)
        _add_alias(entry, key)
        region = REGION_ALIASES.get(key)
        if region:
            for a in region["aliases"]:
                _add_alias(entry, a)

    # 2) Tous les pays du CSV
    for row in loader.load_destinations():
        pays = (row.get("pays") or "").strip()
        if not pays:
            continue
        # Réutiliser la clé REGION_PAYS si le label matche
        key = None
        for rk, label in REGION_PAYS.items():
            if _norm(label) == _norm(pays):
                key = rk
                break
        if key is None:
            key = _pays_slug(pays)
        entry = _ensure(key, pays)
        _add_alias(entry, pays)
        _add_alias(entry, key.replace("_", " "))

    # 3) Alias extra (typos / EN)
    for key, aliases in EXTRA_COUNTRY_ALIASES.items():
        # Rattacher à une entrée existante par slug / pays_norm
        target_key = key if key in registry else None
        if target_key is None:
            for rk, entry in registry.items():
                if entry["pays_norm"] == _norm(key.replace("_", " ")) or rk == key:
                    target_key = rk
                    break
        if target_key is None:
            # Chercher une entrée dont le label normalise comme le premier alias
            for rk, entry in registry.items():
                if any(entry["pays_norm"] == _norm(a) for a in aliases):
                    target_key = rk
                    break
        if target_key is None:
            continue
        entry = registry[target_key]
        for a in aliases:
            _add_alias(entry, a)

    if loader is None or loader is default_loader:
        _catalog_countries_cache = registry
    return registry


def resolve_catalog_country_key(name: str, loader=None) -> str | None:
    """Nom / alias / typo → clé pays catalogue (ex. brezil → bresil)."""
    if not (name or "").strip():
        return None
    needle = _norm(name)
    registry = get_catalog_countries(loader)
    # Exact alias
    for key, entry in registry.items():
        aliases = entry["aliases"]
        assert isinstance(aliases, list)
        if needle == key or needle == entry["pays_norm"]:
            return key
        if any(needle == _norm(a) for a in aliases):
            return key
    # Typo distance 1 (brezil / bresil)
    if len(needle) >= 5:
        for key, entry in registry.items():
            aliases = entry["aliases"]
            assert isinstance(aliases, list)
            candidates = [key, str(entry["pays_norm"])] + [_norm(a) for a in aliases]
            for c in candidates:
                if abs(len(c) - len(needle)) > 1:
                    continue
                if _edit_distance_le1(needle, c):
                    return key
    return None


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    # insertion / deletion
    if len(a) > len(b):
        a, b = b, a
    # a shorter by 1
    i = j = diffs = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            diffs += 1
            if diffs > 1:
                return False
            j += 1
            continue
        i += 1
        j += 1
    return True


def message_country_core(message: str) -> str:
    """Enlève préfixes (« juste », « en ») pour matcher un pays isolé."""
    text = (message or "").strip().rstrip("?.!,;:")
    prev = None
    while prev != text:
        prev = text
        text = COUNTRY_PREFIX_RE.sub("", text).strip()
    return text


# « afrique de sud / sude / dusud » — typos fréquentes ≠ continent Afrique
AFRIQUE_DU_SUD_MSG_RE = re.compile(
    r"\bafrique\s+(?:du|de|d)\s*sud\w*\b|\bafrique\s+sud\b|\bsouth\s+africa\b",
    re.I,
)


def detect_catalog_country_query(message: str, loader=None) -> str | None:
    """Pays catalogue cité (seul ou avec hint question). Prioritaire vs continent."""
    lower = _norm(message)
    if not lower:
        return None
    # Afrique du Sud (typos) avant tout match continent « afrique »
    if AFRIQUE_DU_SUD_MSG_RE.search(message) or AFRIQUE_DU_SUD_MSG_RE.search(lower):
        registry = get_catalog_countries(loader)
        if "afrique_du_sud" in registry:
            return "afrique_du_sud"
        for rk, entry in registry.items():
            if entry.get("pays_norm") == "afrique du sud":
                return rk

    core = message_country_core(message)
    core_norm = _norm(core)

    # Message ≈ nom de pays (évent. typos)
    key = resolve_catalog_country_key(core, loader)
    if key:
        return key

    has_hint = _has_catalog_question_hint(message, lower)
    registry = get_catalog_countries(loader)
    best: tuple[int, str] | None = None
    for rk, entry in registry.items():
        aliases = entry["aliases"]
        assert isinstance(aliases, list)
        for alias in aliases:
            an = _norm(alias)
            if len(an) < 4:
                continue
            if an in lower or (has_hint and an in lower):
                # Mot entier préféré
                if re.search(rf"\b{re.escape(an)}\b", lower):
                    score = len(an) + 10
                elif an in lower:
                    score = len(an)
                else:
                    continue
                if best is None or score > best[0]:
                    best = (score, rk)
    if best and (has_hint or best[0] >= 14 or core_norm == _norm(best[1])):
        return best[1]
    # Pays seul sans hint déjà couvert via resolve ; pays dans phrase courte
    if best and len(lower.split()) <= 4:
        return best[1]
    return None


# Continent → pays catalogue (colonne destinations.csv « pays »)
CONTINENT_PAYS: dict[str, list[str]] = {
    "asie": ["Indonésie", "Chine", "Japon"],
    "europe": [
        "Pays-Bas", "Grèce", "Espagne", "Hongrie", "Pologne", "Portugal",
        "Royaume-Uni", "Malte", "Italie", "France", "Autriche",
    ],
    "afrique": ["Maroc", "Égypte", "Afrique du Sud", "Tanzanie"],
    "amerique": ["Brésil", "États-Unis", "Canada", "Chili", "Mexique"],
    "moyen_orient": ["Émirats arabes unis", "Jordanie", "Turquie"],
}

CONTINENT_ALIASES: dict[str, list[str]] = {
    # Pas « asiatique » seul : matchait les titres (« dessert asiatique »)
    "asie": ["asie", "asia", "asian"],
    "europe": ["europe", "europeen", "européen", "europeenne", "européenne", "europeens"],
    "afrique": ["afrique", "africa", "africain", "africaine", "africains"],
    "amerique": [
        "amerique", "amérique", "americas", "america", "ameriques", "amériques",
        "amerique du sud", "amérique du sud", "amerique du nord", "amérique du nord",
        "latam", "latino",
    ],
    "moyen_orient": [
        "moyen orient", "moyen-orient", "middle east", "proche orient", "proche-orient",
    ],
}

# Demandes explicites de continent (évite faux positifs dans titres collés)
EXPLICIT_CONTINENT_RE: dict[str, re.Pattern[str]] = {
    "asie": re.compile(
        r"\b(?:en|au|vers|pour|l['\u2019]?)\s*asie\b|"
        r"\bpays\s+asiatiques?\b|"
        r"\bcontinent\s+asiatique\b",
        re.I,
    ),
    "europe": re.compile(
        r"\b(?:en|vers|pour|l['\u2019]?)\s*europe\b|\bpays\s+europ[eé]ens?\b",
        re.I,
    ),
    "afrique": re.compile(
        r"\b(?:en|vers|pour|l['\u2019]?)\s*afrique\b|\bpays\s+africains?\b",
        re.I,
    ),
    "amerique": re.compile(
        r"\b(?:en|aux|vers|pour|les?\s+)\s*am[eé]riques?\b|\bamerique\s+du\s+(sud|nord)\b",
        re.I,
    ),
    "moyen_orient": re.compile(
        r"\b(?:au|en|vers|pour)\s+(?:le\s+)?moyen[- ]orient\b|\bmiddle\s+east\b",
        re.I,
    ),
}

ALL_DESTINATIONS_HINTS = (
    "autres destination", "autre destination", "toutes les destination",
    "toute les destination", "quelles destination", "quelle destination",
    "liste des destination", "vos destination", "nos destination",
    "d autres destination", "d'autres destination", "autres pays", "autre pays",
)

COUNTRY_QUERY_HINTS = (
    "avez", "avons", "catalogue", "destination", "lieu", "lieux", "place", "places",
    "ville", "villes", "quoi", "quel", "quelle", "que", "autre", "autres", "disponib",
    "proposez", "propose", "offrez", "couvre", "couvrez", "uniquement", "seulement",
)

CATALOG_QUESTION_RE = re.compile(
    r"\b(il\s*y\s*a|ily|y\s*a|est[- ]ce\s+qu|juste|que|quoi|uniquement|seulement|"
    r"autre|autres|avez|avons|uniquement)\b",
    re.I,
)


def list_catalog_destinations_for_region(region_key: str, loader=None) -> list[str]:
    """Villes réellement présentes dans destinations.csv pour une région/pays/continent."""
    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader

    if region_key == "all":
        picks = []
        for row in loader.load_destinations():
            nom = (row.get("nom") or "").strip()
            if nom:
                picks.append(nom)
        return sorted(picks, key=str.casefold)

    # Pays catalogue dynamique (Brésil, Chili, Chine…) — AVANT continent
    # (évite qu'un slug pays tombe dans CONTINENT_PAYS par erreur)
    catalog = get_catalog_countries(loader)
    if region_key in catalog:
        pays_norm = str(catalog[region_key]["pays_norm"])
        picks = []
        for row in loader.load_destinations():
            if _norm(row.get("pays")) == pays_norm:
                nom = (row.get("nom") or "").strip()
                if nom:
                    picks.append(nom)
        if picks:
            return sorted(picks, key=str.casefold)

    continent_pays = CONTINENT_PAYS.get(region_key)
    if continent_pays:
        pays_norm_set = {_norm(p) for p in continent_pays}
        picks = []
        for row in loader.load_destinations():
            if _norm(row.get("pays")) in pays_norm_set:
                nom = (row.get("nom") or "").strip()
                if nom:
                    picks.append(nom)
        return sorted(picks, key=str.casefold)

    pays = REGION_PAYS.get(region_key)
    if pays:
        picks = []
        for row in loader.load_destinations():
            if _norm(row.get("pays")) == _norm(pays):
                nom = (row.get("nom") or "").strip()
                if nom:
                    picks.append(nom)
        if picks:
            return sorted(picks, key=str.casefold)

    region = REGION_ALIASES.get(region_key)
    if not region:
        return []

    keywords = [_norm(k) for k in region["catalog_keywords"]]
    picks = []
    seen: set[str] = set()

    for row in loader.load_destinations():
        nom = (row.get("nom") or "").strip()
        if not nom:
            continue
        nom_norm = _norm(nom)
        alias_blob = _norm(f"{nom} {row.get('aliases', '')}")
        matched = any(
            kw in nom_norm or nom_norm in kw or nom_norm.startswith(kw) or kw in alias_blob
            for kw in keywords
        )
        if matched and nom_norm not in seen:
            seen.add(nom_norm)
            picks.append(nom)

    return sorted(picks, key=str.casefold)


def list_destinations(
    *,
    continent: str | None = None,
    pays: str | None = None,
    query: str | None = None,
    loader=None,
) -> dict[str, object]:
    """Liste filtrée des destinations catalogue (outil LLM + chemins déterministes)."""
    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader
    rows = loader.load_destinations()

    continent_key = None
    if continent:
        needle = _norm(continent)
        for key, aliases in CONTINENT_ALIASES.items():
            if needle == key or needle in {_norm(a) for a in aliases}:
                continent_key = key
                break
        if continent_key is None and needle in CONTINENT_PAYS:
            continent_key = needle

    pays_filter = _norm(pays) if pays else ""
    query_filter = _norm(query) if query else ""

    # query peut être un continent / pays / "all"
    if not continent_key and query_filter:
        for key, aliases in CONTINENT_ALIASES.items():
            if query_filter == key or any(a in query_filter or query_filter in _norm(a) for a in aliases):
                continent_key = key
                break
        if query_filter in {"all", "tout", "tous", "catalogue"} or any(
            h in query_filter for h in ("autre destination", "toutes les destination", "quelles destination")
        ):
            continent_key = None
            pays_filter = ""
            query_filter = ""
            # list all below
            items = []
            for row in rows:
                nom = (row.get("nom") or "").strip()
                country = (row.get("pays") or "").strip()
                if nom:
                    items.append({"nom": nom, "pays": country})
            return {
                "count": len(items),
                "filter": {"scope": "all"},
                "destinations": items,
                "by_pays": _group_by_pays(items),
            }

    allowed_pays: set[str] | None = None
    if continent_key:
        allowed_pays = {_norm(p) for p in CONTINENT_PAYS.get(continent_key, [])}

    items: list[dict[str, str]] = []
    for row in rows:
        nom = (row.get("nom") or "").strip()
        country = (row.get("pays") or "").strip()
        if not nom:
            continue
        country_norm = _norm(country)
        if allowed_pays is not None and country_norm not in allowed_pays:
            continue
        if pays_filter and pays_filter not in country_norm and country_norm not in pays_filter:
            # aussi matcher nom de ville si pays mal renseigné
            if pays_filter not in _norm(nom):
                continue
        if query_filter and continent_key is None:
            blob = _norm(f"{nom} {country} {row.get('aliases', '')}")
            if query_filter not in blob:
                continue
        items.append({"nom": nom, "pays": country})

    items.sort(key=lambda x: x["nom"].casefold())
    scope = continent_key or (pays if pays else (query if query else "all"))
    return {
        "count": len(items),
        "filter": {
            "continent": continent_key,
            "pays": pays,
            "query": query,
            "scope": scope,
        },
        "destinations": items,
        "by_pays": _group_by_pays(items),
    }


def _group_by_pays(items: list[dict[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        country = item.get("pays") or "Autre"
        grouped.setdefault(country, []).append(item["nom"])
    for country in grouped:
        grouped[country] = sorted(grouped[country], key=str.casefold)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].casefold()))


def detect_continent_query(message: str) -> str | None:
    """Détecte une demande de destinations par continent (ex. Asie)."""
    lower = _norm(message)
    if not lower:
        return None
    from search.themes import detect_themes_from_text

    # Titre d'activité collé (« … asiatique en Europe ») ≠ demande continent
    if _looks_like_activity_title_paste(message):
        return None

    # Afrique du Sud ≠ continent Afrique (« l afrique de sude »)
    if AFRIQUE_DU_SUD_MSG_RE.search(message) or AFRIQUE_DU_SUD_MSG_RE.search(lower):
        return None

    # D'abord les formulations explicites (« en Asie », « pays asiatiques »)
    for key, pattern in EXPLICIT_CONTINENT_RE.items():
        if pattern.search(message):
            return key

    has_theme = bool(detect_themes_from_text(message))
    has_hint = (
        _has_catalog_question_hint(message, lower)
        or has_theme
        or any(
            w in lower
            for w in ("pays", "destination", "ville", "villes", "veux", "vouloir", "cherche")
        )
    )
    for key, aliases in CONTINENT_ALIASES.items():
        if not any(_norm(a) in lower for a in aliases):
            continue
        # Alias court (« asie ») : exiger hint ou message = alias seul
        if has_hint or lower.strip().rstrip("?.!,;:") in {_norm(a) for a in aliases}:
            return key
    return None


def _looks_like_activity_title_paste(message: str) -> bool:
    """Heuristique : partenaire colle un titre catalogue (pas une question géo)."""
    text = (message or "").strip()
    if len(text) < 50:
        return False
    if re.search(r"\b(pays|continent|quelles?\s+destinations?|liste)\b", text, re.I):
        return False
    product = bool(
        re.search(
            r"\b(d[iî]ner|soir[eé]e|visite|excursion|croisi[eè]re|billet|gastronomie)\b",
            text,
            re.I,
        )
    )
    return product


def is_explicit_region_request(message: str) -> bool:
    """True si le message demande clairement un continent/pays (pas un titre collé)."""
    if _looks_like_activity_title_paste(message):
        return False
    if detect_all_destinations_query(message):
        return True
    if detect_catalog_country_query(message):
        return True
    for pattern in EXPLICIT_CONTINENT_RE.values():
        if pattern.search(message):
            return True
    lower = _norm(message)
    for region in REGION_ALIASES.values():
        if any(_norm(a) == lower.strip().rstrip("?.!,;:") for a in region["aliases"]):
            return True
        if any(
            _norm(a) in lower and _has_catalog_question_hint(message, lower)
            for a in region["aliases"]
        ):
            return True
    # « plage en asie » / thème + continent explicite
    if detect_continent_query(message) and detect_themes_from_text_safe(message):
        return True
    return False


def detect_themes_from_text_safe(message: str) -> bool:
    try:
        from search.themes import detect_themes_from_text

        return bool(detect_themes_from_text(message))
    except Exception:
        return False


def detect_all_destinations_query(message: str) -> bool:
    """« autres destinations », « quelles destinations avez-vous », etc."""
    lower = _norm(message)
    if not lower:
        return False
    # Si un pays/continent précis est cité, ce n'est pas une liste globale
    for aliases in CONTINENT_ALIASES.values():
        if any(_norm(a) in lower for a in aliases):
            return False
    for region in REGION_ALIASES.values():
        if any(_norm(a) in lower for a in region["aliases"]):
            return False
    # Pays catalogue (Brésil, Chili…) dans le message → pas une liste « tous les pays »
    if detect_catalog_country_query(message):
        return False
    if any(h in lower for h in ALL_DESTINATIONS_HINTS):
        return True
    if re.search(
        r"\b(autres?|toutes?|quelles?|liste)\b.{0,40}\bdestinations?\b"
        r"|\bdestinations?\b.{0,40}\b(autres?|toutes?|quelles?|liste|avez|avons)\b",
        lower,
    ):
        return True
    return False


def _has_catalog_question_hint(message: str, lower: str) -> bool:
    if "?" in message:
        return True
    if any(h in lower for h in COUNTRY_QUERY_HINTS):
        return True
    return bool(CATALOG_QUESTION_RE.search(message))


def find_catalog_destination_in_message(message: str, loader=None) -> str | None:
    """Ville catalogue mentionnée dans le message (nom ou alias, tolère typos courtes)."""
    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader
    lower = _norm(message)

    best: tuple[int, str] | None = None
    for row in loader.load_destinations():
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
        return best[1]

    for token in re.findall(r"[\wàâäéèêëïîôùûüç'-]+", message, re.I):
        if len(token) < 4:
            continue
        resolved = loader.resolve_destination_name(token)
        if resolved:
            return resolved
    return None


def region_key_for_pays(pays: str) -> str | None:
    if not (pays or "").strip():
        return None
    for key, label in REGION_PAYS.items():
        if _norm(label) == _norm(pays):
            return key
    return resolve_catalog_country_key(pays)


def region_key_for_destination(destination_name: str, loader=None) -> str | None:
    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader
    row = loader.get_destination_by_name(destination_name)
    if not row:
        return None
    return region_key_for_pays(str(row.get("pays") or ""))


def detect_country_query(message: str, loader=None) -> str | None:
    """Détecte une question sur les destinations d'un pays/région/continent."""
    from services.data_loader import data_loader as default_loader

    loader = loader or default_loader
    lower = _norm(message)
    if not lower:
        return None

    # Titre d'activité collé ≠ demande pays/continent
    if _looks_like_activity_title_paste(message):
        return None

    if detect_all_destinations_query(message):
        return "all"

    # Pays catalogue d'abord (bresil ≠ continent Amériques)
    country = detect_catalog_country_query(message, loader)
    if country:
        return country

    continent = detect_continent_query(message)
    if continent:
        return continent

    has_query_hint = _has_catalog_question_hint(message, lower)

    for region_key, region in REGION_ALIASES.items():
        aliases = [_norm(a) for a in region["aliases"]]
        if not any(alias in lower for alias in aliases):
            continue
        if has_query_hint:
            return region_key
        for alias in aliases:
            if lower.strip().rstrip("?.!,;:") == alias:
                return region_key

    if has_query_hint:
        city = find_catalog_destination_in_message(message, loader)
        if city:
            region = region_key_for_destination(city, loader)
            if region:
                return region

    return None


def region_label(region_key: str, loader=None) -> str:
    if region_key in REGION_LABELS:
        return REGION_LABELS[region_key]
    catalog = get_catalog_countries(loader)
    if region_key in catalog:
        return _label_article(str(catalog[region_key]["label"]))
    return region_key


def build_country_catalog_reply(
    region_key: str,
    cities: list[str],
    *,
    context_note: str = "",
) -> str:
    label = region_label(region_key)
    note = f" {context_note.strip()}" if (context_note or "").strip() else ""
    if not cities:
        return (
            f"Nous n'avons pas encore d'activités cataloguées pour {label}.{note} "
            f"Souhaitez-vous explorer une autre destination ?"
        )
    if region_key == "all":
        # Grouper par pays pour lisibilité
        result = list_destinations(query="all")
        by_pays = result.get("by_pays") or {}
        if isinstance(by_pays, dict) and by_pays:
            parts = [f"{pays} ({', '.join(villes)})" for pays, villes in by_pays.items()]
            preview = "; ".join(parts[:12])
            extra = len(parts) - 12
            suffix = f" … et {extra} autre(s) pays." if extra > 0 else "."
            return (
                f"Voici les destinations de notre catalogue : {preview}{suffix}{note} "
                f"Laquelle souhaitez-vous explorer ?"
            )
        joined = ", ".join(cities[:20])
        more = f" (et {len(cities) - 20} autres)" if len(cities) > 20 else ""
        return (
            f"Voici les destinations de notre catalogue : {joined}{more}.{note} "
            f"Laquelle souhaitez-vous explorer ?"
        )
    if len(cities) == 1:
        city = cities[0]
        return (
            f"Dans notre catalogue pour {label}, nous avons des activités à {city} uniquement.{note} "
            f"Souhaitez-vous explorer {city} ?"
        )
    joined = ", ".join(cities)
    return (
        f"Dans notre catalogue pour {label}, nous proposons des activités à : {joined}.{note} "
        f"Laquelle souhaitez-vous explorer ?"
    )


def format_qualification_note(slots: dict) -> str:
    """Résumé court budget / profil / durée déjà notés."""
    bits: list[str] = []
    budget = str(slots.get("budget", "") or "").strip()
    profil = str(slots.get("profil_voyageur", "") or "").strip()
    duree = str(slots.get("duree", "") or "").strip()
    if budget:
        bits.append(f"budget ~{budget} €")
    if profil:
        bits.append(f"profil {profil.replace('_', ' ')}")
    if duree:
        bits.append(duree)
    if not bits:
        return ""
    return "Noté : " + ", ".join(bits) + "."
