"""Exercise native smoke contracts with real Python entrypoint collection semantics."""

import contextlib
import importlib.metadata
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import native_container_smoke as smoke


class NativeSmokeTest(unittest.TestCase):
    """The runtime entrypoint check must work on supported Python 3.12+."""

    def test_rag_smoke_uses_real_entrypoints_collection(self):
        entries = importlib.metadata.EntryPoints(
            [
                importlib.metadata.EntryPoint(
                    name="energy-rag-api", value="energy_rag.api.main:main", group="console_scripts"
                )
            ]
        )
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["smoke", "rag", "arm64", "9.8.7"]),
            mock.patch.object(smoke.platform, "system", return_value="Linux"),
            mock.patch.object(smoke.platform, "machine", return_value="aarch64"),
            mock.patch.object(smoke.os, "getuid", return_value=1000),
            mock.patch.object(smoke.importlib.metadata, "version", return_value="9.8.7"),
            mock.patch.object(smoke.importlib.metadata, "entry_points", return_value=entries),
            mock.patch.object(importlib.metadata.EntryPoint, "load", return_value=lambda: None),
            mock.patch.object(smoke.importlib, "import_module"),
            mock.patch.object(smoke.shutil, "which", return_value="/app/.venv/bin/energy-rag-api"),
            mock.patch.object(
                smoke,
                "response",
                side_effect=[
                    {"status": "alive"},
                    {"info": {"version": "9.8.7"}, "paths": {"/health/live": {}}},
                ],
            ),
            contextlib.redirect_stdout(output),
        ):
            smoke.main()
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "product": "rag",
                "architecture": "arm64",
                "uid": 1000,
                "scope": "offline-http-lifespan-disabled",
                "status": "passed",
            },
        )


if __name__ == "__main__":
    unittest.main()
