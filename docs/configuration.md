# Configuration

All settings are environment variables (prefix-less), also loadable from a
`.env` file in the working directory. Defined in `src/energy_rag/config.py`.

## Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://rag:changeme@localhost:5432/energy_rag` | SQLAlchemy async URL. Inside compose use host `postgres`. |
| `POSTGRES_PASSWORD` | `changeme` | Compose-level password for the postgres container |

## Embeddings & LLM

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model. Must produce 384-dim vectors unless you change the SQL schema. |
| `EMBEDDING_DIMENSION` | `384` | Declared dimension (informational + validation) |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai`, or `anthropic` |
| `LLM_MODEL` | `llama3.1:8b` | Model name for the chosen provider |
| `LLM_BASE_URL` | *(empty)* | Optional base-URL override for `openai`/`anthropic` clients (local proxies such as Free Claude Code) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint; from inside compose use `http://host.docker.internal:11434` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | *(empty)* | Required when the matching provider is selected |

Provider packages (`langchain-openai`, `langchain-anthropic`) are optional
extras: `[...--extra openai --extra anthropic]`; the Docker image ships both.

### Free LLM via Free Claude Code (FCC)

[Free Claude Code](https://github.com/Alishahryar1/free-claude-code) exposes a
local Anthropic-compatible proxy (default `http://localhost:8082`) that routes
to free-tier providers. Pointing this service at it makes `/query` generate
grounded answers with zero API cost — no Ollama install needed:

```dotenv
# .env on the host running FCC
LLM_PROVIDER=anthropic
LLM_BASE_URL=http://localhost:8082
LLM_MODEL=nvidia_nim/nvidia/nemotron-3-super-120b-a12b
ANTHROPIC_API_KEY=freecc        # your FCC proxy auth token from the Admin UI
```

Notes:

- The production compose stack ships an `fcc` service itself — see
  [deployment-synology.md → Free Claude Code on the NAS](deployment-synology.md).
- Match `LLM_MODEL` to a model configured in the FCC Admin UI and use its full
  `<provider>/<model-id>` slug; pick a tool-friendly instruct model.
- When running the stack in docker compose, replace the URL with
  `http://host.docker.internal:8082` (`extra_hosts: host-gateway` is already
  set in compose).
- The token value is only checked by FCC's local proxy if you enabled
  **Proxy Authentication** in its Admin UI; any non-empty key satisfies the
  LangChain client otherwise.
- Restart the api container after changing these variables (`Settings` is read
  once at startup).

## Retrieval

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_TOP_K` | `5` | Chunks retrieved per query |
| `SIMILARITY_THRESHOLD` | `0.3` | Minimum cosine similarity (MiniLM models score 0.3-0.6 on relevant text) |
| `ENABLE_RERANK` | `false` | Cross-encoder reranking of candidates |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |

## Ingestion

| Variable | Default | Description |
|---|---|---|
| `CHUNK_SIZE` | `1000` | Max characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |

## API service

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | uvicorn bind host |
| `API_PORT` | `8000` | uvicorn bind port |
| `API_WORKERS` | `1` | Keep at 1 — models are cached per process |
| `LOG_LEVEL` | `INFO` | Logging level |

## MCP server

| Variable | Default | Description |
|---|---|---|
| `RAG_API_URL` | `http://localhost:8000` | REST API the MCP server proxies to |

## Docker-compose ports

| Variable | Default | Description |
|---|---|---|
| `API_PORT` | `8000` | Host port for the API container |
| `MCP_PORT` | `8800` | Host port for streamable-HTTP MCP |
| `TAG` | `latest` | Image tag pulled by prod compose |

## Precedence notes

1. Environment variables beat `.env` values.
2. `.env` entries must be literal — docker compose does **not** interpolate
   variables between entries of the same file (this is why `.env.example`
   spells out the full `DATABASE_URL`).
3. `Settings` is cached via `lru_cache` at import time; restart the process to
   apply changes.
