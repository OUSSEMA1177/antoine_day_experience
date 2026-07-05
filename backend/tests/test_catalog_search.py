"""Tests for unified catalog search."""

from search.catalog_search import CatalogSearchParams, catalog_search, search_from_context


def test_search_maroc() -> None:
    result = catalog_search(CatalogSearchParams(query="maroc", limit=10))
    assert result.has_results()
    assert "prix_net" in result.to_prompt_block() or result.activities


def test_search_montagne_global() -> None:
    result = catalog_search(CatalogSearchParams(query="montagne alpes", limit=15))
    assert result.has_results()
    hay = " ".join(
        (r.get("titre", "") + " " + r.get("description", "")).casefold()
        for r in result.activities
    )
    assert "montagne" in hay or "alpes" in hay or "atlas" in hay


def test_search_plage_from_context() -> None:
    result = search_from_context("plage", {})
    assert result.has_results()
    assert "search_catalog" in result.tools_used
