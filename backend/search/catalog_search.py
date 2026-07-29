"""Recherche unifiée catalogue — remplace prefetch + thèmes + destination_resolver."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from typing import Any

from agent.context_manager import is_tunnel_slot_message
from agent.destination_policy import refers_to_previous_place
from search.geo import (
    detect_continent_query,
    detect_country_query,
    detect_landmark,
    list_catalog_destinations_for_region,
    resolve_destination_name,
)
from search.ranking import rank_activities, tokenize_query
from search.themes import (
    canonicalize_theme,
    detect_themes_from_text,
    expand_theme_search_terms,
    term_in_text,
    themes_label,
)
from services.data_loader import _parse_price, data_loader

CATALOG_RULES = (
    "RÈGLES CATALOGUE (obligatoires) :\n"
    "- Cite UNIQUEMENT les activités listées ci-dessous avec titres et prix_net exacts.\n"
    "- INTERDIT d'inventer des activités, prix, durées, logements ou disponibilités.\n"
    "- INTERDIT de proposer un devis sans activités listées ci-dessous.\n"
    "- Si count=0 pour une destination demandée : dire qu'aucune activité n'existe pour cette ville. "
    "INTERDIT de proposer des activités dans d'autres pays ou villes."
)

# Fiche produit B2B Day Experience
B2B_ACTIVITY_URL_TEMPLATE = (
    "https://b2b.day-experience.com/produit.cfm?idActivity={id}"
)


def activity_product_url(activity_id: str | int | None) -> str:
    """URL fiche produit B2B pour un id catalogue."""
    aid = str(activity_id or "").strip()
    if not aid:
        return ""
    return B2B_ACTIVITY_URL_TEMPLATE.format(id=aid)


def format_activity_line(
    index: int,
    *,
    titre: str,
    prix_net: str = "",
    zone: str = "",
    activity_id: str | int | None = "",
) -> str:
    """Ligne liste pro : titre + prix + lien fiche (sans markdown **)."""
    title = (titre or "?").strip() or "?"
    prix = (prix_net or "?").strip() or "?"
    zone_txt = (zone or "").strip()
    mid = f" — {zone_txt}" if zone_txt else ""
    line = f"{index}. {title}{mid} — {prix} € (net)"
    url = activity_product_url(activity_id)
    if url:
        line = f"{line}\n   {url}"
    return line


ORDER_REF_RE = re.compile(r"\b([A-Z]{2,}-\d{3,})\b", re.IGNORECASE)


@dataclass
class CatalogSearchParams:
    query: str = ""
    destination: str | None = None
    budget_max: float | None = None
    profil: str | None = None
    themes: list[str] | None = None
    region: str | None = None
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
        aid = row.get("id", "")
        return {
            "id": aid,
            "titre": row.get("titre", ""),
            "zone_catalogue": zone,
            "prix_net": row.get("prix", ""),
            "prix_public": row.get("prix_public", ""),
            "duree": row.get("duree", ""),
            "langues": row.get("langues", ""),
            "profil_cible": row.get("profil_cible", "") or "general",
            "url": activity_product_url(aid),
        }

    def to_prompt_block(self, note: str = "", *, limit: int | None = None) -> str:
        rows = self.activities[:limit] if limit else self.activities
        scores = self.scores[: len(rows)] if self.scores else []
        items = [self.format_activity(r) for r in rows]
        header = note or self.meta.get("note", "Résultats catalogue")
        payload = {"count": len(items), "activities": items}
        if scores and len(scores) == len(items):
            for i, item in enumerate(items):
                item["score"] = scores[i]
        return f"{header}\n{CATALOG_RULES}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    def limited(self, limit: int) -> "CatalogSearchResult":
        """Copie avec activités tronquées (optimisation tokens LLM)."""
        return CatalogSearchResult(
            activities=list(self.activities[:limit]),
            scores=list(self.scores[:limit]),
            meta=dict(self.meta),
            tools_used=list(self.tools_used),
        )


def _effective_query(query: str) -> str | None:
    text = (query or "").strip()
    if not text or is_tunnel_slot_message(text):
        return None
    return text


def _normalize_themes(themes: list[str] | None, raw_query: str | None) -> list[str]:
    found: list[str] = []
    for theme in themes or []:
        key = canonicalize_theme(theme)
        if key and key not in found:
            found.append(key)
    for theme in detect_themes_from_text(raw_query or ""):
        if theme not in found:
            found.append(theme)
    return found


def _destination_names_for_region(region: str, loader: Any) -> set[str]:
    names = list_catalog_destinations_for_region(region, loader)
    return {n.strip() for n in names if n.strip()}


def _filter_pool_by_region(
    loader: Any,
    pool: list[dict[str, str]],
    region: str,
) -> list[dict[str, str]]:
    allowed = _destination_names_for_region(region, loader)
    if not allowed:
        return []
    allowed_norm = {n.casefold() for n in allowed}
    filtered: list[dict[str, str]] = []
    for row in pool:
        dest = loader.get_destination_by_id(row.get("destination_id", ""))
        nom = ((dest or {}).get("nom") or "").strip()
        if nom.casefold() in allowed_norm:
            filtered.append(row)
    return filtered


def _pool_from_themes_and_query(
    loader: Any,
    raw_query: str | None,
    themes: list[str],
    *,
    budget_max: float | None,
    region: str | None = None,
    limit: int = 200,
) -> list[dict[str, str]]:
    """Recherche thématique — jamais tout le catalogue ; matching mot entier."""
    search_terms = expand_theme_search_terms(raw_query, themes)
    if not search_terms and raw_query:
        search_terms = [t for t in tokenize_query(raw_query) if len(t) >= 4]

    seen: set[str] = set()
    pool: list[dict[str, str]] = []
    for term in search_terms:
        for row in loader._search_by_text_in_activities(
            term,
            budget_max=budget_max,
            profil=None,
            limit=60,
        ):
            hay = " ".join(
                [
                    row.get("titre", ""),
                    row.get("description", ""),
                    row.get("categorie", ""),
                ]
            )
            dest = loader.get_destination_by_id(row.get("destination_id", ""))
            if dest:
                hay = f"{hay} {dest.get('nom', '')} {dest.get('pays', '')}"
            if not term_in_text(term, hay):
                continue
            aid = row.get("id", "").strip()
            if aid and aid not in seen:
                seen.add(aid)
                pool.append(row)
            if len(pool) >= limit:
                break
        if len(pool) >= limit:
            break

    if region:
        pool = _filter_pool_by_region(loader, pool, region)
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
    themes = _normalize_themes(params.themes, params.query or search_query)
    region = (params.region or "").strip() or None
    resolved_dest: str | None = None

    if dest:
        resolved = resolve_destination_name(dest, loader)
        if resolved:
            resolved_dest = resolved
            # Pool large : profil = boost ranking uniquement (pas de filtre dur)
            rows, smeta = loader.search_activities_smart(
                destination_name=resolved,
                budget_max=params.budget_max,
                profil=None,
                query=search_query if not themes else None,
                limit=80,
            )
            pool = rows
            meta = {**smeta, "destination": resolved}
            if themes and pool:
                meta["note"] = f"Activités {themes_label(themes)} à {resolved}"
        else:
            meta = {
                "matched_by": "none",
                "destination": dest,
                "note": "destination_hors_catalogue",
            }

    if not pool and resolved_dest:
        pool = loader.search_activities(
            destination_name=resolved_dest,
            budget_max=params.budget_max,
            profil=None,
            query=None,
            limit=80,
        )
        if pool:
            meta = {**meta, "matched_by": "destination_only", "destination": resolved_dest}
        elif resolved_dest:
            meta = {
                **meta,
                "matched_by": "destination_empty",
                "destination": resolved_dest,
                "note": "aucune_activite_pour_destination",
            }

    # Recherche thématique (± continent) si pas de destination ville
    if not pool and not dest and (themes or search_query or region):
        pool = _pool_from_themes_and_query(
            loader,
            params.query,
            themes,
            budget_max=params.budget_max,
            region=region,
        )
        if pool:
            scope = f" ({region})" if region else ""
            meta = {
                "matched_by": "theme_region" if region else "theme_text",
                "note": (
                    f"Recherche {themes_label(themes) if themes else 'catalogue'}"
                    f"{scope}"
                ),
            }
            if region:
                meta["region"] = region
        elif region and themes:
            meta = {
                "matched_by": "theme_region_empty",
                "region": region,
                "note": (
                    f"Aucune activité « {themes_label(themes)} » "
                    f"dans cette zone catalogue"
                ),
            }

    ranked = rank_activities(
        loader,
        pool,
        query=" ".join(filter(None, [search_query or "", dest, *themes])),
        profil=params.profil,
        themes=themes or None,
        limit=params.limit,
    )

    result.activities = [row for _, row in ranked]
    result.scores = [score for score, _ in ranked]
    result.meta = {
        **meta,
        "matched_by": meta.get("matched_by", "catalog_search"),
        "query_tokens": ", ".join(
            tokenize_query(" ".join(filter(None, [search_query or "", dest, *themes])))
        ),
    }
    if themes:
        result.meta["themes"] = ", ".join(themes)
    if result.has_results():
        zones = {
            result.format_activity(r)["zone_catalogue"]
            for r in result.activities
        }
        result.meta["destinations"] = ", ".join(sorted(z for z in zones if z))
    return result


def build_theme_region_reply(
    region_key: str,
    themes: list[str],
    result: CatalogSearchResult,
) -> str:
    """Réponse déterministe thème + continent/pays (0 token LLM)."""
    from search.geo import REGION_LABELS

    label = REGION_LABELS.get(region_key, region_key)
    theme_txt = themes_label(themes)
    if not result.has_results():
        cities = list_catalog_destinations_for_region(region_key)
        joined = ", ".join(cities) if cities else "aucune ville"
        return (
            f"Aucune activité « {theme_txt} » n'est disponible pour {label} "
            f"dans notre catalogue actuel. Destinations couvertes : {joined}. "
            f"Souhaitez-vous explorer une autre envie ou une autre zone ?"
        )

    lines: list[str] = []
    for i, row in enumerate(result.activities[:6], start=1):
        item = result.format_activity(row)
        lines.append(
            format_activity_line(
                i,
                titre=item.get("titre") or "",
                prix_net=item.get("prix_net") or "",
                zone=item.get("zone_catalogue") or "",
                activity_id=item.get("id") or "",
            )
        )

    zones = sorted(
        {
            result.format_activity(r)["zone_catalogue"]
            for r in result.activities
            if result.format_activity(r)["zone_catalogue"]
        }
    )
    dest_hint = zones[0] if len(zones) == 1 else "l'une de ces destinations"
    body = "\n".join(lines)
    return (
        f"Voici des activités « {theme_txt} » pour {label} dans notre catalogue :\n"
        f"{body}\n"
        f"Souhaitez-vous explorer {dest_hint} ?"
    )


def build_region_activities_reply(
    region_key: str,
    result: CatalogSearchResult,
    *,
    budget_max: float | None = None,
    context_note: str = "",
    fallback_without_budget: CatalogSearchResult | None = None,
) -> str:
    """Réponse 0 token : activités sur un pays/région (avec budget éventuel)."""
    from search.geo import REGION_LABELS, build_country_catalog_reply, list_catalog_destinations_for_region

    label = REGION_LABELS.get(region_key, region_key)
    note = f" {context_note.strip()}" if (context_note or "").strip() else ""
    cities = list_catalog_destinations_for_region(region_key)
    budget_txt = f" (≤ {int(budget_max)} € net)" if budget_max else ""

    if not result.has_results():
        # Rien sous budget → montrer les moins chères hors plafond
        if budget_max and fallback_without_budget and fallback_without_budget.has_results():
            lines: list[str] = []
            for i, row in enumerate(fallback_without_budget.activities[:5], start=1):
                item = fallback_without_budget.format_activity(row)
                lines.append(
                    format_activity_line(
                        i,
                        titre=item.get("titre") or "",
                        prix_net=item.get("prix_net") or "",
                        zone=item.get("zone_catalogue") or "",
                        activity_id=item.get("id") or "",
                    )
                )
            body = "\n".join(lines)
            return (
                f"Aucune activité à ≤ {int(budget_max)} € net pour {label}.{note}\n"
                f"Voici les options les moins chères du catalogue :\n"
                f"{body}\n"
                f"Dites « augmentez le budget » pour élargir, ou choisissez une ville "
                f"({', '.join(cities[:4])}{'…' if len(cities) > 4 else ''})."
            )
        city_reply = build_country_catalog_reply(region_key, cities, context_note=context_note)
        if budget_max:
            return (
                f"Aucune activité à ≤ {int(budget_max)} € net pour {label} "
                f"dans notre catalogue actuel.{note} "
                f"Villes couvertes : {', '.join(cities) if cities else '—'}. "
                f"Souhaitez-vous augmenter le budget ou choisir une ville ?"
            )
        return city_reply

    lines = []
    for i, row in enumerate(result.activities[:6], start=1):
        item = result.format_activity(row)
        lines.append(
            format_activity_line(
                i,
                titre=item.get("titre") or "",
                prix_net=item.get("prix_net") or "",
                zone=item.get("zone_catalogue") or "",
                activity_id=item.get("id") or "",
            )
        )

    body = "\n".join(lines)
    return (
        f"Voici des idées d'activités pour {label}{budget_txt} :\n"
        f"{body}\n"
        f"{note} "
        f"Indiquez le(s) numéro(s) qui vous intéressent, ou précisez une ville "
        f"({', '.join(cities[:4])}{'…' if len(cities) > 4 else ''})."
    ).replace("\n \n", "\n").strip()


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
    themes = _normalize_themes(themes, message)

    budget_raw = slots.get("budget")
    budget: float | None = None
    if budget_raw:
        try:
            budget = float(str(budget_raw).replace(",", "."))
        except (TypeError, ValueError):
            budget = None

    destination = str(slots.get("destination", "") or "").strip() or None
    if not destination:
        demandee = str(slots.get("destination_demandee", "") or "").strip()
        if demandee:
            result = CatalogSearchResult()
            result.meta = {
                "destination": demandee,
                "note": "destination_hors_catalogue",
                "matched_by": "none",
            }
            return result

    profil = str(slots.get("profil_voyageur", "") or "").strip() or None

    region = str(slots.get("region_interest", "") or "").strip() or None
    msg_region = detect_country_query(message) or detect_continent_query(message)
    if msg_region and msg_region != "all":
        region = msg_region
    elif refers_to_previous_place(message) and region:
        pass  # garder region_interest
    elif destination:
        region = None  # destination ville prime

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
        themes=themes or None,
        region=region if not destination else None,
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
