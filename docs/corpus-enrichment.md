# Corpus Enrichment: Real Victron Content

How to build a RAG corpus of **real Victron Energy content** — official PDF
manuals plus community threads — from zero, and keep it fresh.

## What gets fetched

| Source | Where | What |
|---|---|---|
| Official manuals | `data/manuals/*.pdf` | English `-pdf-en` manuals discovered by scraping curated product pages (MultiPlus-II/GX/800-3kVA, Quattro/II, Phoenix smart+compact, Cerbo/Venus GX, BMV-712, SmartShunt, Lynx Smart BMS, SmartSolar MPPT RS + 250/100, BlueSolar 150/35, Orion-Tr Smart, Skylla-i, EV Charging Station) and the technical-documents page. Includes the ESS design & installation manual, VE.Bus configuration guide, Wiring Unlimited, CANusb manual. Certificates are filtered out. |
| Community | `data/community/topic-*.json` | Threads from community.victronenergy.com (Discourse) for the queries in `COMMUNITY_QUERIES` — core topics (ESS assistant, minimum SoC, DVCC, grid codes, generator start/stop, node-red, Modbus TCP) plus third-party ecosystem (Pylontech CAN, BYD BMS, Fronius PV, EM24 metering, MQTT topics, dbus services, VRM API). Saved as `forum_json` files the ingest API already understands. |
| Sibling projects | `data/projects/corpus.json` | READMEs + `docs/*.md` + `CLAUDE.md` of every git repo in `~/victron` (inverter-control, inverter-monitoring, dbus-*, venus-os-*, mcp-venus-os, …), exported by [`scripts/export_projects_corpus.py`](../scripts/export_projects_corpus.py). This repo itself is skipped — its docs ship as `docs-corpus/corpus.json`. |

The Victron lists live at the top of [`scripts/fetch_victron_content.py`](../scripts/fetch_victron_content.py)
— edit `PRODUCT_PAGES` / `COMMUNITY_QUERIES` to widen coverage. Manual
*versions* stay current automatically because URLs are scraped from the
product pages at fetch time instead of hardcoded; slugs were verified against
the site sitemap.

## From-zero runbook

Assumes a fresh machine with this repo cloned.

### 1. Fetch content locally

```bash
python3 scripts/fetch_victron_content.py --out data
python3 scripts/export_projects_corpus.py            # sibling repos -> data/projects/corpus.json
# or parts:
python3 scripts/fetch_victron_content.py --out data --manuals-only
python3 scripts/fetch_victron_content.py --out data --community-only
```

Idempotent: files that already exist are skipped, so re-running picks up only
new manuals/topics. Expect ~60+ PDFs (~150 MB) and ~75 community topics after
the 0.2.4 widening; takes a few minutes (0.5 s delay per request, be polite).

### 2. Deploy the stack

```bash
deploy/deploy.sh          # TAG comes from the version file; see deploy.sh header
```

The api container mounts `$DATA_ROOT/data:/data`, so anything rsynced under
`$DATA_ROOT/data/…` appears at `/data/…` inside the container.

### 3. Upload + ingest

```bash
deploy/deploy.sh --with-manuals
```

This uploads `data/manuals/` → `/data/manuals`, `data/community/` →
`/data/community` and `data/projects/` → `/data/projects` on the NAS, then
queues three ingestion jobs, **serialized** — each waits for the previous run
to finish (concurrent ingests race on the DB pool):

- pdf + `technical` chunking for manuals
- forum_json + `recursive` chunking for community threads
- forum_json + `recursive` chunking for sibling-project docs

Ingestion is idempotent per source file: documents whose `source` metadata
is already in the vector store are skipped, so re-running only embeds new
files. Watch progress:

```bash
deploy/deploy.sh logs api | grep -i ingestion
```

A full manual corpus takes ~1.5 h on a NAS ARM CPU (embedding is
CPU-bound). The `/ingest` endpoint returns immediately with a `run_id`;
`INGEST_TIMEOUT_S` (default 3 h) caps how long deploy waits per run.

### 4. Verify retrieval

```bash
ssh synology 'curl -s -m 180 http://localhost:8010/query \
  -X POST -H "content-type: application/json" \
  -d "{\"query\":\"How do I configure the ESS assistant minimum state of charge?\",\"top_k\":3}"'
```

Expect a generated answer citing manual sections (sources list non-empty).
If sources stay empty: check `logs api` for embedding errors and confirm
chunks exist:

```bash
ssh synology 'sudo docker exec energy-rag-postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tAc \"select cmetadata->>'"'"'source_type'"'"',count(*) from langchain_pg_embedding group by 1;\""'
```

Expect rows for `pdf` (manuals) and `forum_json` (community + projects).

## Refresh cadence

Victron updates manual PDFs without changing filenames. Re-run steps 1 + 3
monthly or before trusting answers about settings that changed recently.
Ingestion skips documents whose source path is already stored — unchanged
files cost one DB query, only new/renamed files get embedded.

## Notes

- `data/` is not committed (large binaries); the fetch script is the source
  of truth for reproducing the corpus.
- FCC proxy (`fcc.env`) must be healthy for *generation*, but ingestion and
  retrieval work regardless — only `/query` answer synthesis needs the LLM.
- If victronenergy.com changes its Next.js payload format and discovery
  returns 0 manuals, fall back to adding explicit PDF URLs to
  `discover_manual_urls()` — the rest of the pipeline is unaffected.
