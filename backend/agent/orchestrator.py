"""Orchestrateur agent — point d'entrée conversationnel."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import litellm
from litellm.exceptions import APIConnectionError, BadRequestError, RateLimitError, Timeout

from agent.context_manager import sync_slots_from_message
from agent.intent_detector import Intent, detect_intent
from agent.partner_context import build_greeting_reply, resolve_agency_name
from agent.planner import Action, Plan, build_action_instruction, plan_next
from agent.response_generator import sanitize_response
from app.config import get_settings
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    compute_quote_state,
    detect_destination_in_message,
    is_quote_confirmation,
    pick_proposed_activities,
    record_discussed_activities_from_text,
    save_proposed_activities,
)
from pdf.quote_generator import generate_quote_for_session
from search.catalog_search import (
    append_order_and_faq,
    context_has_activities,
    search_from_context,
)
from search.geo import resolve_destination_name
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

    def _build_system_prompt(self, session_id: str, action_instruction: str) -> str:
        parts = [
            self._load_prompt("system_prompt.txt"),
            "",
            self._load_prompt("tunnel_antoine.txt"),
            "",
            "MÉMOIRE SESSION :",
            memory_manager.context_summary(session_id),
            "",
            action_instruction,
        ]
        if memory_manager.is_escalated(session_id):
            parts.append("\nNote : session escaladée vers un conseiller humain.")
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
        return kwargs

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
        return models

    def _uses_native_tools_for(self, model: str) -> bool:
        return not model.startswith("groq/")

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
                    return litellm.completion(**completion_kwargs)
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
        if self.settings.llm_model.startswith("groq/") and not self.settings.groq_api_key:
            raise AgentConfigurationError("GROQ_API_KEY manquante dans .env")
        if self.settings.llm_model.startswith("gemini/") and not self.settings.gemini_api_key:
            raise AgentConfigurationError("GEMINI_API_KEY manquante dans .env")

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
        return meta

    def _finalize_reply(self, reply: str, plan: Plan, quote_meta: dict) -> str:
        if plan.action == Action.CONFIRM_QUOTE and quote_meta.get("quote_ready"):
            if "générer le devis" not in reply.casefold():
                reply = (
                    f"{reply}\n\n"
                    "Cliquez sur le bouton **Générer le devis PDF** ci-dessous pour télécharger votre devis White Label."
                )
        return reply

    def _maybe_set_destination(self, session_id: str, message: str) -> None:
        dest = detect_destination_in_message(message)
        if dest:
            memory_manager.update_slots(session_id, destination=dest)
            from memory.quote_state import _prune_wrong_destination

            _prune_wrong_destination(session_id, dest)
            return
        tokens = message.strip().split()
        if len(tokens) <= 4:
            candidate = message.strip()
            if resolve_destination_name(candidate, data_loader):
                memory_manager.update_slots(session_id, destination=candidate.title())

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
        self._ensure_configured()
        quote_info: dict[str, str | None] = {"quote_url": None, "devis_ref": None}

        sync_slots_from_message(session_id, user_message)
        self._maybe_set_destination(session_id, user_message)

        slots = memory_manager.get_slots(session_id)
        escalated = memory_manager.is_escalated(session_id)
        intent = detect_intent(user_message, escalated=escalated)

        search_result = search_from_context(user_message, slots)
        tools_used: list[str] = list(search_result.tools_used)

        plan = plan_next(
            intent,
            slots,
            has_catalog_results=search_result.has_results(),
            escalated=escalated,
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
        if inject_catalog:
            if search_result.has_results():
                blocks.append(search_result.to_prompt_block())
            elif intent == Intent.ACTIVITY_SEARCH:
                blocks.append(search_result.to_prompt_block("Aucune activité catalogue"))

        catalog_context = append_order_and_faq(user_message, blocks, tools_used)
        agency_name = resolve_agency_name(session_id)
        action_instruction = build_action_instruction(plan, agency_name=agency_name)

        system_content = self._build_system_prompt(session_id, action_instruction)
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
                system_content += (
                    "\n\nAUCUNE ACTIVITÉ — ne listez rien. Proposez d'élargir ou escalader."
                )

        if not self._uses_native_tools():
            system_content += (
                "\n\nIMPORTANT : prix_net du JSON uniquement. Une question par message si qualification."
            )
            if plan.action == Action.PRESENT_RESULTS:
                system_content += (
                    "\n\nLISTE OBLIGATOIRE : numérotez 3–4 activités du JSON avec titres et prix_net EXACTS. "
                    "Aucune activité hors JSON (pas de médina/riad/désert inventés)."
                )
            if plan.action == Action.CONFIRM_QUOTE:
                system_content += (
                    "\n\nDEVIS : ne jamais simuler ni envoyer par e-mail. "
                    "Indiquez au partenaire de cliquer sur le bouton « Générer le devis PDF »."
                )

        quote_meta = self._quote_meta(session_id)

        messages: list[dict] = [{"role": "system", "content": system_content}]
        messages.extend(conversation_manager.get_history(session_id))
        messages.append({"role": "user", "content": user_message})

        llm_kwargs = self._litellm_kwargs()
        use_tools = self._uses_native_tools()

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
                "Le service IA est temporairement saturé (quota Groq/Gemini). "
                "Réessayez dans 30 secondes, ou basculez LLM_MODEL vers gemini/gemini-2.0-flash dans .env."
            ) from None
        except BadRequestError as exc:
            logger.exception("LLM bad request")
            if "tool_use_failed" in str(exc) and catalog_context:
                try:
                    response = litellm.completion(messages=messages, **llm_kwargs)
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
