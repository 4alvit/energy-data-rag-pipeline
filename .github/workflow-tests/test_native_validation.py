"""Keep native validation mandatory for PRs and merge queues without duplicate releases."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_validation as native
import workflow_contracts as contracts


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=contracts.UniqueKeyLoader
    )


class NativeValidationTest(unittest.TestCase):
    """Verify event policy and the actual required gate dependency graph."""

    def setUp(self):
        self.policy = json.loads((ROOT / ".release-policy.json").read_text())
        self.env = {
            "GITHUB_REPOSITORY": self.policy["repository"],
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": self.policy["repository"]
            + "/.github/workflows/release-pipeline.yml@refs/heads/main",
        }

    def test_pull_request_and_merge_group_require_real_native_build(self):
        for event in ("pull_request", "merge_group"):
            with self.subTest(event=event):
                self.assertEqual(
                    native.scope({**self.env, "GITHUB_EVENT_NAME": event}, self.policy), "native"
                )

    def test_only_known_release_events_delegate_to_release_gate(self):
        for event in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertEqual(
                    native.scope({**self.env, "GITHUB_EVENT_NAME": event}, self.policy),
                    "release-gate",
                )

    def test_wrong_repository_workflow_ref_or_unknown_event_fails(self):
        source = {**self.env, "GITHUB_EVENT_NAME": "workflow_dispatch"}
        for key, value in (
            ("GITHUB_REPOSITORY", "attacker/repo"),
            ("GITHUB_REF", "refs/heads/feature"),
            (
                "GITHUB_WORKFLOW_REF",
                self.policy["repository"] + "/.github/workflows/quality-gate.yml@refs/heads/main",
            ),
            ("GITHUB_EVENT_NAME", "workflow_run"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.scope({**source, key: value}, self.policy)

    def test_native_gate_requires_successful_build_and_scope(self):
        result = {
            "scope": {"result": "success", "outputs": {"mode": "native"}},
            "build": {"result": "success"},
        }
        native.gate(result)
        for job in ("scope", "build"):
            for status in ("skipped", "failure", "cancelled", "timed_out", None):
                changed = copy.deepcopy(result)
                changed[job]["result"] = status
                with self.subTest(job=job, status=status), self.assertRaises(ValueError):
                    native.gate(changed)
        for job in result:
            with self.subTest(missing=job), self.assertRaises(ValueError):
                native.gate({key: value for key, value in result.items() if key != job})

    def test_gate_allows_skip_only_after_proven_release_scope(self):
        result = {
            "scope": {"result": "success", "outputs": {"mode": "release-gate"}},
            "build": {"result": "skipped"},
        }
        native.gate(result)
        for mode in ("", "unknown", None, "native"):
            changed = copy.deepcopy(result)
            changed["scope"]["outputs"]["mode"] = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                native.gate(changed)

    def test_invalid_version_cannot_inject_a_delegated_scope_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".release-policy.json").write_text(json.dumps(self.policy))
            output = root / "outputs"
            environment = {
                **self.env,
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_OUTPUT": str(output),
            }
            for version in (
                "0.2.10\nmode=release-gate",
                "0.2.10-beta.1",
                "",
                "1.2.3\nversion=9.9.9",
            ):
                (root / self.policy["version_file"]).write_text(version)
                with self.subTest(version=version), self.assertRaises(ValueError):
                    native.emit_scope(root, environment)
                self.assertFalse(output.exists())
            (root / self.policy["version_file"]).write_text("9.8.7\n")
            self.assertEqual(native.emit_scope(root, environment), "native")
            self.assertEqual(output.read_text(), "mode=native\nversion=9.8.7\n")

    def test_policy_and_generic_gate_include_native_validator(self):
        self.assertIn("native-validation.yml", self.policy["validation_workflows"])
        quality = workflow("quality-gate.yml")
        self.assertIn("pull_request", quality["on"])
        self.assertIn("merge_group", quality["on"])
        jobs = quality["jobs"]
        validators = [
            key
            for key, value in jobs.items()
            if value.get("uses") == "./.github/workflows/native-validation.yml"
        ]
        self.assertEqual(len(validators), 1)
        self.assertIn(validators[0], jobs["gate"]["needs"])
        self.assertNotIn("continue-on-error", jobs[validators[0]])

    def test_native_gate_and_offline_assembly_cannot_skip_failed_cells(self):
        jobs = workflow("native-validation.yml")["jobs"]
        self.assertEqual(set(jobs["gate"]["needs"]), {"scope", "build"})
        self.assertEqual(jobs["gate"]["if"], "${{ always() }}")
        self.assertEqual(jobs["build"]["uses"], "./.github/workflows/release-build.yml")
        self.assertEqual(jobs["build"]["if"], "${{ needs.scope.outputs.mode == 'native' }}")
        build = workflow("release-build.yml")["jobs"]
        self.assertEqual(set(build), {"native", "package"})
        self.assertEqual(build["package"]["needs"], "native")
        self.assertNotIn("if", build["package"])
        self.assertNotIn("if", build["native"])
        self.assertNotIn("continue-on-error", build["native"])
        self.assertEqual(
            build["native"]["strategy"]["matrix"],
            {
                "product": ["rag", "fcc"],
                "arch": ["amd64", "arm64"],
                "include": [
                    {"arch": "amd64", "runner": "ubuntu-24.04"},
                    {"arch": "arm64", "runner": "ubuntu-24.04-arm"},
                ],
            },
        )
        self.assertEqual(build["native"]["runs-on"], "${{ matrix.runner }}")
        self.assertNotIn("qemu", json.dumps(build).lower())

    def test_downloads_are_exact_current_attempt_current_run_cells(self):
        jobs = workflow("release-build.yml")["jobs"]
        downloads = [
            step["with"]
            for step in jobs["package"]["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        ]
        expected = [
            {
                "name": f"native-cell-{product}-{arch}-attempt-${{{{ github.run_attempt }}}}",
                "path": f"native-inputs/{product}-{arch}",
            }
            for product in ("rag", "fcc")
            for arch in ("amd64", "arm64")
        ]
        self.assertEqual(downloads, expected)
        uploads = [
            step["with"]
            for job in jobs.values()
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact@")
        ]
        self.assertEqual(len(uploads), 2)
        for upload in uploads:
            self.assertIn("${{ github.run_attempt }}", upload["name"])
            self.assertEqual(upload["if-no-files-found"], "error")
            self.assertNotIn("overwrite", upload)

    def test_release_owned_build_remains_a_required_publication_dependency(self):
        release = workflow("release-pipeline.yml")
        self.assertEqual(set(release["on"]), {"push", "schedule", "workflow_dispatch"})
        jobs = release["jobs"]
        self.assertEqual(jobs["build"]["uses"], "./.github/workflows/release-build.yml")
        self.assertEqual(set(jobs["gate"]["needs"]), {"prepare", "checks", "build"})
        self.assertIn("gate", jobs["candidate"]["needs"])
        gate_script = jobs["gate"]["steps"][0]["run"]
        self.assertIn("dict.fromkeys(('prepare', 'checks', 'build'), 'success')", gate_script)
        self.assertIn("raise SystemExit", gate_script)


if __name__ == "__main__":
    unittest.main()
