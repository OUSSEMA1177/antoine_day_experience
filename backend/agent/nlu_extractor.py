"""Extracteur NLU structuré (Claude/LLM → JSON) — compréhension avant action catalogue."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm

from agent.llm_usage import record_llm_usage
from memory.memory_manager import memory_manager
from search.geo import (
    CONTINENT_ALIASES,
    REGION_ALIASES,
    resolve_catalog_country_key,
    resolve_destination_name,
)
from services.data_loader import data_loader

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

VALID_INTENTS = frozenset(
    {
        "qualify",
        "search",
        "list_destinations",
        "confirm",
        "reject",
        "add_activity",
        "quote",
        "other",
    }
)
VALID_PROFILS = frozenset(
    {"couple", "famille", "solo", "groupe", "groupe_amis", "seminaire"}
)
VALID_ENVIES = frozenset(
    {
        "culture",
        "gastronomie",
        "aventure",
        "nature",
        "mer",
        "détente",
        "sahara",
        "montagne",
        "foret",
        "croisiere",
    }
)


@dataclass
class NLUExtract:
    intent: str = "other"
    destination: str | None = None
    continent: str | None = None
    country: str | None = None
    profil: str | None = None
    taille_groupe: int | None = None
    envies: list[str] = field(default_factory=list)
    confirm_selection: bool = False
    wants_another_activity: bool = False
    add_this_activity: bool = False
    selection_indices: list[int] = field(default_factory=list)
    reject_hint: str | None = None
    is_place_name: bool = False
    mix_all_envies: bool = False
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        payload = {
            "intent": self.intent,
            "destination": self.destination,
            "continent": self.continent,
            "country": self.country,
            "profil": self.profil,
            "taille_groupe": self.taille_groupe,
            "envies": self.envies,
            "confirm_selection": self.confirm_selection,
            "wants_another_activity": self.wants_another_activity,
            "add_this_activity": self.add_this_activity,
            "selection_indices": self.selection_indices,
            "reject_hint": self.reject_hint,
            "is_place_name": self.is_place_name,
            "mix_all_envies": self.mix_all_envies,
        }
        return "NLU STRUCTURÉ (interne — respecter pour la réponse) :\n" + json.dumps(
            payload, ensure_ascii=False
        )


def empty_nlu() -> NLUExtract:
    return NLUExtract()


def _load_nlu_prompt() -> str:
    path = PROMPTS_DIR / "nlu_extract.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return (
        "Extrais un JSON d'intention pour un agent B2B tourisme. "
        "Réponds UNIQUEMENT avec un objet JSON valide."
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _norm_continent(value: str | None) -> str | None:
    if not value:
        return None
    needle = value.strip().casefold()
    for key, aliases in CONTINENT_ALIASES.items():
        if needle == key or needle in {a.casefold() for a in aliases}:
            return key
    return None


def _norm_country_key(value: str | None) -> str | None:
    if not value:
        return None
    needle = value.strip()
    for key, region in REGION_ALIASES.items():
        n = needle.casefold()
        if n == key or n in {a.casefold() for a in region["aliases"]}:
            return key
    return resolve_catalog_country_key(needle)


def parse_nlu_payload(data: dict[str, Any]) -> NLUExtract:
    intent = str(data.get("intent") or "other").strip().casefold()
    if intent not in VALID_INTENTS:
        intent = "other"

    profil = data.get("profil")
    profil_s = str(profil).strip().casefold() if profil else None
    if profil_s and profil_s not in VALID_PROFILS:
        profil_s = None

    envies_raw = data.get("envies") or []
    if isinstance(envies_raw, str):
        envies_raw = [e.strip() for e in envies_raw.split(",") if e.strip()]
    from search.themes import canonicalize_theme

    envies: list[str] = []
    for item in envies_raw:
        name = canonicalize_theme(str(item)) or str(item).strip().casefold()
        if name in ("detente",):
            name = "détente"
        if name in VALID_ENVIES and name not in envies:
            envies.append(name)

    taille = data.get("taille_groupe")
    taille_i: int | None = None
    try:
        if taille is not None and str(taille).strip() != "":
            taille_i = int(float(str(taille)))
            if taille_i < 2 or taille_i > 500:
                taille_i = None
    except (TypeError, ValueError):
        taille_i = None

    dest_raw = data.get("destination")
    destination = None
    if dest_raw and str(dest_raw).strip():
        destination = resolve_destination_name(str(dest_raw).strip(), data_loader)

    continent = _norm_continent(str(data.get("continent") or "") or None)
    country = _norm_country_key(str(data.get("country") or "") or None)

    confidence = data.get("confidence")
    try:
        conf_f = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0

    reject = data.get("reject_hint")
    reject_s = str(reject).strip() if reject else None

    indices_raw = data.get("selection_indices") or []
    selection_indices: list[int] = []
    if isinstance(indices_raw, (list, tuple)):
        for item in indices_raw:
            try:
                idx = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= idx <= 20 and idx not in selection_indices:
                selection_indices.append(idx)

    return NLUExtract(
        intent=intent,
        destination=destination,
        continent=continent,
        country=country,
        profil=profil_s,
        taille_groupe=taille_i,
        envies=envies,
        confirm_selection=bool(data.get("confirm_selection")),
        wants_another_activity=bool(data.get("wants_another_activity")),
        add_this_activity=bool(data.get("add_this_activity")),
        selection_indices=selection_indices,
        reject_hint=reject_s or None,
        is_place_name=bool(data.get("is_place_name")),
        mix_all_envies=bool(data.get("mix_all_envies")),
        confidence=max(0.0, min(1.0, conf_f)),
        raw=data,
    )


def is_pure_selection_or_confirm_message(message: str) -> bool:
    """Sélection / oui devis clair → 0 token (pas de NLU).

    Les cas « 2e + une autre » / « oui ajoute » sont routés à part
    (PURE_SELECTION via intent_router + regex quote_state).
    """
    from memory.quote_state import (
        SELECT_ALL_RE,
        is_add_this_activity,
        is_clarifying_question,
        is_quote_confirmation,
        is_wants_another_activity,
        parse_presentation_indices,
    )

    text = (message or "").strip()
    if not text or is_clarifying_question(text):
        return False
    # Gérés par le routeur / quote_state, pas comme « sélection pure » générique
    if is_wants_another_activity(text) or is_add_this_activity(text):
        return False
    if parse_presentation_indices(text) or SELECT_ALL_RE.search(text):
        return True
    return is_quote_confirmation(text)


# Intentions résolues 0 token (Python) — pas de NLU
_NLU_SKIP_INTENTS = frozenset(
    {
        "greeting",
        "support",
        "not_chosen",
        "raise_budget",
        "add_this",
        "select_and_add",
        "other_options",
        "wants_another",
        "reject_remove",
        "confirm",
        "select_indices",
        "country_region",
        "budget_or_search",
    }
)


def should_run_nlu(message: str, *, deterministic_hit: bool = False) -> bool:
    """NLU seulement pour le langage ambigu — le déterministe reste 0 token.

    Décision basée sur `classify_intent` (classifieur unique) :
    intent déterministe → skip ; UNKNOWN / qualification / thème → NLU
    (sauf lieu hors catalogue isolé, refusé 0 token).
    """
    if deterministic_hit:
        return False
    text = message.strip()
    if not text or len(text) < 2:
        return False

    from agent.conversation_state import Intent, classify_intent

    intent = classify_intent(text)
    if intent.value in _NLU_SKIP_INTENTS:
        return False

    # FAQ métier → réponse faq.csv 0 token
    from agent.faq_policy import is_faq_inquiry

    if is_faq_inquiry(text):
        return False

    # Lieu hors catalogue isolé (Monaco, Toulouse) → refus 0 token, pas de NLU
    from agent.destination_policy import detect_unknown_place_request

    if intent is Intent.UNKNOWN and detect_unknown_place_request(text, session_id=None):
        return False

    # Ambigu / qualification floue / thème → NLU
    return True

def apply_nlu_to_session(session_id: str, nlu: NLUExtract) -> dict[str, str]:
    """Applique le JSON NLU aux slots session (source prioritaire sur regex)."""
    updates: dict[str, str] = {}
    if nlu.destination:
        updates["destination"] = nlu.destination
        updates["destination_demandee"] = ""
    if nlu.profil:
        updates["profil_voyageur"] = nlu.profil
    if nlu.taille_groupe:
        updates["taille_groupe"] = str(nlu.taille_groupe)
    if nlu.mix_all_envies:
        updates["envies"] = "culture, gastronomie, aventure, nature, détente"
    elif nlu.envies:
        updates["envies"] = ", ".join(nlu.envies)
    if updates:
        memory_manager.update_slots(session_id, **updates)
    return updates


def extract_nlu(
    message: str,
    *,
    session_id: str,
    litellm_kwargs: dict[str, Any],
    log_usage: bool = True,
) -> NLUExtract:
    """Appel LLM court → NLUExtract. En cas d'échec → empty_nlu()."""
    from agent.conversation_state import derive_state

    slots = memory_manager.get_slots(session_id)
    memory_hint = {
        "destination": slots.get("destination") or None,
        "profil_voyageur": slots.get("profil_voyageur") or None,
        "envies": slots.get("envies") or None,
        "taille_groupe": slots.get("taille_groupe") or None,
        # État machine — permet au NLU d'interpréter « ouii » selon le contexte
        "etat_conversation": derive_state(slots).value,
    }
    system = _load_nlu_prompt()
    user = (
        f"Mémoire session actuelle : {json.dumps(memory_hint, ensure_ascii=False)}\n"
        f"Message partenaire : {message.strip()}"
    )
    kwargs = {
        **litellm_kwargs,
        "max_tokens": min(220, int(litellm_kwargs.get("max_tokens") or 220)),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # JSON mode si le provider le supporte (ignoré sinon)
    try:
        kwargs["response_format"] = {"type": "json_object"}
    except Exception:
        pass

    try:
        response = litellm.completion(**kwargs)
        record_llm_usage(response, str(kwargs.get("model") or ""), log=log_usage)
        content = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            msg = choices[0].message
            content = getattr(msg, "content", None) or ""
        data = _extract_json_object(content)
        if not data:
            logger.warning("NLU: JSON invalide — %s", content[:200])
            return empty_nlu()
        return parse_nlu_payload(data)
    except Exception as exc:
        logger.warning("NLU extract failed: %s", exc)
        return empty_nlu()
