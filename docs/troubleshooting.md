# Troubleshooting

## API

### `/health` returns `degraded`

Database unreachable. From the repo root:

```bash
docker compose exec postgres pg_isready -U rag -d energy_rag
docker compose logs postgres --tail 50
# Wrong password after editing .env? The volume kept the old one:
docker compose down -v        # WARNING: wipes stored documents
```

### Query returns "I don't have enough information..."

Nothing passed the similarity threshold. Checklist:

1. Anything ingested?
   `SELECT count(*) FROM documents;`
2. Chunks have embeddings? (`embedding IS NULL` rows are invisible to search)
3. Threshold too strict — default is 0.3; MiniLM models rarely score above 0.6 even on good matches.
4. LLM reachable: `curl $OLLAMA_BASE_URL/api/tags` from inside the container:
   `docker compose exec api python -c "import httpx;print(httpx.get('http://host.docker.internal:11434/api/tags').status_code)"`

### 503 on /query

RAG components not initialized — check startup errors in
`docker compose logs api`. Typical cause: Ollama down at startup.

## Ingestion

### Ingestion "started" but nothing appears

Paths must exist **inside the api container**. Host `./data/manuals` is
container `/data/manuals`. Check run status:

```bash
docker compose exec postgres psql -U rag -d energy_rag \
  -c "SELECT status, error_message FROM ingestion_runs ORDER BY started_at DESC LIMIT 1;"
```

### forum_json rejected

Loader expects **one JSON document** with an array of posts (or object with a
`posts`-like key) — not JSONL. Re-export via
`scripts/export_docs_corpus.py`, which produces the right shape.

### Embedding model mismatch

`EMBEDDING_MODEL` dimension must equal the SQL column (384 by default). See
[ingestion-and-chunking.md](ingestion-and-chunking.md#re-embedding-after-a-model-change).

## Docker

### Healthcheck fails while app is fine

The image has no `curl`; healthchecks intentionally use `python -c urllib`.
If you edited them back to curl, restore the python form.

### First start is slow

Model download (~100 MB) happens once per container lifecycle; give the
healthcheck its 120 s `start_period`.

### Port conflicts

Change host-side mappings in `.env`: `API_PORT`, `MCP_PORT`,
`POSTGRES_PORT` (dev compose).

## MCP

### Client shows server but no tools

Stdio spawn failed. Run the exact command manually:

```bash
RAG_API_URL=http://localhost:8000 \
  uv --directory /path/to/energy-data-rag-pipeline run energy-rag-mcp
```

It should block silently (waiting for JSON-RPC on stdin). Errors print to
stderr.

### "Cannot reach RAG API" from tools

`RAG_API_URL` wrong or stack down. Inside stdio servers `localhost` means the
workstation, not the NAS — use `http://synology:8000`.

### Claude Code doesn't prompt for .mcp.json

Run `claude mcp list` in the repo root, then `/mcp` in the session; approve
the project server when asked.

## Synology

### deploy.sh dies at preflight

- Passwordless ssh broken → `ssh-copy-id synology`
- Passwordless sudo missing → add sudoers drop-in (see deployment doc)

### Image pull rate-limited or private

GHCR anonymous pulls are limited; either make the package public
(Package settings → change visibility) or `docker login ghcr.io` on the NAS.
