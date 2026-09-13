"""Run database tests against an explicit test database or a disposable local container."""

import os
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


def run_tests(root: Path, url: str) -> None:
    """Reject a production database URL before pytest can create or drop tables."""
    parsed = urlparse(url)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != "/energy_rag_test"
    ):
        raise SystemExit("Tests require a loopback PostgreSQL database named energy_rag_test")
    subprocess.run(
        ["uv", "run", "--locked", "pytest", "--cov=src/energy_rag", "--cov-report=xml"],
        cwd=root,
        env={**os.environ, "TEST_DATABASE_URL": url, "DATABASE_URL": url},
        check=True,
    )


def main() -> None:
    """Provision PostgreSQL without static container names or occupied host ports."""
    root = Path(__file__).resolve().parents[1]
    if url := os.environ.get("TEST_DATABASE_URL"):
        run_tests(root, url)
        return
    host = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], text=True
    ).strip()
    host = os.environ.get("DOCKER_HOST", host)
    if not host.startswith(("unix://", "npipe://")):
        raise SystemExit("The disposable test database requires a local Docker endpoint")
    name = "ci-energy-rag-" + uuid.uuid4().hex[:12]
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_DB=energy_rag_test",
            "--env",
            "POSTGRES_USER=rag",
            "--env",
            "POSTGRES_PASSWORD=testpass",
            "pgvector/pgvector:pg16",
        ],
        check=True,
    )
    try:
        deadline = time.monotonic() + 90
        while subprocess.run(
            ["docker", "exec", name, "pg_isready", "-U", "rag", "-d", "energy_rag_test"],
            capture_output=True,
            check=False,
        ).returncode:
            if time.monotonic() >= deadline:
                raise SystemExit("Disposable PostgreSQL did not become ready within 90 seconds")
            time.sleep(2)
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                name,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "rag",
                "-d",
                "energy_rag_test",
            ],
            input=(root / "sql/init.sql").read_bytes(),
            check=True,
        )
        mapping = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip()
        port = int(mapping.rsplit(":", 1)[1])
        run_tests(root, f"postgresql+asyncpg://rag:testpass@127.0.0.1:{port}/energy_rag_test")
    finally:
        subprocess.run(["docker", "rm", "--force", "--volumes", name], check=True)


if __name__ == "__main__":
    main()
