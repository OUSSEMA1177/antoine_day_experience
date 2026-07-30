"""Orchestrateur agent — point d'entrée conversationnel."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import litellm
from litellm.exceptions import APIConnectionError, BadRequestError, RateLimitError, Timeout

from agent.context_manager import is_qualification_message, sync_slots_from_message
from agent.llm_usage import (
    attach_llm_usage,
    current_llm_usage,
    record_llm_usage,
    reset_llm_usage_tracking,
    start_llm_usage_tracking,
)
from agent.chat_logger import (
    finish_chat_turn,
    mark_dialog,
    mark_nlu,
    reset_chat_turn,
    start_chat_turn,
    update_turn,
)
from agent.destination_policy import (
    activate_catalog_destination,
    activate_unavailable_destination,
    build_destination_help_reply,
    build_destination_unavailable_reply,
    build_no_activities_reply,
    detect_catalog_destination_request,
    detect_gibberish_destination_attempt,
    detect_unknown_place_request,
    is_catalog_destination,
    is_destination_not_chosen_yet,
    refers_to_previous_place,
    unavailable_place_from_slots,
)
from agent.intent_detector import Intent, detect_intent
from agent.nlu_extractor import (
    NLUExtract,
    apply_nlu_to_session,
    empty_nlu,
    extract_nlu,
    is_pure_selection_or_confirm_message,
    should_run_nlu,
)
from agent.partner_context import build_greeting_reply, resolve_agency_name
from agent.planner import Action, Plan, build_action_instruction, plan_next
from agent.response_generator import sanitize_response
from app.config import get_settings
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    compute_quote_state,
    confirm_proposed_activities,
    is_add_this_activity,
    is_clarifying_question,
    is_confirmation_message,
    is_quote_confirmation,
    is_reject_presented_list,
    is_wants_another_activity,
    is_wants_other_options,
    pick_proposed_activities,
    record_discussed_activities_from_text,
    reject_presented_list,
    save_proposed_activities,
    session_has_activity_context,
)
from pdf.quote_generator import generate_quote_for_session
from search.catalog_search import (
    CatalogSearchResult,
    append_order_and_faq,
    context_has_activities,
    format_activity_line,
    search_from_context,
)
from search.geo import (
    build_country_catalog_reply,
    detect_country_query,
    is_explicit_region_request,
    list_catalog_destinations_for_region,
)
from services.data_loader import data_loader
from tools.registry import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_TOOL_ROUNDS = 5


class AgentError(Exception):
    pass


class AgentConfigurationError(AgentError):
    pass


class Orchestrator:
    @property
    def settings(self):
        return get_settings()

    def _load_prompt(self, filename: str) -> str:
        return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()

    def _build_system_prompt(
        self,
        session_id: str,
        action_instruction: str,
        plan: Plan,
    ) -> str:
        parts = [self._load_prompt("system_prompt.txt")]
        if (
            not self.settings.llm_compact_prompt
            or plan.action
            in (Action.ASK_DESTINATION, Action.ASK_PROFIL, Action.ASK_ENVIES)
        ):
            parts.extend(["", self._load_prompt("tunnel_antoine.txt")])
        parts.extend(
            [
                "",
                "MÉMOIRE SESSION :",
                memory_manager.context_summary(session_id),
                "",
                action_instruction,
            ]
        )
        if memory_manager.is_escalated(session_id):
            from agent.support_policy import support_email

            parts.append(
                f"\nNote : dossier sensible — orienter vers {support_email()} "
                "(pas de traitement dans le chat)."
            )
        return "\n".join(parts)

    def _litellm_kwargs(self, model: str | None = None) -> dict:
        model = model or self.settings.llm_model
        kwargs: dict = {
            "model": model,
            "timeout": self.settings.llm_timeout,
            "max_tokens": self.settings.llm_max_tokens,
        }
        if model.startswith("groq/") and self.settings.groq_api_key:
            kwargs["api_key"] = self.settings.groq_api_key
        elif model.startswith("gemini/") and self.settings.gemini_api_key:
            kwargs["api_key"] = self.settings.gemini_api_key
        elif model.startswith("anthropic/") and self.settings.anthropic_api_key:
            kwargs["api_key"] = self.settings.anthropic_api_key
        elif model.startswith("openai/") and self.settings.openai_api_key:
            kwargs["api_key"] = self.settings.openai_api_key
        return kwargs

    def _record_llm_usage(self, response, model: str) -> None:
        record_llm_usage(
            response,
            model,
            log=self.settings.llm_log_usage,
        )

    def _fallback_models(self) -> list[str]:
        models = [self.settings.llm_model]
        explicit = (self.settings.llm_fallback_model or "").strip()
        if explicit and explicit not in models:
            models.append(explicit)
            return models
        primary = self.settings.llm_model
        if primary.startswith("groq/") and self.settings.gemini_api_key:
            fallback = "gemini/gemini-2.0-flash"
            if fallback not in models:
                models.append(fallback)
        elif primary.startswith("gemini/") and self.settings.groq_api_key:
            fallback = "groq/llama-3.3-70b-versatile"
            if fallback not in models:
                models.append(fallback)
        elif primary.startswith("anthropic/"):
            explicit_haiku = "anthropic/claude-haiku-4-5"
            if explicit_haiku not in models and "haiku" not in primary:
                models.append(explicit_haiku)
        return models

    def _uses_native_tools_for(self, model: str) -> bool:
        return not model.startswith("groq/")

    def _should_use_tools(self, plan: Plan, intent: Intent) -> bool:
        """Tools uniquement quand nécessaire — économie de tokens."""
        if plan.action in (Action.USE_TOOLS, Action.ESCALATE):
            return True
        if intent in (Intent.ORDER, Intent.FAQ, Intent.QUOTE, Intent.COUNTRY_QUERY):
            return True
        if plan.action in (Action.ASK_DESTINATION, Action.ASK_PROFIL, Action.ASK_ENVIES):
            return False
        if plan.action in (Action.PRESENT_RESULTS, Action.CONFIRM_QUOTE):
            return False
        # SEARCH_CATALOG : autoriser list_destinations / search_catalog si pas encore de destination
        if plan.action == Action.SEARCH_CATALOG:
            return True
        return False

    def _catalog_for_llm(self, search_result: CatalogSearchResult) -> CatalogSearchResult:
        raw_limit = getattr(self.settings, "llm_catalog_inject_limit", 4)
        try:
            limit = max(1, int(raw_limit))
        except (TypeError, ValueError):
            limit = 4
        if search_result.count <= limit:
            return search_result
        return search_result.limited(limit)

    def _history_limit(self) -> int:
        raw_limit = getattr(self.settings, "llm_history_limit", 8)
        try:
            return max(2, int(raw_limit))
        except (TypeError, ValueError):
            return 8

    def _should_inject_catalog(self, plan: Plan, intent: Intent) -> bool:
        if plan.action in (Action.ASK_DESTINATION, Action.ASK_PROFIL, Action.ASK_ENVIES):
            return False
        if plan.action in (Action.PRESENT_RESULTS, Action.SEARCH_CATALOG, Action.CONFIRM_QUOTE):
            return True
        return intent in (Intent.ACTIVITY_SEARCH, Intent.QUOTE, Intent.ORDER)

    def _completion(
        self,
        messages: list[dict],
        *,
        use_tools: bool,
        base_kwargs: dict,
    ):
        models = self._fallback_models()
        last_error: Exception | None = None

        for model in models:
            for attempt in range(self.settings.llm_retry_max + 1):
                llm_kwargs = {**base_kwargs, **self._litellm_kwargs(model)}
                completion_kwargs: dict = {"messages": messages, **llm_kwargs}
                model_use_tools = use_tools and self._uses_native_tools_for(model)
                if model_use_tools:
                    completion_kwargs["tools"] = TOOL_DEFINITIONS
                    completion_kwargs["tool_choice"] = "auto"
                try:
                    if model != self.settings.llm_model and attempt == 0:
                        logger.warning("Bascule LLM vers %s", model)
                    response = litellm.completion(**completion_kwargs)
                    self._record_llm_usage(response, model)
                    return response
                except RateLimitError as exc:
                    last_error = exc
                    logger.warning(
                        "Rate limit %s (tentative %s/%s)",
                        model,
                        attempt + 1,
                        self.settings.llm_retry_max + 1,
                    )
                    if attempt < self.settings.llm_retry_max:
                        time.sleep(self.settings.llm_retry_delay * (attempt + 1))
                        continue
                    break

        if last_error:
            raise last_error
        raise AgentError("Impossible de joindre le service IA.")

    def _ensure_configured(self) -> None:
        model = self.settings.llm_model
        checks = [
            ("groq/", self.settings.groq_api_key, "GROQ_API_KEY"),
            ("gemini/", self.settings.gemini_api_key, "GEMINI_API_KEY"),
            ("anthropic/", self.settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
            ("openai/", self.settings.openai_api_key, "OPENAI_API_KEY"),
        ]
        for prefix, key, env_name in checks:
            if model.startswith(prefix) and not key:
                raise AgentConfigurationError(f"{env_name} manquante dans .env")

    def _uses_native_tools(self) -> bool:
        return not self.settings.llm_model.startswith("groq/")

    def _message_to_dict(self, message) -> dict:
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        if isinstance(message, dict):
            return message
        data = {"role": getattr(message, "role", "assistant")}
        content = getattr(message, "content", None)
        if content is not None:
            data["content"] = content
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            data["tool_calls"] = [
                tc.model_dump(exclude_none=True) if hasattr(tc, "model_dump") else tc
                for tc in tool_calls
            ]
        return data

    def _quote_meta(self, session_id: str, quote_info: dict[str, str | None] | None = None) -> dict:
        state = compute_quote_state(session_id)
        meta = {
            "quote_url": (quote_info or {}).get("quote_url"),
            "devis_ref": (quote_info or {}).get("devis_ref"),
            "quote_ready": state["quote_ready"],
            "quote_activities": state["activities"],
            "destination": state["destination"],
            "nom_agence": state["nom_agence"],
            "quote_missing": state["missing"],
        }
        return attach_llm_usage(meta)

    def _finalize_reply(self, reply: str, plan: Plan, quote_meta: dict) -> str:
        if plan.action == Action.CONFIRM_QUOTE and quote_meta.get("quote_ready"):
            if "générer le devis" not in reply.casefold():
                reply = (
                    f"{reply}\n\n"
                    "Cliquez sur le bouton Générer le devis PDF ci-dessous pour télécharger votre devis White Label."
                )
        return reply

    def _run_nlu(self, session_id: str, user_message: str) -> NLUExtract:
        enabled = getattr(self.settings, "llm_nlu_extract", True)
        # Exige un bool True explicite (évite MagicMock truthy en tests)
        if enabled is not True:
            return empty_nlu()
        if not should_run_nlu(user_message):
            return empty_nlu()
        nlu = extract_nlu(
            user_message,
            session_id=session_id,
            litellm_kwargs=self._litellm_kwargs(),
            log_usage=bool(getattr(self.settings, "llm_log_usage", True) is True),
        )
        mark_nlu(getattr(nlu, "intent", None))
        return nlu

    def _apply_nlu_side_effects(self, session_id: str, nlu: NLUExtract) -> None:
        apply_nlu_to_session(session_id, nlu)
        if nlu.destination:
            activate_catalog_destination(session_id, nlu.destination)

    def _maybe_set_destination(self, session_id: str, message: str, nlu: NLUExtract | None = None) -> None:
        if is_qualification_message(message) or is_confirmation_message(message):
            return
        if nlu and (
            nlu.confirm_selection
            or nlu.wants_another_activity
            or nlu.mix_all_envies
            or nlu.envies
            or nlu.intent in ("qualify", "confirm", "quote", "add_activity", "reject")
        ):
            if not nlu.is_place_name:
                return

        slots = memory_manager.get_slots(session_id)
        current_dest = str(slots.get("destination", "") or "").strip()
        # Destination catalogue déjà active → ne pas réinterpréter le message comme un lieu
        if current_dest and is_catalog_destination(current_dest):
            catalog_dest = detect_catalog_destination_request(message)
            if catalog_dest and catalog_dest.casefold() != current_dest.casefold():
                activate_catalog_destination(session_id, catalog_dest)
            return

        if session_has_activity_context(session_id) and len(message.strip().split()) >= 2:
            return

        catalog_dest = detect_catalog_destination_request(message)
        if catalog_dest:
            activate_catalog_destination(session_id, catalog_dest)
            return

        # NLU dit que ce n'est pas un nom de lieu → ne pas forcer hors-catalogue
        if nlu and not nlu.is_place_name and len(message.strip().split()) >= 2:
            return

        tokens = message.strip().split()
        # Uniquement 1–2 tokens type « Toulouse » / « New York »
        if 1 <= len(tokens) <= 2:
            candidate = message.strip().rstrip("?.!,;:")
            if activate_catalog_destination(session_id, candidate):
                return
            unknown = detect_unknown_place_request(candidate, session_id=session_id)
            if unknown:
                activate_unavailable_destination(session_id, unknown)

    def _reply_destination_unavailable(
        self,
        session_id: str,
        user_message: str,
        place: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict]:
        from agent.conversation_state import allows_destination_change, derive_state

        slots = memory_manager.get_slots(session_id)
        # État sans changement de destination (ask devis / ajout) → jamais wipe
        if not allows_destination_change(derive_state(slots)):
            confirm = self._try_activity_confirmation(
                session_id, user_message, tools_used, quote_info, nlu=None
            )
            if confirm:
                return confirm
            reply = (
                "Souhaitez-vous que je prépare le devis White Label avec la sélection "
                "actuelle ? Répondez par oui, ou précisez les activités (ex. les 3 premiers)."
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)
        activate_unavailable_destination(session_id, place)
        reply = build_destination_unavailable_reply(place)
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_country_catalog_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        from search.geo import CONTINENT_PAYS, format_qualification_note

        region_key = detect_country_query(user_message)
        if not region_key:
            return None

        # Session déjà sur une ville catalogue : ne pas détourner vers un continent
        # (ex. titre collé « dessert asiatique » → faux Asie)
        # Mais autoriser un suivi pays (« il y a que Marrakech ? »)
        slots = memory_manager.get_slots(session_id)
        dest = str(slots.get("destination", "") or "").strip()
        if dest and is_catalog_destination(dest) and not is_explicit_region_request(user_message):
            if region_key == "all" or region_key in CONTINENT_PAYS:
                return None

        from search.catalog_search import (
            CatalogSearchParams,
            build_region_activities_reply,
            build_theme_region_reply,
            catalog_search,
        )
        from search.themes import detect_themes_from_text

        themes = detect_themes_from_text(user_message)
        if region_key != "all":
            memory_manager.update_slots(session_id, region_interest=region_key)
        if themes:
            memory_manager.update_slots(session_id, envies=", ".join(themes))
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    themes=themes,
                    region=region_key if region_key != "all" else None,
                    limit=8,
                )
            )
            tools_used.extend(result.tools_used)
            reply = build_theme_region_reply(region_key, themes, result)
            if result.has_results():
                save_proposed_activities(session_id, result.activities[:6])
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        slots = memory_manager.get_slots(session_id)
        context_note = format_qualification_note(slots)
        budget_raw = str(slots.get("budget", "") or "").strip()
        budget_max: float | None = None
        if budget_raw:
            try:
                budget_max = float(budget_raw.replace(",", "."))
            except ValueError:
                budget_max = None
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None

        wants_activities = bool(
            re.search(r"\bactivit", user_message, re.I)
            or re.search(r"\b(exp[eé]riences?|excursions?)\b", user_message, re.I)
            or re.search(r"\b(donne[rz]?|propose[rz]?|montre[rz]?)\b", user_message, re.I)
        )
        # Si le message cite un budget, toujours tenter une recherche activités
        if region_key != "all" and (wants_activities or budget_max is not None):
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    region=region_key,
                    budget_max=budget_max,
                    profil=profil,
                    limit=8,
                )
            )
            fallback = None
            if not result.has_results() and budget_max:
                fallback = catalog_search(
                    CatalogSearchParams(
                        query=user_message,
                        region=region_key,
                        budget_max=None,
                        profil=profil,
                        limit=8,
                    )
                )
            tools_used.extend(result.tools_used)
            if fallback:
                tools_used.extend(fallback.tools_used)
            reply = build_region_activities_reply(
                region_key,
                result,
                budget_max=budget_max,
                context_note=context_note,
                fallback_without_budget=fallback,
            )
            pool = result.activities if result.has_results() else (
                fallback.activities if fallback and fallback.has_results() else []
            )
            if pool:
                save_proposed_activities(session_id, pool[:6])
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        cities = list_catalog_destinations_for_region(region_key)
        reply = build_country_catalog_reply(
            region_key, cities, context_note=context_note
        )
        from agent.destination_confirm import remember_city_offer

        # Nouvelle offre pays → plus d'ask devis en cours
        memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
        remember_city_offer(session_id, cities, region_key=region_key)
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _check_destination_availability(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
        nlu: NLUExtract | None = None,
    ) -> tuple[str, list[str], dict] | None:
        if is_qualification_message(user_message) or is_confirmation_message(user_message):
            return None

        if nlu and (
            nlu.confirm_selection
            or nlu.wants_another_activity
            or nlu.mix_all_envies
            or (not nlu.is_place_name and nlu.intent != "other")
        ):
            return None

        if detect_catalog_destination_request(user_message):
            return None

        if session_has_activity_context(session_id):
            # Session déjà engagée sur une destination catalogue — pas de fausse ville
            return None

        unknown = detect_unknown_place_request(user_message, session_id=session_id)
        if unknown:
            return self._reply_destination_unavailable(
                session_id, user_message, unknown, tools_used, quote_info
            )

        if detect_gibberish_destination_attempt(user_message):
            reply = (
                "Je n'ai pas reconnu ce nom de destination. "
                "Pouvez-vous préciser une ville ou un pays (ex. Paris, Barcelone, Bali) ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        slots = memory_manager.get_slots(session_id)
        blocked = unavailable_place_from_slots(slots)
        if blocked and (
            refers_to_previous_place(user_message)
            or "activit" in user_message.casefold()
        ):
            return self._reply_destination_unavailable(
                session_id, user_message, blocked, tools_used, quote_info
            )
        return None

    def _try_support_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """E-mail support / escalade — 0 token, avant ask destination et NLU."""
        from agent.support_policy import (
            build_support_contact_reply,
            build_support_email_reply,
            escalate_session,
            is_support_email_inquiry,
            is_support_request,
        )

        if is_support_email_inquiry(user_message):
            reply = build_support_contact_reply()
            tools_used.append("support_contact")
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if is_support_request(user_message) or memory_manager.is_escalated(session_id):
            payload = escalate_session(session_id, reason=user_message[:120])
            tools_used.append("escalate_to_advisor")
            reply = payload.get("message") or build_support_email_reply()
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        return None

    def _try_pending_city_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """« oui » / ville après offre pays — active destination + liste activités."""
        from agent.destination_confirm import (
            clear_pending_city,
            is_affirmative_short,
            is_negative_short,
            resolve_pending_city_choice,
        )
        from agent.destination_policy import activate_catalog_destination
        from search.catalog_search import CatalogSearchParams, catalog_search
        from search.geo import format_qualification_note

        slots = memory_manager.get_slots(session_id)
        awaiting = str(slots.get("awaiting_city_confirm", "") or "").strip() or str(
            slots.get("awaiting_city_pick", "") or ""
        ).strip()
        if not awaiting:
            return None

        # Pendant ask devis : un « oui » pur = confirmation devis, pas city confirm.
        # Mais un nom de ville (Séville, Barcelone…) ou un indice = changement explicite.
        awaiting_quote = bool(
            str(slots.get("awaiting_quote_confirm", "") or "").strip()
        )
        if awaiting_quote and is_affirmative_short(user_message):
            return None

        if is_negative_short(user_message):
            clear_pending_city(session_id)
            reply = (
                "D'accord. Quelle autre destination ou zone souhaitez-vous explorer "
                "(ex. Espagne, Paris, Bali, Afrique) ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        city = resolve_pending_city_choice(session_id, user_message)
        if not city:
            return None

        # Changement de ville → abandonner l'ancien ask devis
        if awaiting_quote:
            memory_manager.clear_slot(session_id, "awaiting_quote_confirm")

        resolved = activate_catalog_destination(session_id, city)
        if not resolved:
            clear_pending_city(session_id)
            return None

        tools_used.append("city_confirm")
        slots = memory_manager.get_slots(session_id)
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None
        budget_raw = str(slots.get("budget", "") or "").strip()
        budget_max: float | None = None
        if budget_raw:
            try:
                budget_max = float(budget_raw.replace(",", "."))
            except ValueError:
                budget_max = None
        note = format_qualification_note(slots)
        result = catalog_search(
            CatalogSearchParams(
                query=user_message,
                destination=resolved,
                budget_max=budget_max,
                profil=profil,
                limit=8,
            )
        )
        tools_used.extend(result.tools_used)
        if result.has_results():
            save_proposed_activities(session_id, result.activities[:6])
            lines: list[str] = []
            for i, row in enumerate(result.activities[:6], start=1):
                item = result.format_activity(row)
                lines.append(
                    format_activity_line(
                        i,
                        titre=item.get("titre") or "",
                        prix_net=item.get("prix_net") or "",
                        activity_id=item.get("id") or "",
                    )
                )
            prefix = f"{note} " if note else ""
            reply = (
                f"{prefix}Voici des activités à {resolved} :\n"
                + "\n".join(lines)
                + "\nLaquelle vous intéresse (ex. 1 et 2) ?"
            )
        else:
            reply = (
                f"Destination {resolved} notée. Je n'ai pas trouvé d'activités "
                f"catalogue pour le moment. Souhaitez-vous une autre ville ?"
            )
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_other_options_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
        *,
        mark_rejected: bool = False,
    ) -> tuple[str, list[str], dict] | None:
        """« j'ai pas aimé » / « autre option » → nouvelle liste (exclut déjà proposées)."""
        from memory.quote_state import _parse_id_list
        from search.catalog_search import CatalogSearchParams, catalog_search
        from search.geo import region_key_for_destination
        from search.themes import detect_themes_from_text

        slots = memory_manager.get_slots(session_id)
        dest = str(slots.get("destination", "") or "").strip()
        region = str(slots.get("region_interest", "") or "").strip()
        proposed = _parse_id_list(slots.get("activites_proposees"))
        discussed = _parse_id_list(slots.get("activites_discutees"))
        if not dest and not region and not proposed and not discussed:
            return None

        if mark_rejected or is_reject_presented_list(user_message):
            reject_presented_list(session_id)
            slots = memory_manager.get_slots(session_id)

        memory_manager.clear_slot(session_id, "awaiting_add_activity")
        memory_manager.clear_slot(session_id, "awaiting_quote_confirm")

        rejected = set(_parse_id_list(slots.get("activites_rejetees")))
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None
        themes = detect_themes_from_text(user_message)

        def _filter(rows: list[dict]) -> list[dict]:
            out = []
            for row in rows:
                aid = str(row.get("id", "") or "").strip()
                if aid and aid not in rejected:
                    out.append(row)
            return out

        result = None
        if dest and is_catalog_destination(dest):
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    destination=dest,
                    themes=themes or None,
                    profil=profil,
                    limit=12,
                )
            )
            tools_used.extend(result.tools_used)
            pool = _filter(result.activities)
            if not pool and themes:
                # Thème introuvable ici → dire la vérité pays si possible
                rk = region or region_key_for_destination(dest)
                if rk:
                    country_reply = self._try_country_catalog_reply(
                        session_id, user_message, tools_used, quote_info
                    )
                    if country_reply:
                        return country_reply
                reply = (
                    f"Je n'ai pas d'autres activités « {', '.join(themes)} » à {dest} "
                    f"dans le catalogue. Souhaitez-vous revoir les options à {dest}, "
                    "ou une autre destination ?"
                )
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)
            if not pool:
                # Plus rien d'exclu → représenter le catalogue restant / vérité
                all_rows = result.activities if result.has_results() else []
                if not all_rows:
                    result2 = catalog_search(
                        CatalogSearchParams(
                            query=user_message,
                            destination=dest,
                            profil=profil,
                            limit=8,
                        )
                    )
                    tools_used.extend(result2.tools_used)
                    all_rows = result2.activities
                if all_rows:
                    # Tout déjà vu : le dire clairement
                    rk = region or region_key_for_destination(dest) or ""
                    cities = list_catalog_destinations_for_region(rk) if rk else [dest]
                    if len(cities) <= 1:
                        reply = (
                            f"Pour {dest}, le catalogue ne propose que les activités déjà "
                            "présentées. Souhaitez-vous en choisir une (ex. 1 et 2), "
                            "ou explorer une autre destination ?"
                        )
                    else:
                        reply = (
                            f"Pas d'autres activités à {dest} hors de la liste précédente. "
                            f"Autres villes catalogue : {', '.join(cities)}. "
                            "Laquelle souhaitez-vous ?"
                        )
                    conversation_manager.add_turn(session_id, user_message, reply)
                    return reply, tools_used, self._quote_meta(session_id, quote_info)
                return None

            save_proposed_activities(session_id, pool[:6])
            lines = []
            for i, row in enumerate(pool[:6], start=1):
                item = result.format_activity(row)
                lines.append(
                    format_activity_line(
                        i,
                        titre=item.get("titre") or "",
                        prix_net=item.get("prix_net") or "",
                        activity_id=item.get("id") or "",
                    )
                )
            reply = (
                f"D'accord, voici d'autres options à {dest} :\n"
                + "\n".join(lines)
                + "\nLaquelle vous intéresse (ex. 1 et 2) ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if region and region != "all":
            found = self._try_contextual_activity_search(
                session_id, user_message, tools_used, quote_info
            )
            if found:
                return found
        return None

    def _try_awaiting_add_theme_search(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """Après ask thématique (awaiting_add) : chercher une 2e liste sans perdre la sélection."""
        from search.catalog_search import CatalogSearchParams, catalog_search
        from search.themes import detect_themes_from_text

        slots = memory_manager.get_slots(session_id)
        if not str(slots.get("awaiting_add_activity", "") or "").strip():
            return None
        # Pays / autre option gérés ailleurs
        if detect_country_query(user_message):
            return None
        if is_wants_other_options(user_message) or is_reject_presented_list(user_message):
            return None
        dest = str(slots.get("destination", "") or "").strip()
        if not dest or not is_catalog_destination(dest):
            return None
        themes = detect_themes_from_text(user_message)
        if not themes:
            return None
        # Ne pas traiter comme sélection d'indices
        from memory.quote_state import parse_presentation_indices

        if parse_presentation_indices(user_message) or is_add_this_activity(user_message):
            return None

        memory_manager.update_slots(session_id, envies=", ".join(themes))
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None
        result = catalog_search(
            CatalogSearchParams(
                query=user_message,
                destination=dest,
                themes=themes,
                profil=profil,
                limit=8,
            )
        )
        tools_used.extend(result.tools_used)
        if not result.has_results():
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    destination=dest,
                    profil=profil,
                    limit=8,
                )
            )
            tools_used.extend(result.tools_used)
        if not result.has_results():
            reply = (
                f"Je n'ai pas trouvé d'activités « {', '.join(themes)} » à {dest}. "
                "Autre thématique (culture, plage, gastronomie…) ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        save_proposed_activities(session_id, result.activities[:6])
        lines: list[str] = []
        for i, row in enumerate(result.activities[:6], start=1):
            item = result.format_activity(row)
            lines.append(
                format_activity_line(
                    i,
                    titre=item.get("titre") or "",
                    prix_net=item.get("prix_net") or "",
                    activity_id=item.get("id") or "",
                )
            )
        selected = str(slots.get("activites_selectionnees", "") or "").strip()
        keep = (
            "Votre sélection précédente est conservée. "
            if selected
            else ""
        )
        reply = (
            f"{keep}Voici des options ({', '.join(themes)}) à {dest} :\n"
            + "\n".join(lines)
            + "\nIndiquez lesquelles ajouter (ex. 1, ou 1 et 2, ou « ajoute 1 »)."
        )
        # Garder awaiting_add_activity jusqu'au pick
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_faq_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """Question FAQ métier (commission, réservation…) — 0 token via faq.csv."""
        from agent.faq_policy import build_faq_reply, find_faq_answer

        row = find_faq_answer(user_message)
        if not row:
            return None
        tools_used.append("faq_lookup")
        reply = build_faq_reply(row)
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_quote_revision(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """Après devis / sélection : retirer une activité et régénérer le PDF si besoin."""
        from memory.quote_state import (
            REJECT_RE,
            REMOVE_SELECTION_RE,
        )

        if not (REMOVE_SELECTION_RE.search(user_message) or REJECT_RE.search(user_message)):
            return None

        slots = memory_manager.get_slots(session_id)
        selected = str(slots.get("activites_selectionnees", "") or "").strip()
        proposed = str(slots.get("activites_proposees", "") or "").strip()
        devis_ref = str(slots.get("devis_ref", "") or "").strip()
        if not selected and not proposed and not devis_ref:
            return None

        # sync_activity_feedback déjà fait en début de _chat — ne pas re-sync
        # (sinon « pas la 1re » retire deux fois la première restante)
        memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
        had_devis = bool(devis_ref)
        if had_devis:
            memory_manager.clear_slot(session_id, "devis_ref")

        state = compute_quote_state(session_id)
        if not state["activity_ids"]:
            # « j'ai pas aimé » sans sélection = refus de la liste, pas sélection vide
            if is_reject_presented_list(user_message) or (not selected and proposed):
                other = self._try_other_options_reply(
                    session_id, user_message, tools_used, quote_info, mark_rejected=True
                )
                if other:
                    return other
            reply = (
                "Il ne reste plus d'activité dans la sélection. "
                "Indiquez lesquelles garder (ex. 1 et 3), ou demandez d'autres options."
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        titles = ", ".join(a["titre"][:50] for a in state["activities"][:4])
        count = len(state["activities"])

        if had_devis and state.get("destination") and count >= 1:
            try:
                result = generate_quote_for_session(
                    session_id=session_id,
                    destination=state["destination"] or "",
                    activity_ids=state["activity_ids"],
                )
                quote_info["quote_url"] = result["pdf_url"]
                quote_info["devis_ref"] = result["devis_ref"]
                total = str(result["total_net"]).replace(" €", "")
                reply = (
                    f"Devis mis à jour ({count} activité(s), total net {total} €) : {titles}. "
                    f"Réf. {result['devis_ref']} — téléchargez le nouveau PDF ci-dessous."
                )
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)
            except Exception as exc:
                logger.warning("Régénération devis échouée : %s", exc)

        memory_manager.update_slots(session_id, awaiting_quote_confirm="1")
        reply = (
            f"Bien noté, sélection corrigée ({count} activité(s)) : {titles}. "
            f"C'est bon pour vous ? Souhaitez-vous que je prépare le devis White Label ?"
        )
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_activity_confirmation(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
        nlu: NLUExtract | None = None,
    ) -> tuple[str, list[str], dict] | None:
        # Question factuelle (« c'est à Istanbul ? ») ≠ confirmation devis
        if is_clarifying_question(user_message):
            return None

        from memory.quote_state import (
            REJECT_RE,
            REMOVE_SELECTION_RE,
            SELECT_ALL_RE,
            parse_presentation_indices,
            pick_activities_by_presentation_indices,
            sync_activity_feedback_from_message,
        )

        wants_all = bool(SELECT_ALL_RE.search(user_message))
        msg_indices = parse_presentation_indices(user_message)
        nlu_indices = list(nlu.selection_indices) if nlu and nlu.selection_indices else []
        indices = msg_indices or nlu_indices
        has_indices = bool(indices)
        wants_another = is_wants_another_activity(user_message) or bool(
            nlu and nlu.wants_another_activity
        )
        add_this = is_add_this_activity(user_message) or bool(
            nlu and nlu.add_this_activity
        )
        # Retrait (« pas la 1 ») : ne pas traiter comme une nouvelle sélection d'indices
        if REMOVE_SELECTION_RE.search(user_message) or REJECT_RE.search(user_message):
            return None

        nlu_quote = bool(
            nlu
            and (nlu.confirm_selection or nlu.intent in ("confirm", "quote"))
            and not nlu.wants_another_activity
            and not nlu.add_this_activity
            and nlu.intent != "add_activity"
        )
        is_quote_yes = (is_confirmation_message(user_message) or nlu_quote) and not add_this
        slots_pre = memory_manager.get_slots(session_id)
        awaiting_add = bool(
            str(slots_pre.get("awaiting_add_activity", "") or "").strip()
        )
        # « une autre activité » seule → garder la sélection, demander / chercher (pas de devis)
        if wants_another and not has_indices and not wants_all and not add_this and not is_quote_yes:
            memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
            memory_manager.update_slots(session_id, awaiting_add_activity="1")
            from search.themes import detect_themes_from_text

            if not detect_themes_from_text(user_message):
                reply = (
                    "Bien sûr. Quelle thématique pour l'activité supplémentaire : "
                    "culture, gastronomie, plage, aventure, détente ?"
                )
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)
            return None
        # Indices sur liste 2 pendant awaiting_add → même chemin que « ajoute »
        adding_from_list = awaiting_add and has_indices and not is_quote_yes
        # « tous c'est bon » = tout sélectionner + confirmer le devis
        if wants_all and is_quote_yes:
            sync_activity_feedback_from_message(session_id, user_message)
            is_selection_only = False
            confirmed = True
        elif add_this or adding_from_list:
            sync_activity_feedback_from_message(session_id, user_message)
            is_selection_only = not is_quote_yes
            confirmed = True
        else:
            # Sélection d'activités (ordinaux / les N) ≠ encore un oui devis
            is_selection_only = (has_indices or wants_all) and not is_quote_yes
            confirmed = is_quote_yes or has_indices or wants_all
        if not confirmed:
            return None

        # Appliquer indices NLU si le regex n'a rien vu
        if has_indices and not msg_indices and nlu_indices and not add_this:
            picks = pick_activities_by_presentation_indices(
                session_id, nlu_indices, rejected=set()
            )
            if picks:
                memory_manager.update_slots(
                    session_id, activites_selectionnees=",".join(picks)
                )
        # « les trois » / ordinaux message : forcer la sélection présentée
        elif (wants_all or msg_indices) and not (wants_all and is_quote_yes) and not add_this:
            sync_activity_feedback_from_message(session_id, user_message)

        slots = memory_manager.get_slots(session_id)
        discussed = str(slots.get("activites_discutees", "") or "").strip()
        proposed = str(slots.get("activites_proposees", "") or "").strip()
        selected = str(slots.get("activites_selectionnees", "") or "").strip()
        if not discussed and not proposed and not selected:
            return None

        # Garantit activites_selectionnees — sans élargir au cap 4 si le partenaire
        # a déjà choisi explicitement (ex. « les 3 premiers » puis « oui » / « le devis »).
        state = compute_quote_state(session_id)
        if not state["activity_ids"]:
            if is_quote_yes and not (has_indices or wants_all or add_this):
                # Oui devis sans sélection → ne pas remplir 4 activités depuis l'historique
                reply = (
                    "Indiquez d'abord les activités pour le devis "
                    "(ex. les 3 premiers, ou 1 et 2)."
                )
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)
            confirm_proposed_activities(session_id)
            state = compute_quote_state(session_id)
        if not state["activity_ids"]:
            return None

        titles = ", ".join(a["titre"][:50] for a in state["activities"][:4])
        count = len(state["activities"])

        # Ordinal + « une autre activité » → garder la sélection, demander le thème (pas de devis)
        if wants_another and has_indices and not is_quote_yes:
            memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
            memory_manager.update_slots(session_id, awaiting_add_activity="1")
            reply = (
                f"Bien noté ({count} activité(s)) : {titles}. "
                "Quelle thématique pour l'activité supplémentaire : "
                "culture, gastronomie, plage, aventure, détente ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        # Étape 1 — sélection seule / ajout : demander confirmation avant devis
        if is_selection_only:
            memory_manager.clear_slot(session_id, "awaiting_add_activity")
            memory_manager.update_slots(session_id, awaiting_quote_confirm="1")
            reply = (
                f"Bien noté ({count} activité(s)) : {titles}. "
                f"C'est bon pour vous ? Souhaitez-vous que je prépare le devis White Label ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        # Étape 2 — oui / c'est bon → devis (garde exactement la sélection, pas +1 jusqu'à 4)
        memory_manager.clear_slot(session_id, "awaiting_quote_confirm")
        memory_manager.clear_slot(session_id, "awaiting_add_activity")
        state = compute_quote_state(session_id)
        if state["quote_ready"]:
            auto = self._try_auto_generate_quote(session_id, user_message, quote_info)
            if auto:
                conversation_manager.add_turn(session_id, user_message, auto)
                return auto, tools_used, self._quote_meta(session_id, quote_info)
            reply = (
                f"Parfait. Votre sélection ({count} activité(s)) : {titles}. "
                "Cliquez sur le bouton Générer le devis PDF ci-dessous."
            )
        else:
            missing = ", ".join(m for m in state["missing"] if m != "confirmation_devis")
            reply = (
                f"Activités notées ({count}). "
                f"Pour le devis, il manque encore : {missing or 'quelques informations'}."
            )
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_auto_generate_quote(
        self,
        session_id: str,
        user_message: str,
        quote_info: dict[str, str | None],
    ) -> str | None:
        if not is_quote_confirmation(user_message):
            return None
        state = compute_quote_state(session_id)
        if not state["quote_ready"]:
            return None
        try:
            result = generate_quote_for_session(
                session_id=session_id,
                destination=state["destination"] or "",
                activity_ids=state["activity_ids"],
            )
            quote_info["quote_url"] = result["pdf_url"]
            quote_info["devis_ref"] = result["devis_ref"]
            titles = ", ".join(a["titre"][:40] for a in state["activities"][:3])
            total = str(result["total_net"]).replace(" €", "")
            return (
                f"Votre devis {result['devis_ref']} est prêt pour {state['destination']} "
                f"({result['activity_count']} activité(s), total net {total} €). "
                f"Sélection : {titles}. Téléchargez le PDF ci-dessous."
            )
        except Exception as exc:
            logger.warning("Auto-génération devis échouée : %s", exc)
            return None

    def _capture_quote_from_tool(self, name: str, result: str, quote_info: dict[str, str | None]) -> None:
        if name != "generate_quote":
            return
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return
        if data.get("status") == "ok" and data.get("pdf_url"):
            quote_info["quote_url"] = data["pdf_url"]
            quote_info["devis_ref"] = data.get("devis_ref")

    def chat(self, session_id: str, user_message: str) -> tuple[str, list[str], dict[str, str | None]]:
        usage_token = start_llm_usage_tracking()
        slots0 = memory_manager.get_slots(session_id)
        partner_id = str(slots0.get("partner_id", "") or "").strip()
        turn_token = start_chat_turn(
            session_id=session_id,
            user_message=user_message,
            partner_id=partner_id,
        )
        try:
            reply, tools_used, meta = self._chat(session_id, user_message)
            usage = current_llm_usage()
            finish_chat_turn(
                tools_used=tools_used,
                reply=reply,
                meta=meta if isinstance(meta, dict) else {},
                usage=usage,
            )
            return reply, tools_used, meta
        except Exception as exc:
            finish_chat_turn(
                tools_used=[],
                reply="",
                meta={},
                usage=current_llm_usage(),
                error=str(exc)[:200],
            )
            raise
        finally:
            reset_chat_turn(turn_token)
            reset_llm_usage_tracking(usage_token)

    def _try_raise_budget_reply(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """« augmentez le budget » → lever le plafond et relancer la recherche."""
        from search.catalog_search import (
            CatalogSearchParams,
            build_region_activities_reply,
            catalog_search,
        )
        from search.geo import format_qualification_note

        memory_manager.clear_slot(session_id, "budget")
        slots = memory_manager.get_slots(session_id)
        region = str(slots.get("region_interest", "") or "").strip()
        dest = str(slots.get("destination", "") or "").strip()
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None
        context_note = format_qualification_note(slots)
        note = (context_note + " " if context_note else "") + "Budget élargi (sans plafond)."

        if region and region != "all":
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    region=region,
                    budget_max=None,
                    profil=profil,
                    limit=8,
                )
            )
            tools_used.extend(result.tools_used)
            reply = build_region_activities_reply(
                region, result, budget_max=None, context_note=note
            )
            if result.has_results():
                save_proposed_activities(session_id, result.activities[:6])
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if dest and is_catalog_destination(dest):
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    destination=dest,
                    budget_max=None,
                    profil=profil,
                    limit=8,
                )
            )
            tools_used.extend(result.tools_used)
            if result.has_results():
                save_proposed_activities(session_id, result.activities[:6])
                lines = []
                for i, row in enumerate(result.activities[:6], start=1):
                    item = result.format_activity(row)
                    lines.append(
                        format_activity_line(
                            i,
                            titre=item.get("titre") or "",
                            prix_net=item.get("prix_net") or "",
                            activity_id=item.get("id") or "",
                        )
                    )
                reply = (
                    f"Budget élargi pour {dest}. Voici des activités du catalogue :\n"
                    + "\n".join(lines)
                    + "\nLaquelle vous intéresse (ex. 1 et 2) ?"
                )
            else:
                reply = (
                    f"Budget élargi. Je n'ai pas trouvé d'activités catalogue pour {dest}. "
                    "Souhaitez-vous une autre destination ?"
                )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        reply = (
            "D'accord, je retire le plafond budgétaire. "
            "Indiquez une ville ou une zone catalogue pour relancer la recherche "
            "(ex. Afrique, Espagne, Paris)."
        )
        conversation_manager.add_turn(session_id, user_message, reply)
        return reply, tools_used, self._quote_meta(session_id, quote_info)

    def _try_contextual_activity_search(
        self,
        session_id: str,
        user_message: str,
        tools_used: list[str],
        quote_info: dict[str, str | None],
    ) -> tuple[str, list[str], dict] | None:
        """Search dès que destination ou region_interest est connu + demande activités/budget."""
        from search.catalog_search import (
            CatalogSearchParams,
            build_region_activities_reply,
            catalog_search,
        )
        from search.geo import format_qualification_note

        slots = memory_manager.get_slots(session_id)
        region = str(slots.get("region_interest", "") or "").strip()
        dest = str(slots.get("destination", "") or "").strip()
        profil = str(slots.get("profil_voyageur", "") or "").strip() or None
        budget_raw = str(slots.get("budget", "") or "").strip()
        budget_max: float | None = None
        if budget_raw:
            try:
                budget_max = float(budget_raw.replace(",", "."))
            except ValueError:
                budget_max = None
        context_note = format_qualification_note(slots)

        if region and region != "all":
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    region=region,
                    budget_max=budget_max,
                    profil=profil,
                    limit=8,
                )
            )
            fallback = None
            if not result.has_results() and budget_max:
                fallback = catalog_search(
                    CatalogSearchParams(
                        query=user_message,
                        region=region,
                        budget_max=None,
                        profil=profil,
                        limit=8,
                    )
                )
            tools_used.extend(result.tools_used)
            if fallback:
                tools_used.extend(fallback.tools_used)
            reply = build_region_activities_reply(
                region,
                result,
                budget_max=budget_max,
                context_note=context_note,
                fallback_without_budget=fallback,
            )
            pool = result.activities if result.has_results() else (
                fallback.activities if fallback and fallback.has_results() else []
            )
            if pool:
                save_proposed_activities(session_id, pool[:6])
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if dest and is_catalog_destination(dest):
            result = catalog_search(
                CatalogSearchParams(
                    query=user_message,
                    destination=dest,
                    budget_max=budget_max,
                    profil=profil,
                    limit=8,
                )
            )
            tools_used.extend(result.tools_used)
            if result.has_results():
                save_proposed_activities(session_id, result.activities[:6])
                lines = []
                for i, row in enumerate(result.activities[:6], start=1):
                    item = result.format_activity(row)
                    lines.append(
                        format_activity_line(
                            i,
                            titre=item.get("titre") or "",
                            prix_net=item.get("prix_net") or "",
                            activity_id=item.get("id") or "",
                        )
                    )
                budget_txt = f" (≤ {int(budget_max)} €)" if budget_max else ""
                reply = (
                    f"Voici des activités à {dest}{budget_txt} :\n"
                    + "\n".join(lines)
                    + f"\n{context_note} Laquelle vous intéresse ?"
                ).strip()
            else:
                reply = (
                    f"Aucune activité catalogue"
                    + (f" ≤ {int(budget_max)} €" if budget_max else "")
                    + f" pour {dest}. "
                    + (f"{context_note} " if context_note else "")
                    + "Souhaitez-vous augmenter le budget ou changer de destination ?"
                )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        return None

    def _chat(self, session_id: str, user_message: str) -> tuple[str, list[str], dict[str, str | None]]:
        self._ensure_configured()
        quote_info: dict[str, str | None] = {"quote_url": None, "devis_ref": None}

        # Normalisation unique (apostrophes, espaces, unicode) — une fois pour tous
        from agent.conversation_state import normalize_message

        user_message = normalize_message(user_message)

        sync_slots_from_message(session_id, user_message)
        tools_used: list[str] = []

        from agent.destination_policy import build_destination_help_reply, is_destination_not_chosen_yet
        from agent.intent_router import (
            RouteKind,
            build_need_place_reply,
            classify_route,
        )

        slots_now = memory_manager.get_slots(session_id)
        route = classify_route(user_message, slots_now)

        from agent.conversation_state import ConvState, classify_intent, derive_state

        conv_state = derive_state(slots_now)
        intent_now = classify_intent(user_message)
        update_turn(
            conv_state=conv_state.value,
            route_kind=route.kind.value,
            route_reason=route.reason,
            intent=intent_now.value,
            partner_id=str(slots_now.get("partner_id", "") or "").strip(),
            destination=str(slots_now.get("destination", "") or "").strip(),
        )
        # Trace de routage : une ligne par message pour diagnostiquer les misroutes
        logger.info(
            "chat.in session=%s state=%s route=%s/%s intent=%s msg=%r",
            session_id,
            conv_state.value,
            route.kind.value,
            route.reason,
            intent_now.value,
            user_message[:80],
        )

        # ——— Routeur (priorité fixe, 0 token) ———
        if route.kind == RouteKind.SUPPORT_EMAIL or route.kind == RouteKind.SUPPORT:
            support_reply = self._try_support_reply(
                session_id, user_message, tools_used, quote_info
            )
            if support_reply:
                return support_reply

        if route.kind == RouteKind.FAQ:
            faq_reply = self._try_faq_reply(
                session_id, user_message, tools_used, quote_info
            )
            if faq_reply:
                return faq_reply

        # ——— Machine à états : message interprété relativement à l'état ———
        # AWAITING_QUOTE_CONFIRM : oui (même typo « ouii ») → devis, avant tout
        # autre chemin (pays, recherche, lieu inconnu…).
        if conv_state is ConvState.AWAITING_QUOTE_CONFIRM and is_confirmation_message(
            user_message
        ):
            confirm_early = self._try_activity_confirmation(
                session_id, user_message, tools_used, quote_info, nlu=None
            )
            if confirm_early:
                return confirm_early

        # « oui » / ville après « Souhaitez-vous explorer X ? » — avant devis & ask destination
        pending_city = self._try_pending_city_reply(
            session_id, user_message, tools_used, quote_info
        )
        if pending_city:
            return pending_city

        # Pays / continent (typos Afrique du Sud…) AVANT thème awaiting_add
        if route.kind == RouteKind.COUNTRY_OR_CONTINENT or detect_country_query(
            user_message
        ):
            memory_manager.clear_slot(session_id, "awaiting_add_activity")
            country_reply = self._try_country_catalog_reply(
                session_id, user_message, tools_used, quote_info
            )
            if country_reply:
                return country_reply

        # « j'ai pas aimé » / « autre option » → nouvelle liste (pas ask thème add)
        if is_wants_other_options(user_message) or is_reject_presented_list(user_message):
            other = self._try_other_options_reply(
                session_id,
                user_message,
                tools_used,
                quote_info,
                mark_rejected=is_reject_presented_list(user_message),
            )
            if other:
                return other

        # Thème pendant « autre activité » → nouvelle liste (sélection liste 1 conservée)
        add_theme = self._try_awaiting_add_theme_search(
            session_id, user_message, tools_used, quote_info
        )
        if add_theme:
            return add_theme

        if route.kind == RouteKind.NOT_CHOSEN_YET or is_destination_not_chosen_yet(user_message):
            reply = build_destination_help_reply()
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if route.kind == RouteKind.RAISE_BUDGET:
            raised = self._try_raise_budget_reply(
                session_id, user_message, tools_used, quote_info
            )
            if raised:
                return raised

        if route.kind == RouteKind.NEED_PLACE_FOR_SEARCH:
            reply = build_need_place_reply(memory_manager.get_slots(session_id))
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if route.kind == RouteKind.SEARCH_ACTIVITIES:
            if route.reason == "other_options" or is_wants_other_options(user_message):
                other = self._try_other_options_reply(
                    session_id, user_message, tools_used, quote_info, mark_rejected=True
                )
                if other:
                    return other
            found = self._try_contextual_activity_search(
                session_id, user_message, tools_used, quote_info
            )
            if found:
                return found

        if route.kind == RouteKind.COUNTRY_OR_CONTINENT:
            country_reply = self._try_country_catalog_reply(
                session_id, user_message, tools_used, quote_info
            )
            if country_reply:
                return country_reply

        # Support (si non capturé plus haut)
        support_reply = self._try_support_reply(
            session_id, user_message, tools_used, quote_info
        )
        if support_reply:
            return support_reply

        # Correction post-devis / retrait d'activité AVANT sélection classique
        revision = self._try_quote_revision(
            session_id, user_message, tools_used, quote_info
        )
        if revision:
            return revision

        # Sélection / oui devis PURS (0 token) — avant hors-catalogue
        # (le oui pendant AWAITING_QUOTE_CONFIRM est déjà traité en tête de _chat)
        if (
            route.kind == RouteKind.PURE_SELECTION
            or is_pure_selection_or_confirm_message(user_message)
        ):
            select_reply = self._try_activity_confirmation(
                session_id, user_message, tools_used, quote_info, nlu=None
            )
            if select_reply:
                return select_reply

        # « autre activité » / « 1 est ok + d'autres » (CONTINUE) — avant NLU / search LLM
        if is_wants_another_activity(user_message):
            another_reply = self._try_activity_confirmation(
                session_id, user_message, tools_used, quote_info, nlu=None
            )
            if another_reply:
                return another_reply

        # Lieu/pays hors catalogue (Monaco, Toulouse…) — AVANT NLU / continent inventé
        unknown_early = detect_unknown_place_request(user_message, session_id=session_id)
        if unknown_early:
            return self._reply_destination_unavailable(
                session_id, user_message, unknown_early, tools_used, quote_info
            )

        # NLU structuré (Claude) — langage flou / mixte avant action Python
        nlu = self._run_nlu(session_id, user_message)
        self._apply_nlu_side_effects(session_id, nlu)
        self._maybe_set_destination(session_id, user_message, nlu=nlu)

        # Continent / pays détectés par NLU si le regex a manqué
        # Priorité : pays catalogue (message ou NLU) > continent NLU
        # Ne jamais élargir au continent si le message est un lieu isolé hors catalogue
        from search.geo import detect_catalog_country_query

        country_from_msg = detect_catalog_country_query(user_message)
        region_key = country_from_msg or nlu.country or nlu.continent
        if region_key and not country_from_msg and not nlu.country:
            # Continent NLU seul : refuser si le message ressemble à un toponyme hors catal.
            if detect_unknown_place_request(user_message, session_id=None):
                region_key = None
        if region_key:
            slots_now = memory_manager.get_slots(session_id)
            dest_now = str(slots_now.get("destination", "") or "").strip()
            # Ne pas écraser une ville session avec un faux continent (titre « asiatique »)
            if (
                dest_now
                and is_catalog_destination(dest_now)
                and not nlu.destination
                and not is_explicit_region_request(user_message)
            ):
                region_key = None
            if region_key:
                from search.catalog_search import (
                    CatalogSearchParams,
                    build_theme_region_reply,
                    catalog_search,
                )
                from search.geo import (
                    build_country_catalog_reply,
                    list_catalog_destinations_for_region,
                )
                from search.themes import detect_themes_from_text

                cities = list_catalog_destinations_for_region(region_key)
                themes = list(nlu.envies) or detect_themes_from_text(user_message)
                if region_key != "all":
                    memory_manager.update_slots(session_id, region_interest=region_key)
                if themes and not nlu.destination:
                    memory_manager.update_slots(session_id, envies=", ".join(themes))
                    result = catalog_search(
                        CatalogSearchParams(
                            query=user_message,
                            themes=themes,
                            region=region_key,
                            limit=8,
                        )
                    )
                    tools_used.extend(result.tools_used)
                    reply = build_theme_region_reply(region_key, themes, result)
                    conversation_manager.add_turn(session_id, user_message, reply)
                    return reply, tools_used, self._quote_meta(session_id, quote_info)
                if cities and (
                    country_from_msg
                    or nlu.country
                    or nlu.intent in ("list_destinations", "search", "qualify", "other")
                ):
                    # Ne pas court-circuiter si une destination ville est déjà claire
                    if not nlu.destination:
                        reply = build_country_catalog_reply(region_key, cities)
                        from agent.destination_confirm import remember_city_offer

                        remember_city_offer(session_id, cities, region_key=region_key)
                        conversation_manager.add_turn(session_id, user_message, reply)
                        return reply, tools_used, self._quote_meta(session_id, quote_info)

        # Sélection / ajout / devis — Python agit sur le JSON NLU (+ filet regex)
        confirm_reply = self._try_activity_confirmation(
            session_id, user_message, tools_used, quote_info, nlu=nlu
        )
        if confirm_reply:
            return confirm_reply
        early = self._check_destination_availability(
            session_id, user_message, tools_used, quote_info, nlu=nlu
        )
        if early:
            return early

        slots = memory_manager.get_slots(session_id)
        escalated = memory_manager.is_escalated(session_id)
        intent = detect_intent(user_message, escalated=escalated)
        if nlu.intent == "quote":
            intent = Intent.QUOTE
        elif nlu.intent in ("search", "add_activity") and intent == Intent.GENERAL:
            intent = Intent.ACTIVITY_SEARCH
        elif nlu.intent == "list_destinations":
            intent = Intent.COUNTRY_QUERY

        search_result = search_from_context(user_message, slots)
        tools_used = list(search_result.tools_used)

        dest_slot = str(slots.get("destination", "") or "").strip()
        if dest_slot and is_catalog_destination(dest_slot) and not search_result.has_results():
            if (
                "activit" in user_message.casefold()
                or intent in (Intent.ACTIVITY_SEARCH, Intent.QUOTE)
                or (nlu and nlu.wants_another_activity)
                or is_wants_another_activity(user_message)
            ):
                # Laisser le LLM + tools chercher plutôt qu'un refus sec si demande d'autre activité
                if not (
                    (nlu and nlu.wants_another_activity)
                    or is_wants_another_activity(user_message)
                ):
                    reply = build_no_activities_reply(dest_slot)
                    conversation_manager.add_turn(session_id, user_message, reply)
                    return reply, tools_used, self._quote_meta(session_id, quote_info)

        plan = plan_next(
            intent,
            slots,
            has_catalog_results=search_result.has_results(),
            escalated=escalated,
        )
        if nlu.wants_another_activity or is_wants_another_activity(user_message):
            plan = Plan(Action.USE_TOOLS, "Ajouter une activité catalogue", one_question_only=False)

        # Support / escalade : réponse e-mail déterministe (0 token) — pas de « conseiller chat »
        if plan.action == Action.ESCALATE or intent == Intent.SUPPORT:
            from agent.support_policy import build_support_email_reply, escalate_session, is_support_request

            if intent == Intent.SUPPORT or is_support_request(user_message) or escalated:
                payload = escalate_session(session_id, reason=user_message[:120])
                tools_used.append("escalate_to_advisor")
                reply = payload.get("message") or build_support_email_reply()
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)

        if is_qualification_message(user_message) and plan.action == Action.ASK_ENVIES:
            # Demande explicite d'activités / budget → search plutôt que reposer les envies
            from agent.intent_router import wants_activity_listing

            if wants_activity_listing(user_message) or str(slots.get("budget", "") or "").strip():
                found = self._try_contextual_activity_search(
                    session_id, user_message, tools_used, quote_info
                )
                if found:
                    return found
            dest = str(slots.get("destination", "") or "").strip() or "cette destination"
            profil = str(slots.get("profil_voyageur", "") or "").strip()
            profil_labels = {
                "couple": "couple",
                "famille": "famille",
                "solo": "solo",
                "groupe": "groupe",
                "groupe_amis": "groupe d'amis",
                "seminaire": "séminaire",
            }
            profil_text = profil_labels.get(profil, profil or "voyageurs")
            reply = (
                f"Noté, voyage en {profil_text} à {dest}. "
                f"Qu'est-ce qui attire votre client : plage, montagne, forêt, culture, aventure, détente ?"
            )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        if is_qualification_message(user_message) and plan.action == Action.ASK_PROFIL:
            dest = str(slots.get("destination", "") or "").strip()
            if dest:
                reply = (
                    f"Parfait pour {dest} ! Votre client voyage en couple, en famille, "
                    f"en groupe, en solo ou en séminaire ?"
                )
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)

        if plan.action == Action.ASK_DESTINATION:
            # « non pas encore » → aide (région / thème / villes), pas la même question
            if is_destination_not_chosen_yet(user_message):
                reply = build_destination_help_reply()
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)

            slots = memory_manager.get_slots(session_id)
            bits: list[str] = []
            taille = str(slots.get("taille_groupe", "") or "").strip()
            duree = str(slots.get("duree", "") or "").strip()
            profil = str(slots.get("profil_voyageur", "") or "").strip()
            if taille:
                bits.append(f"{taille} personnes")
            if profil:
                bits.append(f"profil {profil.replace('_', ' ')}")
            if duree:
                bits.append(duree)
            if bits:
                reply = (
                    f"Bien noté ({', '.join(bits)}). "
                    f"Quelle destination pour votre client ?"
                )
            else:
                agency = resolve_agency_name(session_id)
                if intent == Intent.GREETING and agency:
                    reply = build_greeting_reply(agency)
                else:
                    reply = (
                        "Votre client a choisi sa destination ? "
                        "Dites-moi où il va — je vous montre ce qu'il peut y vivre."
                    )
            conversation_manager.add_turn(session_id, user_message, reply)
            return reply, tools_used, self._quote_meta(session_id, quote_info)

        blocked = unavailable_place_from_slots(memory_manager.get_slots(session_id))
        if (
            blocked
            and not str(memory_manager.get_slots(session_id).get("destination", "") or "").strip()
            and plan.action
            in (
                Action.ASK_PROFIL,
                Action.ASK_ENVIES,
                Action.PRESENT_RESULTS,
                Action.CONFIRM_QUOTE,
            )
        ):
            return self._reply_destination_unavailable(
                session_id, user_message, blocked, tools_used, quote_info
            )

        if intent == Intent.GREETING and plan.action == Action.ASK_DESTINATION:
            agency = resolve_agency_name(session_id)
            if agency:
                reply = build_greeting_reply(agency)
                conversation_manager.add_turn(session_id, user_message, reply)
                return reply, tools_used, self._quote_meta(session_id, quote_info)

        auto_quote_reply = self._try_auto_generate_quote(session_id, user_message, quote_info)
        if auto_quote_reply:
            conversation_manager.add_turn(session_id, user_message, auto_quote_reply)
            return auto_quote_reply, tools_used, self._quote_meta(session_id, quote_info)

        inject_catalog = self._should_inject_catalog(plan, intent)

        if inject_catalog and search_result.has_results():
            slots = memory_manager.get_slots(session_id)
            proposed = pick_proposed_activities(search_result.activities, slots)
            if proposed:
                save_proposed_activities(session_id, proposed)

        blocks: list[str] = []
        llm_catalog = self._catalog_for_llm(search_result)
        if inject_catalog:
            if llm_catalog.has_results():
                blocks.append(llm_catalog.to_prompt_block())
            elif intent == Intent.ACTIVITY_SEARCH:
                blocks.append(llm_catalog.to_prompt_block("Aucune activité catalogue"))

        catalog_context = append_order_and_faq(user_message, blocks, tools_used)
        agency_name = resolve_agency_name(session_id)
        action_instruction = build_action_instruction(plan, agency_name=agency_name)

        system_content = self._build_system_prompt(session_id, action_instruction, plan)
        if nlu.intent != "other" or nlu.destination or nlu.envies or nlu.confirm_selection:
            system_content += "\n\n" + nlu.to_prompt_block()
        if nlu.wants_another_activity or is_wants_another_activity(user_message):
            system_content += (
                "\nLe partenaire veut AJOUTER une activité. "
                "Appelez search_catalog et proposez 1–2 options supplémentaires (titres et prix_net exacts)."
            )
        if catalog_context:
            system_content += (
                "\n\nDONNÉES CATALOGUE (source fiable — seule source pour titres et prix) :\n"
                + catalog_context
            )
            if context_has_activities(catalog_context):
                system_content += (
                    "\n\nOBLIGATION : citez les activités du JSON (titre, prix_net, zone). "
                    "Pas de devis ni logement inventés."
                )
            else:
                blocked = unavailable_place_from_slots(memory_manager.get_slots(session_id))
                note = (
                    f"AUCUNE ACTIVITÉ pour {blocked} — ne listez RIEN, ne proposez PAS d'autres pays."
                    if blocked
                    else "AUCUNE ACTIVITÉ — ne listez rien. Ne proposez pas d'autres destinations sans accord."
                )
                system_content += f"\n\n{note}"

        if plan.action == Action.PRESENT_RESULTS:
            system_content += (
                "\n\nLISTE OBLIGATOIRE : présentez 3–4 activités du JSON ainsi :\n"
                "1. Titre exact — prix_net €\n"
                "2. Titre exact — prix_net €\n"
                "3. Titre exact — prix_net €\n"
                "Une seule liste numérotée. INTERDIT de regrouper par thème "
                "(Spectacles, Musées, Croisières, etc.). Aucune activité hors JSON."
            )
        if plan.action == Action.CONFIRM_QUOTE:
            system_content += (
                "\n\nDEVIS : ne jamais simuler ni envoyer par e-mail. "
                "Indiquez au partenaire de cliquer sur le bouton « Générer le devis PDF »."
            )

        if not self._uses_native_tools():
            system_content += (
                "\n\nIMPORTANT : prix_net du JSON uniquement. Une question par message si qualification."
            )

        quote_meta = self._quote_meta(session_id)

        mark_dialog()
        messages: list[dict] = [{"role": "system", "content": system_content}]
        messages.extend(
            conversation_manager.get_history(
                session_id,
                limit=self._history_limit(),
            )
        )
        messages.append({"role": "user", "content": user_message})

        llm_kwargs = self._litellm_kwargs()
        use_tools = self._uses_native_tools() and self._should_use_tools(plan, intent)

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self._completion(messages, use_tools=use_tools, base_kwargs=llm_kwargs)
                assistant_message = response.choices[0].message
                messages.append(self._message_to_dict(assistant_message))

                tool_calls = getattr(assistant_message, "tool_calls", None) or []
                if not tool_calls:
                    reply = sanitize_response((assistant_message.content or "").strip())
                    record_discussed_activities_from_text(session_id, reply)
                    meta = self._quote_meta(session_id, quote_info)
                    reply = self._finalize_reply(reply, plan, meta)
                    conversation_manager.add_turn(session_id, user_message, reply)
                    return reply, tools_used, meta

                for tool_call in tool_calls:
                    fn = tool_call.function
                    name = fn.name
                    try:
                        args = json.loads(fn.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tools_used.append(name)
                    logger.info("Tool call: %s(%s)", name, args)
                    result = execute_tool(session_id, name, args)
                    self._capture_quote_from_tool(name, result, quote_info)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": name,
                            "content": result,
                        }
                    )

            fallback = "Pouvez-vous préciser la destination ou le type d'expérience recherchée ?"
            conversation_manager.add_turn(session_id, user_message, fallback)
            return fallback, tools_used, self._quote_meta(session_id, quote_info)

        except RateLimitError:
            raise AgentError(
                "Le service IA est temporairement saturé (quota). "
                "Réessayez dans quelques secondes ou vérifiez LLM_FALLBACK_MODEL dans .env."
            ) from None
        except BadRequestError as exc:
            logger.exception("LLM bad request")
            if "tool_use_failed" in str(exc) and catalog_context:
                try:
                    response = litellm.completion(messages=messages, **llm_kwargs)
                    self._record_llm_usage(response, self.settings.llm_model)
                    reply = sanitize_response((response.choices[0].message.content or "").strip())
                    if reply:
                        record_discussed_activities_from_text(session_id, reply)
                        meta = self._quote_meta(session_id, quote_info)
                        reply = self._finalize_reply(reply, plan, meta)
                        conversation_manager.add_turn(session_id, user_message, reply)
                        return reply, tools_used, meta
                except Exception:
                    pass
            raise AgentError(f"Erreur du modèle IA : {exc}") from exc
        except (Timeout, APIConnectionError):
            raise AgentError("Impossible de joindre le service IA.") from None
        except Exception as exc:
            logger.exception("LLM error")
            raise AgentError(f"Erreur du modèle IA : {exc}") from exc


orchestrator = Orchestrator()

# Compatibilité routes existantes
agent_service = orchestrator
