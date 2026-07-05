"""Tests génération devis PDF."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from memory.memory_manager import memory_manager
from pdf.quote_generator import OUTPUT_DIR, build_quote_document, generate_quote_pdf
from tools.registry import execute_tool

client = TestClient(app)


def test_build_quote_document_dubai() -> None:
    quote = build_quote_document(
        devis_ref="DEV-TEST-0001",
        destination="Dubaï",
        activity_ids=["50245", "39444"],
        partner_id="1",
        profil_voyageur="couple",
        envies="aventure, détente",
        validite_jours=7,
    )
    assert len(quote.lines) == 2
    assert quote.partner_name
    assert quote.total_net > 0


def test_generate_quote_pdf_file() -> None:
    quote = build_quote_document(
        devis_ref="DEV-TEST-PDF",
        destination="Dubaï",
        activity_ids=["39648"],
        partner_id="1",
        profil_voyageur="couple",
    )
    path = generate_quote_pdf(quote)
    assert path.is_file()
    assert path.stat().st_size > 500


def test_generate_quote_tool() -> None:
    session = "quote-tool-test"
    memory_manager.update_slots(
        session,
        partner_id="1",
        destination="Dubaï",
        profil_voyageur="couple",
        envies="aventure",
    )
    result = json.loads(
        execute_tool(
            session,
            "generate_quote",
            {"destination": "Dubaï", "activity_ids": ["50245", "39444"]},
        )
    )
    assert result["status"] == "ok"
    assert result["pdf_url"].startswith("/quotes/")
    assert result["devis_ref"].startswith("DEV-")


def test_post_quote_endpoint() -> None:
    session = "quote-api-test"
    memory_manager.update_slots(session, partner_id="1", profil_voyageur="couple")
    response = client.post(
        "/quote",
        json={
            "session_id": session,
            "destination": "Dubaï",
            "activity_ids": ["39648", "50247"],
            "partner_id": "1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pdf_url"].startswith("/quotes/")
    assert data["activity_count"] == 2

    filename = Path(data["pdf_url"]).name
    download = client.get(f"/quotes/{filename}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"


def test_post_quote_invalid_activity() -> None:
    response = client.post(
        "/quote",
        json={
            "session_id": "bad-quote",
            "destination": "Dubaï",
            "activity_ids": ["INVALID-ID-999"],
        },
    )
    assert response.status_code == 400


def test_quote_from_session_endpoint() -> None:
    session = "quote-from-session"
    memory_manager.update_slots(
        session,
        destination="Marrakech",
        profil_voyageur="couple",
        nom_agence="Sousou Voyage",
        activites_selectionnees="54433,54926",
    )
    response = client.post(
        "/quote/from-session",
        json={"session_id": session},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pdf_url"].startswith("/quotes/")
    assert data["activity_count"] == 2


def test_quote_state_endpoint() -> None:
    session = "quote-state-api"
    memory_manager.update_slots(session, destination="Marrakech", profil_voyageur="couple")
    response = client.get(f"/session/{session}/quote-state")
    assert response.status_code == 200
    data = response.json()
    assert data["quote_ready"] is False
    assert "activites" in data["missing"] or "agence" in data["missing"]
