# MCP Integration

The pipeline ships an **MCP (Model Context Protocol) server** so any
MCP-capable AI agent can query your private Victron knowledge base as native
tools. MCP is an open protocol (originated by Anthropic, now multi-vendor)
that lets coding agents call external tools through a JSON-RPC transport.

## Server overview

Entry point: `src/energy_rag/mcp_server.py`, console script `energy-rag-mcp`.
It is a thin, stateless adapter over the REST API (`RAG_API_URL`,
default `http://localhost:8000`) — start the docker stack first.

| Transport | Command | Typical consumer |
|---|---|---|
| `stdio` *(default)* | `energy-rag-mcp` | Local agents: Claude Code, opencode, Cursor, ... |
| `streamable-http` | `energy-rag-mcp --transport streamable-http --host 0.0.0.0 --port 8800` | Remote/shared agents; exposed by compose on port 8800 at `/mcp` |

### Tools

| Tool | Description |
|---|---|
| `rag_ask(question, top_k?, product?)` | Grounded answer with `[doc_N]` citations |
| `rag_search(query, top_k?, product?)` | Raw semantic retrieval of chunks (no LLM) |
| `rag_ingest(source_type, paths, chunk_strategy?)` | Queue ingestion of files visible to the api container |
| `rag_health()` | API + database status |
| `rag_stats()` | Embedding/LLM/retrieval configuration |

## Prerequisite

The docker stack must be running somewhere reachable:

```bash
docker compose up -d          # workstation
# or on the NAS after deploy.sh:
curl http://synology:8000/health
```

For stdio clients the server is spawned locally and needs Python + this repo
(or the published package). Install once:

```bash
cd /path/to/energy-data-rag-pipeline
uv sync --extra mcp           # creates .venv with the mcp extra
```

---

## Client configurations

All examples assume the repo at `/path/to/energy-data-rag-pipeline` — replace
with your absolute path, or point `RAG_API_URL` at the Synology instance
(`http://synology:8000`). For remote-only usage prefer the HTTP variant shown
at the end.

### Claude Code

Project-scope file **`.mcp.json`** in the repo root (shared via git):

```json
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

Or register imperatively (user scope, available everywhere):

```bash
claude mcp add energy-rag \
  --scope user \
  --env RAG_API_URL=http://localhost:8000 \
  -- uv --directory /path/to/energy-data-rag-pipeline run energy-rag-mcp
```

HTTP transport against the NAS:

```bash
claude mcp add --scope user --transport http energy-rag http://synology:8800/mcp
```

This repository ships a ready `.mcp.json` with the energy-rag entry —
approve it when Claude Code prompts, then check `/mcp`.

> Claude Code expands `${ENV_VAR}` inside `.mcp.json`; avoid committing secrets.

### Free Claude Code (FCC) — Claude Code without a paid plan

[Free Claude Code](https://github.com/Alishahryar1/free-claude-code) (FCC) is
an independent open-source proxy that routes Claude Code's Anthropic API calls
to free-tier providers (NVIDIA NIM, OpenRouter, LM Studio, Ollama, ...). It is
a drop-in replacement for the model backend only — **MCP configuration works
exactly as in the section above**, because `.mcp.json` and `claude mcp add`
are handled by Claude Code itself regardless of which backend serves the
model.

Setup:

```bash
# 1. Install FCC (installs fcc-server, fcc-claude, ...; re-run to update)
curl -fsSL "https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/install.sh" | sh

# 2. Start the proxy + Admin UI (keep this terminal open on Linux;
#    macOS ships a menu-bar app)
fcc-server

# 3. In the Admin UI: paste a provider key (e.g. NVIDIA_NIM_API_KEY from
#    build.nvidia.com), pick a tool-capable MODEL, Validate, Apply

# 4. Run Claude Code through FCC — from the repo root so .mcp.json is picked up
cd /path/to/energy-data-rag-pipeline
fcc-claude
```

Approve the `energy-rag` MCP server when prompted (`/mcp` lists it), then ask
`rag_ask: ...` as usual. Nothing in this repository needs to change.

Notes and caveats:

- `fcc-claude` points `ANTHROPIC_BASE_URL` at the local FCC proxy
  (default `http://localhost:8082`) with a proxy auth token configured in the
  Admin UI; your Anthropic login/API key is never used.
