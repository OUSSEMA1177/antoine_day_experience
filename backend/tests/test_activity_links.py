"""Format lignes activités + URL fiche B2B."""

from search.catalog_search import activity_product_url, format_activity_line


def test_activity_product_url() -> None:
    assert (
        activity_product_url("53155")
        == "https://b2b.day-experience.com/produit.cfm?idActivity=53155"
    )
    assert activity_product_url("") == ""
    assert activity_product_url(None) == ""


def test_format_activity_line_no_bold_with_link() -> None:
    line = format_activity_line(
        1,
        titre="Safari Kruger",
        prix_net="618.34",
        activity_id="53155",
    )
    assert "**" not in line
    assert line.startswith("1. Safari Kruger — 618.34 € (net)")
    assert "produit.cfm?idActivity=53155" in line


def test_format_activity_line_with_zone() -> None:
    line = format_activity_line(
        2,
        titre="Alcazar",
        prix_net="40",
        zone="Séville",
        activity_id="1",
    )
    assert "— Séville —" in line
    assert "**" not in line
