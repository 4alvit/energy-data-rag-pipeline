#!/usr/bin/env python3
"""Export the sibling Victron projects' documentation into a RAG corpus.

Walks the parent directory (~/victron by default), and for every git repo
collects README.md, docs/*.md and CLAUDE.md, splits them into titled sections
and writes data/projects/corpus.json in the exact shape the forum_json loader
accepts (ingest via POST /ingest {"source_type": "forum_json", ...}).

With --include-code also emits one record per source file (.py/.go/.ts/.tsx/
.js/.sh/.yaml/.yml), so the RAG can answer implementation questions with
citations pointing at real files. Adds ~5 MB / ~1000 files for this workspace.

This repo is skipped - its own docs already ship as docs-corpus/corpus.json.

Stdlib only; safe to run anywhere.

Usage:
    scripts/export_projects_corpus.py [--root ~/victron] [--out data/projects]
                                      [--include-code]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF = REPO_ROOT.name
OUT_DIR = REPO_ROOT / "data" / "projects"

MAX_FILE_BYTES = 200_000  # skip generated/vendored monsters
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

DOC_FILES = ("README.md", "CLAUDE.md")

CODE_EXTS = {".py", ".go", ".ts", ".tsx", ".js", ".sh", ".yaml", ".yml"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "vendor",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    "htmlcov",
    "coverage",
    ".next",
    ".terraform",
}


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


def github_base(repo: Path) -> str | None:
    """https://github.com/<owner>/<name>/blob/main, or None if no origin."""
    try:
        url = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        return None
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return f"https://github.com/{match.group(1)}/blob/main" if match else None


def load_files(repo: Path) -> list[Path]:
    files = [repo / name for name in DOC_FILES]
    docs_dir = repo / "docs"
    if docs_dir.is_dir():
        files.extend(sorted(docs_dir.glob("*.md")))
    return [f for f in files if f.is_file() and f.stat().st_size <= MAX_FILE_BYTES]


def load_code_files(repo: Path) -> list[Path]:
    """All source/config files worth indexing, junk dirs pruned."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix in CODE_EXTS and path.stat().st_size <= MAX_FILE_BYTES:
                out.append(path)
    return sorted(out)


def code_record(repo: Path, base: str, path: Path) -> dict:
    rel = path.relative_to(repo).as_posix()
    return {
        "title": f"{repo.name} > {rel}",
        "body": path.read_text(encoding="utf-8"),
        "url": f"{base}/{rel}",
        "author": "project-code",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tags": [
            "project-code",
            repo.name,
            path.suffix.lstrip("."),
            *path.relative_to(repo).parts[:-1],
        ][:8],
        "score": 10,
        "accepted": True,
    }


def build_records(root: Path, include_code: bool = False) -> list[dict]:
    records: list[dict] = []
    repos = sorted(p for p in root.iterdir() if p.is_dir() and p.name != SELF)
    for repo in repos:
        base = github_base(repo)
        if base is None:
            print(f"skip (no github origin): {repo.name}", file=sys.stderr)
            continue
        repo_docs = 0
        for path in load_files(repo):
            rel = path.relative_to(repo).as_posix()
            text = path.read_text(encoding="utf-8")
            doc_title = next(
                (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")),
                path.stem,
            )
            for heading, body in split_sections(text):
                if not body:
                    continue
                title = f"{repo.name} > {doc_title}"
                if heading and heading != doc_title:
                    title += f" > {heading}"
                records.append(
                    {
                        "title": title,
                        "body": body,
                        "url": f"{base}/{rel}",
                        "author": "project-docs",
                        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                        "tags": [
                            "victron-projects",
                            repo.name,
                            *(
                                part.lower().replace(" ", "-")
                                for part in heading.split(" > ")
                                if part
                            ),
                        ][:8],
                        "score": 10,
                        "accepted": True,
                    }
                )
            repo_docs += 1
        code_count = 0
        if include_code:
            for path in load_code_files(repo):
                records.append(code_record(repo, base, path))
                code_count += 1
        summary = f"{repo_docs} docs"
        if include_code:
            summary += f", {code_count} code files"
        print(f"{repo.name}: {summary}")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT.parent, help="directory of sibling git repos"
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    parser.add_argument(
        "--include-code",
        action="store_true",
        help="also index source files (.py/.go/.ts/.tsx/.js/.sh/.yaml/.yml)",
    )
    args = parser.parse_args()
    if not args.root.is_dir():
        print(f"error: {args.root} not found", file=sys.stderr)
        return 1

    records = build_records(args.root, include_code=args.include_code)
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "corpus.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    chars = sum(len(r["body"]) for r in records)
    print(
        f"Wrote {len(records)} records ({chars:,} chars) from "
        f"{len({r['url'].split('/blob/')[0] for r in records})} repos -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
