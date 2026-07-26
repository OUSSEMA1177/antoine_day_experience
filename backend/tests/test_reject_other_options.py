"""Refus liste / autre option / typos Afrique du Sud."""

from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    is_reject_presented_list,
    is_wants_another_activity,
    is_wants_other_options,
)
from memory.session_store import session_store
from search.geo import detect_continent_query, detect_country_query, invalidate_catalog_countries_cache


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


def test_helpers_autre_option_vs_autre_activite() -> None:
    assert is_wants_other_options("autre option")
    assert is_wants_other_options("autres options")
    assert is_reject_presented_list("j ai pas aime")
    assert is_reject_presented_list("autre option")
    assert not is_wants_another_activity("autre option")
    assert is_wants_another_activity("je veux une autre activite")
    assert not is_reject_presented_list("pas la 1")


def test_afrique_du_sud_typos_not_continent() -> None:
    invalidate_catalog_countries_cache()
    for msg in (
        "Afrique du Sud",
        "afrique de sud",
        "afrique de sude",
        "et l afrique de sude ???",
        "dans l afrique de sud vous avez juste Parc Kruger ??",
        "plage dans l afrique de sude",
    ):
        assert detect_country_query(msg) == "afrique_du_sud", msg
        assert detect_continent_query(msg) is None, msg


@patch("agent.orchestrator.get_settings")
def test_jai_pas_aime_offers_other_not_empty_selection(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "reject-list-kruger"
    session_store.clear(session)
    ids = ["54782", "54783", "41555", "72738", "51876", "51871"]
    # IDs Kruger réels si dispo — sinon Marrakech ok pour le flux
    from services.data_loader import data_loader

    kruger = data_loader.search_activities(destination_name="Parc Kruger", limit=6)
    if kruger:
        ids = [str(r["id"]) for r in kruger[:6]]
        dest = "Parc Kruger"
    else:
        dest = "Marrakech"
        m = data_loader.search_activities(destination_name="Marrakech", limit=6)
        ids = [str(r["id"]) for r in m[:6]]

    memory_manager.update_slots(
        session,
        destination=dest,
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="TUI",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
        region_interest="afrique_du_sud" if dest == "Parc Kruger" else "",
    )
    conversation_manager.add_turn(
        session,
        "oui",
        "1. **A** — 10 €\n2. **B** — 20 €\n3. **C** — 30 €",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(session, "j ai pas aime")

    assert "ne reste plus" not in reply.casefold()
    assert "sélection" not in reply.casefold() or "options" in reply.casefold() or dest.casefold() in reply.casefold()
    assert meta.get("llm_used") is not True
    mock_nlu.assert_not_called()


@patch("agent.orchestrator.get_settings")
def test_autre_option_not_theme_ask(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "autre-option-kruger"
    session_store.clear(session)
    from services.data_loader import data_loader

    kruger = data_loader.search_activities(destination_name="Parc Kruger", limit=6)
    assert kruger
    ids = [str(r["id"]) for r in kruger[:6]]
    memory_manager.update_slots(
        session,
        destination="Parc Kruger",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="TUI",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
        region_interest="afrique_du_sud",
        awaiting_add_activity="1",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(session, "autre option")

    assert "thématique" not in reply.casefold()
    assert "gastronomie" not in reply.casefold() or "Parc Kruger" in reply
    assert meta.get("llm_used") is not True
    mock_nlu.assert_not_called()
    assert not memory_manager.get_slots(session).get("awaiting_add_activity")


@patch("agent.orchestrator.get_settings")
def test_afrique_de_sude_stays_country(mock_settings) -> None:
    mock_settings.return_value = _settings()
    session = "typo-afrique-sud"
    session_store.clear(session)
    memory_manager.update_slots(
        session,
        destination="Parc Kruger",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="TUI",
        region_interest="afrique_du_sud",
        awaiting_add_activity="1",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(session, "et l afrique de sude ???")

    assert "Le Caire" not in reply
    assert "Marrakech" not in reply or "Parc Kruger" in reply
    assert "Parc Kruger" in reply
    assert "Afrique" in reply or "afrique" in reply.casefold()
    assert meta.get("llm_used") is not True
    mock_nlu.assert_not_called()
