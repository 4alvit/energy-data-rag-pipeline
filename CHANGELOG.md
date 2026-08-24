# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-08-24

### Fixed
- `deploy.sh` pre-creates `DATA_ROOT/pgdata`; Synology's dockerd does not
  auto-create missing bind dirs on first `up -d`
- api healthcheck `start_period` 120 s -> 600 s and a persistent `hf_cache`
  volume: first-boot embedding-model downloads on slow NAS disks blew the old
  window and re-downloaded ~100 MB on every container recreation
- Container healthcheck exec timeout 5 s -> 10 s: `python -c` startup on a
  busy NAS flapped checks to unhealthy while `/health` answered 200
- FCC provider config moved to gitignored `deploy/fcc.env` uploaded by
  `deploy.sh` and consumed by the compose `fcc` service via `env_file`;
  Admin UI is optional again
- `query_rag` flattens Anthropic-style content-block lists (reasoning models
  reached through Free Claude Code, e.g. nvidia/nemotron) before citation
  extraction instead of crashing with "expected string or bytes-like object"

## [0.2.0] - 2026-08-23

### Added
- MCP server (`energy_rag/mcp_server.py`, `energy-rag-mcp`) exposing
  `rag_ask`, `rag_search`, `rag_ingest`, `rag_health`, `rag_stats` tools over
  stdio and streamable HTTP; wired into docker compose as the `mcp` service
- `POST /query/search` - pure semantic retrieval without an LLM provider
  (usable on NAS deployments with no Ollama/OpenAI)
- Multi-arch Docker publishing (linux/amd64 + linux/arm64) to GHCR via
  `.github/workflows/docker-publish.yml` with SBOM/provenance attestations
- Synology deployment kit: `deploy/docker-compose.prod.yml` (prebuilt images)
  and `deploy/deploy.sh.example` → local gitignored `deploy.sh` for SSH deploys
- RAG-consumable documentation set under `docs/` plus
  `scripts/export_docs_corpus.py` generating `docs-corpus/corpus.json`
  ingestible through `/ingest` (`forum_json`)
- Optional dependency extras: `openai`, `anthropic`, `mcp`; Docker image
  ships all of them
- `LLM_BASE_URL` setting to override the OpenAI/Anthropic client endpoint -
  enables using a local [Free Claude Code](https://github.com/Alishahryar1/free-claude-code)
  proxy as a zero-cost LLM backend for `/query` answer generation; documented
  alongside an FCC client-shell guide in `docs/mcp-integration.md`
- Bundled [Free Claude Code](https://github.com/Alishahryar1/free-claude-code)
  server: headless image `ghcr.io/4alvit/free-claude-code`
  (`deploy/fcc/Dockerfile`, upstream pinned by commit SHA) deployed as the
  `fcc` service in the production compose stack (Admin UI + proxy on port
  8082, config persisted in a named volume, host networking so an SSH
  tunnel reaches the loopback-only Admin UI)
- Root `version` file synced with pyproject and release tags
- Unit tests: citations, CLI parser, corpus exporter, MCP server

### Fixed
- Broken console script `energy-rag-ingest` (async entry point + unpackaged
  module) replaced by sync `energy_rag.cli` implementation
- Ingestion stored chunks without embeddings in a table the query path never
  read; chunks are now embedded and stored via the LangChain pgvector store
- Vector store migrated to `langchain_postgres.PGVector` (async mode) -
  `langchain_community` changed its PGVector constructor and broke startup;
  pgvector extension creation bypasses a langchain_postgres asyncpg bug
  (multi-statement prepared SQL)
- Default `SIMILARITY_THRESHOLD` lowered 0.7 -> 0.3; with all-MiniLM-L6-v2
  the old value filtered out virtually every relevant chunk
- SQLAlchemy 2.0 raw-string execution in health check (`text("SELECT 1")`)
- Compose API healthcheck used `curl`, absent from runtime image; now uses
  python stdlib; added `start_period` for model download
- Container ran as user without `$HOME`; HuggingFace model cache now points
  to writable `/app/.cache`
- Dockerfile failed at build: `uv sync` installs the root package but `src/`
  was not copied into the builder stage
- `.env.example` nested variable interpolation that never resolved
- Hardcoded versions in app metadata/schemas now read installed package version
- `deploy.sh`: Synology's non-interactive sudo truncates PATH before
  `/usr/local/bin` (docker/compose live there); docs-corpus ingestion posted
  the wrong filename (`corpus.jsonl` instead of `corpus.json`)

### Changed
- Docker image uses CPU-only torch wheels (`download.pytorch.org/whl/cpu`);
  image size ~1.4 GB instead of multi-GB CUDA stack
- `docker-compose.yml`: added data mount, port overrides, host-gateway for
  Ollama, GHCR image tag default

## [0.1.1] - 2026-08-11

### Fixed
- CI tooling: install dev/test extras and satisfy lint checks (#20)
- CI tooling: Fix/ci tooling (#21)
- CI tooling: Fix/ci tooling (#22)

## [0.1.0] - 2026-08-10

### Added
- Initial RAG pipeline for Victron Energy documentation
- Document ingestion for PDF manuals, forum HTML, and JSON
- Smart chunking with MarkdownHeaderTextSplitter and RecursiveCharacterTextSplitter
- pgvector storage with metadata filtering (product, section, page)
- FastAPI query endpoint with source citations
- LangChain retrieval with configurable LLM providers (Ollama, OpenAI, Anthropic)
- Docker Compose stack (PostgreSQL + pgvector + API)
- CI pipeline with Ruff, Pylint, pytest, and coverage
- Release workflow with automated GitHub releases

### Changed
- Fixed CI badge URL in README (was pointing to wrong org)

[0.1.0]: https://github.com/4alvit/energy-data-rag-pipeline/releases/tag/v0.1.0