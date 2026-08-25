#!/usr/bin/env python3
"""Fetch real Victron Energy content for the RAG corpus.

Downloads, into ``data/manuals`` and ``data/community``:

1. Official English PDF manuals - discovered by scraping the product pages
   listed in PRODUCT_PAGES (so manual versions stay current without editing
   hardcoded filenames), plus the technical-documents highlights page.
2. Community threads from community.victronenergy.com (Discourse) for the
   queries in COMMUNITY_QUERIES, saved as forum_json files the ingest API
   already understands.

Idempotent: existing files are skipped, so re-running only picks up new
content. Run before ``deploy/deploy.sh --with-manuals``.

Usage:
    scripts/fetch_victron_content.py [--out data] [--community-only|--manuals-only]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.victronenergy.com"
COMMUNITY = "https://community.victronenergy.com"
UA = {"User-Agent": "Mozilla/5.0 (energy-data-rag-pipeline corpus fetcher)"}

# Product pages whose English manuals should be mirrored.
PRODUCT_PAGES = {
    "multiplus-ii-gx": f"{BASE}/inverters-chargers/multiplus-ii-gx",
    "multiplus-ii": f"{BASE}/inverters-chargers/multiplus-ii",
    "cerbo-gx": f"{BASE}/panel-systems-remote-monitoring/cerbo-gx",
    "smartsolar-mppt-rs": f"{BASE}/solar-charge-controllers/smartsolar-mppt-rs-450-tr",
    "smartsolar-250-100": f"{BASE}/solar-charge-controllers/smartsolar-250-85-250-100",
    "phoenix-inverter-smart": f"{BASE}/inverters/phoenix-inverter-smart",
}

TECH_DOCS_PAGE = f"{BASE}/support-and-downloads/technical-information"

COMMUNITY_QUERIES = [
    "ESS assistant MultiPlus-II",
    "ESS minimum state of charge",
    "DVCC settings",
    "MultiPlus-II grid code ESS",
    "SmartSolar MPPT configuration",
    "Cerbo GX generator start stop relay",
    "Venus OS node-red large",
    "Modbus TCP victron",
]

REQUEST_DELAY_S = 0.5  # be polite to victronenergy.com and the Discourse API
MANUAL_EXCLUDE = re.compile(r"certificate", re.IGNORECASE)
MANUAL_INCLUDE = re.compile(r"-pdf-en\.pdf$|manual", re.IGNORECASE)


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: int = 30) -> dict:
    return json.loads(_get(url, timeout).decode("utf-8"))


def _page_text(url: str) -> str:
    """Return the page HTML with RSC/HTML escapes resolved."""
    raw = _get(url, timeout=60).decode("utf-8", "ignore")
    txt = html.unescape(raw)
    # Next.js RSC payload also \uXXXX-escapes & etc.; the regex unescape is
    # safe here because URLs we extract are ASCII.
    txt += re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw)
    return html.unescape(txt)


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment or "")
    return html.unescape(unicodedata.normalize("NFKC", text)).strip()


def discover_manual_urls() -> list[str]:
    """Collect English-manual PDF URLs from the curated pages."""
    urls: list[str] = []
    seen: set[str] = set()
    sources = [*PRODUCT_PAGES.values(), TECH_DOCS_PAGE]
    for page in sources:
        try:
            body = _page_text(page)
        except Exception as exc:
            print(f"WARN: failed to scrape {page}: {exc}", file=sys.stderr)
            continue
        found = re.findall(r"/upload/documents/[^\"'\\\s<>]+?\.pdf", body)
        for path in sorted(set(found)):
            url = BASE + urllib.parse.quote(path, safe="/:")
            if url in seen or MANUAL_EXCLUDE.search(path):
                continue
            if not MANUAL_INCLUDE.search(path):
                continue
            seen.add(url)
            urls.append(url)
        time.sleep(REQUEST_DELAY_S)
        print(f"{page.rsplit('/', 1)[-1]}: +{len(urls)} cumulative manuals")
    return urls


def _safe_name(url: str) -> str:
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:150]


def download_manuals(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = discover_manual_urls()
    print(f"\nDownloading {len(urls)} manuals to {out_dir} ...")
    ok = skipped = failed = 0
    for i, url in enumerate(urls, 1):
        dest = out_dir / _safe_name(url)
        if dest.exists() and dest.stat().st_size > 1024:
            skipped += 1
            continue
        try:
            data = _get(url)
            if not data.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            dest.write_bytes(data)
            ok += 1
            print(f"[{i}/{len(urls)}] {dest.name} ({len(data) // 1024} KiB)")
        except Exception as exc:
            failed += 1
            print(f"[{i}/{len(urls)}] FAIL {url}: {exc}", file=sys.stderr)
        time.sleep(REQUEST_DELAY_S)
    print(f"manuals: {ok} downloaded, {skipped} cached, {failed} failed")


def _topic_posts(topic_id: int, slug: str) -> dict | None:
    data = _get_json(f"{COMMUNITY}/t/{topic_id}.json")
    posts = data.get("post_stream", {}).get("posts", [])[:15]
    if not posts:
        return None
    first = posts[0]
    answers = []
    for post in posts[1:]:
        answers.append(
            {"body": post.get("cooked", ""), "accepted": bool(post.get("accepted_answer"))}
        )
    return {
        "title": data.get("title") or first.get("topic_title", ""),
        "url": f"{COMMUNITY}/t/{slug or data.get('slug')}/{topic_id}",
        "author": (first.get("username") or "")[:120],
        "created_at": first.get("created_at", ""),
        "tags": [t for t in (data.get("tags") or [])],
        "body": first.get("cooked", ""),
        "answers": answers,
    }


def fetch_community(out_dir: Path, per_query: int = 5) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_ids: dict[int, tuple[str, str]] = {}
    for query in COMMUNITY_QUERIES:
        try:
            data = _get_json(f"{COMMUNITY}/search.json?q={urllib.parse.quote(query)}")
        except Exception as exc:
            print(f"WARN: search failed for '{query}': {exc}", file=sys.stderr)
            continue
        for topic in data.get("topics", [])[:per_query]:
            topic_ids.setdefault(topic["id"], (topic.get("slug", ""), query))
        time.sleep(REQUEST_DELAY_S)
    print(f"\nFetching {len(topic_ids)} community topics to {out_dir} ...")
    new = 0
    for topic_id, (slug, query) in sorted(topic_ids.items()):
        dest = out_dir / f"topic-{topic_id}.json"
        if dest.exists():
            continue
        try:
            post = _topic_posts(topic_id, slug)
            if post is None:
                continue
            post["search_query"] = query
            dest.write_text(
                json.dumps({"posts": [post]}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            new += 1
        except Exception as exc:
            print(f"WARN: topic {topic_id} failed: {exc}", file=sys.stderr)
        time.sleep(REQUEST_DELAY_S)
    total = len(list(out_dir.glob("*.json")))
    print(f"community: {new} new topics, {total} total")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data"), help="output root dir")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--manuals-only", action="store_true")
    group.add_argument("--community-only", action="store_true")
    args = parser.parse_args()

    if not args.community_only:
        download_manuals(args.out / "manuals")
    if not args.manuals_only:
        fetch_community(args.out / "community")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
