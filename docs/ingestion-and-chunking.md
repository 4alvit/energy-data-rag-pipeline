# Ingestion & Chunking

## Sources

### PDF manuals — `source_type: pdf`

`energy_rag/ingestion/pdf_loader.py` (PyMuPDF):

- `load_victron_manual(path)` → page-wise documents with Victron metadata.
- `load_pdf_pages(path)` → one Document per page.
- `load_pdf_as_markdown(path)` → markdown-converted text.
- `ingest_pdf_directory(dir, recursive=True)` via the pipeline.

Metadata: `source`, `doc_type="manual"`, `product` / `product_line`
(parsed from filename/title where possible), `page_number`, `title`.

### Forum HTML — `source_type: forum_html`

BeautifulSoup with per-engine CSS selectors
(`FORUM_SELECTORS` in `forum_loader.py`). Known engine:
`community.victronenergy.com`; everything else uses the default selector set.
Answers are appended to the content and mirrored into `metadata.answers`.

### Forum JSON — `source_type: forum_json`

Expects a **single JSON document** containing an array of posts, or an object
with one of the keys: `posts`, `topics`, `questions`, `items`, `data`,
`results`. Each post accepts:

```json
{
  "title": "MultiPlus-II ESS no grid feed-in",
  "body": "markdown or HTML text ...",
  "url": "https://community.victronenergy.com/questions/123/...",
  "author": "mvader",
  "created_at": "2025-11-02",
  "tags": ["ess", "multiplus-II"],
  "score": 12,
  "accepted": true,
  "answers": [{"body": "...", "accepted": false}]
}
```

HTML in `body`/`answers` is stripped automatically. This is also the format
produced by [`scripts/export_docs_corpus.py`](../scripts/export_docs_corpus.py)
for the project's own documentation corpus.

## Chunking strategies (`--chunk-strategy`)

| Strategy | Behavior |
|---|---|
| `technical` *(default)* | Markdown header split (h1–h4) preserving hierarchy; falls back to recursive split when a chunk/document has no headers. Annotates chunks with `h1..h4`, `chunk_method`. |
| `markdown` | Pure `MarkdownHeaderTextSplitter`. |
| `recursive` | `RecursiveCharacterTextSplitter` on `\n\n` → `\n` → `. ` → space. |
| `fixed` | Character-window splitting. |

Sizing from `CHUNK_SIZE` (1000) and `CHUNK_OVERLAP` (200).

## Metadata contract

Every stored chunk carries JSONB `metadata`. Fields used by retrieval,
filters and citations:

| Field | Example | Set by |
|---|---|---|
| `source` | `/data/manuals/multiplus-ii.pdf` | all loaders |
| `source_type` | `pdf` \| `forum_html` \| `forum_json` | loaders |
| `title` | `MultiPlus-II GX 48/3000/35-32 Manual` | loaders |
| `product` | `MultiPlus-II` | pdf loader heuristics |
| `section_title` | `ESS settings` | technical/markdown chunkers |
| `page_number` | `42` | pdf loader |
| `url` | community thread URL | forum loaders |

Filter example: `{"filters": {"product": "MultiPlus-II"}}`.

## Running ingestion

```bash
# Via REST (paths are container paths; ./data is mounted at /data)
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"source_type":"pdf","paths":["/data/manuals"]}'

# Via CLI inside the api container
docker compose exec api energy-rag-ingest --source-type pdf --source-dir /data/manuals

# Ingest this repo's own docs corpus
docker compose exec api energy-rag-ingest --source-type forum_json \
  --paths /data/docs-corpus/corpus.json --chunk-strategy recursive
```

Each run is tracked in `ingestion_runs` with status, counters and error text.

## Re-embedding after a model change

Embeddings live in `documents.embedding VECTOR(384)`. Switching
`EMBEDDING_MODEL` to another dimension requires:

```sql
ALTER TABLE documents ALTER COLUMN embedding TYPE vector(768);
DROP INDEX documents_embedding_idx;
CREATE INDEX documents_embedding_idx ON documents
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

…and a full re-ingestion so every chunk is re-embedded.
