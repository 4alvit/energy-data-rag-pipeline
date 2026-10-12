# Documentation Corpus (generated)

Generated: 2026-10-12T20:52:16+00:00
Records: 162 (~74,205 chars)

Produced by `scripts/export_docs_corpus.py` from `docs/*.md` and `README.md`.

From the repository root, stage the export under `./data` (mounted at
`/data` in the Compose API container), then ingest into the RAG stack:

```bash
mkdir -p data/docs-corpus
cp docs-corpus/corpus.json data/docs-corpus/corpus.json
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"forum_json","paths":["/data/docs-corpus/corpus.json"],
       "chunk_strategy":"technical"}'
```

Do not edit corpus.json by hand - edit docs/ and re-run the exporter.
