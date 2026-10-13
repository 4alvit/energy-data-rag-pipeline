#!/usr/bin/env python3
"""Create a guarded cache-only Deployment patch; never perform a rollout."""

import argparse
import copy
import json
import os
from pathlib import Path

MOUNTS = {
    "dependency-cache": "/runner-cache",
    "toolcache": "/opt/hostedtoolcache",
}
CACHE_LIMIT = "16Gi"
ENVIRONMENT = {
    "XDG_CACHE_HOME": "/runner-cache",
    "PIP_CACHE_DIR": "/runner-cache/pip",
    "UV_CACHE_DIR": "/runner-cache/uv",
    "RUNNER_TOOL_CACHE": "/opt/hostedtoolcache",
    "AGENT_TOOLSDIRECTORY": "/opt/hostedtoolcache",
}


def cache_patch(deployment):
    metadata, spec = deployment["metadata"], deployment["spec"]
    if (metadata["name"], metadata.get("namespace")) != ("gha-runner-fcc", "energy-rag"):
        raise ValueError("Expected energy-rag/gha-runner-fcc")
    if spec.get("replicas") != 1 or spec.get("strategy", {}).get("type") != "Recreate":
        raise ValueError("Expected one Recreate listener; drain it before applying")
    pod = spec["template"]["spec"]
    if pod.get("nodeSelector", {}).get("kubernetes.io/hostname") != "mp":
        raise ValueError("Expected mp placement")
    indexes = [i for i, item in enumerate(pod["containers"]) if item["name"] == "runner"]
    if len(indexes) != 1:
        raise ValueError("Expected one runner container")
    index = indexes[0]
    container = pod["containers"][index]
    base = f"/spec/template/spec/containers/{index}"
    changes = []
    mounts = copy.deepcopy(container.get("volumeMounts", []))
    volumes = copy.deepcopy(pod.get("volumes", []))
    for name, path in MOUNTS.items():
        for participant in [*pod["containers"], *pod.get("initContainers", [])]:
            for mount in participant.get("volumeMounts", []):
                if mount["name"] == name and mount["mountPath"] != path:
                    raise ValueError(f"Cache volume {name} is mounted outside {path}")
        expected_mount = {"name": name, "mountPath": path}
        existing_mounts = [m for m in mounts if m["mountPath"] == path]
        if existing_mounts and existing_mounts != [expected_mount]:
            raise ValueError(f"Conflicting mount at {path}")
        if not existing_mounts:
            mounts.append(expected_mount)
        matching_volumes = [i for i, v in enumerate(volumes) if v["name"] == name]
        expected_volume = {"name": name, "emptyDir": {"sizeLimit": CACHE_LIMIT}}
        if matching_volumes:
            if len(matching_volumes) != 1:
                raise ValueError(f"Duplicate volume {name}")
            old_volume = volumes[matching_volumes[0]]
            if set(old_volume) != {"name", "emptyDir"} or old_volume["emptyDir"].get("medium", ""):
                raise ValueError(f"Expected a disk-backed emptyDir for {name}")
            if set(old_volume["emptyDir"]) - {"sizeLimit", "medium"}:
                raise ValueError(f"Unrecognized emptyDir settings for {name}")
            volumes[matching_volumes[0]] = expected_volume
        else:
            volumes.append(expected_volume)
    if mounts != container.get("volumeMounts"):
        changes.append({"op": "add", "path": base + "/volumeMounts", "value": mounts})
    if volumes != pod.get("volumes"):
        changes.append({"op": "add", "path": "/spec/template/spec/volumes", "value": volumes})
    environment = container.get("env", [])
    if "env" not in container:
        changes.append({"op": "add", "path": base + "/env", "value": []})
    for name, value in ENVIRONMENT.items():
        indexes = [i for i, entry in enumerate(environment) if entry["name"] == name]
        if len(indexes) > 1:
            raise ValueError(f"Duplicate environment variable {name}")
        expected = {"name": name, "value": value}
        if indexes:
            if environment[indexes[0]] != expected:
                changes.append(
                    {"op": "replace", "path": base + f"/env/{indexes[0]}", "value": expected}
                )
        else:
            changes.append({"op": "add", "path": base + "/env/-", "value": expected})
    if not changes:
        return []
    return [
        {"op": "test", "path": "/metadata/uid", "value": metadata["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": metadata["resourceVersion"]},
        {"op": "test", "path": "/spec/replicas", "value": 1},
        {"op": "test", "path": "/spec/strategy/type", "value": "Recreate"},
        *changes,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deployment", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    patch = cache_patch(json.loads(args.deployment.read_text()))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(patch, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "patchCreated": True,
                "changeOperations": sum(p["op"] != "test" for p in patch),
                "rolloutPerformed": False,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
