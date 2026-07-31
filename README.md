# Energy Data RAG Pipeline

RAG (Retrieval-Augmented Generation) pipeline for Victron Energy documentation and community knowledge. Built with FastAPI, LangChain, pgvector, and PostgreSQL.

## Features

- **Document Ingestion**: Victron PDF manuals, community forum posts (HTML/JSON)
- **Smart Chunking**: Technical documentation-aware splitting preserving hierarchy
- **Vector Storage**: pgvector with metadata filtering (product, section, page)
- **FastAPI Query Endpoint**: RESTful API with source citations
- **LangChain Retrieval**: LCEL chains with configurable LLM providers
- **Docker Compose**: PostgreSQL + pgvector + API in one stack

## Quickstart

```bash
# Clone and enter
cd energy-data-rag-pipeline

# Copy env template
cp .env.example .env
# Edit .env with your settings

# Start services
docker compose up -d

# Verify health
curl http://localhost:8000/health

# Ingest sample documents
docker compose exec api energy-rag-ingest --source-type pdf --path /data/manuals

# Query the RAG
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How to configure ESS grid-zero on MultiPlus-II?", "top_k": 5}'
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   Ingest    │────▶│  Chunking   │────▶│  pgvector    │
│  (PDF/HTML) │     │  (Technical)│     │  (PostgreSQL)│
└─────────────┘     └─────────────┘     └──────┬───────┘
                                               │
                    ┌─────────────┐            │
                    │   Query     │◀───────────┘
                    │  (FastAPI)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  LangChain  │
                    │  Retrieval  │
                    └─────────────┘
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

GitHub Actions workflow (`.github/workflows/ci.yml`):
- Ruff linting & formatting
- Pylint
- Pytest with coverage
- SonarCloud analysis

## Project Structure

```
energy-data-rag-pipeline/
├── src/energy_rag/
│   ├── config.py              # Pydantic settings
│   ├── ingestion/             # PDF, forum loaders
│   ├── chunking/              # Technical chunking strategies
│   ├── storage/               # pgvector models & repository
│   ├── retrieval/             # LangChain chains, citations
│   └── api/                   # FastAPI routes & schemas
├── tests/
├── scripts/                   # Ingestion CLI scripts
├── sql/init.sql               # Database schema
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## License

MIT