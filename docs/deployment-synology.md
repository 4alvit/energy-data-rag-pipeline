# Deployment (Docker & Synology)

## Local development stack

```bash
cp .env.example .env
docker compose up -d          # postgres + api + mcp (builds locally)
curl localhost:8000/health
```

`./data` is mounted into the api container at `/data` — drop PDFs and exports
there for ingestion. The `mcp` service exposes streamable-HTTP MCP on port
8800 (`http://localhost:8800/mcp`).

## Production images

Releases publish multi-arch images (linux/amd64 + linux/arm64) to GHCR:

```
ghcr.io/4alvit/energy-data-rag-pipeline:<version>   # e.g. 0.2.0
ghcr.io/4alvit/energy-data-rag-pipeline:<major.minor>
ghcr.io/4alvit/energy-data-rag-pipeline:latest
ghcr.io/4alvit/free-claude-code:<version>           # bundled FCC proxy
```

Published by `.github/workflows/docker-publish.yml` on every `v*` tag and on
pushes to `main`. See [release-and-images.md](release-and-images.md).

## Synology deployment via deploy.sh

The NAS runs the same stack from prebuilt images — no compiler, no build step.

### One-time setup

```bash
# On your workstation:
cd energy-data-rag-pipeline

# 1. Create the local-only deploy script
cp deploy/deploy.sh.example deploy/deploy.sh   # gitignored
chmod +x deploy/deploy.sh

# 2. Edit the config block in deploy/deploy.sh:
#    SYNOLOGY_HOST=synology            # ssh alias or IP
#    REMOTE_DIR=/volume1/docker/energy-rag
#    API_PORT=8010                     # 8000 is taken by Portainer on many NAS setups
#    POSTGRES_PASSWORD=<strong password>
#    OLLAMA_BASE_URL=http://<lan-ip-of-ollama-host>:11434

# 3. Verify prerequisites (passwordless ssh AND passwordless sudo):
ssh synology true && ssh synology 'sudo -n true'
```

If you don't have a passwordless-sudo user yet, on the NAS:

```
# /usr/local/etc/sudoers.d/deploy  (edit as root)
<victron> ALL=(ALL) NOPASSWD: ALL
```

### Daily operation

```bash
deploy/deploy.sh                 # sync files, pull images, restart, health check, smoke query
deploy/deploy.sh --with-docs     # also upload docs-corpus/ and trigger ingestion
deploy/deploy.sh status          # container states
deploy/deploy.sh logs api        # tail api logs (also: mcp, postgres)
deploy/deploy.sh down            # stop everything
```

What `deploy.sh --with-docs` does:

1. Generates `docs-corpus/` locally via `scripts/export_docs_corpus.py`
   (if missing).
2. `rsync`s it to `$DATA_ROOT/data/docs-corpus/` on the NAS.
3. POSTs `/ingest` with `source_type=forum_json` pointing at
   `/data/docs-corpus/corpus.json`.

### What lands on the NAS

```
/volume1/docker/energy-rag/
├── docker-compose.prod.yml      # synced by deploy.sh
├── sql/init.sql                 # schema bootstrap (first start only)
├── .env                         # created once; manual edits preserved
├── data/                        # mounted into api:/data
│   └── docs-corpus/corpus.json  # uploaded documentation knowledge
└── pgdata/                      # postgres volume
```

### Manual deployment (without deploy.sh)

```bash
ssh synology 'sudo mkdir -p /volume1/docker/energy-rag/sql'
rsync -av deploy/docker-compose.prod.yml sql/init.sql synology:/tmp/erag/
ssh synology 'sudo mv /tmp/erag/* /volume1/docker/energy-rag/'
ssh synology "cd /volume1/docker/energy-rag && \
  TAG=0.2.0 POSTGRES_PASSWORD=secret sudo -E \
  docker compose -f docker-compose.prod.yml up -d"
```

### Free Claude Code on the NAS

The prod stack includes an `fcc` service: a headless
[Free Claude Code](https://github.com/Alishahryar1/free-claude-code) server
(Anthropic-compatible proxy to free-tier providers, image pinned by commit
SHA in `deploy/fcc/Dockerfile`). It runs with **host networking** because its
Admin UI hard-rejects any request whose client IP or Origin header is not
loopback; host networking lets an SSH tunnel present genuine loopback while
LAN clients can still reach the proxy endpoints.

Two ways to configure a provider:

**Option A - Admin UI via SSH tunnel (full features):**

```bash
ssh -N -L 8082:127.0.0.1:8082 synology    # keep running
# then open http://localhost:8082/admin in your browser
```

Paste your `NVIDIA_NIM_API_KEY` from
[build.nvidia.com](https://build.nvidia.com/settings/api-keys), pick a
tool-capable model in the `MODEL` dropdown, click **Validate**, **Apply**.

**Option B - headless via `.env` (no UI):**

Set `NVIDIA_NIM_API_KEY=<key>` and optionally `FCC_MODEL=<slug>` in the
remote `/volume1/docker/energy-rag/.env` (or export both before the first
`deploy.sh` run) and redeploy. Container environment takes precedence over
the Admin UI's stored config until you change values in the UI.

Pointing clients at it:

- Claude Code on any machine:
  `ANTHROPIC_BASE_URL=http://<nas-ip>:8082 ANTHROPIC_AUTH_TOKEN=freecc claude`
  (token differs if you enabled Proxy Authentication in the Admin UI).
- This very stack's answer generation: set `LLM_PROVIDER=anthropic`,
  `LLM_BASE_URL=http://host.docker.internal:8082`,
  `LLM_MODEL=<fcc-model-slug>`, `ANTHROPIC_API_KEY=freecc` in the remote
  `.env`, then redeploy — see
  [configuration.md → Free LLM via Free Claude Code](configuration.md).

Notes:

- Provider keys and the model mapping persist in the `fcc_config` docker
  volume (`~/.fcc/.env` inside the container) and survive redeploys.
- The proxy trusts anyone who can reach port 8082 — keep it LAN-only; enable
  **Proxy Authentication** in the Admin UI for a bearer token.
- Upstream moves fast without release tags; bump the pinned `FCC_REF` commit
  SHA in `deploy/fcc/Dockerfile` deliberately.

### Synology specifics

- Container Manager (GUI) can import
  `deploy/docker-compose.prod.yml`, but SSH+compose gives reproducibility.
- arm64 models (DS220+, DS920+ re-badged units, newer "+" series) run the
  same image thanks to multi-arch manifests.
- First API start downloads embedding models (~100 MB) to the container
  layer; subsequent restarts reuse them unless the container is recreated.
- If Ollama runs on another LAN host, set `OLLAMA_BASE_URL=http://<ip>:11434`
  (no `host.docker.internal` needed from the NAS).

## Upgrades & rollback

```bash
TAG=v0.2.1 deploy/deploy.sh       # move to a version
TAG=v0.2.0 deploy/deploy.sh       # roll back — pgdata volume persists
```

Schema changes are additive (`sql/init.sql` runs only on first DB creation);
check CHANGELOG.md for migration notes between versions.
