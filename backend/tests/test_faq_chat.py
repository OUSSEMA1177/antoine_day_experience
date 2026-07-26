"""FAQ dans le chat — détection, routeur et réponse 0 token."""

from unittest.mock import MagicMock, patch

from agent.faq_policy import build_faq_reply, find_faq_answer, is_faq_inquiry
from agent.intent_router import RouteKind, classify_route
from agent.orchestrator import orchestrator
from memory.session_store import session_store


def _settings():
    return MagicMock(
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
        support_email="support@day-experience-demo.com",
    )


def test_is_faq_inquiry_positive() -> None:
    assert is_faq_inquiry("quel est le taux de commission ?")
    assert is_faq_inquiry("comment fonctionne la réservation")
    assert is_faq_inquiry("combien je gagne en revendant des activités")
    assert is_faq_inquiry("qui est day experience")
    assert is_faq_inquiry("quelle est la politique d'annulation ?")
    assert is_faq_inquiry("les prix sont-ils garantis ?")
    # Sujet fort sans mot interrogatif
    assert is_faq_inquiry("taux de commission")
    assert is_faq_inquiry("la facturation")


def test_is_faq_inquiry_negative() -> None:
    assert not is_faq_inquiry("bonjour")
    assert not is_faq_inquiry("des activités à barcelone pour un couple")
    assert not is_faq_inquiry("juste les deux premiers")
    assert not is_faq_inquiry("AFRIQUE")
    assert not is_faq_inquiry("mix de tout autour de la plage")


def test_find_faq_answer_returns_best_row() -> None:
    row = find_faq_answer("quel est le taux de commission ?")
    assert row is not None
    assert "14" in row.get("reponse", "")

    row2 = find_faq_answer("quelle est la politique d'annulation ?")
    assert row2 is not None
    assert "annulation" in row2.get("question", "").casefold()

    assert find_faq_answer("des activités à barcelone") is None


def test_build_faq_reply_contains_answer() -> None:
    row = find_faq_answer("comment se passe la facturation ?")
    assert row is not None
    reply = build_faq_reply(row)
    assert row["reponse"] in reply
    assert "FAQ" in reply


def test_router_routes_faq_after_support() -> None:
    assert classify_route("quel est le taux de commission ?").kind == RouteKind.FAQ
    assert classify_route("comment fonctionne la réservation").kind == RouteKind.FAQ
    # Support garde la priorité
    assert classify_route("c est quoi votre email").kind == RouteKind.SUPPORT_EMAIL
    assert classify_route("je veux un remboursement").kind == RouteKind.SUPPORT
    # « combien je gagne en revendant des activités » ≠ recherche catalogue
    assert (
        classify_route("combien je gagne en revendant des activités").kind
        == RouteKind.FAQ
    )
    # Catalogue reste catalogue
    assert classify_route("AFRIQUE").kind == RouteKind.COUNTRY_OR_CONTINENT
    assert classify_route("juste les deux premiers").kind == RouteKind.PURE_SELECTION


@patch("agent.orchestrator.get_settings")
def test_scenario_faq_commission_zero_token(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-faq-commission"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(
            session, "quel est le taux de commission ?"
        )
    assert "14" in reply
    assert "faq_lookup" in tools
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True


@patch("agent.orchestrator.get_settings")
def test_scenario_faq_annulation_zero_token(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "scen-faq-annulation"
    session_store.clear(session)
    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, tools, meta = orchestrator.chat(
            session, "quelle est la politique d'annulation ?"
        )
    assert "2 jours" in reply or "sans frais" in reply.casefold()
    assert "faq_lookup" in tools
    mock_nlu.assert_not_called()
    assert meta.get("llm_used") is not True
