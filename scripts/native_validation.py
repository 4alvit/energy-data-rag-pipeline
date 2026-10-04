"""Require native PR builds; delegate only to the existing release build gate."""

import argparse
import json
import os
import re
from pathlib import Path


def scope(environment, policy):
    """Recognize exactly the supported outer entry workflows and events."""
    repository = policy["repository"]
    branch = "refs/heads/" + policy["default_branch"]
    event = environment.get("GITHUB_EVENT_NAME")
    if environment.get("GITHUB_REPOSITORY") != repository:
        raise ValueError("Native validation repository differs")
    if event in {"pull_request", "merge_group"}:
        return "native"
    if (
        event in {"push", "schedule", "workflow_dispatch"}
        and environment.get("GITHUB_REF") == branch
        and environment.get("GITHUB_WORKFLOW_REF")
        == f"{repository}/.github/workflows/release-pipeline.yml@{branch}"
    ):
        return "release-gate"
    raise ValueError("Unrecognized native validation entry workflow or event")


def gate(results):
    """Missing, skipped, cancelled or failed PR matrix cells must block CI."""
    if set(results) != {"scope", "build"} or results["scope"].get("result") != "success":
        raise ValueError("Native validation scope failed or job inventory differs")
    mode = results["scope"].get("outputs", {}).get("mode")
    expected = {"native": "success", "release-gate": "skipped"}.get(mode)
    if expected is None or results["build"].get("result") != expected:
        raise ValueError("Native validation did not pass")


def emit_scope(root, environment):
    """Validate every output value before opening GitHub's workflow output file."""
    policy = json.loads((root / ".release-policy.json").read_text())
    mode = scope(environment, policy)
    version = (root / policy["version_file"]).read_text().strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Native validation requires a one-line numeric base version")
    with open(environment["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"mode={mode}\nversion={version}\n")
    return mode


def main():
    """Emit validated workflow outputs or evaluate the always-running gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["scope", "gate"])
    args = parser.parse_args()
    if args.operation == "gate":
        gate(json.loads(os.environ["RESULTS"]))
    else:
        root = Path(__file__).resolve().parents[1]
        mode = emit_scope(root, os.environ)
        print(
            "Build all four native cells"
            if mode == "native"
            else "The release pipeline requires its own native build and Release gate"
        )


if __name__ == "__main__":
    main()
