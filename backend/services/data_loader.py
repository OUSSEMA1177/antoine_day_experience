"""
Lecture et cache des fichiers CSV du MVP Day Experience AI.

Point d'accès unique aux données pour l'API, l'agent et les tools.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from search.geo import expand_to_keywords

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ACTIVITIES_FILE = "activities.csv"
DESTINATIONS_FILE = "destinations.csv"
PARTNERS_FILE = "partners.csv"
FAQ_FILE = "faq.csv"
ORDERS_FILE = "orders.csv"
POLICIES_FILE = "policies.csv"


def _parse_price(value: str | None) -> float | None:
    if not value or not str(value).strip():
        return None
    cleaned = str(value).strip().replace(",", ".")
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _norm(text: str | None) -> str:
    return (text or "").strip().casefold()


class DataLoader:
    """Charge les CSV une fois en mémoire et recharge si le fichier change."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _read_csv(self, filename: str) -> list[dict[str, str]]:
        path = self.data_dir / filename
        if not path.exists():
            return []

        mtime = path.stat().st_mtime
        cached = self._cache.get(filename)
        if cached and cached[0] == mtime:
            return cached[1]

        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self._cache[filename] = (mtime, rows)
        return rows

    # --- Chargement brut ---

    def load_activities(self) -> list[dict[str, str]]:
        return self._read_csv(ACTIVITIES_FILE)

    def load_destinations(self) -> list[dict[str, str]]:
        return self._read_csv(DESTINATIONS_FILE)

    def load_partners(self) -> list[dict[str, str]]:
        return self._read_csv(PARTNERS_FILE)

    def load_faq(self) -> list[dict[str, str]]:
        return self._read_csv(FAQ_FILE)

    def load_orders(self) -> list[dict[str, str]]:
        rows = self._read_csv(ORDERS_FILE)
        return [r for r in rows if any(v.strip() for v in r.values() if v)]

    def load_policies(self) -> list[dict[str, str]]:
        rows = self._read_csv(POLICIES_FILE)
        return [r for r in rows if r.get("activite_id", "").strip()]

    # --- Destinations ---

    def get_destination_by_id(self, destination_id: str | int) -> dict[str, str] | None:
        target = str(destination_id).strip()
        for row in self.load_destinations():
            if row.get("id", "").strip() == target:
                return row
        return None

    def get_destination_by_name(self, name: str) -> dict[str, str] | None:
        needle = _norm(name)
        if not needle:
            return None
        for row in self.load_destinations():
            if _norm(row.get("nom")) == needle:
                return row
        for row in self.load_destinations():
            if needle in _norm(row.get("nom")):
                return row
        return None

    def resolve_destination_id(
        self,
        destination_id: str | int | None = None,
        destination_name: str | None = None,
    ) -> str | None:
        if destination_id is not None and str(destination_id).strip():
            if self.get_destination_by_id(destination_id):
                return str(destination_id).strip()
        if destination_name:
            dest = self.get_destination_by_name(destination_name)
            if dest:
                return dest.get("id", "").strip() or None
        return None

    # --- Activités ---

    def get_activity_by_id(self, activity_id: str | int) -> dict[str, str] | None:
        target = str(activity_id).strip()
        for row in self.load_activities():
            if row.get("id", "").strip() == target:
                return row
        return None

    def search_activities(
        self,
        *,
        destination_id: str | int | None = None,
        destination_name: str | None = None,
        budget_max: float | None = None,
        profil: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        resolved_id = self.resolve_destination_id(destination_id, destination_name)
        profil_norm = _norm(profil) if profil else None
        query_norm = _norm(query) if query else None

        if destination_name and not resolved_id and destination_id is None and not query_norm:
            return []

        results: list[dict[str, str]] = []
        for row in self.load_activities():
            if resolved_id and row.get("destination_id", "").strip() != resolved_id:
                continue

            if budget_max is not None:
                price = _parse_price(row.get("prix")) or _parse_price(row.get("prix_public"))
                if price is None or price > budget_max:
                    continue

            if profil_norm and profil_norm not in _norm(row.get("profil_cible")):
                continue

            if query_norm:
                haystack = _norm(
                    " ".join(
                        [
                            row.get("titre", ""),
                            row.get("description", ""),
                            row.get("langues", ""),
                            row.get("categorie", ""),
                        ]
                    )
                )
                if query_norm not in haystack:
                    continue

            results.append(row)
            if limit is not None and len(results) >= limit:
                break

        return results

    def _search_by_text_in_activities(
        self,
        needle: str,
        *,
        budget_max: float | None = None,
        profil: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        needle_norm = _norm(needle)
        if not needle_norm:
            return []

        profil_norm = _norm(profil) if profil else None
        results: list[dict[str, str]] = []
        seen_ids: set[str] = set()

        for row in self.load_activities():
            activity_id = row.get("id", "").strip()
            if not activity_id or activity_id in seen_ids:
                continue

            dest = self.get_destination_by_id(row.get("destination_id", ""))
            haystack = _norm(
                " ".join(
                    [
                        row.get("titre", ""),
                        row.get("description", ""),
                        row.get("categorie", ""),
                        dest.get("nom", "") if dest else "",
                        dest.get("pays", "") if dest else "",
                        dest.get("region", "") if dest else "",
                    ]
                )
            )
            if needle_norm not in haystack:
                continue

            if budget_max is not None:
                price = _parse_price(row.get("prix")) or _parse_price(row.get("prix_public"))
                if price is None or price > budget_max:
                    continue

            if profil_norm and profil_norm not in _norm(row.get("profil_cible")):
                continue

            seen_ids.add(activity_id)
            results.append(row)
            if limit is not None and len(results) >= limit:
                break

        return results

    def search_activities_smart(
        self,
        *,
        destination_name: str | None = None,
        budget_max: float | None = None,
        profil: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """
        Recherche activités avec résolution élargie (pays → villes du catalogue, titre…).
        Retourne (résultats, métadonnées de résolution).
        """
        limit = limit or 5
        label = (destination_name or query or "").strip()

        rows = self.search_activities(
            destination_name=destination_name,
            budget_max=budget_max,
            profil=profil,
            query=query,
            limit=limit,
        )
        if rows:
            return rows, {"matched_by": "destination", "label": label or "catalogue"}

        if profil and destination_name:
            rows = self.search_activities(
                destination_name=destination_name,
                budget_max=budget_max,
                profil=None,
                query=query,
                limit=limit,
            )
            if rows:
                return rows, {
                    "matched_by": "destination_profil_relaxed",
                    "label": label or "catalogue",
                }

        search_terms: list[str] = []
        if destination_name:
            search_terms.extend(expand_to_keywords(destination_name))
        if query and query not in search_terms:
            search_terms.extend(expand_to_keywords(query))

        seen_ids: set[str] = set()
        merged: list[dict[str, str]] = []
        matched_keyword = ""

        for term in search_terms:
            for row in self._search_by_text_in_activities(
                term,
                budget_max=budget_max,
                profil=profil,
                limit=None,
            ):
                activity_id = row.get("id", "").strip()
                if activity_id in seen_ids:
                    continue
                seen_ids.add(activity_id)
                merged.append(row)
                if not matched_keyword:
                    matched_keyword = term
                if len(merged) >= limit:
                    break
            if len(merged) >= limit:
                break

        if merged:
            meta = {
                "matched_by": "region" if expand_to_keywords(label) != [label] else "text",
                "label": matched_keyword or label,
                "original": label,
            }
            return merged, meta

        return [], {"matched_by": "none", "label": label}

    # Termes de recherche par envie (pour scoring recommandations)
    ENVIE_SEARCH_TERMS: dict[str, list[str]] = {
        "mer": ["mer", "essaouira", "mogador", "bateau", "plage", "côte", "cote", "atlantique"],
        "sahara": [
            "sahara",
            "désert",
            "desert",
            "merzouga",
            "agafay",
            "dune",
            "chameau",
            "dromadaire",
            "berbère",
            "berbere",
            "campement",
        ],
        "aventure": ["quad", "4x4", "buggy", "montgolfière", "montgolfiere", "safari", "buggy"],
        "culture": ["médina", "medina", "souk", "palais", "musée", "musee", "monument", "bahia"],
        "gastronomie": ["dîner", "diner", "restaurant", "gastronom", "spectacle", "repas"],
        "détente": ["spa", "jardin", "calèche", "caleche", "botanique"],
        "nature": ["atlas", "ouzoud", "ourika", "cascade", "montagne", "vallée", "vallee"],
    }

    FAMILY_BOOST_TERMS = (
        "aquatique",
        "chameau",
        "dromadaire",
        "parc",
        "famille",
        "calèche",
        "caleche",
        "jardin",
        "enfant",
    )

    def _activity_haystack(self, row: dict[str, str]) -> str:
        dest = self.get_destination_by_id(row.get("destination_id", ""))
        return _norm(
            " ".join(
                [
                    row.get("titre", ""),
                    row.get("description", ""),
                    row.get("categorie", ""),
                    row.get("profil_cible", ""),
                    dest.get("nom", "") if dest else "",
                ]
            )
        )

    def _score_activity(
        self,
        row: dict[str, str],
        *,
        envies: list[str] | None = None,
        profil: str | None = None,
    ) -> int:
        haystack = self._activity_haystack(row)
        score = 0
        profil_norm = _norm(profil) if profil else None
        row_profil = _norm(row.get("profil_cible"))

        if profil_norm:
            if profil_norm in row_profil:
                score += 4
            elif row_profil in ("", "general"):
                score += 2
            if profil_norm == "famille":
                if any(term in haystack for term in self.FAMILY_BOOST_TERMS):
                    score += 2

        for envie in envies or []:
            envie_key = _norm(envie)
            terms = self.ENVIE_SEARCH_TERMS.get(envie_key, [envie_key])
            for term in terms:
                if _norm(term) in haystack:
                    score += 3
                    break

        return score

    def recommend_activities(
        self,
        *,
        destination_name: str,
        envies: list[str] | None = None,
        profil: str | None = None,
        budget_max: float | None = None,
        query: str | None = None,
        limit: int = 8,
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """
        Recommande des activités pour une destination avec scoring profil/envies.
        Ne filtre pas strictement sur profil=famille : inclut general avec score.
        """
        pool, meta = self.search_activities_smart(
            destination_name=destination_name,
            budget_max=budget_max,
            query=query,
            limit=50 if query else 40,
        )
        if not pool:
            return [], meta

        if query:
            query_norm = _norm(query)
            filtered = [row for row in pool if query_norm in self._activity_haystack(row)]
            if filtered:
                pool = filtered
                meta = {**meta, "query": query, "matched_by": "product"}

        envie_list = [_norm(e) for e in (envies or []) if e.strip()]
        scored = [
            (self._score_activity(row, envies=envie_list, profil=profil), row)
            for row in pool
        ]
        scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))

        if envie_list or profil:
            positive = [row for score, row in scored if score > 0]
            results = positive[:limit] if positive else [row for _, row in scored[:limit]]
            meta = {
                **meta,
                "recommendation": True,
                "profil": profil or "",
                "envies": ", ".join(envies or []),
                "profil_strict_match": bool(profil and any(
                    _norm(profil) in _norm(r.get("profil_cible", "")) for r in results
                )),
            }
            return results, meta

        return [row for _, row in scored[:limit]], meta

    def search_theme_across_destinations(
        self,
        theme: str,
        *,
        excluded_destinations: list[str] | None = None,
        envies: list[str] | None = None,
        profil: str | None = None,
        limit_per_destination: int = 4,
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Legacy — préférer search.catalog_search.catalog_search."""
        from search.catalog_search import CatalogSearchParams, catalog_search

        params = CatalogSearchParams(
            query=theme,
            profil=profil,
            themes=envies or [theme],
            limit=limit_per_destination * 5,
        )
        result = catalog_search(params, self)
        return result.activities, result.meta

    def search_by_distinctive_tokens(
        self, tokens: list[str], limit: int = 5
    ) -> list[dict[str, str]]:
        """Recherche globale par mots distinctifs (titres) — pour produits hors destination connue."""
        seen_ids: set[str] = set()
        results: list[dict[str, str]] = []
        for token in tokens:
            for row in self._search_by_text_in_activities(token, limit=None):
                aid = row.get("id", "").strip()
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                results.append(row)
                if len(results) >= limit:
                    return results
        return results

    # --- FAQ ---

    def search_faq(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        needle = _norm(query)
        if not needle:
            return []

        scored: list[tuple[int, dict[str, str]]] = []
        for row in self.load_faq():
            question = _norm(row.get("question"))
            answer = _norm(row.get("reponse"))
            score = 0
            if needle in question:
                score += 2
            if needle in answer:
                score += 1
            if score:
                scored.append((score, row))

        scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))
        return [row for _, row in scored[:limit]]

    # --- Partenaires ---

    def get_partner_by_id(self, partner_id: str | int) -> dict[str, str] | None:
        target = str(partner_id).strip()
        for row in self.load_partners():
            if row.get("id", "").strip() == target:
                return row
        return None

    # --- Commandes / policies (vides pour l'instant) ---

    def get_order_by_reference(self, reference: str) -> dict[str, str] | None:
        ref = reference.strip().casefold()
        for row in self.load_orders():
            if row.get("reference", "").strip().casefold() == ref:
                return row
        return None

    def get_policy_by_activity_id(self, activity_id: str | int) -> dict[str, str] | None:
        target = str(activity_id).strip()
        for row in self.load_policies():
            if row.get("activite_id", "").strip() == target:
                return row
        activity = self.get_activity_by_id(target)
        if activity and activity.get("conditions_annulation", "").strip():
            return {
                "activite_id": target,
                "conditions_annulation": activity["conditions_annulation"],
                "delai_remboursement": "",
                "politique_commerciale": "",
            }
        return None


# Instance partagée pour l'application (import simple dans routes / agent)
data_loader = DataLoader()
