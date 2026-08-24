#!/usr/bin/env python3
"""Export project documentation into a RAG-ready corpus.

Reads docs/*.md (+ root README.md), splits them into titled sections and
writes:

- docs-corpus/corpus.json   - array of post objects in the exact shape the
                              forum_json loader accepts (ingest via
  POST /ingest {"source_type": "forum_json", "paths": [...]}).
- docs-corpus/README.md     - provenance & usage notes.

Stdlib only; safe to run anywhere.
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
OUT_DIR = REPO_ROOT / "docs-corpus"

GITHUB_BASE = "https://github.com/4alvit/energy-data-rag-pipeline/blob/main"
DOC_TYPE_TAG = "project-docs"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading_path, body) sections on h1/h2 boundaries."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("", text.strip())]

    sections: list[tuple[str, str]] = []
    preamble_end = matches[0].start()
    if text[:preamble_end].strip():
        sections.append(("", text[:preamble_end].strip()))

    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2)
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        # Build hierarchical heading path from preceding headings of the section
        parents = []
        for prev in reversed(matches[:i]):
            prev_level = len(prev.group(1))
            if prev_level < level:
                parents.insert(0, prev.group(2))
                level = prev_level
        heading = " > ".join([*parents, title])
        if body or heading:
            sections.append((heading, body))
    return sections


def load_source_files() -> list[Path]:
    """Collect documentation files in a stable order."""
    files = []
    if DOCS_DIR.is_dir():
        files.extend(sorted(p for p in DOCS_DIR.glob("*.md") if p.name != "corpus.json"))
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    return files


def build_records() -> list[dict]:
    """Convert every documentation section into a corpus record."""
    records = []
    for path in load_source_files():
        rel = path.relative_to(REPO_ROOT)
        doc_title = next(
            (
                line.lstrip("# ").strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("# ")
            ),
            path.stem,
        )
        for heading, body in split_sections(path.read_text(encoding="utf-8")):
            if not body:
                continue
            if not heading:
                title = doc_title
            elif heading == doc_title or heading.startswith(doc_title + " > "):
                title = heading
            else:
                title = f"{doc_title} > {heading}"
            records.append(
                {
                    "title": title,
                    "body": body,
                    "url": f"{GITHUB_BASE}/{rel.as_posix()}",
                    "author": DOC_TYPE_TAG,
                    "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "tags": [
                        DOC_TYPE_TAG,
                        rel.stem,
                        *(part.lower().replace(" ", "-") for part in heading.split(" > ") if part),
                    ][:8],
                    "score": 10,
                    "accepted": True,
                }
            )
    return records


def main() -> int:
    if not DOCS_DIR.is_dir():
        print(f"error: {DOCS_DIR} not found", file=sys.stderr)
        return 1

    records = build_records()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    corpus_path = OUT_DIR / "corpus.json"
    corpus_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    total_chars = sum(len(r["body"]) for r in records)
    (OUT_DIR / "README.md").write_text(
        "\n".join(
            [
                "# Documentation Corpus (generated)",
                "",
                f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
                f"Records: {len(records)} (~{total_chars:,} chars)",
                "",
                "Produced by `scripts/export_docs_corpus.py` from `docs/*.md` and `README.md`.",
                "",
                "Ingest into the RAG stack:",
                "",
                "```bash",
                "curl -X POST http://localhost:8000/ingest \\",
                "  -H 'Content-Type: application/json' \\",
                '  -d \'{"source_type":"forum_json","paths":["/data/docs-corpus/corpus.json"],',
                '       "chunk_strategy":"technical"}\'',
                "```",
                "",
                "Do not edit corpus.json by hand - edit docs/ and re-run the exporter.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(records)} records ({total_chars:,} chars) -> {corpus_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
