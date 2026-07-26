"""Tests extracteur NLU structuré."""

from unittest.mock import MagicMock, patch

from agent.nlu_extractor import (
    apply_nlu_to_session,
    parse_nlu_payload,
    should_run_nlu,
)
from memory.memory_manager import memory_manager


def test_parse_mix_de_tout() -> None:
    nlu = parse_nlu_payload(
        {
            "intent": "qualify",
            "destination": None,
            "continent": None,
            "country": None,
            "profil": None,
            "taille_groupe": None,
            "envies": [],
            "confirm_selection": False,
            "wants_another_activity": False,
            "reject_hint": None,
            "is_place_name": False,
            "mix_all_envies": True,
            "confidence": 0.9,
        }
    )
    assert nlu.mix_all_envies is True
    assert nlu.is_place_name is False
    assert nlu.intent == "qualify"


def test_parse_confirm_not_place() -> None:
    nlu = parse_nlu_payload(
        {
            "intent": "confirm",
            "confirm_selection": True,
            "is_place_name": False,
            "confidence": 0.95,
        }
    )
    assert nlu.confirm_selection is True
    assert nlu.is_place_name is False


def test_parse_destination_resolved() -> None:
    nlu = parse_nlu_payload(
        {
            "intent": "search",
            "destination": "cairo",
            "is_place_name": True,
            "confidence": 0.8,
        }
    )
    assert nlu.destination == "Le Caire"


def test_parse_continent() -> None:
    nlu = parse_nlu_payload(
        {
            "intent": "list_destinations",
            "continent": "Asie",
            "is_place_name": False,
        }
    )
    assert nlu.continent == "asie"


def test_apply_nlu_updates_slots() -> None:
    session = "nlu-apply"
    nlu = parse_nlu_payload(
        {
            "intent": "qualify",
            "destination": "Barcelone",
            "profil": "groupe",
            "taille_groupe": 6,
            "mix_all_envies": True,
            "is_place_name": False,
        }
    )
    apply_nlu_to_session(session, nlu)
    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Barcelone"
    assert slots.get("profil_voyageur") == "groupe"
    assert slots.get("taille_groupe") == "6"
    assert "culture" in slots.get("envies", "")


def test_should_run_nlu_skips_bonjour() -> None:
    assert should_run_nlu("bonjour") is False
    assert should_run_nlu("mix de tout") is True
    assert should_run_nlu("non pas encore") is False
    assert should_run_nlu("non") is False


def test_should_run_nlu_skips_pure_selection_runs_mixed() -> None:
    from agent.nlu_extractor import is_pure_selection_or_confirm_message

    assert is_pure_selection_or_confirm_message("juste les deux premiers") is True
    assert should_run_nlu("juste les deux premiers") is False
    assert is_pure_selection_or_confirm_message("oui c est bon") is True
    assert should_run_nlu("oui c est bon") is False
    # Pas « pure » générique, mais routeur + regex → 0 token
    assert is_pure_selection_or_confirm_message("la deusieme et je veux une autre activite") is False
    assert should_run_nlu("la deusieme et je veux une autre activite") is False
    assert is_pure_selection_or_confirm_message("oui ajoute ceci") is False
    assert should_run_nlu("oui ajoute ceci") is False
    assert should_run_nlu("mix de tout autour de la plage") is True


def test_parse_add_activity_fields() -> None:
    nlu = parse_nlu_payload(
        {
            "intent": "add_activity",
            "wants_another_activity": True,
            "add_this_activity": False,
            "selection_indices": [2],
            "confirm_selection": False,
            "is_place_name": False,
            "confidence": 0.9,
        }
    )
    assert nlu.wants_another_activity is True
    assert nlu.add_this_activity is False
    assert nlu.selection_indices == [2]
    assert nlu.intent == "add_activity"


@patch("agent.nlu_extractor.litellm.completion")
def test_extract_nlu_parses_response(mock_completion) -> None:
    from agent.nlu_extractor import extract_nlu

    mock_completion.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"intent":"qualify","mix_all_envies":true,"is_place_name":false,"confidence":0.9}'
                )
            )
        ],
        usage=MagicMock(prompt_tokens=50, completion_tokens=30, total_tokens=80),
    )
    nlu = extract_nlu(
        "mix de tout",
        session_id="nlu-extract",
        litellm_kwargs={"model": "anthropic/claude-haiku-4-5", "api_key": "x"},
        log_usage=False,
    )
    assert nlu.mix_all_envies is True
    assert nlu.is_place_name is False
