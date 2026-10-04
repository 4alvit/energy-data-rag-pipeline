"""Offline native image checks; RAG model/database startup is deliberately excluded."""

import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


def require(condition, message):
    """Keep verification active even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


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
