# Architecture

## High-level data flow

```mermaid
graph TD
    subgraph Ingestion
        PDF[PDF Manuals] --> PDFLoader[PyMuPDF Loader]
        HTML[Forum HTML] --> HTMLLoader[BeautifulSoup Loader]
        JSON["Forum JSON (array of posts)"] --> JSONLoader[JSON Loader]
        PDFLoader --> Pipeline[Ingestion Pipeline]
        HTMLLoader --> Pipeline
        JSONLoader --> Pipeline
    end

    subgraph Chunking
        Pipeline --> HeaderSplitter[MarkdownHeaderTextSplitter]
        HeaderSplitter -->|headers found| Chunks[Chunks + metadata]
        HeaderSplitter -->|no headers| RecursiveSplitter[RecursiveCharacterTextSplitter]
        RecursiveSplitter --> Chunks
    end

    subgraph Storage
        Chunks --> Embeddings[Sentence Transformers<br/>all-MiniLM-L6-v2, 384-dim]
        Embeddings --> PGVector[(pgvector / PostgreSQL 16)]
        PGVector --> IVF[IVFFlat cosine index]
        PGVector --> GIN[GIN metadata index]
    end

    subgraph Query
        Q[User Question] --> Retriever[LangChain Retriever<br/>similarity_score_threshold]
        GIN --> Retriever
        IVF --> Retriever
        Retriever --> LLM["LLM: Ollama / OpenAI / Anthropic"]
        LLM --> Answer[Answer + [doc_N] citations]
    end
```

## Components

### `src/energy_rag/`

| Module | Responsibility |
|---|---|
| `config.py` | Pydantic settings from env/`.env` (`energy_rag.config.settings`) |
| `ingestion/pdf_loader.py` | PDF → markdown/pages via PyMuPDF, Victron manual metadata |
| `ingestion/forum_loader.py` | Forum HTML (CSS selectors per engine), forum JSON (Discourse-like), URL fetcher |
| `ingestion/pipeline.py` | Orchestrates loader → chunker for directories/files |
| `chunking/technical.py` | Markdown-header-aware splitting with recursive fallback |
| `storage/models.py` | SQLAlchemy models: `documents`, `ingestion_runs` |
| `storage/pgvector.py` | Async engine/session management (`PgVectorDatabase`) |
| `storage/repository.py` | CRUD + cosine similarity search with metadata filters |
| `retrieval/chain.py` | LCEL RAG chain, prompt template, citation extraction wiring |
| `retrieval/citations.py` | `[doc_N]` marker parsing → structured sources |
| `retrieval/rerank.py` | Optional cross-encoder reranking |
| `api/main.py` | FastAPI app factory, lifespan init, singleton embeddings/LLM/vector store |
| `api/routes/` | `/health`, `/query`, `/ingest` routers |
| `cli.py` | Sync console entry points (`energy-rag-ingest`) |
| `mcp_server.py` | MCP server (stdio + streamable HTTP) wrapping the REST API |

## Storage schema

`documents` — one row per chunk:

- `id UUID PK`
- `content TEXT` — chunk text
- `embedding VECTOR(384)` — nullable until embedded
- `metadata JSONB` — product, section_title, page_number, url, source_type, ...
- `created_at` / `updated_at TIMESTAMPTZ` (trigger-maintained)

Indexes: `ivfflat (embedding vector_cosine_ops) WITH lists=100`, `GIN(metadata)`, btree on `created_at`.

`ingestion_runs` — audit trail: source_type, source_path, status
(pending/completed/failed), documents_processed, chunks_created,
error_message, timestamps.

Schema is provisioned by [`sql/init.sql`](../sql/init.sql) mounted into the
postgres container's `docker-entrypoint-initdb.d`.

> Note on dimensions: `EMBEDDING_MODEL` and `embedding_dimension` must match
> the `VECTOR(384)` column. Changing models requires re-ingesting.

## Design decisions

1. **pgvector over a dedicated vector DB** — one less system to operate on a
   NAS; PostgreSQL already runs everywhere; metadata filtering in SQL is
   expressive enough.
2. **REST API as single source of truth** — CLI, MCP server and dashboards all
   speak HTTP to the same API; no duplicated retrieval logic.
3. **MCP server as thin adapter** — stdlib-only HTTP client inside; keeps the
   `mcp` dependency optional and the server stateless.
4. **Citations by construction** — the prompt forces `[doc_N]` markers which
   are parsed back into structured sources; ungrounded answers are detectable.
5. **Async SQLAlchemy + asyncpg** — FastAPI-native, pool_pre_ping for NAS
   databases that restart.
