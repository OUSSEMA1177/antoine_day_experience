"""Tests catalogue normalisé — villes, alias, pays, fusion Le Caire."""

from agent.destination_policy import (
    detect_unknown_place_request,
    is_catalog_destination,
)
from search.geo import (
    detect_country_query,
    list_catalog_destinations_for_region,
    resolve_destination_name,
)
from services.data_loader import data_loader


def test_marrakech_is_catalog_destination() -> None:
    assert is_catalog_destination("Marrakech")
    assert is_catalog_destination("marrakech")
    assert is_catalog_destination("Désert d'Agafay")
    assert detect_unknown_place_request("marrakech ?") is None
    assert resolve_destination_name("Marrakech", data_loader) == "Marrakech"


def test_seville_milan_amsterdam_london_aliases() -> None:
    assert resolve_destination_name("Séville", data_loader) == "Séville"
    assert resolve_destination_name("Palais Alcazar de Séville", data_loader) == "Séville"
    assert resolve_destination_name("Milan", data_loader) == "Milan"
    assert resolve_destination_name("Duomo de Milan", data_loader) == "Milan"
    assert resolve_destination_name("Amsterdam", data_loader) == "Amsterdam"
    assert resolve_destination_name("Musée Van Gogh", data_loader) == "Amsterdam"
    assert resolve_destination_name("Londres", data_loader) == "Londres"
    assert resolve_destination_name("Studios Warner Bros", data_loader) == "Londres"


def test_le_caire_merge_and_alias() -> None:
    assert data_loader.get_destination_by_id("202816") is None
    assert resolve_destination_name("Grand Musée égyptien", data_loader) == "Le Caire"
    rows = data_loader.search_activities(destination_name="Le Caire", limit=5)
    assert len(rows) >= 5
    merged = [r for r in data_loader.load_activities() if r["destination_id"] == "1138"]
    assert len(merged) >= 180


def test_maroc_lists_marrakech() -> None:
    assert detect_country_query("maroc") == "maroc"
    cities = list_catalog_destinations_for_region("maroc")
    assert cities == ["Marrakech"]


def test_espagne_lists_cities() -> None:
    cities = list_catalog_destinations_for_region("espagne")
    assert "Barcelone" in cities
    assert "Séville" in cities
    assert "Grenade" in cities


def test_italie_lists_cities() -> None:
    cities = list_catalog_destinations_for_region("italie")
    assert "Rome" in cities
    assert "Milan" in cities
    assert "Naples" in cities
    assert "Venise" in cities


def test_all_destinations_have_pays() -> None:
    for row in data_loader.load_destinations():
        assert (row.get("pays") or "").strip(), f"pays manquant pour {row.get('nom')}"


def test_no_orphan_activity_destination_ids() -> None:
    dest_ids = {r["id"] for r in data_loader.load_destinations()}
    orphans = {
        r["destination_id"]
        for r in data_loader.load_activities()
        if r["destination_id"] not in dest_ids
    }
    assert orphans == set()
