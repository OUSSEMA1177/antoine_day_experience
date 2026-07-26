"""Tests matching thématique B2B : plage, montagne, forêt + continent."""

from search.catalog_search import CatalogSearchParams, catalog_search, search_from_context
from search.themes import detect_themes_from_text, term_in_text


def test_mer_not_substring_of_merzouga() -> None:
    assert term_in_text("mer", "étoiles de mer plage de paje") is True
    assert term_in_text("mer", "merzouga excursion desert") is False
    assert term_in_text("plage", "équitation sur la plage de seminyak") is True


def test_detect_themes_plage_montagne_foret() -> None:
    assert "mer" in detect_themes_from_text("il veut de la plage")
    assert "montagne" in detect_themes_from_text("plutôt de la montagne")
    assert "foret" in detect_themes_from_text("une forêt tropicale")
    assert "foret" in detect_themes_from_text("jungle et nature")


def test_plage_search_excludes_merzouga() -> None:
    result = catalog_search(CatalogSearchParams(query="plage", themes=["mer"], limit=20))
    assert result.has_results()
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert "merzouga" not in titles
    hay = titles + " " + result.to_prompt_block().casefold()
    assert "plage" in hay or "lagon" in hay or "zanzibar" in hay or "bali" in hay


def test_plage_asie_finds_bali() -> None:
    result = catalog_search(
        CatalogSearchParams(query="plage en asie", themes=["mer"], region="asie", limit=15)
    )
    assert result.has_results()
    zones = {result.format_activity(r)["zone_catalogue"] for r in result.activities}
    assert "Bali" in zones
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert any(k in titles for k in ("plage", "snorkeling", "seminyak", "nusa", "water"))


def test_montagne_search() -> None:
    result = search_from_context("montagne", {})
    assert result.has_results()
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert any(
        k in titles
        for k in ("montagne", "atlas", "volcan", "alpes", "fuji", "canyon", "torres")
    )


def test_foret_search() -> None:
    result = search_from_context("forêt jungle", {})
    assert result.has_results()
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert any(k in titles for k in ("forêt", "foret", "jungle", "tijuca", "jozani"))


def test_plage_labas_uses_region_interest() -> None:
    result = search_from_context(
        "je veux du plage là-bas",
        {"envies": "mer", "region_interest": "asie"},
    )
    assert result.has_results()
    zones = {result.format_activity(r)["zone_catalogue"] for r in result.activities}
    assert "Bali" in zones
    assert "Pékin" not in zones or any(
        "plage" in r.get("titre", "").casefold() for r in result.activities
    )


def test_bali_plage_with_couple_profil() -> None:
    """Profil couple ne doit pas masquer les activités plage (souvent solo/general)."""
    result = catalog_search(
        CatalogSearchParams(
            query="plage",
            destination="Bali",
            themes=["mer"],
            profil="couple",
            limit=10,
        )
    )
    assert result.has_results()
    titles = " ".join(r.get("titre", "") for r in result.activities).casefold()
    assert "plage" in titles or "snorkeling" in titles or "seminyak" in titles
