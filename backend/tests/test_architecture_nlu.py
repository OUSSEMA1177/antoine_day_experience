"""Tests architecture NLU : qualification vs fausse destination, confirmation bornée."""

from unittest.mock import MagicMock, patch

from agent.context_manager import is_qualification_message, sync_slots_from_message
from agent.destination_policy import detect_unknown_place_request
from agent.orchestrator import orchestrator
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    CONFIRMATION_MAX_ACTIVITIES,
    compute_quote_state,
    sync_activity_feedback_from_message,
)


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


def test_mix_de_tout_is_qualification_not_place() -> None:
    assert is_qualification_message("mix de tout")
    assert detect_unknown_place_request("mix de tout") is None
    session = "mix-envies"
    memory_manager.update_slots(session, destination="Le Caire", profil_voyageur="groupe")
    sync_slots_from_message(session, "mix de tout")
    slots = memory_manager.get_slots(session)
    assert "aventure" in slots.get("envies", "").casefold() or "culture" in slots.get("envies", "").casefold()
    assert slots.get("destination") == "Le Caire"


@patch("agent.orchestrator.get_settings")
def test_mix_de_tout_orchestrator_keeps_cairo(mock_settings) -> None:
    mock_settings.return_value = _mock_settings()
    session = "mix-orch"
    memory_manager.update_slots(
        session,
        destination="Le Caire",
        profil_voyageur="groupe",
        taille_groupe="6",
        partner_id="1",
        nom_agence="TUI",
    )

    with patch("agent.orchestrator.litellm.completion") as mock_completion:
        mock_completion.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content="Voici des activités au Caire…",
                        tool_calls=[],
                        role="assistant",
                        model_dump=MagicMock(
                            return_value={"role": "assistant", "content": "Voici des activités au Caire…"}
                        ),
                    )
                )
            ],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        reply, _, _ = orchestrator.chat(session, "mix de tout")

    assert "Mix De Tout" not in reply
    assert "pas d'activités à Mix" not in reply.casefold()
    assert memory_manager.get_slots(session).get("destination") == "Le Caire"


def test_confirmation_does_not_select_all_discussed() -> None:
    session = "confirm-cap"
    # Beaucoup d'IDs « discutés » (bug historique) + une seule présentation récente
    many = ",".join(str(i) for i in range(10001, 10041))
    memory_manager.update_slots(
        session,
        destination="Le Caire",
        profil_voyageur="groupe",
        partner_id="1",
        nom_agence="TUI",
        activites_discutees=many,
        activites_proposees=many,
        activites_selectionnees=many,
    )
    conversation_manager.add_turn(
        session,
        "mix",
        "Super ! **Visite de groupe aux pyramides de Gizeh, à la ville de Memphis "
        "et à la pyramide de Sakkara** — 57,62 € par personne.",
    )
    sync_activity_feedback_from_message(session, "oui c est bon")
    state = compute_quote_state(session)
    assert len(state["activity_ids"]) <= CONFIRMATION_MAX_ACTIVITIES
    assert len(state["activity_ids"]) >= 1


def test_unknown_place_skipped_when_destination_set() -> None:
    session = "dest-set"
    memory_manager.update_slots(session, destination="Le Caire", profil_voyageur="groupe")
    assert detect_unknown_place_request("mix de tout", session_id=session) is None
    assert detect_unknown_place_request("quelque chose de fun", session_id=session) is None
