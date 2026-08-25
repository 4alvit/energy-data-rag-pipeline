# Energy Data RAG Pipeline

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Build](https://github.com/4alvit/energy-data-rag-pipeline/actions/workflows/ci.yml/badge.svg)
![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![Type Checking: Pylint](https://img.shields.io/badge/type%20checking-pylint-blue.svg)
![Tests](https://img.shields.io/badge/tests-pytest-green.svg)
![SonarCloud](https://sonarcloud.io/api/project_badges/measure?project=victron-venus_energy-data-rag-pipeline&metric=alert_status)
![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker&logoColor=white)

RAG (Retrieval-Augmented Generation) pipeline for Victron Energy documentation and community knowledge. Built with FastAPI, LangChain, pgvector, and PostgreSQL.

## Features

- **Document Ingestion**: Victron PDF manuals, community forum posts (HTML/JSON)
- **Smart Chunking**: Technical documentation-aware splitting preserving hierarchy
- **Vector Storage**: pgvector with metadata filtering (product, section, page)
- **FastAPI Query Endpoint**: RESTful API with source citations
- **LangChain Retrieval**: LCEL chains with configurable LLM providers
- **MCP Server**: Plug the knowledge base into Claude Code, opencode, Cursor,
  Codex CLI, Gemini CLI and any MCP-capable agent ([docs](docs/mcp-integration.md))
- **Free Claude Code**: run agents (and this API's answer generation) through
  [FCC's](https://github.com/Alishahryar1/free-claude-code) free provider
  proxy — no paid Anthropic plan or local Ollama required
  ([client setup](docs/mcp-integration.md#free-claude-code-fcc--claude-code-without-a-paid-plan),
  [LLM backend](docs/configuration.md#free-llm-via-free-claude-code-fcc))
- **Multi-Arch Images**: linux/amd64 + linux/arm64 on GHCR for every release
- **Synology Deployment**: one-command deploys via gitignored `deploy/deploy.sh`
  ([docs](docs/deployment-synology.md))
- **Docker Compose**: PostgreSQL + pgvector + API + MCP in one stack

## Documentation

Full RAG-consumable documentation lives in [`docs/`](docs/index.md) — start at
the [index](docs/index.md). `scripts/export_docs_corpus.py` turns it into
`docs-corpus/corpus.json` that can be ingested by this very pipeline.

## Quickstart

```bash
# Clone and enter
cd energy-data-rag-pipeline

# Copy env template
cp .env.example .env
# Edit .env with your settings

# Start services (postgres + api + mcp)
docker compose up -d

# Verify health
curl http://localhost:8000/health

# Put manuals into ./data/manuals then ingest them
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type": "pdf", "paths": ["/data/manuals"]}'

# Query the RAG
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How to configure ESS grid-zero on MultiPlus-II?", "top_k": 5}'
```

### Feed the project's own docs to the RAG

```bash
python3 scripts/export_docs_corpus.py     # builds docs-corpus/corpus.json
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type": "forum_json", "paths": ["/data/docs-corpus/corpus.json"], "chunk_strategy": "recursive"}'
```

(`./data` is mounted at `/data` inside the api container.)

### Feed real Victron content to the RAG

```bash
python3 scripts/fetch_victron_content.py --out data   # official PDF manuals + community forum export
python3 scripts/export_projects_corpus.py             # sibling ~/victron repos -> data/projects/corpus.json
```

Then ingest `data/manuals` (`source_type: pdf`, `chunk_strategy: technical`) and
`data/community` / `data/projects` (`source_type: forum_json`, one call after the
other — concurrent ingests race on the DB pool; re-ingestion skips already-stored
sources). On a Synology deployment, `deploy/deploy.sh --with-manuals` does
upload + serialized ingest + wait for you.
See [docs/corpus-enrichment.md](docs/corpus-enrichment.md).

### Connect your AI coding agent

```jsonc
// .mcp.json / client config — see docs/mcp-integration.md for all clients
{
  "mcpServers": {
    "energy-rag": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" }
    }
  }
}
```

Then ask things like *“rag_ask: how do I set up DVCC on a Cerbo GX?”* right in
Claude Code, opencode, Cursor, Windsurf, Codex CLI, Gemini CLI, Goose, Zed,
VS Code Copilot or JetBrains.

## Architecture

### Data Flow

```mermaid
graph TD
    subgraph Ingestion
        PDF[PDF Manuals] --> PDFLoader[PyMuPDF Loader]
        HTML[Forum HTML] --> HTMLLoader[BeautifulSoup Loader]
        JSON[Forum JSON] --> JSONLoader[JSON Loader]
        PDFLoader --> Pipeline[Ingestion Pipeline]
        HTMLLoader --> Pipeline
        JSONLoader --> Pipeline
    end

    subgraph Chunking
        Pipeline --> MarkdownSplitter[MarkdownHeaderTextSplitter]
        MarkdownSplitter -->|Headers found| Chunks[Chunks with metadata]
        MarkdownSplitter -->|No headers| RecursiveSplitter[RecursiveCharacterTextSplitter]
        RecursiveSplitter --> Chunks
    end

    subgraph Storage
        Chunks --> Embeddings[Sentence Transformers]
        Embeddings --> PGVector[pgvector / PostgreSQL 16]
        PGVector --> |IVFFlat index| VectorSearch
        PGVector --> |GIN index| MetadataFilter
    end

    subgraph Query
        UserQuery[User Question] --> VectorSearch
        MetadataFilter --> VectorSearch
        VectorSearch --> Retriever[LangChain Retriever]
        Retriever --> LLM["LLM (Ollama/OpenAI/Anthropic)"]
        LLM --> Answer[Answer with citations]
    end

    style PGVector fill:#336791,color:#fff
    style LLM fill:#f04e23,color:#fff
```

### Component Overview

```mermaid
graph LR
    A[Ingestion\nPDF + Forum] --> B[Chunking\nMarkdown + Recursive]
    B --> C[Embeddings\nall-MiniLM-L6-v2]
    C --> D[pgvector\nPostgreSQL 16]
    D --> E[Retrieval\nLangChain + LLM]
    E --> F[Answer + Citations]
    
    style D fill:#336791,color:#fff
    style E fill:#f04e23,color:#fff
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://rag:changeme@localhost:5432/energy_rag` | PostgreSQL connection |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model (384-dim) |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai`, `anthropic` |
| `LLM_MODEL` | `llama3.1:8b` | LLM model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `LOG_LEVEL` | `INFO` | Logging level |

## API Endpoints

### `POST /query`
Query the RAG system.

**Request:**
```json
{
  "query": "How to configure ESS grid-zero?",
  "top_k": 5,
  "filters": {"product": "MultiPlus-II"},
  "include_citations": true
}
```

**Response:**
```json
{
  "answer": "To configure ESS grid-zero on MultiPlus-II...",
  "sources": [
    {
      "content": "ESS Grid-zero configuration...",
      "metadata": {"product": "MultiPlus-II", "section": "ESS", "page": 42},
      "score": 0.92
    }
  ],
  "processing_time_ms": 245
}
```

### `POST /ingest`
Trigger document ingestion.

**Request:**
```json
{
  "source_type": "pdf",
  "paths": ["/data/manuals/multiplus-ii.pdf"]
}
```

### `GET /health`
Health check with DB connectivity.

## Chunking Strategy

1. **MarkdownHeaderTextSplitter** - Splits by `# ## ###` preserving document hierarchy
2. **RecursiveCharacterTextSplitter** - Fallback for unstructured text (chunk_size=1000, overlap=200)
3. **Metadata enrichment**: `doc_type`, `product_line`, `section_title`, `page_num`, `url`, `source`

## Development

```bash
# Install dependencies
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest

# Lint
uv run ruff check .
uv run ruff format .

# Type check (if using mypy)
uv run pylint src/energy_rag
```

## CI/CD

- **CI** (`.github/workflows/ci.yml`): Ruff, Pylint, pytest + coverage,
  SonarCloud
- **Release** (`.github/workflows/release.yml`): on `v*` tags — tests, build,
  GitHub Release with artifacts
- **Docker Publish** (`.github/workflows/docker-publish.yml`): multi-arch
  (amd64+arm64) images to `ghcr.io/4alvit/energy-data-rag-pipeline`

Versioning: root `version` file = `pyproject.toml` version = git tag. Runbook:
[docs/release-and-images.md](docs/release-and-images.md).

## Project Structure

```mermaid
graph TD
    Root[energy-data-rag-pipeline]
    Root --> Src[src/energy_rag]
    Root --> Tests[tests/]
    Root --> Scripts[scripts/]
    Root --> SQL[sql/]
    Root --> Docker[docker-compose.yml]
    Root --> Dockerfile[Dockerfile]
    Root --> PyProject[pyproject.toml]

    Src --> Config[config.py]
    Src --> Ingestion[ingestion/]
    Src --> Chunking[chunking/]
    Src --> Storage[storage/]
    Src --> Retrieval[retrieval/]
    Src --> API[api/]

    Ingestion --> PDFLoader[pdf_loader.py]
    Ingestion --> ForumLoader[forum_loader.py]
    Ingestion --> Pipeline[pipeline.py]

    Chunking --> Technical[technical.py]

    Storage --> Models[models.py]
    Storage --> PgVector[pgvector.py]
    Storage --> Repository[repository.py]

    Retrieval --> Chain[chain.py]
    Retrieval --> Citations[citations.py]
    Retrieval --> Rerank[rerank.py]

    API --> Main[main.py]
    API --> Schemas[schemas.py]
    API --> Routes[routes/]
    Routes --> Health[health.py]
    Routes --> Query[query.py]
    Routes --> Ingest[ingest.py]
```

## License

MIT