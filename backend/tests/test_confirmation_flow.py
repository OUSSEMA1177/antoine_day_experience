"""Tests confirmation activités et gibberish."""

from unittest.mock import MagicMock, patch

from agent.destination_policy import detect_unknown_place_request
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager
from memory.quote_state import is_confirmation_message


def _mock_settings():
    return MagicMock(
        llm_model="groq/llama-3.3-70b-versatile",
        groq_api_key="test-key",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_log_usage=False,
    )


def test_confirmation_not_a_place() -> None:
    assert is_confirmation_message("oui c est bon")
    assert is_confirmation_message("oui c est parfait")
    assert is_confirmation_message("ouii")
    assert is_confirmation_message("Ouii")
    assert is_confirmation_message("le devis")
    assert is_confirmation_message("j ai dit c est bon a les activites ?")
    assert is_confirmation_message("je veux le devis")
    assert is_confirmation_message("donner moi le devis")
    assert is_confirmation_message("j ai dit oui je veux le devis oui c est parfait")
    assert detect_unknown_place_request("oui c est parfait") is None
    assert detect_unknown_place_request("Oui C Est Parfait") is None
    assert detect_unknown_place_request("ouii") is None
    assert detect_unknown_place_request("le devis") is None


@patch("agent.orchestrator.get_settings")
def test_ouii_confirms_quote_keeps_selection(mock_settings) -> None:
    """Typo « ouii » pendant awaiting_quote → devis, pas wipe destination."""
    from memory.quote_state import _parse_id_list

    mock_settings.return_value = _mock_settings()
    session = "ouii-quote"
    ids = ["53155", "54878", "54492", "55855"]
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        taille_groupe="2",
        partner_id="1",
        nom_agence="Test Agence",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
        activites_selectionnees=",".join(ids[:3]),
        awaiting_quote_confirm="1",
    )
    assert detect_unknown_place_request("ouii", session_id=session) is None

    reply, _, meta = orchestrator.chat(session, "ouii")
    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Marrakech"
    selected = _parse_id_list(slots.get("activites_selectionnees"))
    assert selected == ids[:3]
    assert "devis" in reply.casefold()
    assert "pas disponible" not in reply.casefold()
    assert not slots.get("awaiting_quote_confirm")
    assert meta.get("quote_ready") is True
    assert len(meta.get("quote_activities") or []) == 3


@patch("agent.orchestrator.get_settings")
def test_les_trois_premiers_quote_stays_three(mock_settings) -> None:
    """« les 3 premiers » puis oui → exactement 3 IDs, pas 4 via CONFIRMATION_MAX."""
    from memory.conversation_manager import conversation_manager
    from memory.quote_state import _parse_id_list, parse_presentation_indices

    mock_settings.return_value = _mock_settings()
    assert parse_presentation_indices("les 3 premiers") == [1, 2, 3]
    assert parse_presentation_indices("les trois premiers") == [1, 2, 3]

    session = "trois-premiers-quote"
    ids = ["53155", "54878", "54492", "55855"]
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test Agence",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "activites",
        "1. **Act A** — 10 €\n2. **Act B** — 20 €\n3. **Act C** — 30 €\n4. **Act D** — 40 €",
    )

    reply1, _, meta1 = orchestrator.chat(session, "les 3 premiers")
    selected = _parse_id_list(
        memory_manager.get_slots(session).get("activites_selectionnees")
    )
    assert selected == ids[:3]
    assert "3 activité" in reply1.casefold() or "3 activit" in reply1.casefold()
    assert memory_manager.get_slots(session).get("awaiting_quote_confirm") == "1"
    assert meta1.get("quote_ready") is False

    reply2, _, meta2 = orchestrator.chat(session, "oui")
    selected2 = _parse_id_list(
        memory_manager.get_slots(session).get("activites_selectionnees")
    )
    assert selected2 == ids[:3]
    assert len(meta2.get("quote_activities") or []) == 3
    assert "devis" in reply2.casefold()
    assert meta2.get("quote_ready") is True


@patch("agent.orchestrator.get_settings")
def test_gibberish_not_a_destination(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "gibberish"
    reply, _, _ = orchestrator.chat(session, "dfgbdfgdfg")
    assert "pas reconnu" in reply.casefold()
    assert "Dfgbdfgdfg" not in reply


@patch("agent.orchestrator.get_settings")
def test_activity_confirmation_after_selection(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "confirm-activities"
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="groupe",
        taille_groupe="4",
        envies="aventure",
        partner_id="1",
        nom_agence="TUI Test",
        activites_discutees="53286,54685",
        activites_proposees="53286,54685",
        activites_selectionnees="53286,54685",
        awaiting_quote_confirm="1",
    )

    reply, _, meta = orchestrator.chat(session, "oui c est bon")
    assert "pas d'activités" not in reply.casefold()
    assert "Oui C Est Bon" not in reply
    assert "devis" in reply.casefold()
    assert "Souhaitez-vous que je prépare" not in reply
    assert meta["quote_ready"] is True
    assert not memory_manager.get_slots(session).get("awaiting_quote_confirm")


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.generate_quote_for_session")
def test_quote_revision_regenerates_pdf(mock_gen, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    mock_gen.return_value = {
        "pdf_url": "/quotes/new.pdf",
        "devis_ref": "DEV-NEW-1",
        "total_net": "80 €",
        "activity_count": 1,
    }
    session = "revise-devis"
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="groupe",
        partner_id="1",
        nom_agence="TUI Test",
        activites_discutees="53286,54685",
        activites_proposees="53286,54685",
        activites_selectionnees="53286,54685",
        devis_ref="DEV-OLD",
    )
    from memory.conversation_manager import conversation_manager

    conversation_manager.add_turn(
        session,
        "ok",
        "1. **Première act** — 10 €\n2. **Deuxième act** — 20 €",
    )
    reply, _, meta = orchestrator.chat(
        session, "desole je veux pas la premiere"
    )
    assert "mis à jour" in reply.casefold() or "corrigée" in reply.casefold()
    ref = memory_manager.get_slots(session).get("devis_ref")
    assert ref != "DEV-OLD"
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert "53286" not in selected.split(",")
    assert "54685" in selected
    assert meta.get("quote_url") == "/quotes/new.pdf"
    mock_gen.assert_called_once()
    mock_settings.return_value = _mock_settings()
    session = "select-ask-quote"
    ids = ["53286", "54685", "99901"]
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="TUI Test",
        activites_proposees=",".join(ids[:2]),
        activites_discutees=",".join(ids[:2]),
    )
    from memory.conversation_manager import conversation_manager

    conversation_manager.add_turn(
        session,
        "aventure",
        "1. **Act A** — 10 €\n2. **Act B** — 20 €",
    )
    reply, _, meta = orchestrator.chat(session, "la 1 et la 2")
    assert "prépare" in reply.casefold() or "souhaitez-vous" in reply.casefold()
    assert "Cliquez sur le bouton" not in reply
    assert meta["quote_ready"] is False
    assert memory_manager.get_slots(session).get("awaiting_quote_confirm") == "1"

