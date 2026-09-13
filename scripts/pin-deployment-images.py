#!/usr/bin/env python3
"""Pin the approved API/MCP and FCC digests before any Kubernetes apply."""

import json
import re
import sys
from pathlib import Path

import yaml


def pin(evidence: Path, kustomization: Path, version: str) -> None:
    data = json.loads(evidence.read_text())
    if (
        data.get("repository") != "4alvit/energy-data-rag-pipeline"
        or data.get("tag") != "v" + version
    ):
        raise ValueError("Deployment evidence does not match this stable release")
    images = []
    for name in ("ghcr.io/4alvit/energy-data-rag-pipeline", "ghcr.io/4alvit/free-claude-code"):
        ref = data.get("images", {}).get(name, "")
        if not re.fullmatch(re.escape(name) + r"@sha256:[0-9a-f]{64}", ref):
            raise ValueError("Missing approved immutable digest for " + name)
        images.append({"name": name, "newName": name, "digest": ref.split("@", 1)[1]})
    config = yaml.safe_load(kustomization.read_text())
    config["images"] = images
    kustomization.write_text(yaml.safe_dump(config, sort_keys=False))


if __name__ == "__main__":
    pin(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
