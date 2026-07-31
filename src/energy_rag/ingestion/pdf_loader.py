"""PDF document loader for Victron manuals."""

import hashlib
import logging
from collections.abc import Iterator
from pathlib import Path

import fitz  # PyMuPDF
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def extract_pdf_metadata(doc: fitz.Document, file_path: Path) -> dict:
    """Extract metadata from PDF document."""
    metadata = doc.metadata or {}
    return {
        "source": str(file_path),
        "source_type": "pdf",
        "title": metadata.get("title", file_path.stem),
        "author": metadata.get("author", ""),
        "subject": metadata.get("subject", ""),
        "creator": metadata.get("creator", ""),
        "producer": metadata.get("producer", ""),
        "creation_date": metadata.get("creationDate", ""),
        "modification_date": metadata.get("modDate", ""),
        "page_count": doc.page_count,
        "file_size": file_path.stat().st_size,
        "file_hash": _compute_file_hash(file_path),
    }


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_pdf_pages(file_path: Path) -> Iterator[Document]:
    """Load PDF and yield one Document per page with metadata."""
    doc = fitz.open(file_path)
    file_metadata = extract_pdf_metadata(doc, file_path)

    try:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = page.get_text("text")

            if not text.strip():
                continue

            # Extract tables as markdown
            tables = page.find_tables()
            table_markdown = ""
            for table in tables:
                table_markdown += "\n" + table.to_markdown() + "\n"

            content = text + table_markdown

            page_metadata = {
                **file_metadata,
                "page_number": page_num + 1,
                "chunk_type": "page",
            }

            yield Document(page_content=content, metadata=page_metadata)
    finally:
        doc.close()


def load_pdf_as_markdown(file_path: Path) -> Iterator[Document]:
    """Load PDF and convert to markdown preserving structure."""
    doc = fitz.open(file_path)
    file_metadata = extract_pdf_metadata(doc, file_path)

    try:
        for page_num in range(doc.page_count):
            page = doc[page_num]

            # Get text with formatting hints
            blocks = page.get_text("dict")["blocks"]
            markdown_lines = []

            for block in blocks:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        text = span["text"]
                        flags = span["flags"]

                        # Bold
                        if flags & 2**4:
                            text = f"**{text}**"
                        # Italic
                        if flags & 2**1:
                            text = f"*{text}*"

                        line_text += text

                    if line_text.strip():
                        markdown_lines.append(line_text)

            content = "\n".join(markdown_lines)

            if not content.strip():
                continue

            page_metadata = {
                **file_metadata,
                "page_number": page_num + 1,
                "chunk_type": "markdown_page",
            }

            yield Document(page_content=content, metadata=page_metadata)
    finally:
        doc.close()


def load_victron_manual(file_path: Path) -> list[Document]:
    """Load Victron manual with product detection from filename/content."""
    documents = list(load_pdf_as_markdown(file_path))

    # Detect product from filename
    product = _detect_product(file_path.name, documents)

    # Detect doc type
    doc_type = _detect_doc_type(file_path.name, documents)

    for doc in documents:
        doc.metadata.update({
            "product": product,
            "doc_type": doc_type,
        })

    return documents


def _detect_product(filename: str, documents: list[Document]) -> str:
    """Detect Victron product from filename and content."""
    filename_lower = filename.lower()

    products = [
        "MultiPlus", "MultiPlus-II", "Quattro", "EasySolar", "EasyPlus",
        "Cerbo GX", "Color Control GX", "Venus GX", "Octo GX",
        "SmartSolar", "BlueSolar", "MPPT",
        "BMV-700", "BMV-712", "SmartShunt", "Lynx Shunt",
        "Phoenix Inverter", "Phoenix Charger",
        "Skylla-i", "Skylla-TG",
        "BatteryProtect", "BatteryMonitor",
        "ESS", "Energy Storage System",
    ]

    for product in products:
        if product.lower() in filename_lower:
            return product

    # Check content
    content_sample = " ".join(d.page_content[:500] for d in documents[:3]).lower()
    for product in products:
        if product.lower() in content_sample:
            return product

    return "Unknown"


def _detect_doc_type(filename: str, documents: list[Document]) -> str:
    """Detect document type from filename."""
    filename_lower = filename.lower()

    if any(kw in filename_lower for kw in ["manual", "user guide", "instruction"]):
        return "user_manual"
    if any(kw in filename_lower for kw in ["datasheet", "data sheet", "spec"]):
        return "datasheet"
    if any(kw in filename_lower for kw in ["quick start", "quickstart", "install"]):
        return "quick_start"
    if any(kw in filename_lower for kw in ["firmware", "changelog", "release"]):
        return "firmware_notes"

    return "manual"