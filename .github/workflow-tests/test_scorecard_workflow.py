"""Keep OpenSSF publication compatible and GitHub upload fail closed."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "actions/checkout",
    "actions/upload-artifact",
    "github/codeql-action/upload-sarif",
    "ossf/scorecard-action",
    "step-security/harden-runner",
}
# The Scorecard build each pinned ossf/scorecard-action commit embeds. Bumping
# the action without recording its build here fails the pin contract, and a
# build the guard does not accept fails it as well.
SCORECARD_ACTION_BUILDS = {
    "23f22cd43608bae7a1f1fa2603d7314dee9538a5": "v5.7.0",
}


def load_guard():
    """Load the completeness guard the analysis job runs before the upload."""
    spec = importlib.util.spec_from_file_location(
        "validate_scorecard_json", ROOT / "scripts/validate_scorecard_json.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the Scorecard guard for the pin contract")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def check_scorecard_pin(workflow, versions):
    """Fail while a pinned action's Scorecard build is absent from the guard."""
    scan = next(
        step
        for step in workflow["jobs"]["scorecard"]["steps"]
        if step["uses"].startswith("ossf/scorecard-action@")
    )
    pinned = scan["uses"].split("@", 1)[1].split()[0]
    if pinned not in SCORECARD_ACTION_BUILDS:
        raise AssertionError(
            f"ossf/scorecard-action@{pinned} has no recorded Scorecard build; "
            "add it to SCORECARD_ACTION_BUILDS and to VERSIONS in "
            "scripts/validate_scorecard_json.py"
        )
    build = SCORECARD_ACTION_BUILDS[pinned]
    if build not in versions:
        raise AssertionError(
            f"ossf/scorecard-action@{pinned} embeds Scorecard {build}, which "
            "scripts/validate_scorecard_json.py would reject before the upload"
        )


def validate(workflow):
    """Apply the pinned action's publishing constraints to the real workflow."""
    assert "env" not in workflow and "defaults" not in workflow
    permissions = workflow["permissions"]
    assert permissions == "read-all" or (
        isinstance(permissions, dict) and set(permissions.values()) <= {"read", "none"}
    )
    jobs = workflow["jobs"]
    publisher = jobs["scorecard"]
    assert publisher["runs-on"] == "ubuntu-latest"
    assert not {"env", "defaults", "container", "services"} & publisher.keys()
    assert publisher["permissions"]["id-token"] == "write"
    for job_id, job in jobs.items():
        if job_id != "scorecard":
            assert job.get("permissions", {}).get("id-token") != "write"
    for step in publisher["steps"]:
        assert "run" not in step
        assert step["uses"].split("@")[0] in ALLOWED
    scan = next(s for s in publisher["steps"] if s["uses"].startswith("ossf/scorecard-action@"))
    assert scan["with"]["publish_results"] == "true"
    artifact = next(
        s for s in publisher["steps"] if s["uses"].startswith("actions/upload-artifact@")
    )
    assert set(artifact["with"]["path"].split()) == {"results.json", "results.sarif"}
    assert artifact["with"]["if-no-files-found"] == "error"
    analysis = jobs["analysis"]
    assert analysis["needs"] == "scorecard"
    steps = analysis["steps"]
    download = next(s for s in steps if s.get("uses", "").startswith("actions/download-artifact@"))
    assert download["with"] == {"name": artifact["with"]["name"]}
    guard_index = next(i for i, s in enumerate(steps) if s.get("id") == "scorecard_completeness")
    upload_index = next(
        i
        for i, s in enumerate(steps)
        if s.get("uses", "").startswith("github/codeql-action/upload-sarif@")
    )
    assert guard_index < upload_index
    assert "python3 scripts/validate_scorecard_json.py" in steps[guard_index]["run"]
    assert (
        steps[upload_index]["if"]
        == "${{ success() && steps.scorecard_completeness.outcome == 'success' }}"
    )
    assert steps[upload_index]["with"]["sarif_file"] == "results.sarif"


class ScorecardWorkflowTests(unittest.TestCase):
    """Exercise the checked-in workflow and the known unsafe arrangements."""

    def setUp(self):
        self.workflow = yaml.load(
            (ROOT / ".github/workflows/scorecards.yml").read_text(),
            Loader=yaml.BaseLoader,
        )

    def test_publishing_and_guarded_upload_contract(self):
        validate(self.workflow)

    def test_pinned_action_build_is_accepted_by_the_guard(self):
        check_scorecard_pin(self.workflow, load_guard().VERSIONS)

    def test_no_stale_build_stays_accepted_by_the_guard(self):
        versions = load_guard().VERSIONS
        check_scorecard_pin(self.workflow, versions)
        self.assertEqual(set(versions), set(SCORECARD_ACTION_BUILDS.values()))

    def test_action_bump_without_recorded_build_fails(self):
        for step in self.workflow["jobs"]["scorecard"]["steps"]:
            if step["uses"].startswith("ossf/scorecard-action@"):
                step["uses"] = "ossf/scorecard-action@" + "0" * 40
        with self.assertRaises(AssertionError) as caught:
            check_scorecard_pin(self.workflow, load_guard().VERSIONS)
        self.assertIn("SCORECARD_ACTION_BUILDS", str(caught.exception))

    def test_recorded_build_missing_from_the_guard_fails(self):
        pinned = next(
            step["uses"]
            for step in self.workflow["jobs"]["scorecard"]["steps"]
            if step["uses"].startswith("ossf/scorecard-action@")
        ).split("@", 1)[1]
        with (
            patch.dict(SCORECARD_ACTION_BUILDS, {pinned: "v5.8.0"}),
            self.assertRaises(AssertionError) as caught,
        ):
            check_scorecard_pin(self.workflow, load_guard().VERSIONS)
        self.assertIn("v5.8.0", str(caught.exception))

    def test_custom_run_in_publishing_job_is_rejected(self):
        self.workflow["jobs"]["scorecard"]["steps"].append({"run": "python3 guard.py"})
        with self.assertRaises(AssertionError):
            validate(self.workflow)

    def test_global_write_permissions_are_rejected(self):
        self.workflow["permissions"] = {"contents": "write"}
        with self.assertRaises(AssertionError):
            validate(self.workflow)

    def test_validation_job_cannot_mint_publication_identity(self):
        self.workflow["jobs"]["analysis"]["permissions"]["id-token"] = "write"
        with self.assertRaises(AssertionError):
            validate(self.workflow)

    def test_artifact_must_be_from_this_workflow_run(self):
        for step in self.workflow["jobs"]["analysis"]["steps"]:
            if step.get("uses", "").startswith("actions/download-artifact@"):
                step["with"]["run-id"] = "1234"
        with self.assertRaises(AssertionError):
            validate(self.workflow)

    def test_upload_cannot_run_without_successful_completeness_guard(self):
        for step in self.workflow["jobs"]["analysis"]["steps"]:
            if step.get("uses", "").startswith("github/codeql-action/upload-sarif@"):
                step["if"] = "always()"
        with self.assertRaises(AssertionError):
            validate(self.workflow)

    def test_scan_must_preserve_both_original_formats(self):
        for step in self.workflow["jobs"]["scorecard"]["steps"]:
            if step["uses"].startswith("actions/upload-artifact@"):
                step["with"]["path"] = "results.sarif"
        with self.assertRaises(AssertionError):
            validate(self.workflow)


if __name__ == "__main__":
    unittest.main()
