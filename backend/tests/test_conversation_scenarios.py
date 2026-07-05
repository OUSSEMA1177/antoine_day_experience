"""Tests anti-hallucination et scénarios conversation."""

import re

from agent.context_manager import sync_slots_from_message
from memory.memory_manager import memory_manager
from search.catalog_search import search_from_context
from services.data_loader import data_loader


def test_sahara_search() -> None:
    result = search_from_context("sahara", {})
    assert result.has_results()
    lower = result.to_prompt_block().casefold()
    assert "sahara" in lower or "désert" in lower or "desert" in lower or "agafay" in lower


def test_tour_eiffel_catalog() -> None:
    result = search_from_context("je veux Tour Eiffel", {})
    assert result.has_results()
    block = result.to_prompt_block()
    assert "prix_net" in block
    assert not re.search(r'"prix_net": "17\.', block)


def test_marrakech_couple_slots() -> None:
    session = "marrakech-tunnel"
    sync_slots_from_message(session, "Il part à Marrakech, 5 jours")
    sync_slots_from_message(session, "Couple, première fois au Maroc")
    slots = memory_manager.get_slots(session)
    assert slots.get("duree") == "5 jours"
    assert slots.get("profil_voyageur") == "couple"


def test_plage_without_destination() -> None:
    session = "plage-theme"
    result = search_from_context("plage", {})
    assert result.has_results()
    sync_slots_from_message(session, "j ai aime zanzibar")
    sync_slots_from_message(session, "famille")
    result2 = search_from_context("plage", memory_manager.get_slots(session))
    assert result2.has_results()
    zones = {result2.format_activity(r)["zone_catalogue"] for r in result2.activities}
    assert all(z == "Zanzibar" for z in zones if z)


def test_montagne_search_finds_catalog() -> None:
    result = search_from_context("montagne aventure groupe amis", {"profil_voyageur": "groupe_amis"})
    assert result.has_results()
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert "montagne" in titles or "alpes" in titles or "atlas" in titles
