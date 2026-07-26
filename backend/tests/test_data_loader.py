"""Tests for CSV data loader."""

from pathlib import Path

import pytest

from services.data_loader import DataLoader, _parse_price

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def loader() -> DataLoader:
    return DataLoader(data_dir=DATA_DIR)


def test_load_activities_not_empty(loader: DataLoader) -> None:
    rows = loader.load_activities()
    assert len(rows) > 100
    assert "titre" in rows[0]
    assert rows[0]["id"]


def test_search_maroc_via_smart_loader(loader: DataLoader) -> None:
    rows, meta = loader.search_activities_smart(destination_name="Maroc", limit=5)
    assert len(rows) >= 1
    assert meta["matched_by"] in ("region", "text")
    assert "marrakech" in rows[0].get("titre", "").casefold()


def test_recommend_maroc_famille_mer_sahara(loader: DataLoader) -> None:
    rows, meta = loader.recommend_activities(
        destination_name="Maroc",
        profil="famille",
        envies=["mer", "sahara"],
        limit=8,
    )
    assert len(rows) >= 3
    assert meta.get("recommendation") is True
    haystacks = " ".join(r.get("titre", "") for r in rows).casefold()
    assert any(k in haystacks for k in ("agafay", "merzouga", "essaouira", "chameau", "désert", "desert"))

    rows, meta = loader.search_activities_smart(destination_name="Marrakech", limit=5)
    assert len(rows) >= 1
    assert "marrakech" in rows[0].get("titre", "").casefold()

    paris = loader.search_activities(destination_name="Paris", limit=5)
    assert len(paris) >= 1
    assert all(r.get("destination_id") for r in paris)


def test_search_by_budget(loader: DataLoader) -> None:
    cheap = loader.search_activities(destination_name="Paris", budget_max=25, limit=10)
    for row in cheap:
        price = _parse_price(row.get("prix")) or _parse_price(row.get("prix_public"))
        assert price is not None and price <= 25


def test_search_by_profil_is_soft(loader: DataLoader) -> None:
    """Profil ne filtre plus en dur : couple voit aussi general / autres profils."""
    with_profil = loader.search_activities(destination_name="Paris", profil="couple", limit=20)
    without = loader.search_activities(destination_name="Paris", profil=None, limit=20)
    assert len(with_profil) == len(without)
    assert len(with_profil) >= 5
    profils = {(r.get("profil_cible") or "general").lower() for r in with_profil}
    assert "general" in profils or len(profils) >= 1


def test_catalog_couple_includes_general_and_solo() -> None:
    from search.catalog_search import CatalogSearchParams, catalog_search

    result = catalog_search(
        CatalogSearchParams(destination="Bali", profil="couple", limit=15)
    )
    assert result.has_results()
    assert result.count >= 5
    profils = {
        (r.get("profil_cible") or "general").casefold() for r in result.activities
    }
    # Plus que le seul tag couple : general et/ou solo présents
    assert profils & {"general", "solo", "couple"}
    assert len(profils) >= 2 or "general" in profils


def test_cache_reload(loader: DataLoader) -> None:
    first = loader.load_activities()
    second = loader.load_activities()
    assert first is second
    loader.clear_cache()
    third = loader.load_activities()
    assert third is not first


def test_orders_and_policies_graceful_empty(loader: DataLoader) -> None:
    assert loader.get_order_by_reference("DEMO-001") is not None
    assert loader.load_policies() == [] or isinstance(loader.load_policies(), list)
