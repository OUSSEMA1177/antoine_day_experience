"""Multi-listes : sélection liste 1 + append depuis liste 2."""

from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import sync_activity_feedback_from_message
from memory.session_store import session_store


def test_indices_append_when_awaiting_add() -> None:
    """Avec awaiting_add, « 1 » sur la 2e liste append (n'écrase pas)."""
    session = "multi-list-append"
    session_store.clear(session)
    list1 = ["a1", "a2", "a3", "a4"]
    list2 = ["b1", "b2", "b3", "b4"]
    memory_manager.update_slots(
        session,
        destination="Barcelone",
        profil_voyageur="groupe",
        activites_selectionnees="a1,a2",
        activites_proposees=",".join(list2),
        activites_discutees=",".join(list1 + list2),
        awaiting_add_activity="1",
    )
    conversation_manager.add_turn(
        session,
        "gastronomie",
        "Votre sélection précédente est conservée. Voici des options :\n"
        + "\n".join(f"{i}. **Act B{i}** — {10 * i} €" for i in range(1, 5))
        + "\nIndiquez lesquelles ajouter (ex. 1).",
    )
    sync_activity_feedback_from_message(session, "1")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["a1", "a2", "b1"]


def test_indices_replace_without_awaiting_add() -> None:
    """Sans awaiting_add, « 1 et 2 » remplace (première sélection)."""
    session = "multi-list-replace"
    session_store.clear(session)
    ids = ["a1", "a2", "a3", "a4"]
    memory_manager.update_slots(
        session,
        destination="Barcelone",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    conversation_manager.add_turn(
        session,
        "ok",
        "\n".join(f"{i}. **Act {i}** — {10 * i} €" for i in range(1, 5)),
    )
    sync_activity_feedback_from_message(session, "1 et 2")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["a1", "a2"]


def test_correction_juste_still_replaces() -> None:
    session = "multi-list-juste"
    session_store.clear(session)
    ids = ["a1", "a2", "a3", "a4"]
    memory_manager.update_slots(
        session,
        destination="Barcelone",
        activites_selectionnees="a1,a2,a3",
        activites_proposees=",".join(ids),
        awaiting_add_activity="1",
    )
    conversation_manager.add_turn(
        session,
        "ok",
        "\n".join(f"{i}. **Act {i}** — {10 * i} €" for i in range(1, 5)),
    )
    sync_activity_feedback_from_message(session, "juste 1 et 2")
    selected = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
    assert selected.split(",") == ["a1", "a2"]


from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator


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


@patch("agent.orchestrator.get_settings")
def test_scenario_list1_then_autre_then_append_list2(mock_settings) -> None:
    """Liste1 select → autre activité → thème → pick liste2 append."""
    mock_settings.return_value = _settings()
    session = "scen-multi-list"
    session_store.clear(session)
    # Sélection initiale + destination catalogue
    memory_manager.update_slots(
        session,
        destination="Séville",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test",
        activites_selectionnees="53286",
        activites_proposees="53286,54685",
        activites_discutees="53286,54685",
        awaiting_add_activity="1",
    )
    conversation_manager.add_turn(
        session,
        "culture",
        "1. **Act A** — 50 €\n2. **Act B** — 80 €",
    )

    with patch("agent.nlu_extractor.litellm.completion") as mock_nlu:
        # Thème → 2e liste (awaiting_add conservé)
        reply1, _, meta1 = orchestrator.chat(session, "gastronomie")
        assert memory_manager.get_slots(session).get("awaiting_add_activity") == "1"
        assert "1." in reply1
        assert "conservée" in reply1.casefold() or "ajouter" in reply1.casefold()
        proposees = str(memory_manager.get_slots(session).get("activites_proposees", ""))
        assert proposees  # nouvelle liste
        first_sel = str(memory_manager.get_slots(session).get("activites_selectionnees", ""))
        assert "53286" in first_sel

        # Pick #1 de la 2e liste → append
        reply2, _, meta2 = orchestrator.chat(session, "1")
        selected = [
            x
            for x in str(
                memory_manager.get_slots(session).get("activites_selectionnees", "")
            ).split(",")
            if x.strip()
        ]
        assert "53286" in selected
        assert len(selected) >= 2
        assert "prépare" in reply2.casefold() or "devis" in reply2.casefold()
        mock_nlu.assert_not_called()
        assert meta1.get("llm_used") is not True
        assert meta2.get("llm_used") is not True
