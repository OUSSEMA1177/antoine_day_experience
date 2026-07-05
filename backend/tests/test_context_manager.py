"""Tests for slot sync via context_manager."""

from agent.context_manager import sync_slots_from_message
from memory.memory_manager import memory_manager


def test_sync_famille_montagne() -> None:
    session = "sync-test"
    updates = sync_slots_from_message(session, "famille montagne aventure")
    assert updates.get("profil_voyageur") == "famille"
    assert "nature" in str(updates.get("envies", ""))


def test_sync_group_size_typo() -> None:
    session = "sync-group"
    sync_slots_from_message(session, "20 personnes")
    assert memory_manager.get_slots(session).get("taille_groupe") == "20"


def test_sync_en_couple() -> None:
    session = "sync-couple"
    updates = sync_slots_from_message(session, "en couple")
    assert updates.get("profil_voyageur") == "couple"
