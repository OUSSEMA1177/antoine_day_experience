"""Tool definitions and execution for the agent."""

from __future__ import annotations

import json
from typing import Any, Callable

from memory.memory_manager import memory_manager
from search.catalog_search import CatalogSearchParams, catalog_search
from search.geo import list_destinations
from agent.destination_policy import activate_catalog_destination, activate_unavailable_destination
from services.data_loader import data_loader

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Rechercher des activités dans le catalogue B2B. "
                "Filtres : destination, budget, profil, thèmes, mots-clés."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés (ex: montagne, plage, Tour Eiffel)"},
                    "destination": {"type": "string", "description": "Ville ou destination"},
                    "budget_max": {"type": "string", "description": "Budget max par personne en euros"},
                    "profil": {"type": "string", "description": "famille, couple, solo, groupe"},
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Thèmes : mer/plage, montagne, foret, nature, sahara, "
                            "aventure, culture, gastronomie, détente, croisiere"
                        ),
                    },
                    "region": {
                        "type": "string",
                        "description": (
                            "Continent ou pays catalogue : asie, europe, afrique, "
                            "amerique, moyen_orient, maroc, france…"
                        ),
                    },
                    "limit": {"type": "string", "description": "Nombre max de résultats (défaut 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_destinations",
            "description": (
                "Lister les destinations/villes réellement présentes dans le catalogue Day Experience. "
                "OBLIGATOIRE avant de répondre à : pays d'un continent (Asie, Europe…), "
                "« autres destinations », « quelles destinations avez-vous », "
                "ou toute question sur la couverture géographique. "
                "Ne jamais inventer de villes — utiliser uniquement le résultat de cet outil."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "continent": {
                        "type": "string",
                        "description": "asie | europe | afrique | amerique | moyen_orient",
                    },
                    "pays": {
                        "type": "string",
                        "description": "Filtrer par pays (ex: Japon, Italie, Maroc)",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Texte libre : continent, pays, ou 'all' pour tout le catalogue"
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_details",
            "description": "Obtenir le détail d'une activité par son identifiant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {"type": "string", "description": "ID de l'activité"},
                },
                "required": ["activity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Consulter le statut d'une commande à partir de sa référence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "Référence commande (ex: DEMO-001)"},
                },
                "required": ["reference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_faq",
            "description": "Rechercher une réponse dans la FAQ Day Experience.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question ou mots-clés"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_advisor",
            "description": (
                "Escalade hors chat : remboursement, litige, réclamation, plainte. "
                "Retourne support_email — indiquer au partenaire d'écrire à cette adresse. "
                "Ne pas promettre un rappel dans le chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Motif de l'escalade"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quote",
            "description": "Générer un devis White Label PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "activity_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["destination", "activity_ids"],
            },
        },
    },
]


def _format_activities(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": row.get("id", ""),
            "titre": row.get("titre", ""),
            "prix": row.get("prix") or row.get("prix_public", ""),
            "prix_public": row.get("prix_public", ""),
            "duree": row.get("duree", ""),
            "langues": row.get("langues", ""),
            "profil_cible": row.get("profil_cible", ""),
            "destination_id": row.get("destination_id", ""),
        }
        for row in rows
    ]


def _parse_limit(value: Any, default: int = 20) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _parse_budget(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _search_catalog(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    themes = args.get("themes")
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    region = args.get("region") or args.get("continent")
    params = CatalogSearchParams(
        query=str(args.get("query", "") or ""),
        destination=args.get("destination"),
        budget_max=_parse_budget(args.get("budget_max")),
        profil=args.get("profil"),
        themes=themes,
        region=str(region).strip() if region else None,
        limit=_parse_limit(args.get("limit")),
    )
    result = catalog_search(params)
    if args.get("destination"):
        raw_dest = str(args["destination"]).strip()
        if activate_catalog_destination(session_id, raw_dest):
            pass
        else:
            activate_unavailable_destination(session_id, raw_dest)
    if region:
        memory_manager.update_slots(session_id, region_interest=str(region).strip())
    if args.get("budget_max") is not None:
        memory_manager.update_slots(session_id, budget=str(args["budget_max"]))
    if args.get("profil"):
        memory_manager.update_slots(session_id, profil_voyageur=str(args["profil"]))
    if themes:
        memory_manager.update_slots(session_id, envies=", ".join(themes))
    return {
        "count": result.count,
        "activities": _format_activities(result.activities),
        "meta": result.meta,
    }


def _search_activities(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return _search_catalog(session_id, args)


def _recommend_experiences(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    merged = {**args}
    if args.get("destination") and not args.get("query"):
        merged["query"] = str(args.get("destination"))
    out = _search_catalog(session_id, merged)
    return {"recommendations": out.get("activities", []), "meta": out.get("meta", {})}


def _list_destinations(_session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    continent = str(args.get("continent") or "").strip() or None
    pays = str(args.get("pays") or "").strip() or None
    query = str(args.get("query") or "").strip() or None
    if not continent and not pays and not query:
        query = "all"
    return list_destinations(continent=continent, pays=pays, query=query)


def _get_activity_details(_session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    row = data_loader.get_activity_by_id(str(args.get("activity_id", "")))
    if not row:
        return {"error": "Activité introuvable"}
    return {"activity": row}


def _get_order_status(_session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    row = data_loader.get_order_by_reference(str(args.get("reference", "")))
    if not row:
        return {"error": "Commande introuvable", "reference": args.get("reference")}
    return {"order": row}


def _search_faq(_session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    rows = data_loader.search_faq(str(args.get("query", "")), limit=3)
    return {"results": rows}


def _escalate_to_advisor(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    from agent.support_policy import escalate_session

    return escalate_session(session_id, reason=str(args.get("reason", "") or ""))


def _generate_quote(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    from pdf.quote_generator import generate_quote_for_session

    activity_ids = [str(aid) for aid in (args.get("activity_ids") or [])]
    destination = str(args.get("destination", "") or "").strip()
    if not destination:
        slots = memory_manager.get_slots(session_id)
        destination = str(slots.get("destination", "") or "").strip()
    if not destination:
        return {"status": "error", "message": "Destination requise pour le devis."}
    if not activity_ids:
        return {"status": "error", "message": "Sélectionnez au moins une activité (activity_ids)."}

    try:
        return generate_quote_for_session(
            session_id=session_id,
            destination=destination,
            activity_ids=activity_ids,
        )
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "message": f"Échec génération PDF : {exc}"}


_HANDLERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "search_catalog": _search_catalog,
    "search_activities": _search_activities,
    "recommend_experiences": _recommend_experiences,
    "list_destinations": _list_destinations,
    "get_activity_details": _get_activity_details,
    "get_order_status": _get_order_status,
    "search_faq": _search_faq,
    "escalate_to_advisor": _escalate_to_advisor,
    "generate_quote": _generate_quote,
}


def execute_tool(session_id: str, name: str, arguments: dict[str, Any]) -> str:
    handler = _HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Outil inconnu: {name}"}, ensure_ascii=False)
    try:
        result = handler(session_id, arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
