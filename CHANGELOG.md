# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.19]

### Changed

- Update the FCC sidecar's locked dnspython dependency to 2.9.0 while retaining the existing universal platform dependencies.
- Update Pylint to 4.0.9 in the development lock and pre-commit hook.

### Upgrade

Use the existing package and container update procedure. Preserve local configuration, credentials and data volumes, and retain the previous immutable artifacts for rollback. Rebuild the FCC sidecar to receive its dependency update; publishing this release does not deploy it.

### Security

- dnspython 2.9.0 fixes excessive CPU consumption when parsing untrusted DNS messages ([GHSA-45c3-73f7-pv4m](https://github.com/rthalley/dnspython/security/advisories/GHSA-45c3-73f7-pv4m)). This update applies to the FCC sidecar dependency set.
- Pylint 4.0.9 replaces its pickle-backed cache format ([GHSA-22qq-2fwx-7p67](https://github.com/pylint-dev/pylint/security/advisories/GHSA-22qq-2fwx-7p67)). The development-tool issue requires an attacker-writable cache; no active compromise is asserted.

## [0.2.18]

### Changed

- Require OpenTelemetry API 1.45.1 or newer for the MCP extra and refresh its runtime lock.
- Add inbound metadata regression checks for normal, boundary-size and oversized tracestate values.

### Upgrade

Install the new package or container through the existing release procedure. Preserve local configuration and credentials, and retain the previous immutable artifacts for rollback. Publishing this release does not deploy it.

### Security

- Refresh the fuzzing environment to certifi 2026.10.19 and the Torch-transitive setuptools dependency to 84.1.0, addressing GHSA-6q48-6c7w-9gw2 and GHSA-xmj3-9gf7-h52w.

Fix [GHSA-xcq7-p3pf-p88h](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h), an availability issue caused by unbounded tracestate parsing in OpenTelemetry API through 1.45.0. The optional MCP service parses W3C context from inbound request metadata. The patched standard propagator rejects oversized tracestate while retaining valid parent trace context.

## [0.2.17] - 2026-10-20

### Changed

- Update aiohttp to 3.14.4 and its required yarl URL dependency to 1.25.1 in both the application and FCC dependency locks.
- Validate the complete documentation corpus in a temporary directory so tests detect stale content without modifying the checkout.

### Upgrade

Use the existing update procedure, preserve local configuration and retain the previous immutable package for rollback. No configuration migration is required.

### Security

- Update the locked development tools to filelock 4.2.1 and virtualenv 21.14.13, addressing CVE-2026-112940 and CVE-2026-115586. Application dependencies and required security checks are unchanged.

Required dependency, source and release checks remain enabled. This maintenance beta does not claim a new application vulnerability fix or device acceptance.

## [0.2.16] - 2026-10-18

### Changed

- Refresh pinned shared review, merge and RC fuzzing workflows while preserving the required CI gates.

### Upgrade

This is a maintenance release with no configuration or data migration. Preserve installation-specific configuration and retain the previous package for rollback.

### Security

Required CI, dependency checks and source-bound RC qualification remain enabled. No additional runtime security fix is claimed.

## [0.2.15] - 2026-10-17

### Changed

- Add illustrated RC fuzzing process and results documentation and link it from the project guides.

### Upgrade

This documentation release preserves runtime behavior and configuration from 0.2.14, including its MCP session-retention fix. Keep the existing deployment and configuration rollback procedure.

### Security

No new runtime security fix is claimed. The release documents the existing bounded, source-bound RC fuzzing checks and their limits.

## [0.2.14] - 2026-10-16

### Security

Require MCP Python SDK 2.2.0 or newer and lock the container dependency to 2.2.0, fixing unbounded stateful Streamable HTTP session retention (CVE-2026-59951 / GHSA-84m7-p3x7-pcfv). Verify session capacity, deletion and expiry through the production MCP server's HTTP application.

### Upgrade

Replace the API/MCP container or upgrade the installed `mcp` extra. Existing stateful HTTP sessions may need to reconnect after restart or 30 minutes without an active request. The SDK caps simultaneous sessions at 10,000 and returns HTTP 503 when full; ended and expired sessions release capacity. Stdio transport and stored RAG data are unchanged. Continue restricting the MCP endpoint to trusted clients.

## [0.2.13] - 2026-10-14

### Changed

- Validate each public release candidate with bounded, network-isolated fuzz campaigns against its exact source revision.
- Require positive engine execution counts, instrumented production code and validated seed corpora; retain source-bound reports and diagnostic evidence.
- Run deterministic seed and configuration checks in ordinary CI without starting mutation campaigns on betas.

### Upgrade

Use the existing installation procedure, preserve local configuration and keep the previous accepted package for rollback. This maintenance release updates release validation and does not change the application configuration format. Deployment and applicable device or integration acceptance remain separate from publication.

### Security

RC publication rejects absent or invalid source-bound fuzz reports. The fuzz runner bounds corpus paths, file types and size. No application vulnerability or new target-device acceptance is claimed by these tooling changes.

## [0.2.12]

### Changed

Forum downloads now use the same exact verified-chain TLS policy as the MCP and corpus clients. Add an opt-in local/offline deployment profile that uses pre-staged models and trusted loopback Ollama/PostgreSQL, rejecting unmanaged SDK TLS and download fallback.

Give FCC a bounded startup grace period before liveness checks begin, so slow initialization does not cause a restart loop. Open the next beta series after stable 0.2.11, including the TLS, dependency and release-verification improvements added since that release.

### Upgrade

The compatibility deployment remains the default. To opt into `STRICT_LOCAL_PROFILE`, follow `docs/tls-policy.md`, export the offline flags before startup and provide verified local model directories. Replace weak forum certificate chains; normal certificate/hostname verification remains required.

Preserve PostgreSQL/pgvector data and existing broker and certificate settings. The FCC deployment permits up to ten minutes for startup and retains liveness checks after initialization. Publishing this beta does not apply the deployment manifests or migrate stored data.

### Security

Keep the pinned FCC source, hash-locked dependencies and required native AMD64/ARM64 checks. No verification or container security setting is relaxed by the startup grace period.

## [0.2.11]

### Changed

Preserve streaming document ingestion and report failed documents instead of silently completing. Check for a vector collection before querying it on the first import, so lazy vector-table creation does not break initial ingestion. Add contributor, security and OpenSSF evidence documentation and source-bound human release notes.

### Upgrade

Keep existing PostgreSQL/pgvector data and use the documented integration-test environment before rollout. The first-ingestion fix does not require deleting collections or re-embedding existing documents. Review failed-document results and retry the affected source after fixing its input.

### Security

Retain the pinned FCC source and hash-locked runtime/build dependencies. This update does not claim a new application vulnerability fix; it validates release change notes against the exact packaged source and requires explicit upgrade/security guidance.

## [0.2.10] - 2026-10-04

### Changed
- Build RAG and FCC release images on native AMD64 and ARM64 runners. Assemble
  the same two multi-platform OCI assets offline, preserving SBOM and provenance.
- Require native architecture, non-root image startup and offline HTTP smoke checks
  before PR merge and release publication. Record exact source, run attempt,
  image configuration, filesystem digests and toolchain evidence with the assets.

## [0.2.5] - 2026-08-25

### Fixed
- Ingestion: batch vector store inserts (5000 texts per `aadd_texts` call) to
  stay under asyncpg's 32767 statement-argument limit — corpora above ~6553
  chunks failed only after the full embedding pass (#56).
- Ingestion: roll back the poisoned session before recording a failed run so
  the `ingestion_runs` audit row actually commits.

## [0.2.4] - 2026-08-25

### Added
- Ecosystem-wide corpus coverage: `PRODUCT_PAGES` widened from 6 to 18
  product families (Quattro/II, MultiPlus, Phoenix compact, Venus GX, BMV-712,
  SmartShunt, Lynx Smart BMS, BlueSolar MPPT, Orion-Tr Smart, Skylla-i,
  EV Charging Station; slugs verified against the site sitemap) and
  `COMMUNITY_QUERIES` extended with third-party ecosystem topics
  (Pylontech CAN, BYD BMS, Fronius PV, EM24 metering, MQTT topics,
  dbus services, VRM API).
- `scripts/export_projects_corpus.py`: exports READMEs + docs of every
  sibling git repo in the Victron workspace (~33 repos) into
  `data/projects/corpus.json`; `deploy.sh --with-manuals` uploads and
  ingests it as a third corpus.

### Fixed
- Ingestion is now idempotent per source file: before embedding, sources
  already present in the vector store are skipped. Re-running
  `--with-manuals` (or any ingest) no longer duplicates the whole corpus.

## [0.2.3] - 2026-08-24

### Added
- Real Victron content pipeline (the pieces v0.2.2 announced but failed to
  commit): `scripts/fetch_victron_content.py` (scrapes official English PDF
  manuals + community Discourse threads), `docs/corpus-enrichment.md`
  (from-zero runbook, validated end to end on Synology: 27 manuals → 3117
  chunks, community threads → 209 chunks), `deploy/deploy.sh --with-manuals`,
  README section.

### Fixed
- `deploy.sh --with-manuals` now serializes ingestion runs and waits for each
  run to complete before posting the next. Concurrent `/ingest` calls race on
  the DB connection pool; the losing run dies with an asyncpg connect timeout
  before processing anything. Timeout configurable via `INGEST_TIMEOUT_S`
  (default 3h per run — embedding on NAS CPU is slow).

## [0.2.2] - 2026-08-24

### Added
- `scripts/fetch_victron_content.py`: fetches real Victron content for the
  corpus — official English PDF manuals (discovered by scraping curated
  product pages, so manual versions stay current) and community threads from
  community.victronenergy.com saved as `forum_json`. Idempotent.
- `deploy/deploy.sh --with-manuals`: uploads `data/manuals` + `data/community`
  to the NAS and queues both ingestions; runbook in
  [docs/corpus-enrichment.md](docs/corpus-enrichment.md)

### Fixed
- `ChunkingStrategy.create` wraps raw LangChain splitters (markdown /
  recursive / fixed) in an adapter exposing `chunk_documents` — the
  ingestion pipeline crashed with AttributeError and stored 0 chunks for any
  non-technical strategy (#51)
- `deploy.sh` now syncs `TAG=` into the remote `.env` on every deploy;
  previously a released tag never reached an existing deployment (#49)
- compose passes `LLM_BASE_URL` through to the api container (#50)

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
