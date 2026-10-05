"""Offline native image checks; RAG model/database startup is deliberately excluded."""

import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def require(condition, message):
    """Keep verification active even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def verify_bytecode(source):
    """Reject missing, incompatible, unchecked or stale precompiled module caches."""
    cache = Path(importlib.util.cache_from_source(str(source)))
    data = cache.read_bytes()
    require(len(data) >= 16, "Truncated bytecode header")
    require(data[:4] == importlib.util.MAGIC_NUMBER, "Bytecode interpreter differs")
    require(int.from_bytes(data[4:8], "little") == 3, "Bytecode must use checked hashes")
    require(data[8:16] == importlib.util.source_hash(source.read_bytes()), "Stale bytecode")


def verify_packaged_bytecode():
    """Check representative heavy dependencies and the application before importing."""
    for distribution, relative in (
        ("sentence-transformers", "sentence_transformers/__init__.py"),
        ("sentence-transformers", "sentence_transformers/sparse_encoder/__init__.py"),
        ("langchain-text-splitters", "langchain_text_splitters/__init__.py"),
        ("transformers", "transformers/__init__.py"),
    ):
        source = Path(importlib.metadata.distribution(distribution).locate_file(relative))
        verify_bytecode(source)
    verify_bytecode(Path("/app/src/energy_rag/api/main.py"))


def response(port, path):
    """Only contact the server in this network-isolated container."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as reply:
        require(reply.status == 200, "Unexpected smoke HTTP status")
        return json.load(reply)


def main():
    """Validate packaged imports, console entrypoints and bounded real HTTP responses."""
    product, arch, version = sys.argv[1:]
    require(arch in {"amd64", "arm64"} and product in {"rag", "fcc"}, "Unexpected smoke cell")
    require(platform.system() == "Linux", "Container must be Linux")
    require(
        platform.machine() == {"amd64": "x86_64", "arm64": "aarch64"}[arch],
        "Container is not native",
    )
    require(os.getuid() == 1000, "Container must run as its non-root default user")
    if product == "rag":
        require(
            importlib.metadata.version("energy-rag-pipeline") == version,
            "Installed RAG version differs",
        )
        require(not os.access("/app/src", os.W_OK), "RAG root filesystem must be read-only")
        verify_packaged_bytecode()
        for name in ("torch", "numpy", "asyncpg", "pymupdf", "energy_rag.api.main"):
            importlib.import_module(name)
        entries = tuple(
            importlib.metadata.entry_points(group="console_scripts", name="energy-rag-api")
        )
        require(
            len(entries) == 1 and callable(entries[0].load()), "RAG console entrypoint is invalid"
        )
        require(shutil.which("energy-rag-api") is not None, "RAG launcher missing from PATH")
        port, path, expected = 8000, "/health/live", "alive"
        scope = "offline-http-lifespan-disabled"
    else:
        require(shutil.which("fcc-server") is not None, "FCC launcher missing from PATH")
        subprocess.run(["fcc-server", "--version"], check=True, timeout=30, stdout=sys.stderr)
        port, path, expected = 8082, "/health", "healthy"
        scope = "offline-default-server"
    deadline = time.monotonic() + 90
    while True:
        try:
            value = response(port, path)
            require(value.get("status") == expected, "Application liveness response differs")
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    if product == "rag":
        document = response(port, "/openapi.json")
        require(
            document["info"]["version"] == version and "/health/live" in document["paths"],
            "Packaged OpenAPI identity differs",
        )
    print(
        json.dumps(
            {
                "product": product,
                "architecture": arch,
                "uid": os.getuid(),
                "scope": scope,
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
