"""Tests for geographic helpers."""

from search.geo import detect_landmark, expand_to_keywords


def test_expand_maroc_to_cities() -> None:
    keywords = expand_to_keywords("Maroc")
    assert "marrakech" in [k.casefold() for k in keywords]


def test_detect_landmark_eiffel() -> None:
    hit = detect_landmark("je veux Tour Eiffel")
    assert hit is not None
    assert hit[0] == "Paris"
