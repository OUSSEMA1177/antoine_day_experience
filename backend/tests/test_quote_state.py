"""Tests quote state et sélection catalogue."""

from agent.context_manager import sync_slots_from_message
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.quote_state import (
    compute_quote_state,
    detect_destination_in_message,
    is_quote_confirmation,
    match_activities_by_titles,
    save_proposed_activities,
    sync_activity_feedback_from_message,
)
from services.data_loader import data_loader


def test_plan_couple_sets_marrakech() -> None:
    session = "plan-couple"
    sync_slots_from_message(session, "fais moi un plan a ton choix juste pour un couple")
    slots = memory_manager.get_slots(session)
    assert slots.get("profil_voyageur") == "couple"
    assert slots.get("destination") == "Marrakech"


def test_tous_sets_envies() -> None:
    session = "tous-envies"
    sync_slots_from_message(session, "tous")
    assert "culture" in str(memory_manager.get_slots(session).get("envies", ""))


def test_agency_name_slot() -> None:
    session = "agency"
    sync_slots_from_message(session, "sousou voyage")
    assert memory_manager.get_slots(session).get("nom_agence") == "Sousou Voyage"


def test_quote_ready_after_proposal_and_confirm() -> None:
    session = "quote-ready"
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        envies="culture, aventure",
        nom_agence="Sousou Voyage",
    )
    rows = data_loader.search_activities_smart(destination_name="Marrakech", limit=4)[0]
    save_proposed_activities(session, rows)
    memory_manager.update_slots(session, activites_selectionnees=rows[0]["id"])

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) >= 1


def test_detect_zanzibar_destination() -> None:
    assert detect_destination_in_message("j ai aime zanzibar") == "Zanzibar"


def test_reject_activity_removes_from_quote() -> None:
    session = "reject-aquarium"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        nom_agence="Test Agence",
        activites_proposees="54117,61097",
    )
    sync_activity_feedback_from_message(
        session,
        "j ai pas aime Aquarium de Baraka",
    )
    state = compute_quote_state(session)
    assert state["quote_ready"] is False
    assert all("Baraka" not in a["titre"] for a in state["activities"])


def test_select_activity_and_filter_dubai() -> None:
    session = "select-kuza"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
        activites_proposees="54117,61097,50333,74136",
    )
    sync_activity_feedback_from_message(session, "j ai pas aime Aquarium de Baraka")
    conversation_manager.add_turn(
        session,
        "alternatives",
        "1. Visite de la grotte de Kuza, lagon bleu — 141,04€",
    )
    sync_activity_feedback_from_message(session, "oui j ai aime ca")

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) == 1
    assert "Kuza" in state["activities"][0]["titre"]
    assert state["destination"] == "Zanzibar"


def test_is_quote_confirmation() -> None:
    assert is_quote_confirmation("oui") is True
    assert is_quote_confirmation("oui j ai aime ca") is False


def test_select_four_activities_by_numbered_list() -> None:
    session = "four-activities"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
    )
    msg = (
        "non pour ces "
        "1. **Visite de la grotte de Kuza, lagon bleu, aventure des étoiles de mer, "
        "restaurant The Rock, plage de Paje** pour 141.04€. "
        "2. **Journée sur l'île de la prison et la plage de Nakupenda Sandbank** pour 193.50€. "
        "3. **Forêt de Jozani, visite du village et plage de Mtende Zanzibar** pour 102.34€. "
        "4. **Visite des dauphins, grotte de Kuza, plage de Paje et Forêt de Jozani** pour 123.84€"
    )
    sync_activity_feedback_from_message(session, msg)

    state = compute_quote_state(session)
    assert state["quote_ready"] is True
    assert len(state["activities"]) == 4
    ids = {a["id"] for a in state["activities"]}
    assert ids == {"61097", "58235", "58238", "61082"}


def test_match_four_titles_from_catalog() -> None:
    text = (
        "1. Visite de la grotte de Kuza, lagon bleu, aventure des étoiles de mer\n"
        "2. Journée sur l'île de la prison et la plage de Nakupenda Sandbank\n"
        "3. Forêt de Jozani, visite du village et plage de Mtende Zanzibar\n"
        "4. Visite des dauphins, grotte de Kuza, plage de Paje et Forêt de Jozani"
    )
    ids = match_activities_by_titles(text, "Zanzibar")
    assert len(ids) == 4
    assert set(ids) == {"61097", "58235", "58238", "61082"}


def test_select_all_discussed() -> None:
    session = "all-discussed"
    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
        activites_discutees="61097,58235,58238,61082",
    )
    sync_activity_feedback_from_message(
        session,
        "oui je veux toutes les activites qu on a discute",
    )
    state = compute_quote_state(session)
    assert len(state["activities"]) == 4