- Pick **tool-capable** models with enough context window — coding agents send
  large system prompts plus MCP tool definitions.
- Free-tier rate limits apply per provider; configure Fallback Models in the
  Admin UI to survive outages mid-turn.
- Bonus: the same FCC proxy can serve as the RAG API's own LLM backend so
  `/query` produces cited answers for free — see
  [configuration.md → Free LLM via Free Claude Code](configuration.md).

### opencode

`~/.config/opencode/opencode.json` or project `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "energy-rag": {
      "type": "local",
      "command": ["uv", "--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "environment": { "RAG_API_URL": "http://localhost:8000" },
      "enabled": true
    }
  }
}
```

Remote variant:

```json
{
  "mcp": {
    "energy-rag": {
      "type": "remote",
      "url": "http://synology:8800/mcp",
      "enabled": true
    }
  }
}
```

### Cursor

`.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "energy-rag": {
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" }
    }
  }
}
```

Cursor also accepts `"url": "http://synology:8800/mcp"` instead of
`command`/`args` for HTTP servers.

### Windsurf (Codeium)

`~/.codeium/windsurf/mcp_config.json` — identical shape to Cursor's:

```json
{
  "mcpServers": {
    "energy-rag": {
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" }
    }
  }
}
```

### OpenAI Codex CLI

`~/.codex/config.toml`:

```toml
[mcp_servers.energy-rag]
command = "uv"
args = ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"]
env = { "RAG_API_URL" = "http://localhost:8000" }
```

### Google Gemini CLI

`~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "energy-rag": {
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" },
      "trust": true
    }
  }
}
```

### Visual Studio Code (Copilot agent mode)

`.vscode/mcp.json`:

```json
{
  "servers": {
    "energy-rag": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" }
    }
  }
}
```

HTTP variant: `{ "type": "http", "url": "http://synology:8800/mcp" }`.

### JetBrains IDEs (AI Assistant / Junie)

Settings → Tools → AI Assistant → Model Context Protocol → add server:
command `uv`, args
`--directory /path/to/energy-data-rag-pipeline run energy-rag-mcp`,
environment `RAG_API_URL=http://localhost:8000`.

### Cline / Roo Code (VS Code extensions)

Extension UI → MCP Servers → Configure. Both write the same schema as Cursor
(`cline_mcp_settings.json`): paste the Cursor snippet above.

### Zed

`settings.json`:

```json
{
  "context_servers": {
    "energy-rag": {
      "source": "custom",
      "command": "uv",
      "args": ["--directory", "/path/to/energy-data-rag-pipeline", "run", "energy-rag-mcp"],
      "env": { "RAG_API_URL": "http://localhost:8000" }
    }
  }
}
```

### Goose

`~/.config/goose/config.yaml`:

```yaml
extensions:
  energy-rag:
    cmd: uv
    args: [--directory, /path/to/energy-data-rag-pipeline, run, energy-rag-mcp]
    enabled: true
    envs: { RAG_API_URL: "http://localhost:8000" }
    type: stdio
```

### Anything else (Aider, custom agents)

Any client speaking MCP stdio can launch:

```bash
RAG_API_URL=http://localhost:8000 \
  uv --directory /path/to/energy-data-rag-pipeline run energy-rag-mcp
```

Any client speaking streamable HTTP can connect to
`http://<host>:8800/mcp` once the compose stack is up.

---

## Verifying the wiring

```bash
# Handshake over stdio (no client needed):
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' | \
  uv run energy-rag-mcp | head -1

# From Claude Code:
/mcp            # lists servers + tools
# Then just ask: "rag_ask: what does ESS grid-zero do?"

# Direct tool call smoke test against a running stack:
curl -X POST http://localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"query":"VE.Direct protocol","top_k":2}'
```

## Security notes

- The MCP server trusts whoever can reach it. Keep `8800` off the public
  internet; bind `127.0.0.1` locally or restrict access at the NAS firewall.
- No secrets flow through the MCP layer — it only forwards queries to the
  REST API. Provider keys stay in the api container env.
