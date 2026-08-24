"""Unit tests for the MCP server module."""

import json
from unittest.mock import patch

import pytest

from energy_rag.mcp_server import RagApiClient, _format_sources, create_mcp_server


def test_rag_api_client_health_parses_response():
    client = RagApiClient("http://api.test")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"status": "healthy"}'
        )
        result = client.health()

    assert result == {"status": "healthy"}


def test_rag_api_client_query_builds_payload():
    client = RagApiClient("http://api.test/")

    with patch("energy_rag.mcp_server.RagApiClient._request", return_value={}) as mock_req:
        client.query("how does ESS work?", top_k=3, product="MultiPlus-II")

    payload = mock_req.call_args.args[2]
    assert payload["query"] == "how does ESS work?"
    assert payload["top_k"] == 3
    assert payload["filters"] == {"product": "MultiPlus-II"}


def test_mcp_server_registers_expected_tools():
    mcp = create_mcp_server()
    import asyncio

    tools = {t.name for t in asyncio.run(mcp.list_tools())}
    assert tools == {"rag_health", "rag_stats", "rag_search", "rag_ask", "rag_ingest"}


@pytest.mark.anyio
async def test_rag_ask_tool_formats_answer_and_sources():
    fake_response = {
        "answer": "Grid zero stops feed-in [doc_1].",
        "sources": [
            {
                "index": 1,
                "content": "ESS configuration text",
                "metadata": {
                    "title": "Manual",
                    "product": "MultiPlus-II",
                    "section_title": None,
                    "page_number": 7,
                },
            }
        ],
        "processing_time_ms": 42,
    }
    with patch.object(RagApiClient, "query", return_value=fake_response):
        mcp = create_mcp_server()
        result = await mcp.call_tool("rag_ask", {"question": "What is grid zero?"})

    # call_tool returns a CallToolResult
    text = result.content[0].text
    assert "Grid zero stops feed-in [doc_1]." in text
    assert "[doc_1] Manual | MultiPlus-II | page 7" in text
    assert "response time: 42 ms" in text


@pytest.mark.anyio
async def test_rag_ingest_rejects_unknown_source_type():
    mcp = create_mcp_server()
    result = await mcp.call_tool(
        "rag_ingest",
        {"source_type": "bogus", "paths": ["/data/x.pdf"]},
    )
    assert "Invalid source_type" in result.content[0].text


def test_format_sources_handles_missing_metadata():
    lines = _format_sources([{"index": 2, "content": "c" * 400, "metadata": {}}])
    assert lines[0].startswith("[doc_2]")
    assert "..." in lines[0]


def test_json_payload_roundtrip():
    payload = {"a": 1}
    assert json.loads(json.dumps(payload)) == payload
