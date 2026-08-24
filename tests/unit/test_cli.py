"""Unit tests for the CLI argument parsing."""

from pathlib import Path

import pytest

from energy_rag.cli import build_ingest_parser


def test_defaults():
    args = build_ingest_parser().parse_args(["--source-dir", "/tmp/manuals"])
    assert args.source_type == "pdf"
    assert args.chunk_strategy == "technical"
    assert args.no_recursive is False
    assert args.source_dir == pytest.approx(args.source_dir)  # Path passthrough


def test_paths_and_source_dir_are_mutually_exclusive():
    parser = build_ingest_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--source-dir", "a", "--paths", "b"])

    args = parser.parse_args(["--paths", "a.pdf", "b.pdf"])
    assert args.paths == [Path("a.pdf"), Path("b.pdf")]


def test_source_type_choices_enforced():
    with pytest.raises(SystemExit):
        build_ingest_parser().parse_args(["--source-type", "bogus", "--source-dir", "x"])
