"""Escalade support → e-mail (pas de conseiller in-chat)."""

from unittest.mock import MagicMock, patch

from agent.intent_detector import Intent, detect_intent
from agent.orchestrator import orchestrator
from agent.support_policy import (
    DEFAULT_SUPPORT_EMAIL,
    build_support_contact_reply,
    build_support_email_reply,
    escalate_session,
    is_support_email_inquiry,
    is_support_request,
)
from memory.memory_manager import memory_manager
from tools.registry import execute_tool


def test_support_request_detection() -> None:
    assert is_support_request("je veux un remboursement")
    assert is_support_request("j ai une réclamation")
    assert is_support_request("litige sur ma commande")
    assert detect_intent("je veux un remboursement") == Intent.SUPPORT


def test_support_email_inquiry_detection() -> None:
    assert is_support_email_inquiry("c est quoi votre e mail ?")
    assert is_support_email_inquiry("c'est quoi votre email")
    assert is_support_email_inquiry("quelle est votre adresse mail")
    assert is_support_email_inquiry("votre email support")
    assert is_support_email_inquiry("donnez moi votre mail")
    assert is_support_email_inquiry("comment je peux contacter le support")
    assert is_support_email_inquiry("comment contacter le support ?")
    assert is_support_email_inquiry("comment joindre le SAV")
    assert is_support_email_inquiry("comment faire pour contacter le support")
    assert not is_support_email_inquiry("je veux un remboursement")
    assert not is_support_email_inquiry("Paris")


def test_support_contact_reply_gives_email() -> None:
    reply = build_support_contact_reply()
    assert DEFAULT_SUPPORT_EMAIL in reply or "support@" in reply
    assert "adresse support" in reply.casefold()


def test_support_email_reply_mentions_mail_not_chat_callback() -> None:
    reply = build_support_email_reply(reason="remboursement")
    assert DEFAULT_SUPPORT_EMAIL in reply or "support@" in reply
    assert "écrire" in reply.casefold() or "ecrire" in reply.casefold()
    assert "contactera rapidement" not in reply.casefold()
    assert "transmise à notre équipe" not in reply.casefold()


def test_escalate_tool_returns_email() -> None:
    session = "escalate-email"
    raw = execute_tool(session, "escalate_to_advisor", {"reason": "remboursement"})
    import json

    data = json.loads(raw) if isinstance(raw, str) else raw
    assert data.get("support_email")
    assert "support@" in data["support_email"]
    assert memory_manager.is_escalated(session)
    assert "contactera" not in (data.get("message") or "").casefold()


def test_escalate_session_payload() -> None:
    session = "escalate-session-2"
    payload = escalate_session(session, reason="plainte")
    assert payload["status"] == "escalated_to_email"
    assert payload["support_email"]
    assert memory_manager.is_escalated(session)


@patch("agent.orchestrator.get_settings")
def test_email_question_returns_support_address_zero_token(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        support_email=DEFAULT_SUPPORT_EMAIL,
    )
    session = "ask-email"
    memory_manager.update_slots(session, partner_id="33", nom_agence="Japanticket Inc.")
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(session, "c est quoi votre e mail ?")
    assert "support@" in reply.casefold() or DEFAULT_SUPPORT_EMAIL in reply
    assert "destination" not in reply.casefold()
    assert "support_contact" in tools
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True


@patch("agent.orchestrator.get_settings")
def test_comment_contacter_support_zero_token(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        support_email=DEFAULT_SUPPORT_EMAIL,
    )
    session = "ask-contact-support"
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(
            session, "comment je peux contacter le support"
        )
    assert "support@" in reply.casefold()
    assert "destination" not in reply.casefold()
    assert "support_contact" in tools
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True


@patch("agent.orchestrator.get_settings")
def test_remboursement_early_zero_token(mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        support_email=DEFAULT_SUPPORT_EMAIL,
    )
    session = "refund-early"
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(session, "je veux un remboursement")
    assert "support@" in reply.casefold()
    assert "escalate_to_advisor" in tools
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True
