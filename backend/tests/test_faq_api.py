"""Tests endpoint FAQ."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_faq() -> None:
    res = client.get("/faq")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 10
    assert data["items"]
    first = data["items"][0]
    assert first["question"]
    assert first["reponse"]


def test_search_faq_commission() -> None:
    res = client.get("/faq", params={"q": "commission"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    blob = " ".join(
        f"{i['question']} {i['reponse']}".casefold() for i in data["items"]
    )
    assert "commission" in blob
