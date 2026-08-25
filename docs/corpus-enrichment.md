# Corpus Enrichment: Real Victron Content

How to build a RAG corpus of **real Victron Energy content** — official PDF
manuals plus community threads — from zero, and keep it fresh.

## What gets fetched

| Source | Where | What |
|---|---|---|
| Official manuals | `data/manuals/*.pdf` | English `-pdf-en` manuals discovered by scraping curated product pages (MultiPlus-II / GX, Cerbo GX, SmartSolar MPPT RS + 250/100, Phoenix inverter) and the technical-documents page. Includes the ESS design & installation manual, VE.Bus configuration guide, Wiring Unlimited. Certificates are filtered out. |
| Community | `data/community/topic-*.json` | Threads from community.victronenergy.com (Discourse) for the queries in `COMMUNITY_QUERIES` (ESS assistant, minimum SoC, DVCC, grid codes, generator start/stop, node-red, Modbus TCP, …). Saved as `forum_json` files the ingest API already understands. |

Both lists live at the top of [`scripts/fetch_victron_content.py`](../scripts/fetch_victron_content.py)
— edit `PRODUCT_PAGES` / `COMMUNITY_QUERIES` to widen coverage. Manual
*versions* stay current automatically because URLs are scraped from the
product pages at fetch time instead of hardcoded.

## From-zero runbook

Assumes a fresh machine with this repo cloned.

### 1. Fetch content locally

```bash
python3 scripts/fetch_victron_content.py --out data
# or parts:
python3 scripts/fetch_victron_content.py --out data --manuals-only
python3 scripts/fetch_victron_content.py --out data --community-only
```

Idempotent: files that already exist are skipped, so re-running picks up only
new manuals/topics. Expect ~30+ PDFs (~50 MB) and ~30 community topics on a
first run; takes a few minutes (0.5 s delay per request, be polite).

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

This uploads `data/manuals/` → `/data/manuals` and `data/community/` →
`/data/community` on the NAS, then queues two ingestion jobs:

- pdf + `technical` chunking for manuals
- forum_json + `recursive` chunking for community threads

Ingestion runs in background; watch it:

```bash
deploy/deploy.sh logs api | grep -i ingestion
```

A full manual corpus takes several minutes on a NAS (embedding model is
CPU-bound). The `/ingest` endpoint returns immediately with a `run_id`.

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
ssh synology "cd $REMOTE_DIR && docker exec energy-rag-postgres psql -U rag -d energy_rag \
  -c 'select source_type, count(*) from chunks group by 1;'"
```

(Adjust table/column names to the current schema if they changed.)

## Refresh cadence

Victron updates manual PDFs without changing filenames. Re-run steps 1 + 3
monthly or before trusting answers about settings that changed recently.
Existing chunks are re-ingested by file hash; unchanged files cost one skip.

## Notes

- `data/` is not committed (large binaries); the fetch script is the source
  of truth for reproducing the corpus.
- FCC proxy (`fcc.env`) must be healthy for *generation*, but ingestion and
  retrieval work regardless — only `/query` answer synthesis needs the LLM.
- If victronenergy.com changes its Next.js payload format and discovery
  returns 0 manuals, fall back to adding explicit PDF URLs to
  `discover_manual_urls()` — the rest of the pipeline is unaffected.
