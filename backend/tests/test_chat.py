"""Agent and chat endpoint tests (mocked LLM)."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _mock_llm_response(content: str, tool_calls=None):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    message.role = "assistant"
    message.model_dump.return_value = {"role": "assistant", "content": content}

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_tool_call(name: str, args: dict, call_id: str = "call_1"):
    fn = MagicMock()
    fn.name = name
    fn.arguments = json.dumps(args)
    tc = MagicMock()
    tc.id = call_id
    tc.function = fn
    return tc


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_chat_success(mock_completion, mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="groq/llama-3.3-70b-versatile",
        groq_api_key="test-key",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
    )
    mock_completion.return_value = _mock_llm_response(
        "Bonjour ! Je peux vous aider à trouver des activités pour vos clients."
    )

    response = client.post(
        "/chat",
        json={"session_id": "test-session-1", "message": "Bonjour"},
    )
    assert response.status_code == 200
    data = response.json()
    # « Bonjour » → greeting déterministe 0 token (ask destination)
    assert (
        "destination" in data["reply"].lower()
        or "activités" in data["reply"].lower()
        or "aider" in data["reply"].lower()
    )
    assert data["session_id"] == "test-session-1"


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_greeting_with_partner_id(mock_completion, mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="groq/llama-3.3-70b-versatile",
        groq_api_key="test-key",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
    )

    response = client.post(
        "/chat",
        json={
            "session_id": "test-greeting-partner",
            "message": "Bonjour",
            "partner_id": "1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "TUI España" in data["reply"]
    assert data["nom_agence"] == "TUI España Turismo, S.L.U"
    mock_completion.assert_not_called()


@patch("agent.orchestrator.generate_quote_for_session")
@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_auto_quote_on_oui(mock_completion, mock_settings, mock_generate) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="groq/llama-3.3-70b-versatile",
        groq_api_key="test-key",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
    )
    mock_generate.return_value = {
        "devis_ref": "DEV-TEST-001",
        "pdf_url": "/quotes/test.pdf",
        "destination": "Zanzibar",
        "activity_count": "1",
        "total_net": "141.04",
    }

    session = "auto-quote-session"
    from memory.memory_manager import memory_manager

    memory_manager.update_slots(
        session,
        destination="Zanzibar",
        profil_voyageur="famille",
        partner_id="1",
        activites_selectionnees="61097",
    )

    response = client.post(
        "/chat",
        json={"session_id": session, "message": "oui", "partner_id": "1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quote_url"] == "/quotes/test.pdf"
    assert data["quote_ready"] is True
    mock_completion.assert_not_called()
    mock_generate.assert_called_once()


@patch("agent.orchestrator.get_settings")
@patch("agent.orchestrator.litellm.completion")
def test_chat_with_tool_call(mock_completion, mock_settings) -> None:
    mock_settings.return_value = MagicMock(
        llm_model="gemini/gemini-2.0-flash",
        groq_api_key="",
        gemini_api_key="test-key",
        llm_fallback_model="",
        llm_max_tokens=1024,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
    )
    tool_msg = MagicMock()
    tool_msg.content = None
    tool_msg.tool_calls = [
        _mock_tool_call("search_catalog", {"query": "Paris", "destination": "Paris", "limit": "3"})
    ]
    tool_msg.role = "assistant"
    tool_msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    final_msg = MagicMock()
    final_msg.content = "Voici des activités à Paris pour vos clients."
    final_msg.tool_calls = []
    final_msg.role = "assistant"
    final_msg.model_dump.return_value = {"role": "assistant", "content": final_msg.content}

    choice1 = MagicMock()
    choice1.message = tool_msg
    choice2 = MagicMock()
    choice2.message = final_msg

    mock_completion.side_effect = [
        MagicMock(choices=[choice1]),
        MagicMock(choices=[choice2]),
    ]

    response = client.post(
        "/chat",
        json={"session_id": "test-session-2", "message": "Activités à Paris"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "search_catalog" in data["tools_used"] or "Paris" in data["reply"]


def test_chat_missing_api_key() -> None:
    with patch("agent.orchestrator.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            llm_model="groq/llama-3.3-70b-versatile",
            groq_api_key="",
            gemini_api_key="",
            llm_max_tokens=1024,
            llm_timeout=90,
        )
        response = client.post(
            "/chat",
            json={"session_id": "test-no-key", "message": "Bonjour"},
        )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]
