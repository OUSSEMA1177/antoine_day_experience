"""Tool registry tests."""

import json

from tools.registry import execute_tool


def test_search_activities_tool_string_limit() -> None:
    result = json.loads(
        execute_tool(
            "tool-test",
            "search_activities",
            {"destination": "Paris", "limit": "3"},
        )
    )
    assert result["count"] >= 1

    result = json.loads(
        execute_tool(
            "tool-test",
            "search_activities",
            {"destination": "Paris", "limit": 3},
        )
    )
    assert result["count"] >= 1
    assert result["activities"][0]["titre"]


def test_search_faq_tool() -> None:
    result = json.loads(execute_tool("tool-test", "search_faq", {"query": "commission"}))
    assert "results" in result


def test_get_order_demo() -> None:
    result = json.loads(
        execute_tool("tool-test", "get_order_status", {"reference": "DEMO-001"})
    )
    assert result["order"]["reference"] == "DEMO-001"
