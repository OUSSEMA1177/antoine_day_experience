"""API endpoint tests."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_activities_paris() -> None:
    response = client.get("/activities", params={"destination": "Paris", "limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) <= 5
    assert data["items"][0]["titre"]


def test_list_activities_budget_filter() -> None:
    response = client.get(
        "/activities",
        params={"destination": "Paris", "budget": 30, "limit": 10},
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 0


def test_get_activity_not_found() -> None:
    response = client.get("/activities/00000000")
    assert response.status_code == 404


def test_list_destinations() -> None:
    response = client.get("/destinations")
    assert response.status_code == 200
    assert response.json()["total"] >= 10


def test_get_order_demo() -> None:
    response = client.get("/orders/DEMO-001")
    assert response.status_code == 200
    assert response.json()["reference"] == "DEMO-001"


def test_get_order_not_found() -> None:
    response = client.get("/orders/INEXISTANT-999")
    assert response.status_code == 404


def test_get_partner() -> None:
    response = client.get("/partners/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "1"
    assert "TUI España" in data["nom_agence"]
    assert "TUI España" in data["greeting_message"]
    assert "Bonjour" in data["greeting_message"]


def test_get_partner_not_found() -> None:
    response = client.get("/partners/99999999")
    assert response.status_code == 404
