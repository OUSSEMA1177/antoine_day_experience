"""Tests for slot sync via context_manager."""

from agent.context_manager import sync_slots_from_message
from memory.memory_manager import memory_manager


def test_sync_famille_montagne() -> None:
    session = "sync-test"
    updates = sync_slots_from_message(session, "famille montagne aventure")
    assert updates.get("profil_voyageur") == "famille"
    envies = str(updates.get("envies", ""))
    assert "montagne" in envies
    assert "aventure" in envies


def test_sync_group_size_typo() -> None:
    session = "sync-group"
    sync_slots_from_message(session, "20 personnes")
    assert memory_manager.get_slots(session).get("taille_groupe") == "20"


def test_sync_en_couple() -> None:
    session = "sync-couple"
    updates = sync_slots_from_message(session, "en couple")
    assert updates.get("profil_voyageur") == "couple"


def test_sync_budget_and_duree() -> None:
    from agent.context_manager import parse_budget_from_message

    assert parse_budget_from_message("j ai 200 euro") == "200"
    assert parse_budget_from_message("budget 150 €") == "150"
    assert parse_budget_from_message("max 80 euros") == "80"
    session = "sync-budget"
    updates = sync_slots_from_message(
        session,
        "j ai 200 euro je veux des activite en espagne pour un couple pour 2 jours",
    )
    assert updates.get("budget") == "200"
    assert updates.get("profil_voyageur") == "couple"
    assert updates.get("duree") == "2 jours"
    slots = memory_manager.get_slots(session)
    assert slots.get("budget") == "200"
    assert slots.get("profil_voyageur") == "couple"


def test_sync_budget_and_duree() -> None:
    from agent.context_manager import parse_budget_from_message

    assert parse_budget_from_message("j ai 200 euro") == "200"
    assert parse_budget_from_message("budget 150 €") == "150"
    assert parse_budget_from_message("max 80 euros") == "80"
    session = "sync-budget"
    updates = sync_slots_from_message(
        session,
        "j ai 200 euro je veux des activite en espagne pour un couple pour 2 jours",
    )
    assert updates.get("budget") == "200"
    assert updates.get("profil_voyageur") == "couple"
    assert updates.get("duree") == "2 jours"
    slots = memory_manager.get_slots(session)
    assert slots.get("budget") == "200"
    assert slots.get("profil_voyageur") == "couple"
