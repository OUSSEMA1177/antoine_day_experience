"""Machine à états conversationnelle + whitelist lieu inconnu + classifieur."""

from unittest.mock import MagicMock, patch

from agent.conversation_state import (
    ConvState,
    Intent,
    allows_destination_change,
    classify_intent,
    derive_state,
    matches_known_intent,
    normalize_message,
)
from agent.destination_policy import (
    activate_unavailable_destination,
    detect_unknown_place_request,
)
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager
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


def test_derive_state_priorities() -> None:
    assert derive_state({}) is ConvState.QUALIFYING
    assert derive_state({"destination": "Paris"}) is ConvState.QUALIFYING
    assert (
        derive_state({"activites_proposees": "1,2"}) is ConvState.PRESENTING_LIST
    )
    assert (
        derive_state({"destination": "Paris", "activites_discutees": "1"})
        is ConvState.PRESENTING_LIST
    )
    assert derive_state({"devis_ref": "DEV-1"}) is ConvState.POST_QUOTE
    assert (
        derive_state({"awaiting_add_activity": "1", "devis_ref": "DEV-1"})
        is ConvState.AWAITING_ADD_ACTIVITY
    )
    assert (
        derive_state({"awaiting_city_confirm": "1"})
        is ConvState.AWAITING_CITY_CONFIRM
    )
    assert derive_state({"awaiting_city_pick": "1"}) is ConvState.AWAITING_CITY_PICK
    # Quote confirm prioritaire sur tout
    assert (
        derive_state(
            {
                "awaiting_quote_confirm": "1",
                "awaiting_city_confirm": "1",
                "awaiting_add_activity": "1",
                "devis_ref": "DEV-1",
            }
        )
        is ConvState.AWAITING_QUOTE_CONFIRM
    )


def test_allows_destination_change() -> None:
    assert allows_destination_change(ConvState.QUALIFYING)
    assert allows_destination_change(ConvState.PRESENTING_LIST)
    assert allows_destination_change(ConvState.POST_QUOTE)
    assert allows_destination_change(ConvState.AWAITING_CITY_CONFIRM)
    assert not allows_destination_change(ConvState.AWAITING_QUOTE_CONFIRM)
    assert not allows_destination_change(ConvState.AWAITING_ADD_ACTIVITY)


def test_normalize_message() -> None:
    assert normalize_message("  oui \u2019 c\u2019est   bon  ") == "oui ' c'est bon"
    assert normalize_message("le\u00a0devis") == "le devis"
    assert normalize_message("") == ""
    assert normalize_message("Afrique du Sud ?") == "Afrique du Sud ?"


def test_classify_intent_priority() -> None:
    assert classify_intent("bonjour") is Intent.GREETING
    assert classify_intent("remboursement") is Intent.SUPPORT
    assert classify_intent("non pas encore") is Intent.NOT_CHOSEN
    assert classify_intent("augmentez budjet") is Intent.RAISE_BUDGET
    assert classify_intent("oui ajoute ceci") is Intent.ADD_THIS
    assert classify_intent("ajouter 6 aussi") is Intent.ADD_THIS
    assert (
        classify_intent("1 est ok vous avez d autre activite ?")
        is Intent.SELECT_AND_ADD
    )
    assert classify_intent("autre option") is Intent.OTHER_OPTIONS
    assert classify_intent("j ai pas aime") is Intent.OTHER_OPTIONS
    assert classify_intent("je veux une autre activite") is Intent.WANTS_ANOTHER
    assert classify_intent("pas la 1") is Intent.REJECT_REMOVE
    for msg in ("oui", "ouii", "ouais", "ok", "le devis", "oui c est bon"):
        assert classify_intent(msg) is Intent.CONFIRM, msg
    assert classify_intent("1 et 3") is Intent.SELECT_INDICES
    assert classify_intent("les 3 premiers") is Intent.SELECT_INDICES
    assert classify_intent("en couple") is Intent.QUALIFICATION
    assert classify_intent("afrique de sude") is Intent.COUNTRY_REGION
    assert classify_intent("espagne") is Intent.COUNTRY_REGION
    assert classify_intent("budget 400 euros donne activites") is Intent.BUDGET_OR_SEARCH
    # Thème pur ou envie de qualification — les deux sont des intentions connues
    assert classify_intent("plage") in (Intent.THEME, Intent.QUALIFICATION)
    assert classify_intent("detente") in (Intent.THEME, Intent.QUALIFICATION)
    assert classify_intent("sahara") in (Intent.THEME, Intent.QUALIFICATION)
    # Question factuelle ≠ sélection malgré l'ordinal
    assert classify_intent("la premiere activite c est a istanbul ?") is Intent.UNKNOWN
    # Toponymes hors catalogue → UNKNOWN (gérés par detect_unknown_place_request)
    assert classify_intent("toulouse") is Intent.UNKNOWN
    assert classify_intent("monaco") is Intent.UNKNOWN


