"""Planification du prochain pas agent (question, recherche, outil)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.intent_detector import Intent


class Action(str, Enum):
    ASK_DESTINATION = "ask_destination"
    ASK_PROFIL = "ask_profil"
    ASK_ENVIES = "ask_envies"
    SEARCH_CATALOG = "search_catalog"
    PRESENT_RESULTS = "present_results"
    CONFIRM_QUOTE = "confirm_quote"
    USE_TOOLS = "use_tools"
    ESCALATE = "escalate"


@dataclass
class Plan:
    action: Action
    reason: str
    one_question_only: bool = True


def _filled(slots: dict, key: str) -> bool:
    v = slots.get(key)
    return bool(str(v or "").strip())


def plan_next(
    intent: Intent,
    slots: dict[str, str | list[str]],
    *,
    has_catalog_results: bool,
    escalated: bool,
) -> Plan:
    if escalated or intent == Intent.SUPPORT:
        return Plan(Action.ESCALATE, "Situation sensible ou escalade active")

    if intent == Intent.ORDER:
        return Plan(Action.USE_TOOLS, "Référence commande détectée", one_question_only=False)

    if intent == Intent.FAQ:
        return Plan(Action.USE_TOOLS, "Question FAQ", one_question_only=False)

    if intent == Intent.COUNTRY_QUERY:
        return Plan(Action.USE_TOOLS, "Liste destinations catalogue", one_question_only=False)

    # Sans destination : demander le lieu avant un catalogue mondial
    # (sauf recherche thématique déjà en mémoire : plage, montagne…)
    if not _filled(slots, "destination"):
        if _filled(slots, "envies"):
            return Plan(
                Action.SEARCH_CATALOG,
                "Recherche thématique sans destination",
                one_question_only=False,
            )
        return Plan(Action.ASK_DESTINATION, "Destination requise avant catalogue")

    if intent == Intent.QUOTE:
        if _filled(slots, "activites_selectionnees") or _filled(slots, "activites_proposees"):
            return Plan(Action.CONFIRM_QUOTE, "Bouton devis PDF", one_question_only=False)
        if has_catalog_results and _filled(slots, "destination"):
            return Plan(Action.PRESENT_RESULTS, "Afficher activités avant devis", one_question_only=False)
        return Plan(Action.SEARCH_CATALOG, "Collecte avant devis")

    if has_catalog_results and (
        intent == Intent.ACTIVITY_SEARCH
        or (_filled(slots, "profil_voyageur") and _filled(slots, "envies"))
    ):
        return Plan(Action.PRESENT_RESULTS, "Afficher activités catalogue", one_question_only=False)

    if (
        _filled(slots, "activites_selectionnees")
        and _filled(slots, "destination")
        and _filled(slots, "profil_voyageur")
        and (_filled(slots, "nom_agence") or _filled(slots, "partner_id"))
    ):
        return Plan(Action.CONFIRM_QUOTE, "Bouton devis PDF", one_question_only=False)

    if _filled(slots, "destination") and not _filled(slots, "profil_voyageur"):
        return Plan(Action.ASK_PROFIL, "Profil inconnu")

    if _filled(slots, "profil_voyageur") and not _filled(slots, "envies"):
        return Plan(Action.ASK_ENVIES, "Envies inconnues")

    return Plan(Action.SEARCH_CATALOG, "Recherche catalogue par défaut", one_question_only=False)


def build_action_instruction(plan: Plan, *, agency_name: str | None = None) -> str:
    lines = [
        "ACTION MAINTENANT (interne) :",
        f"- Plan : {plan.action.value} — {plan.reason}",
        "- Ne jamais mentionner « tunnel », « Antoine », « étape », « processus ».",
    ]
    if plan.one_question_only:
        lines.append("- UNE seule question courte. Pas de questionnaire groupé.")
        lines.append("- Pas de logement, vols, ou activités hors JSON catalogue.")

    instructions = {
        Action.ASK_DESTINATION: "Demander où va le client ou proposer 2–3 villes du catalogue si envie thème.",
        Action.ASK_PROFIL: "Demander uniquement le profil (couple, famille, groupe, solo, séminaire).",
        Action.ASK_ENVIES: "Demander uniquement les envies (plage, montagne, forêt, culture, aventure, gastronomie…).",
        Action.SEARCH_CATALOG: "Utiliser les DONNÉES CATALOGUE injectées — titres et prix_net exacts.",
        Action.PRESENT_RESULTS: (
            "Lister 3 à 4 activités UNIQUEMENT depuis le JSON (titre exact + prix_net). "
            "FORMAT OBLIGATOIRE : liste numérotée 1. 2. 3. 4. — une activité par ligne. "
            "INTERDIT : regrouper par thème/catégorie (pas de titres « Spectacles », « Musées », « Croisières »). "
            "Pas d'activités inventées. Pas de devis dans ce message. "
            "Finir par : laquelle vous intéresse (ex. 1 et 3) ?"
        ),
        Action.CONFIRM_QUOTE: (
            "Confirmer brièvement la sélection catalogue. "
            "Dire : « Cliquez sur le bouton Générer le devis PDF ci-dessous. » "
            "INTERDIT : simuler un devis, envoyer par e-mail, inventer des prix, mentionner generate_quote ou un outil."
        ),
        Action.ESCALATE: (
            "Appeler escalate_to_advisor. "
            "Répondre uniquement : écrire à support_email (pas de contact conseiller dans le chat)."
        ),
        Action.USE_TOOLS: (
            "Utiliser les outils appropriés. "
            "Pour continents / autres destinations / couverture catalogue : appeler list_destinations. "
            "Ne jamais inventer de villes hors résultat outil."
        ),
    }
    if plan.action == Action.ASK_DESTINATION and agency_name:
        instructions[Action.ASK_DESTINATION] = (
            f"Commencer par « Bonjour {agency_name} ! » puis demander où va le client "
            "(une seule question courte)."
        )
    lines.append(f"- {instructions.get(plan.action, '')}")
    return "\n".join(lines)
