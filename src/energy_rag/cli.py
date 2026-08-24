"""Console entry points for energy-rag tools."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from energy_rag.config import settings
from energy_rag.ingestion.service import run_ingestion

logger = logging.getLogger("energy_rag.cli")

SOURCE_TYPES = ("pdf", "forum_html", "forum_json")


def build_ingest_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ingest command."""
    parser = argparse.ArgumentParser(
        prog="energy-rag-ingest",
        description="Ingest Victron manuals and community content into the RAG store",
    )
    parser.add_argument(
        "--source-type",
        default="pdf",
        choices=SOURCE_TYPES,
        help="Type of source material to ingest (default: pdf)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--source-dir",
        type=Path,
        help="Directory containing source files",
    )
    group.add_argument(
        "--paths",
        nargs="+",
        type=Path,
        help="One or more explicit files or directories",
    )
    parser.add_argument(
        "--chunk-strategy",
        default="technical",
        choices=["technical", "markdown", "recursive", "fixed"],
        help="Chunking strategy (default: technical)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not descend into subdirectories",
    )
    parser.add_argument(
        "--log-level",
        default=settings.log_level,
        help=f"Logging level (default: {settings.log_level})",
    )
    return parser


def ingest_cli(argv: list[str] | None = None) -> int:
    """Synchronous entry point for the energy-rag-ingest console script."""
    args = build_ingest_parser().parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    paths = args.paths if args.paths else [args.source_dir]
    missing = [p for p in paths if not p.exists()]
    if missing:
        logger.error("Source paths do not exist: %s", ", ".join(str(m) for m in missing))
        return 1

    logger.info("Starting %s ingestion from %d path(s)", args.source_type, len(paths))

    docs, chunks = asyncio.run(
        run_ingestion(
            source_type=args.source_type,
            paths=list(paths),
            chunk_strategy=args.chunk_strategy,
            recursive=not args.no_recursive,
        )
    )
    logger.info("Ingestion complete: %d documents, %d chunks", docs, chunks)
    return 0


def main() -> None:
    """Entry point wrapper that exits with the CLI status code."""
    sys.exit(ingest_cli())
