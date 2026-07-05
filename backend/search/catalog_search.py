"""Recherche unifiée catalogue — remplace prefetch + thèmes + destination_resolver."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from typing import Any

from agent.context_manager import is_tunnel_slot_message
from search.geo import detect_landmark, resolve_destination_name
from search.ranking import ENVIE_TERMS, rank_activities, tokenize_query
from services.data_loader import _parse_price, data_loader

CATALOG_RULES = (
    "RÈGLES CATALOGUE (obligatoires) :\n"
    "- Cite UNIQUEMENT les activités listées ci-dessous avec titres et prix_net exacts.\n"
    "- INTERDIT d'inventer des activités, prix, durées, logements ou disponibilités.\n"
    "- INTERDIT de proposer un devis sans activités listées ci-dessous.\n"
    "- Si count=0 : dire honnêtement qu'aucune activité ne correspond et proposer d'élargir la recherche."
)

ORDER_REF_RE = re.compile(r"\b([A-Z]{2,}-\d{3,})\b", re.IGNORECASE)


@dataclass
class CatalogSearchParams:
    query: str = ""
    destination: str | None = None
    budget_max: float | None = None
    profil: str | None = None
    themes: list[str] | None = None
    langue: str | None = None
    limit: int = 20


@dataclass
class CatalogSearchResult:
    activities: list[dict[str, str]] = field(default_factory=list)
    scores: list[int] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    tools_used: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.activities)

    def has_results(self) -> bool:
        return self.count > 0

    def format_activity(self, row: dict[str, str]) -> dict[str, str]:
        dest = data_loader.get_destination_by_id(row.get("destination_id", ""))
        zone = (dest or {}).get("nom", "") or row.get("destination_id", "")
        return {
            "id": row.get("id", ""),
            "titre": row.get("titre", ""),
            "zone_catalogue": zone,
            "prix_net": row.get("prix", ""),
            "prix_public": row.get("prix_public", ""),
            "duree": row.get("duree", ""),
            "langues": row.get("langues", ""),
            "profil_cible": row.get("profil_cible", "") or "general",
        }

    def to_prompt_block(self, note: str = "") -> str:
        items = [self.format_activity(r) for r in self.activities]
        header = note or self.meta.get("note", "Résultats catalogue")
        payload = {"count": len(items), "activities": items}
        if self.scores and len(self.scores) == len(items):
            for i, item in enumerate(items):
                item["score"] = self.scores[i]
        return f"{header}\n{CATALOG_RULES}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def _effective_query(query: str) -> str | None:
    text = (query or "").strip()
    if not text or is_tunnel_slot_message(text):
        return None
    return text


def _theme_search_terms(raw_query: str | None, themes: list[str]) -> list[str]:
    terms: list[str] = []
    for theme in themes:
        terms.extend(ENVIE_TERMS.get(theme, [theme]))
    text = (raw_query or "").strip()
    if not text:
        return list(dict.fromkeys(t for t in terms if t))
    terms.extend(tokenize_query(text))
    lower = text.casefold()
    if "plage" in lower or "mer" in lower or "océan" in lower or "ocean" in lower:
        terms.extend(ENVIE_TERMS.get("mer", []))
    if "sahara" in lower or "désert" in lower or "desert" in lower:
        terms.extend(ENVIE_TERMS.get("sahara", []))
    if "montagne" in lower or "nature" in lower or "alpes" in lower:
        terms.extend(ENVIE_TERMS.get("nature", []))
    if "aventure" in lower:
        terms.extend(ENVIE_TERMS.get("aventure", []))
    return list(dict.fromkeys(t for t in terms if t))


def _pool_from_themes_and_query(
    loader: Any,
    raw_query: str | None,
    themes: list[str],
    *,
    budget_max: float | None,
    limit: int = 200,
) -> list[dict[str, str]]:
    """Recherche thématique sans destination — jamais tout le catalogue."""
    search_terms = _theme_search_terms(raw_query, themes)
    if not search_terms and raw_query:
        search_terms = [raw_query.strip()]

    seen: set[str] = set()
    pool: list[dict[str, str]] = []
    for term in search_terms:
        for row in loader._search_by_text_in_activities(
            term,
            budget_max=budget_max,
            profil=None,
            limit=40,
        ):
            aid = row.get("id", "").strip()
            if aid and aid not in seen:
                seen.add(aid)
                pool.append(row)
            if len(pool) >= limit:
                return pool
    return pool


def catalog_search(
    params: CatalogSearchParams,
    loader: Any | None = None,
) -> CatalogSearchResult:
    """Point d'entrée unique : filtrage + scoring + top K."""
    loader = loader or data_loader
    result = CatalogSearchResult(tools_used=["search_catalog"])

    pool: list[dict[str, str]] = []
    meta: dict[str, str] = {}

    dest = (params.destination or "").strip()
    search_query = _effective_query(params.query)
    resolved_dest: str | None = None

    if dest:
        resolved = resolve_destination_name(dest, loader)
        if resolved:
            resolved_dest = resolved
            rows, smeta = loader.search_activities_smart(
                destination_name=resolved,
                budget_max=params.budget_max,
                profil=params.profil,
                query=search_query,
                limit=50,
            )
            pool = rows
            meta = {**smeta, "destination": resolved}
        else:
            meta = {"matched_by": "none", "destination": dest, "note": "destination_inconnue"}

    if not pool and resolved_dest:
        pool = loader.search_activities(
            destination_name=resolved_dest,
            budget_max=params.budget_max,
            profil=None,
            query=search_query,
            limit=50,
        )
        if pool:
            meta = {**meta, "matched_by": "destination_only", "destination": resolved_dest}

    if not pool and not resolved_dest:
        pool = _pool_from_themes_and_query(
            loader,
            params.query,
            params.themes or [],
            budget_max=params.budget_max,
        )
        if pool:
            meta = {"matched_by": "theme_text", "note": "recherche_thematique_sans_destination"}

    themes = params.themes or []
    query = " ".join(filter(None, [search_query or "", dest, *themes]))
    ranked = rank_activities(
        loader,
        pool,
        query=query,
        profil=params.profil,
        themes=themes,
        limit=params.limit,
    )

    result.activities = [row for _, row in ranked]
    result.scores = [score for score, _ in ranked]
    result.meta = {
        **meta,
        "matched_by": meta.get("matched_by", "catalog_search"),
        "query_tokens": ", ".join(tokenize_query(query)),
    }
    if result.has_results():
        zones = {
            result.format_activity(r)["zone_catalogue"]
            for r in result.activities
        }
        result.meta["destinations"] = ", ".join(sorted(z for z in zones if z))
    return result


