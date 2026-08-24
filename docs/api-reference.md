# API Reference

Base URL: `http://<host>:8000` (default port 8000).
Interactive OpenAPI docs: `http://localhost:8000/docs`.

## `GET /health`

Liveness + database connectivity.

```json
{ "status": "healthy", "database": "connected", "version": "0.2.0" }
```

Status is `degraded` when the DB check fails. Also available:
`GET /health/ready`, `GET /health/live`.

## `POST /query`

Request:

```json
{
  "query": "How to configure ESS grid-zero on MultiPlus-II?",
  "top_k": 5,
  "filters": { "product": "MultiPlus-II" },
  "include_citations": true
}
```

- `query`: required, 1..2000 chars.
- `top_k`: 1..20, default from `DEFAULT_TOP_K` (5).
- `filters`: arbitrary JSONB metadata equality filter (e.g. `product`,
  `doc_type`, `section_title`).
- `include_citations`: parse `[doc_N]` markers into a sources list.

Response:

```json
{
  "answer": "To configure ESS grid-zero ... [doc_1]",
  "sources": [
    {
      "index": 1,
      "content": "ESS Grid-zero configuration ...",
      "metadata": { "product": "MultiPlus-II", "page_number": 42 }
    }
  ],
  "processing_time_ms": 245
}
```

When nothing clears the similarity threshold (`SIMILARITY_THRESHOLD`, 0.3),
the answer is a fixed "not enough information" string with empty `sources`.

## `POST /query/search`

Pure semantic retrieval **without LLM generation** — works even when no LLM
provider is configured (e.g. NAS without Ollama):

```json
{ "query": "ESS grid zero configuration", "top_k": 5 }
```

Response:

```json
{
  "results": [{ "index": 1, "content": "...", "metadata": { "...": "..." } }],
  "processing_time_ms": 213
}
```

## `GET /query/stats`

Retrieval configuration snapshot:

```json
{
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_dimension": 384,
  "llm_provider": "ollama",
  "llm_model": "llama3.1:8b",
  "default_top_k": 5,
  "similarity_threshold": 0.3
}
```

## `POST /ingest`

Queues background ingestion and returns immediately.

```json
{
  "source_type": "pdf",
  "paths": ["/data/manuals", "/data/manuals/multiplus-ii.pdf"],
  "chunk_strategy": "technical"
}
```

- `source_type`: one of `pdf`, `forum_html`, `forum_json`, `url`.
- `paths`: paths **as seen by the api container**. The compose stack mounts
  `./data` → `/data`.
- Response: `{ "status": "started", ..., "run_id": "<uuid>" }`.

Progress lands in the `ingestion_runs` table. Inspect it with:

```bash
docker compose exec postgres psql -U rag -d energy_rag \
  -c "SELECT status, documents_processed, chunks_created, error_message FROM ingestion_runs ORDER BY started_at DESC LIMIT 5;"
```

## Error handling

Unhandled exceptions return `{"detail": "...", "error_code": "INTERNAL_ERROR"}`
with HTTP 500; query before startup completes returns 503.

## CLI equivalents

```bash
energy-rag-ingest --source-type pdf --source-dir /data/manuals
energy-rag-ingest --source-type forum_json --paths corpus.json --chunk-strategy recursive
```

The CLI writes to the same database via `DATABASE_URL`; run it inside the api
container (`docker compose exec api energy-rag-ingest ...`) or locally against
a forwarded port.