@patch("agent.orchestrator.get_settings")
def test_oui_c_est_parfait_not_destination(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "parfait-not-place"
    memory_manager.update_slots(
        session,
        destination="Barcelone",
        profil_voyageur="groupe_amis",
        taille_groupe="6",
        envies="culture, gastronomie",
        partner_id="1",
        nom_agence="TUI España",
        activites_discutees="74579,74575",
        activites_proposees="74579,74575",
        activites_rejetees="39518",
    )

    reply, _, meta = orchestrator.chat(session, "oui c est parfait")
    slots = memory_manager.get_slots(session)

    assert "Oui C Est Parfait" not in reply
    assert "pas d'activités à Oui" not in reply.casefold()
    assert slots.get("destination") == "Barcelone"
    assert meta["quote_ready"] is True
    assert "devis" in reply.casefold() or "validée" in reply.casefold()
    assert len(meta.get("quote_activities") or []) <= 4
    assert len(meta.get("quote_activities") or []) >= 1


@patch("agent.orchestrator.get_settings")
def test_je_veux_le_devis_activates_quote(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "devis-request"
    memory_manager.update_slots(
        session,
        destination="Barcelone",
        profil_voyageur="groupe_amis",
        partner_id="1",
        nom_agence="TUI España",
        activites_discutees="74579,74575",
        activites_proposees="74579,74575",
    )

    reply, _, meta = orchestrator.chat(session, "donner moi le devis")
    assert meta["quote_ready"] is True
    assert "pas d'activités" not in reply.casefold()
    assert len(meta.get("quote_activities") or []) == 2


@patch("agent.orchestrator.get_settings")
def test_ordinal_plus_autre_activite_asks_theme_not_devis(mock_settings) -> None:
    """« la 2e et une autre activité » → 0 token : sélectionne #2, demande le thème."""
    from memory.conversation_manager import conversation_manager
    from services.data_loader import data_loader

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
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
    )
    a = data_loader.get_activity_by_id("53286")
    b = data_loader.get_activity_by_id("54685")
    assert a and b
    session = "ordinal-autre"
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test Agency",
        activites_proposees="53286,54685",
        activites_discutees="53286,54685",
    )
    conversation_manager.add_turn(
        session,
        "culture",
        f"1. **{a['titre']}** — 50 €\n2. **{b['titre']}** — 80 €",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(
            session, "la deusieme et je veux une autre activite"
        )

    assert "thématique" in reply.casefold() or "gastronomie" in reply.casefold()
    assert "prépare le devis" not in reply.casefold()
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert "54685" in selected
    assert "53286" not in selected
    assert not memory_manager.get_slots(session).get("awaiting_quote_confirm")
    assert memory_manager.get_slots(session).get("awaiting_add_activity") == "1"
    mock_nlu.assert_not_called()
    assert meta.get("quote_ready") is False


@patch("agent.orchestrator.get_settings")
def test_oui_ajoute_ceci_appends_then_asks_devis(mock_settings) -> None:
    """« oui ajoute ceci » → 0 token append, demande confirmation devis."""
    from memory.conversation_manager import conversation_manager
    from services.data_loader import data_loader

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
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
    )
    a = data_loader.get_activity_by_id("53286")
    b = data_loader.get_activity_by_id("54685")
    assert a and b
    session = "ajoute-ceci"
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test Agency",
        activites_selectionnees="53286",
        activites_proposees="53286,54685",
        activites_discutees="53286,54685",
    )
    conversation_manager.add_turn(
        session,
        "culture",
        f"1. **{b['titre']}** — 80 €",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        reply, _, meta = orchestrator.chat(session, "oui ajoute ceci")

    selected = [
        x
        for x in str(memory_manager.get_slots(session).get("activites_selectionnees", "")).split(",")
        if x.strip()
    ]
    assert selected == ["53286", "54685"]
    assert "prépare" in reply.casefold() or "devis" in reply.casefold()
    assert "Cliquez sur le bouton" not in reply
    assert memory_manager.get_slots(session).get("awaiting_quote_confirm") == "1"
    assert meta.get("quote_ready") is False
    mock_nlu.assert_not_called()