def search_from_context(
    message: str,
    slots: dict[str, str | list[str]],
    *,
    loader: Any | None = None,
) -> CatalogSearchResult:
    """Recherche à partir du message utilisateur + slots mémoire session."""
    loader = loader or data_loader
    themes_raw = str(slots.get("envies", "") or "")
    themes = [t.strip() for t in themes_raw.split(",") if t.strip()]

    budget_raw = slots.get("budget")
    budget: float | None = None
    if budget_raw:
        try:
            budget = float(str(budget_raw).replace(",", "."))
        except (TypeError, ValueError):
            budget = None

    destination = str(slots.get("destination", "") or "").strip() or None
    profil = str(slots.get("profil_voyageur", "") or "").strip() or None

    landmark = detect_landmark(message)
    if landmark:
        destination, product_query = landmark
        params = CatalogSearchParams(
            query=product_query,
            destination=destination,
            budget_max=budget,
            profil=profil,
            themes=themes,
            limit=15,
        )
        result = catalog_search(params, loader)
        result.meta["note"] = f"Produit demandé : {product_query} — {destination}"
        return result

    params = CatalogSearchParams(
        query=message,
        destination=destination,
        budget_max=budget,
        profil=profil,
        themes=themes,
        limit=20,
    )
    result = catalog_search(params, loader)
    if result.has_results():
        if destination:
            result.meta["note"] = f"Activités catalogue pour {destination}"
        else:
            result.meta["note"] = (
                f"Recherche catalogue : « {message[:80]} » — "
                f"zones : {result.meta.get('destinations', '')}"
            )
    else:
        result.meta["note"] = (
            f"Aucune activité trouvée pour « {message[:80]} ». "
            "Ne pas inventer — proposer d'élargir ou escalader."
        )
    return result


def context_has_activities(context: str) -> bool:
    if not context or '"activities"' not in context:
        return False
    match = re.search(r'"count":\s*(\d+)', context)
    return bool(match and int(match.group(1)) > 0)


def append_order_and_faq(message: str, blocks: list[str], tools_used: list[str]) -> str:
    order_match = ORDER_REF_RE.search(message)
    if order_match:
        ref = order_match.group(1).upper()
        order = data_loader.get_order_by_reference(ref)
        tools_used.append("get_order_status")
        if order:
            blocks.append(f"Commande {ref} :\n{json.dumps(order, ensure_ascii=False, indent=2)}")
        else:
            blocks.append(f"Commande {ref} : introuvable.")

    faq_hints = ("commission", "annulation", "paiement", "facture", "remboursement")
    lower = message.casefold()
    if "?" in message or any(h in lower for h in faq_hints):
        faq_rows = data_loader.search_faq(message, limit=3)
        if faq_rows:
            tools_used.append("search_faq")
            blocks.append("FAQ :\n" + json.dumps(faq_rows, ensure_ascii=False, indent=2))

    return "\n\n".join(blocks)
