# Documentation Corpus (generated)

Generated: 2026-10-08T09:12:41+00:00
Records: 154 (~65,847 chars)

Produced by `scripts/export_docs_corpus.py` from `docs/*.md` and `README.md`.

Ingest into the RAG stack:

```bash
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"source_type":"forum_json","paths":["/data/docs-corpus/corpus.json"],
       "chunk_strategy":"technical"}'
```

Do not edit corpus.json by hand - edit docs/ and re-run the exporter.
