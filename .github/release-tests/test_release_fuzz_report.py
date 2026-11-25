# Vendored release toolkit; change the toolkit source, then render again.
# ruff: noqa
# mypy: ignore-errors
# pylint: skip-file
# fmt: off
"""Accept the RC fuzz report that an earlier attempt of the same run produced."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SPEC = importlib.util.spec_from_file_location("release_fuzz", SCRIPTS / "release_fuzz.py")
fuzz = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fuzz)

MANIFEST = {
    "schema": 1,
    "language": "go",
    "setup": [],
    "targets": [{"name": "parse", "engine": "go", "command": ["true"], "seconds": 1}],
}


class FuzzReportAttemptTests(unittest.TestCase):
    """A failed-only rerun keeps the campaign of the attempt that ran it."""

    def setUp(self):
        # pylint: disable-next=consider-using-with
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.root / ".github").mkdir()
        raw = json.dumps(MANIFEST).encode()
        (self.root / fuzz.MANIFEST).write_bytes(raw)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.report = {
            "schema": 1,
            "repository": "owner/project",
            "source_sha": "a" * 40,
            "run_id": 7,
            "run_attempt": 1,
            "channel": "rc",
            "private": False,
            "network": "isolated",
            "status": "passed",
            "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "targets": [{"name": "parse", "seconds": 1, "exit_code": 0}],
        }

    def verify(self, attempt=2):
        (self.stage / fuzz.REPORT).write_bytes(json.dumps(self.report).encode())
        fuzz.verify_report(self.stage, self.root, "owner/project", "a" * 40, 7, attempt)

    def test_earlier_attempt_report_of_the_same_run_is_accepted(self):
        self.verify()

    def test_later_attempt_another_run_or_source_is_rejected(self):
        for changed in (
            {"run_attempt": 3},
            {"run_id": 8},
            {"source_sha": "b" * 40},
            {"repository": "other/project"},
        ):
            with self.subTest(changed=changed):
                self.report.update(changed)
                with self.assertRaisesRegex(ValueError, "identity or outcome"):
                    self.verify()
                self.report.update(
                    {
                        "run_attempt": 1,
                        "run_id": 7,
                        "source_sha": "a" * 40,
                        "repository": "owner/project",
                    }
                )


if __name__ == "__main__":
    unittest.main()
