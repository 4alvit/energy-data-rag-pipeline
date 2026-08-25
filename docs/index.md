# Energy Data RAG Pipeline — Documentation Index

RAG (Retrieval-Augmented Generation) pipeline over Victron Energy documentation
and community knowledge. FastAPI + LangChain + pgvector (PostgreSQL 16),
packaged as multi-arch Docker images (linux/amd64 + linux/arm64).

## Documentation map

| Document | Purpose |
|---|---|
| [architecture.md](architecture.md) | Components, data flow, design decisions |
| [api-reference.md](api-reference.md) | REST endpoints, request/response schemas |
| [configuration.md](configuration.md) | Every environment variable and setting |
| [ingestion-and-chunking.md](ingestion-and-chunking.md) | Loaders, chunking strategies, metadata schema |
| [corpus-enrichment.md](corpus-enrichment.md) | Fetching real Victron manuals + community content into the corpus |
| [deployment-synology.md](deployment-synology.md) | Synology/NAS deployment via `deploy/deploy.sh` |
| [mcp-integration.md](mcp-integration.md) | Connecting AI coding agents (Claude Code, opencode, Cursor, ...) via MCP |
| [release-and-images.md](release-and-images.md) | Versioning policy, multi-arch images, release runbook |
| [troubleshooting.md](troubleshooting.md) | Common failure modes and fixes |

## The 60-second tour

```bash
cp .env.example .env          # configure
docker compose up -d          # postgres + api + mcp
curl localhost:8000/health    # -> {"status": "healthy", ...}
```

Feed it knowledge, then ask questions:

```bash
# Ingest PDFs mounted at ./data/manuals
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"source_type":"pdf","paths":["/data/manuals"]}'

# Ask
curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"query":"How to configure ESS grid-zero on MultiPlus-II?"}'
```

Or plug it straight into your AI coding agent via MCP — see
[mcp-integration.md](mcp-integration.md).
