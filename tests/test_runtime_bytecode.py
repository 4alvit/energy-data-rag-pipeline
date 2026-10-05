"""Regression coverage for bytecode validation in the native RAG image smoke."""

import importlib.util
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "native_container_smoke",
    Path(__file__).resolve().parents[1] / "scripts/native_container_smoke.py",
)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.fixture
def cached_source(tmp_path):
    """Compile a real module with the same validation mode as the image."""
    source = tmp_path / "module.py"
    source.write_text("answer = 42\n")
    cache = Path(
        py_compile.compile(
            str(source),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
        )
    )
    return source, cache


def test_matching_checked_bytecode_is_accepted(cached_source):
    source, _ = cached_source
    smoke.verify_bytecode(source)


def test_changed_source_is_rejected(cached_source):
    source, _ = cached_source
    source.write_text("answer = 43\n")
    with pytest.raises(ValueError, match="Stale bytecode"):
        smoke.verify_bytecode(source)


def test_missing_bytecode_is_rejected(cached_source):
    source, cache = cached_source
    cache.unlink()
    with pytest.raises(FileNotFoundError):
        smoke.verify_bytecode(source)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [(b"\0\0\0\0", "interpreter differs"), (b"", "Truncated bytecode")],
)
def test_invalid_header_is_rejected(cached_source, replacement, message):
    source, cache = cached_source
    cache.write_bytes(replacement + cache.read_bytes()[4:] if replacement else b"")
    with pytest.raises(ValueError, match=message):
        smoke.verify_bytecode(source)


def test_unchecked_hash_is_rejected(cached_source):
    source, cache = cached_source
    data = cache.read_bytes()
    cache.write_bytes(data[:4] + (1).to_bytes(4, "little") + data[8:])
    with pytest.raises(ValueError, match="checked hashes"):
        smoke.verify_bytecode(source)


def test_compileall_converts_existing_timestamp_cache(tmp_path):
    """Force compilation must replace even an otherwise valid timestamp cache."""
    source = tmp_path / "existing.py"
    source.write_text("answer = 42\n")
    py_compile.compile(
        str(source), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP
    )
    with pytest.raises(ValueError, match="checked hashes"):
        smoke.verify_bytecode(source)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-f",
            "--invalidation-mode",
            "checked-hash",
            "-q",
            str(tmp_path),
        ],
        check=True,
        timeout=30,
    )
    smoke.verify_bytecode(source)
