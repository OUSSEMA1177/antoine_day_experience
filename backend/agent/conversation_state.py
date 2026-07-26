"""Machine à états conversationnelle — source de vérité unique pour le routage.

Remplace la lecture éparpillée des slots `awaiting_*` : tous les modules
consultent `derive_state()` et les gates associés au lieu de re-tester
chaque slot dans un ordre différent.

Contient aussi :
- `normalize_message` : normalisation unique du message à l'entrée de _chat
  (apostrophes, espaces, unicode) — les regex n'ont plus à gérer les variantes ;
- `Intent` + `classify_intent` : LE classifieur d'intention déterministe,
  priorité encodée à UN seul endroit (fini les ordres différents par module).

Principe (whitelist) : un message n'est interprété comme « lieu inconnu »
que si (1) l'état de la session autorise un changement de destination ET
(2) aucune intention métier connue ne matche (`matches_known_intent`).
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum


def normalize_message(text: str) -> str:
    """Normalisation unique à l'entrée : unicode NFC, apostrophes droites,
    espaces multiples/insécables réduits. Ne touche ni accents ni ponctuation
    (les questions « ? » et titres cités doivent rester intacts)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    t = t.replace("\u00a0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


class ConvState(str, Enum):
    # Tunnel qualification — pas de liste ni de sélection en cours
    QUALIFYING = "qualifying"
    # « Souhaitez-vous explorer Parc Kruger ? » (1 ville proposée)
    AWAITING_CITY_CONFIRM = "awaiting_city_confirm"
    # Choix parmi N villes (« Barcelone, Grenade, Séville ? »)
    AWAITING_CITY_PICK = "awaiting_city_pick"
    # Liste d'activités affichée / sélection en cours, devis pas encore confirmé
    PRESENTING_LIST = "presenting_list"
    # « C'est bon pour vous ? Je prépare le devis ? » — seul oui/non/modif attendu
    AWAITING_QUOTE_CONFIRM = "awaiting_quote_confirm"
    # « Quelle thématique pour l'activité supplémentaire ? » / liste 2
    AWAITING_ADD_ACTIVITY = "awaiting_add_activity"
    # Devis généré (devis_ref) — révisions / nouvelle recherche possibles
    POST_QUOTE = "post_quote"


def _filled(slots: dict, key: str) -> bool:
    return bool(str(slots.get(key, "") or "").strip())


def derive_state(slots: dict) -> ConvState:
    """État unique dérivé des slots session (priorité fixe)."""
    if _filled(slots, "awaiting_quote_confirm"):
        return ConvState.AWAITING_QUOTE_CONFIRM
    if _filled(slots, "awaiting_city_confirm"):
        return ConvState.AWAITING_CITY_CONFIRM
    if _filled(slots, "awaiting_city_pick"):
        return ConvState.AWAITING_CITY_PICK
    if _filled(slots, "awaiting_add_activity"):
        return ConvState.AWAITING_ADD_ACTIVITY
    if _filled(slots, "devis_ref"):
        return ConvState.POST_QUOTE
    if (
        _filled(slots, "activites_proposees")
        or _filled(slots, "activites_selectionnees")
        or (_filled(slots, "destination") and _filled(slots, "activites_discutees"))
    ):
        return ConvState.PRESENTING_LIST
    return ConvState.QUALIFYING


# États où un message ambigu NE doit JAMAIS devenir un « lieu inconnu »
# (typo « ouii » pendant ask devis, thème « detente » pendant ajout…)
_NO_DESTINATION_CHANGE_STATES = frozenset(
    {
        ConvState.AWAITING_QUOTE_CONFIRM,
        ConvState.AWAITING_ADD_ACTIVITY,
    }
)


def allows_destination_change(state: ConvState) -> bool:
    """False si l'état interdit d'interpréter le message comme un nouveau lieu."""
    return state not in _NO_DESTINATION_CHANGE_STATES


def state_for_session(session_id: str) -> ConvState:
    from memory.memory_manager import memory_manager

    return derive_state(memory_manager.get_slots(session_id))


# Mots-clés sélection / retrait — filet regex (ordinaux + corrections)
_SELECTION_KEYWORDS_RE = re.compile(
    r"\b("
    r"premier(?:e|s|es)?|deuxi[eè]me|troisi[eè]me|quatri[eè]me|"
    r"1er|2e|3e|4e|les\s+deux|les\s+trois|activit|"
    r"d[eé]sol[eé]|enlever|retirer|veux\s+pas|budg"
    r")\b",
    re.I,
)

_GREETING_RE = re.compile(
    r"^(?:bonjour|bonsoir|salut|hello|hi|hey|coucou|merci)\s*[!.?]*$",
    re.I,
)


class Intent(str, Enum):
    """Intention déterministe dominante — priorité encodée dans classify_intent."""

    GREETING = "greeting"
    SUPPORT = "support"
    NOT_CHOSEN = "not_chosen"          # « non pas encore » (destination inconnue)
    RAISE_BUDGET = "raise_budget"
    ADD_THIS = "add_this"              # « ajoute ceci », « ajouter 6 »
    SELECT_AND_ADD = "select_and_add"  # « 2e + une autre activité »
    OTHER_OPTIONS = "other_options"    # « autre option », « j'ai pas aimé »
    WANTS_ANOTHER = "wants_another"    # « une autre activité »
    REJECT_REMOVE = "reject_remove"    # « pas la 1 », « enlever X »
    CONFIRM = "confirm"                # oui / ouii / c'est bon / le devis
    SELECT_INDICES = "select_indices"  # « 1 et 3 », « les 3 premiers »
    QUALIFICATION = "qualification"    # « en couple », envies, taille groupe
    COUNTRY_REGION = "country_region"  # Espagne, Afrique, Afrique du Sud (typos)
    BUDGET_OR_SEARCH = "budget_or_search"  # budget cité / « donne activités »
    THEME = "theme"                    # plage, détente, gastronomie…
    UNKNOWN = "unknown"                # ambigu → NLU / LLM


def classify_intent(text: str) -> Intent:
    """LE classifieur d'intention déterministe (0 token).

    Ordre = priorité unique pour tous les modules. Un message classé
    autrement que UNKNOWN ne peut jamais être traité comme un lieu inconnu.
    FAQ reste géré par le routeur (`is_faq_inquiry`).
    """
    msg = (text or "").strip()
    if not msg:
        return Intent.UNKNOWN

    if _GREETING_RE.match(msg):
        return Intent.GREETING

    from agent.support_policy import is_support_email_inquiry, is_support_request

    if is_support_email_inquiry(msg) or is_support_request(msg):
        return Intent.SUPPORT

    from agent.destination_policy import is_destination_not_chosen_yet

    if is_destination_not_chosen_yet(msg):
        return Intent.NOT_CHOSEN

    from agent.intent_router import is_raise_budget_request, wants_activity_listing

    if is_raise_budget_request(msg):
        return Intent.RAISE_BUDGET

    from memory.quote_state import (
        REJECT_RE,
        REMOVE_SELECTION_RE,
        is_add_this_activity,
        is_confirmation_message,
        is_quote_confirmation,
        is_reject_presented_list,
        is_wants_another_activity,
        is_wants_other_options,
        parse_presentation_indices,
    )

    indices = parse_presentation_indices(msg)
    if is_add_this_activity(msg):
        return Intent.ADD_THIS
    if indices and is_wants_another_activity(msg):
        return Intent.SELECT_AND_ADD
    if is_wants_other_options(msg) or is_reject_presented_list(msg):
        return Intent.OTHER_OPTIONS
    if is_wants_another_activity(msg):
        return Intent.WANTS_ANOTHER
    if REMOVE_SELECTION_RE.search(msg) or REJECT_RE.search(msg):
        return Intent.REJECT_REMOVE
    if is_confirmation_message(msg) or is_quote_confirmation(msg):
        return Intent.CONFIRM
    # Question factuelle (« la 1re c'est à Istanbul ? ») → ambigu (NLU/LLM),
    # pas une sélection malgré l'ordinal
    from memory.quote_state import is_clarifying_question

    if is_clarifying_question(msg):
        return Intent.UNKNOWN
    if indices or _SELECTION_KEYWORDS_RE.search(msg):
        return Intent.SELECT_INDICES

    from agent.context_manager import is_qualification_message, parse_budget_from_message

    if is_qualification_message(msg):
        return Intent.QUALIFICATION

    from search.geo import detect_country_query

    if detect_country_query(msg):
        return Intent.COUNTRY_REGION

    if parse_budget_from_message(msg) or (
        wants_activity_listing(msg) and len(msg.split()) >= 2
    ):
        return Intent.BUDGET_OR_SEARCH

    from search.themes import detect_themes_from_text

    if detect_themes_from_text(msg):
        return Intent.THEME

    return Intent.UNKNOWN


def matches_known_intent(text: str) -> bool:
    """True si le message correspond à une intention métier connue (whitelist).

    Un message qui matche ici ne peut PAS être traité comme un lieu inconnu.
    """
    msg = (text or "").strip()
    if not msg:
        return True  # rien à interpréter
    return classify_intent(msg) is not Intent.UNKNOWN
