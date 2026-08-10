"""Forum/community post loader for HTML and JSON sources."""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


FORUM_SELECTORS = {
    "community.victronenergy.com": {
        "question": ".question-body, .post-content, .message-content",
        "answer": ".answer-body, .accepted-answer .post-content",
        "title": "h1, .question-title",
        "metadata": {
            "author": ".author-name, .username",
            "date": ".post-date, time",
            "tags": ".tags a, .label",
            "votes": ".vote-count, .upvotes",
        },
    },
    "default": {
        "question": "article, .post, .message, .content",
        "answer": ".answer, .reply, .response",
        "title": "h1, h2, .title",
        "metadata": {
            "author": ".author, .username",
            "date": "time, .date",
            "tags": ".tag, .label",
        },
    },
}


def detect_forum_type(url: str) -> str:
    """Detect forum type from URL."""
    domain = urlparse(url).netloc.lower()
    for known_domain in FORUM_SELECTORS:
        if known_domain in domain:
            return known_domain
    return "default"


def load_forum_html(file_path: Path) -> Iterator[Document]:
    """Load forum posts from local HTML file."""
    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    forum_type = detect_forum_type(file_path.name)
    selectors = FORUM_SELECTORS.get(forum_type, FORUM_SELECTORS["default"])

    # Find all question/thread containers
    threads = soup.select(selectors["question"])

    for thread in threads:
        title_elem = thread.select_one(selectors["title"])
        title = title_elem.get_text(strip=True) if title_elem else ""

        content = thread.get_text(separator="\n", strip=True)

        if not content.strip():
            continue

        # Extract metadata
        metadata = {
            "source": str(file_path),
            "source_type": "forum_html",
            "forum_type": forum_type,
            "title": title,
        }

        for key, selector in selectors["metadata"].items():
            elem = thread.select_one(selector)
            if elem:
                metadata[key] = elem.get_text(strip=True)

        # Try to find answers
        answers = thread.select(selectors["answer"])
        if answers:
            answer_texts = [a.get_text(separator="\n", strip=True) for a in answers]
            metadata["answers"] = answer_texts
            content += "\n\n--- ANSWERS ---\n\n" + "\n\n".join(answer_texts)

        yield Document(page_content=content, metadata=metadata)


def load_forum_json(file_path: Path) -> Iterator[Document]:
    """Load forum posts from JSON file (e.g., exported from Discourse/StackExchange)."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle different JSON structures
    posts = _extract_posts(data)

    for post in posts:
        content = _build_post_content(post)
        if not content.strip():
            continue

        metadata = {
            "source": str(file_path),
            "source_type": "forum_json",
            "title": post.get("title", ""),
            "url": post.get("url", ""),
            "author": post.get("author", {}).get("username", "")
            if isinstance(post.get("author"), dict)
            else post.get("author", ""),
            "created_at": post.get("created_at", post.get("date", "")),
            "tags": post.get("tags", []),
            "score": post.get("score", post.get("votes", 0)),
            "is_accepted": post.get("accepted", False),
        }

        yield Document(page_content=content, metadata=metadata)


def _extract_posts(data: dict | list) -> list[dict]:
    """Extract posts from various JSON structures."""
    if isinstance(data, list):
        return data

    # Common structures
    for key in ["posts", "topics", "questions", "items", "data", "results"]:
        if key in data and isinstance(data[key], list):
            return data[key]

    # Single post
    return [data]


def _build_post_content(post: dict) -> str:
    """Build content string from post data."""
    parts = []

    title = post.get("title", "")
    if title:
        parts.append(f"# {title}")

    body = post.get("body", post.get("content", post.get("text", "")))
    if body:
        # Clean HTML if present
        if "<" in body and ">" in body:
            soup = BeautifulSoup(body, "html.parser")
            body = soup.get_text(separator="\n", strip=True)
        parts.append(body)

    # Add answers/replies
    answers = post.get("answers", post.get("replies", []))
    if answers:
        parts.append("\n## Answers")
        for i, answer in enumerate(answers, 1):
            answer_body = answer.get("body", answer.get("content", ""))
            if answer_body:
                if "<" in answer_body and ">" in answer_body:
                    soup = BeautifulSoup(answer_body, "html.parser")
                    answer_body = soup.get_text(separator="\n", strip=True)
                accepted = " ✓" if answer.get("accepted", answer.get("is_accepted", False)) else ""
                parts.append(f"\n### Answer {i}{accepted}\n{answer_body}")

    return "\n".join(parts)


def fetch_forum_url(url: str, selectors: dict | None = None) -> Iterator[Document]:
    """Fetch and parse forum page from URL."""
    forum_type = detect_forum_type(url)
    sel = selectors or FORUM_SELECTORS.get(forum_type, FORUM_SELECTORS["default"])

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return

    soup = BeautifulSoup(response.text, "html.parser")

    title_elem = soup.select_one(sel["title"])
    title = title_elem.get_text(strip=True) if title_elem else ""

    question_elem = soup.select_one(sel["question"])
    if not question_elem:
        logger.warning("No question element found for %s", url)
        return

    content = question_elem.get_text(separator="\n", strip=True)

    metadata = {
        "source": url,
        "source_type": "forum_url",
        "forum_type": forum_type,
        "title": title,
        "url": url,
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    for key, selector in sel["metadata"].items():
        elem = soup.select_one(selector)
        if elem:
            metadata[key] = elem.get_text(strip=True)

    # Get answers
    answers = soup.select(sel["answer"])
    if answers:
        answer_texts = [a.get_text(separator="\n", strip=True) for a in answers]
        metadata["answers"] = answer_texts
        content += "\n\n--- ANSWERS ---\n\n" + "\n\n".join(answer_texts)

    yield Document(page_content=content, metadata=metadata)


def load_victron_community_export(export_dir: Path) -> Iterator[Document]:
    """Load Victron community export (Discourse JSON export)."""
    for json_file in export_dir.glob("*.json"):
        try:
            yield from load_forum_json(json_file)
        except Exception as e:
            logger.error("Failed to load %s: %s", json_file, e)
