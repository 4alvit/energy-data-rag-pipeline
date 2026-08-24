"""CLI script to ingest Victron PDF manuals (thin wrapper).

The implementation lives in :mod:`energy_rag.cli`; this module is kept
for backwards compatibility with existing invocations.
"""

from energy_rag.cli import ingest_cli

if __name__ == "__main__":
    # Default to pdf source type for legacy direct invocations.
    import sys

    argv = sys.argv[1:]
    if not any(a.startswith("--source-type") or a == "--paths" for a in argv):
        argv = ["--source-type", "pdf", *argv]
    raise SystemExit(ingest_cli(argv))
