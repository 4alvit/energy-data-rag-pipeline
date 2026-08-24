"""MCP (Model Context Protocol) server exposing the Energy RAG API.

Runs over stdio (default, for local coding agents such as Claude Code,
opencode, Cursor, Codex CLI) or streamable HTTP (for shared/remote setups).

The server is a thin adapter: it forwards requests to the RAG REST API
pointed to by ``RAG_API_URL`` (default ``http://localhost:8000``).
"""

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("energy_rag.mcp_server")

DEFAULT_API_URL = "http://localhost:8000"
HTTP_TIMEOUT = 120.0


class RagApiClient:
    """Minimal synchronous HTTP client for the RAG API (stdlib only)."""

    def __init__(self, base_url: str = DEFAULT_API_URL):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                body = resp.read().decode()
            return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"RAG API returned {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach RAG API at {self.base_url} ({exc.reason}). "
                "Is the stack running? Start it with 'docker compose up -d'."
            ) from exc

    def health(self) -> dict[str, Any]:
        """Check API and database status."""
        return self._request("GET", "/health")  # type: ignore[return-value]

    def stats(self) -> dict[str, Any]:
        """Return retrieval configuration statistics."""
        return self._request("GET", "/query/stats")  # type: ignore[return-value]

    def search(self, query: str, top_k: int = 5, product: str | None = None) -> dict[str, Any]:
        """Pure semantic retrieval without LLM generation."""
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if product:
            payload["filters"] = {"product": product}
        return self._request("POST", "/query/search", payload)  # type: ignore[return-value]

    def query(
        self,
        query: str,
        top_k: int = 5,
        product: str | None = None,
        include_citations: bool = True,
    ) -> dict[str, Any]:
        """Execute a RAG query with optional product filter."""
        payload: dict[str, Any] = {
            "query": query,
            "top_k": top_k,
            "include_citations": include_citations,
        }
        if product:
            payload["filters"] = {"product": product}
        return self._request("POST", "/query", payload)  # type: ignore[return-value]

    def ingest(self, source_type: str, paths: list[str], chunk_strategy: str) -> dict[str, Any]:
        """Trigger background ingestion of documents."""
        payload = {
            "source_type": source_type,
            "paths": paths,
            "chunk_strategy": chunk_strategy,
        }
        return self._request("POST", "/ingest", payload)  # type: ignore[return-value]


def _normalize_search_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Map /query/search results to the sources shape used by /query."""
    return [
        {"index": item["index"], "content": item["content"], "metadata": item.get("metadata", {})}
        for item in result.get("results", [])
    ]


def _format_sources(sources: list[dict[str, Any]]) -> list[str]:
    lines = []
    for src in sources:
        meta = src.get("metadata", {})
        where = " | ".join(
            part
            for part in (
                meta.get("title"),
                meta.get("product"),
                meta.get("section_title"),
                f"page {meta.get('page_number')}" if meta.get("page_number") else None,
            )
            if part
        )
        score_note = ""
        content = src.get("content", "")
        snippet = content[:300] + ("..." if len(content) > 300 else "")
        prefix = f"[doc_{src['index']}]" + (f" {where}" if where else "")
        lines.append(f"{prefix}\n{snippet}{score_note}")
    return lines


def create_mcp_server(api_url: str = DEFAULT_API_URL):
    """Create the MCP server instance with tools registered.

    Returns the raw MCPServer object so callers control the transport.
    """
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise SystemExit(
            "The 'mcp' package (>=2.0) is required. Install it with:\n"
            "  uv sync --extra mcp      # or\n"
            "  pip install 'energy-rag-pipeline[mcp]'"
        ) from exc

    client = RagApiClient(api_url)
    mcp = MCPServer(
        name="energy-rag",
        instructions=(
            "Retrieval-Augmented Generation over Victron Energy documentation "
            "and community knowledge. Use rag_search for keyword-free semantic "
            "retrieval of manual excerpts; use rag_ask for full answers with "
            "citations generated by an LLM grounded in retrieved sources."
        ),
    )

    @mcp.tool()
    def rag_health() -> str:
        """Check that the RAG service and its PostgreSQL/pgvector backend are reachable."""
        health = client.health()
        return json.dumps(health)

    @mcp.tool()
    def rag_stats() -> str:
        """Show RAG configuration: embedding model, LLM provider/model, retrieval defaults."""
        return json.dumps(client.stats())

    @mcp.tool()
    def rag_search(query: str, top_k: int = 5, product: str | None = None) -> str:
        """Retrieve relevant document chunks from Victron docs without LLM generation.

        Works even when no LLM provider is configured. Use rag_ask for a
        synthesized answer instead.

        Args:
            query: Natural-language question or keywords.
            top_k: Number of chunks to retrieve (1-20).
            product: Optional metadata filter, e.g. "MultiPlus-II", "Venus OS".
        """
        result = client.search(query, top_k=max(1, min(top_k, 20)), product=product)
        sections = ["Sources:"]
        sections.extend(_format_sources(_normalize_search_results(result)))
        return "\n\n".join(sections)

    @mcp.tool()
    def rag_ask(question: str, top_k: int = 5, product: str | None = None) -> str:
        """Ask a question about Victron/energy systems and get a cited answer.

        Args:
            question: The user's question.
            top_k: Number of context chunks to ground the answer (1-20).
            product: Optional metadata filter, e.g. "MultiPlus-II", "Cerbo GX".
        """
        result = client.query(
            question,
            top_k=max(1, min(top_k, 20)),
            product=product,
            include_citations=True,
        )
        out = [result.get("answer", "")]
        sources = result.get("sources", [])
        if sources:
            out.append("\nSources:")
            out.extend(_format_sources(sources))
        out.append(f"\n(response time: {result.get('processing_time_ms', '?')} ms)")
        return "\n".join(out)

    @mcp.tool()
    def rag_ingest(source_type: str, paths: list[str], chunk_strategy: str = "technical") -> str:
        """Queue documents for ingestion into the vector store.

        Args:
            source_type: One of "pdf", "forum_html", "forum_json".
            paths: Paths visible INSIDE the api container (e.g. /data/manuals/x.pdf).
            chunk_strategy: One of technical, markdown, recursive, fixed.
        """
        if source_type not in ("pdf", "forum_html", "forum_json"):
            return f"Invalid source_type '{source_type}'. Use pdf, forum_html or forum_json."
        result = client.ingest(source_type, paths, chunk_strategy)
        run_id = result.get("run_id", "?")
        return (
            f"Ingestion started (run_id={run_id}). Paths are processed inside the "
            "api container; mount host directories under ./data (-> /data)."
        )

    return mcp


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for the MCP server."""
    parser = argparse.ArgumentParser(
        prog="energy-rag-mcp",
        description="Expose the Energy RAG pipeline as an MCP server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for HTTP transport")
    parser.add_argument(
        "--port",
        type=int,
        default=8800,
        help="Bind port for HTTP transport (default: 8800)",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"RAG API base URL (default: $RAG_API_URL or {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Console entry point for energy-rag-mcp."""
    import os

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    api_url = args.api_url or os.environ.get("RAG_API_URL", DEFAULT_API_URL)

    mcp = create_mcp_server(api_url)

    kwargs: dict[str, Any] = {}
    if args.transport == "streamable-http":
        kwargs["host"] = args.host
        kwargs["port"] = args.port

    logger.info("Starting MCP server (%s) -> RAG API at %s", args.transport, api_url)
    mcp.run(transport=args.transport, **kwargs)


if __name__ == "__main__":
    main(sys.argv[1:])