def test_should_run_nlu_uses_classifier() -> None:
    from agent.nlu_extractor import should_run_nlu

    # Déterministe → pas de NLU
    for msg in (
        "oui",
        "ouii",
        "1 et 3",
        "autre option",
        "j ai pas aime",
        "afrique de sude",
        "augmentez budjet",
        "toulouse",  # lieu hors catalogue → refus 0 token
        "bonjour",
    ):
        assert not should_run_nlu(msg), msg
    # Ambigu / flou → NLU
    for msg in (
        "quelque chose de fun pour mon client",
        "la premiere activite c est a istanbul ?",
        "mon client hesite entre plusieurs choses",
    ):
        assert should_run_nlu(msg), msg


def test_matches_known_intent_whitelist() -> None:
    # Confirmations / typos
    for msg in ("oui", "ouii", "ouais", "ok", "le devis", "oui c est bon"):
        assert matches_known_intent(msg), msg
    # Sélection / refus / options
    for msg in (
        "1 et 3",
        "les 3 premiers",
        "j ai pas aime",
        "autre option",
        "je veux une autre activite",
        "ajoute la 2",
    ):
        assert matches_known_intent(msg), msg
    # Métier
    for msg in (
        "augmentez budjet",
        "budget 400 euros donne activites",
        "en couple",
        "non pas encore",
        "afrique",
        "afrique de sude",
        "remboursement",
    ):
        assert matches_known_intent(msg), msg
    # Thèmes ≠ toponymes
    for msg in ("plage", "detente", "gastronomie"):
        assert matches_known_intent(msg), msg
    # Vrais toponymes hors catalogue → PAS une intention connue
    for msg in ("toulouse", "monaco"):
        assert not matches_known_intent(msg), msg


def test_unknown_place_gated_by_state() -> None:
    # Sans session : toponyme détecté
    assert detect_unknown_place_request("toulouse") == "Toulouse"
    assert detect_unknown_place_request("monaco") == "Monaco"
    # Thème / typo oui : jamais un lieu
    assert detect_unknown_place_request("detente") is None
    assert detect_unknown_place_request("plage") is None
    assert detect_unknown_place_request("ouii") is None

    # État AWAITING_QUOTE_CONFIRM : même « toulouse » n'écrase rien
    session = "state-gate-quote"
    session_store.clear(session)
    memory_manager.update_slots(session, awaiting_quote_confirm="1")
    assert detect_unknown_place_request("toulouse", session_id=session) is None
    assert detect_unknown_place_request("ouii", session_id=session) is None

    # État AWAITING_ADD_ACTIVITY : idem
    session2 = "state-gate-add"
    session_store.clear(session2)
    memory_manager.update_slots(session2, awaiting_add_activity="1")
    assert detect_unknown_place_request("toulouse", session_id=session2) is None


def test_activate_unavailable_non_destructive_with_selection() -> None:
    session = "non-destructive"
    session_store.clear(session)
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        activites_proposees="53155,54878",
        activites_selectionnees="53155",
    )
    activate_unavailable_destination(session, "Monaco")
    slots = memory_manager.get_slots(session)
    # Sélection + destination conservées, demande mémorisée
    assert slots.get("destination") == "Marrakech"
    assert slots.get("activites_selectionnees") == "53155"
    assert slots.get("destination_demandee") == "Monaco"


def test_activate_unavailable_blocked_during_quote_confirm() -> None:
    session = "blocked-activate"
    session_store.clear(session)
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        activites_selectionnees="53155",
        awaiting_quote_confirm="1",
    )
    activate_unavailable_destination(session, "Monaco")
    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Marrakech"
    assert "destination_demandee" not in slots


def test_activate_unavailable_still_clears_without_selection() -> None:
    session = "destructive-ok"
    session_store.clear(session)
    memory_manager.update_slots(session, destination="Marrakech")
    activate_unavailable_destination(session, "Toulouse")
    slots = memory_manager.get_slots(session)
    assert "destination" not in slots
    assert slots.get("destination_demandee") == "Toulouse"


@patch("agent.orchestrator.get_settings")
def test_fuzz_confirmations_never_destroy_state(mock_settings) -> None:
    """Variantes de « oui » pendant ask devis : jamais de wipe destination."""
    mock_settings.return_value = _settings()
    ids = ["53155", "54878", "54492"]
    for i, msg in enumerate(("ouii", "ouiii", "ouais", "ok", "Oui", "OK !", "le devis")):
        session = f"fuzz-oui-{i}"
        session_store.clear(session)
        memory_manager.update_slots(
            session,
            destination="Marrakech",
            profil_voyageur="couple",
            partner_id="1",
            nom_agence="Test",
            activites_proposees=",".join(ids),
            activites_discutees=",".join(ids),
            activites_selectionnees=",".join(ids),
            awaiting_quote_confirm="1",
        )
        with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
            reply, _, _ = orchestrator.chat(session, msg)
        slots = memory_manager.get_slots(session)
        assert slots.get("destination") == "Marrakech", msg
        assert "pas disponible" not in reply.casefold(), msg
        assert "catalogue Day Experience" not in reply or "devis" in reply.casefold(), msg
        mock_nlu.assert_not_called()
