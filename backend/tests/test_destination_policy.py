"""Tests destinations hors catalogue (ex. Toulouse)."""

from unittest.mock import MagicMock, patch

from agent.destination_policy import (
    activate_catalog_destination,
    activate_unavailable_destination,
    build_destination_unavailable_reply,
    detect_unknown_place_request,
    is_catalog_destination,
    unavailable_place_from_slots,
)
from agent.orchestrator import orchestrator
from memory.memory_manager import memory_manager
from search.catalog_search import search_from_context


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
    )


def test_toulouse_not_in_catalog() -> None:
    assert not is_catalog_destination("Toulouse")
    assert detect_unknown_place_request("toulouse") == "Toulouse"
    assert detect_unknown_place_request("toulouse ?") == "Toulouse"
    assert detect_unknown_place_request("monaco") == "Monaco"
    assert detect_unknown_place_request("dfgbdfgdfg") is None
    assert detect_unknown_place_request("oui c est bon") is None
    assert detect_unknown_place_request("bresil") is None  # pays catalogue
    assert detect_unknown_place_request("juste les deux premiers") is None
    assert detect_unknown_place_request("le premier et le quatrieme") is None


def test_gibberish_detection() -> None:
    from agent.destination_policy import detect_gibberish_destination_attempt

    assert detect_gibberish_destination_attempt("dfgbdfgdfg")
    assert not detect_gibberish_destination_attempt("toulouse")


def test_toulouse_search_no_foreign_fallback() -> None:
    slots = {"destination_demandee": "Toulouse", "envies": "culture, gastronomie"}
    result = search_from_context(
        "donner moi les activites qu on peut faire la bas",
        slots,
    )
    assert not result.has_results()
    assert result.meta.get("note") == "destination_hors_catalogue"


@patch("agent.orchestrator.get_settings")
def test_toulouse_orchestrator_early_reply(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "toulouse-early"
    reply, tools, meta = orchestrator.chat(session, "toulouse")
    assert "Toulouse" in reply
    lower = reply.casefold()
    assert "pas toulouse" in lower or "pas d'activités" in lower or "pas d'activit" in lower
    assert "Istanbul" not in reply
    assert "Tulum" not in reply
    slots = memory_manager.get_slots(session)
    assert slots.get("destination_demandee") == "Toulouse"
    assert not slots.get("destination")
    assert meta["quote_ready"] is False


@patch("agent.orchestrator.get_settings")
@patch("agent.nlu_extractor.litellm.completion")
def test_monaco_not_europe(mock_nlu, mock_settings) -> None:
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
    assert detect_unknown_place_request("monaco") == "Monaco"
    reply, _, _ = orchestrator.chat("monaco-no-eu", "monaco")
    assert "Monaco" in reply
    assert "pas Monaco" in reply or "pas monaco" in reply.casefold()
    assert "Europe" not in reply
    assert "pour l'Europe" not in reply.casefold()
    assert "Venise" not in reply  # pas le dump du continent
    assert "Vienne" not in reply
    mock_nlu.assert_not_called()


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_toulouse_then_bali_switches_destination(mock_completion, mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    mock_completion.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content="Parfait pour Bali ! Votre client voyage en couple, en famille, en groupe, en solo ou en séminaire ?",
                    tool_calls=[],
                    role="assistant",
                    model_dump=MagicMock(return_value={"role": "assistant", "content": "..."}),
                )
            )
        ]
    )

    session = "toulouse-bali"
    orchestrator.chat(session, "toulouse")
    reply, _, meta = orchestrator.chat(session, "bali")

    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Bali"
    assert "destination_demandee" not in slots
    assert "Toulouse" not in reply
    assert "Bali" in reply
    assert unavailable_place_from_slots(slots) is None
    assert meta["quote_ready"] is False


def test_activate_catalog_clears_blocked_state() -> None:
    session = "activate-bali"
    activate_unavailable_destination(session, "Toulouse")
    assert memory_manager.get_slots(session).get("destination_demandee") == "Toulouse"

    resolved = activate_catalog_destination(session, "bali")
    assert resolved == "Bali"
    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Bali"
    assert "destination_demandee" not in slots


def test_memory_clear_slot_via_empty_string() -> None:
    session = "clear-slot"
    memory_manager.update_slots(session, destination_demandee="Toulouse")
    memory_manager.update_slots(session, destination_demandee="")
    assert "destination_demandee" not in memory_manager.get_slots(session)


def test_unavailable_reply_suggests_france_not_abroad() -> None:
    reply = build_destination_unavailable_reply("Toulouse")
    assert "Paris" in reply
    assert "Istanbul" not in reply
    assert "Tulum" not in reply


def test_paris_still_valid() -> None:
    assert is_catalog_destination("Paris")
    assert detect_unknown_place_request("Paris") is None
