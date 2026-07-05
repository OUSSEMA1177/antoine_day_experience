"""Tests Zanzibar + famille — pas de fuite vers Le Caire."""

from agent.context_manager import is_tunnel_slot_message, sync_slots_from_message
from memory.memory_manager import memory_manager
from search.catalog_search import search_from_context


def test_tunnel_slot_messages() -> None:
    assert is_tunnel_slot_message("une famille") is True
    assert is_tunnel_slot_message("plage") is True
    assert is_tunnel_slot_message("bro j ai dit zanzibar") is False


def test_zanzibar_famille_no_cairo() -> None:
    session = "zanzibar-famille-fix"
    sync_slots_from_message(session, "j ai aime zanzibar")
    sync_slots_from_message(session, "une famille")
    slots = memory_manager.get_slots(session)
    assert slots.get("destination") == "Zanzibar"
    assert slots.get("profil_voyageur") == "famille"

    result = search_from_context("une famille", slots)
    assert result.has_results()
    zones = {result.format_activity(r)["zone_catalogue"] for r in result.activities}
    assert all(z == "Zanzibar" for z in zones if z)
    assert not any("Caire" in z or "caire" in z.casefold() for z in zones)
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert "egyptien" not in titles
    assert "egyptienne" not in titles


def test_plage_without_destination_stays_thematic() -> None:
    result = search_from_context("plage", {"envies": "mer"})
    assert result.has_results()
    block = result.to_prompt_block().casefold()
    assert "zanzibar" in block or "plage" in block or "mer" in block or "côte" in block
