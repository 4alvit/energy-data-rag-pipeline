"""Build native OCI cells, bind their smoke evidence, then assemble offline."""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import merge_oci_archives as oci
import package_release as package

PRODUCTS = {
    "rag": "energy-data-rag-pipeline-container.oci.tar",
    "fcc": "energy-rag-fcc-container.oci.tar",
}
ARCHITECTURES = {"amd64": ("x86_64", "X64"), "arm64": ("aarch64", "ARM64")}
SBOM = "https://spdx.dev/Document"
SMOKE_SCOPE = {"rag": "offline-http-lifespan-disabled", "fcc": "offline-default-server"}


def command(args, **kwargs):
    """Use bounded checked subprocesses; never shell-expand build inputs."""
    return subprocess.check_output(
        args, text=True, timeout=kwargs.pop("timeout", 300), **kwargs
    ).strip()


def file_identity(path):
    """Hash streamed bytes without loading container layers into memory."""
    with path.open("rb") as stream:
        return {
            "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
            "size": path.stat().st_size,
        }


def fingerprint(source, names):
    """Bind every tracked snapshot byte and executable bit, not timestamps."""
    entries = [
        {
            "name": name,
            "executable": bool((source / name).stat().st_mode & 0o111),
            **file_identity(source / name),
        }
        for name in names
    ]
    return hashlib.sha256(oci.canonical({"files": entries})).hexdigest()


def binding(root, version, channel):
    """Require the committed checkout and exact current Actions attempt."""
    policy = json.loads((root / ".release-policy.json").read_text())
    oci.require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "Invalid base version")
    oci.require(
        package.read_version(root, policy) == version, "Version differs from committed metadata"
    )
    oci.require(channel in {"nightly", "beta", "rc"}, "Stable must promote RC bytes")
    revision = command(["git", "rev-parse", "HEAD"], cwd=root)
    oci.require(re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid source SHA")
    oci.require(revision == os.environ.get("GITHUB_SHA"), "Checkout differs from Actions SHA")
    oci.require(
        not command(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root),
        "Tracked inputs changed",
    )
    result = {"schema": 1, "version": version, "channel": channel, "revision": revision}
    for key, variable in (("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        value = os.environ.get(variable, "")
        oci.require(re.fullmatch(r"[1-9][0-9]*", value), f"Invalid {variable}")
        result[key] = value
    return result


def configuration(root):
    """Keep the existing asset names, platforms and promotion mapping exact."""
    config = json.loads((root / ".release-package.json").read_text())["containers"]
    policy = json.loads((root / ".release-policy.json").read_text())["container_assets"]
    oci.require(
        set(config) == set(policy) == set(PRODUCTS.values()), "Container asset inventory changed"
    )
    for asset, value in config.items():
        oci.require(
            value["platforms"] == "linux/amd64,linux/arm64", f"Unsupported platforms: {asset}"
        )
    return config


def inspect_archive(path, arch, expected):
    """Verify content closure, native config, SBOM and provenance subjects."""
    with ExitStack() as stack:
        archive = oci.Archive(
            path, f"linux/{arch}", expected["version"], expected["revision"], stack
        )
        predicates = {kind for item in archive.attestations for kind in item["predicate_types"]}
        oci.require(bool(predicates & oci.PROVENANCE_TYPES), "Native archive lacks provenance")
        oci.require(SBOM in predicates, "Native archive lacks SBOM")
        image = archive.images[0]
        config = archive.read_json(oci.BLOB_PREFIX + image["config_sha256"])
        oci.require(
            config["config"].get("User") in {"1000", "1000:1000", "appuser", "fcc"},
            "Image must default to non-root",
        )
        archive.unchanged()
        return {
            "archive": archive.archive_identity,
            "config_digest": "sha256:" + image["config_sha256"],
            "manifest_digest": image["descriptor"]["digest"],
            "diff_ids": config["rootfs"]["diff_ids"],
            "attestations": archive.attestations,
        }


def validate_loaded(loaded, checked, arch):
    """A Docker image ID is the config digest, not the OCI manifest digest."""
    oci.require(
        loaded["Id"] == checked["config_digest"], "Loaded config differs from archived image"
    )
    oci.require(
        loaded["Os"] == "linux" and loaded["Architecture"] == arch, "Loaded image platform differs"
    )
    oci.require(
        loaded["RootFS"]["Type"] == "layers" and loaded["RootFS"]["Layers"] == checked["diff_ids"],
        "Loaded rootfs differs from archive",
    )


def smoke(root, archive, product, arch, expected, checked, endpoint):
    """Materialize only the checked host image; retain full OCI attestations."""
    tag = f"native-{product}:run-{expected['run_id']}-attempt-{expected['run_attempt']}-{arch}"
    command(
        [
            "skopeo",
            "--override-os",
            "linux",
            "--override-arch",
            arch,
            "copy",
            "--dest-daemon-host",
            endpoint,
            f"oci-archive:{archive}",
            f"docker-daemon:{tag}",
        ],
        timeout=900,
    )
    docker = ["docker", "--host", endpoint]
    loaded = json.loads(command([*docker, "image", "inspect", tag]))
    oci.require(len(loaded) == 1, "Expected one loaded image")
    validate_loaded(loaded[0], checked, arch)
    # FCC uses its real default CMD/lifespan. RAG starts the real HTTP app
    # with lifespan disabled because offline smoke has no database or models.
    expected_cmd = {"rag": ["energy-rag-api"], "fcc": ["fcc-server"]}[product]
    oci.require(
        loaded[0]["Config"].get("Cmd") == expected_cmd
        and not loaded[0]["Config"].get("Entrypoint"),
        "Image startup command differs",
    )
    name = tag.replace(":", "-")
    launch = [
        *docker,
        "run",
        "--detach",
        "--name",
        name,
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--mount",
        f"type=bind,src={root / 'scripts/native_container_smoke.py'},dst=/tmp/native-smoke.py,readonly",
    ]
    if product == "rag":
        launch += [
            "--read-only",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
            "--entrypoint=python",
            tag,
            "-m",
            "uvicorn",
            "energy_rag.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--lifespan",
            "off",
        ]
    else:
        launch += ["--env=VOICE_NOTE_ENABLED=false", tag]
    try:
        command(launch)
        raw = command(
            [
                *docker,
                "exec",
                name,
                "python",
                "/tmp/native-smoke.py",
                product,
                arch,
                expected["version"],
            ],
            timeout=180,
        )
        result = json.loads(raw.splitlines()[-1])
        oci.require(
            result
            == {
                "product": product,
                "architecture": arch,
                "uid": 1000,
                "scope": SMOKE_SCOPE[product],
                "status": "passed",
            },
            "Native runtime smoke did not pass",
        )
    except (ValueError, subprocess.SubprocessError):
        subprocess.run([*docker, "logs", name], check=False, timeout=30, stdout=sys.stderr)
        raise
    finally:
        subprocess.run(
            [*docker, "rm", "--force", "--volumes", name],
            check=False,
            timeout=30,
            stdout=sys.stderr,
        )
        command([*docker, "image", "rm", tag])
    return result


def build(root, output, product, arch, version, channel):
    """Build one image on matching hosted hardware, without QEMU or registry pushes."""
    expected = binding(root, version, channel)
    config = configuration(root)[PRODUCTS[product]]
    machine, runner_arch = ARCHITECTURES[arch]
    oci.require(
        platform.system() == "Linux" and platform.machine() == machine,
        "Host is not the requested native Linux architecture",
    )
    oci.require(
        os.environ.get("RUNNER_ARCH") == runner_arch and os.environ.get("RUNNER_OS") == "Linux",
        "Runner architecture differs",
    )
    endpoint = os.environ.get("DOCKER_HOST") or command(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
    )
    oci.require(
        endpoint.startswith("unix:///"), "Native builds require a local UNIX Docker endpoint"
    )
    output.mkdir(parents=True, exist_ok=True)
    oci.require(not any(output.iterdir()), "Native output must be empty")
    target = output / "image.oci.tar"
    with TemporaryDirectory(prefix="native-source-") as directory:
        source = Path(directory).resolve()
        names = package.snapshot(root, source)
        inputs_digest = fingerprint(source, names)
        context, dockerfile = (
            (source / config["context"]).resolve(),
            (source / config["dockerfile"]).resolve(),
        )
        context.relative_to(source)
        dockerfile.relative_to(source)
        started = time.monotonic()
        subprocess.run(
            [
                "docker",
                "--host",
                endpoint,
                "buildx",
                "build",
                "--platform",
                f"linux/{arch}",
                "--provenance=true",
                "--sbom=true",
                # BuildKit derives in-toto subjects from ImageName. This names
                # the local OCI export only; neither --push nor registry output is used.
                "--tag",
                f"energy-native-{product}:{version}-{expected['revision']}",
                "--label",
                f"org.opencontainers.image.version={version}",
                "--label",
                f"org.opencontainers.image.revision={expected['revision']}",
                "--file",
                str(dockerfile),
                "--output",
                f"type=oci,dest={target}",
                str(context),
            ],
            check=True,
            timeout=1800,
        )
        build_seconds = time.monotonic() - started
    checked = inspect_archive(target, arch, expected)
    started = time.monotonic()
    runtime = smoke(root, target, product, arch, expected, checked, endpoint)
    oci.require(file_identity(target) == checked["archive"], "Archive changed during smoke")
    receipt = {
        **expected,
        "product": product,
        "architecture": arch,
        "platform": f"linux/{arch}",
        "inputs_sha256": inputs_digest,
        **checked,
        "smoke": runtime,
        "runner": {"os": "Linux", "machine": machine, "arch": runner_arch},
        "tools": {
            "docker": command(["docker", "--version"]),
            "buildx": command(["docker", "buildx", "version"]),
            "skopeo": command(["skopeo", "--version"]),
        },
        "timings": {
            "build_seconds": round(build_seconds, 3),
            "smoke_seconds": round(time.monotonic() - started, 3),
        },
    }
    (output / "receipt.json").write_bytes(oci.canonical(receipt) + b"\n")


def validate_receipt(receipt, expected, product, arch, inputs_digest, checked):
    """Reject stale attempts, wrong products, untested inputs or rewritten bytes."""
    required = {
        **expected,
        "product": product,
        "architecture": arch,
        "platform": f"linux/{arch}",
        "inputs_sha256": inputs_digest,
        **checked,
    }
    oci.require(
        all(receipt.get(key) == value for key, value in required.items()),
        "Native receipt binding differs",
    )
    machine, runner_arch = ARCHITECTURES[arch]
    oci.require(
        receipt.get("runner") == {"os": "Linux", "machine": machine, "arch": runner_arch},
        "Native runner proof differs",
    )
    oci.require(
        receipt.get("smoke")
        == {
            "product": product,
            "architecture": arch,
            "uid": 1000,
            "scope": SMOKE_SCOPE[product],
            "status": "passed",
        },
        "Native smoke proof differs",
    )
    tools = receipt.get("tools", {})
    oci.require(
        set(tools) == {"docker", "buildx", "skopeo"}
        and all(isinstance(value, str) and value for value in tools.values()),
        "Missing native toolchain proof",
    )


def assemble(root, inputs, output, version, channel):
    """Assemble the same release assets from exactly four checked native cells."""
    expected = binding(root, version, channel)
    configuration(root)
    oci.require(
        not inputs.is_symlink() and inputs.is_dir(), "Native inputs must be a regular directory"
    )
    cells = {f"{product}-{arch}" for product in PRODUCTS for arch in ARCHITECTURES}
    oci.require({path.name for path in inputs.iterdir()} == cells, "Native cell inventory differs")
    with TemporaryDirectory(prefix="native-assembly-source-") as directory:
        source = Path(directory).resolve()
        inputs_digest = fingerprint(source, package.snapshot(root, source))
    receipts, archives = {}, {}
    # Validate all cells before creating any candidate output.
    for product in PRODUCTS:
        archives[product] = {}
        for arch in ARCHITECTURES:
            cell = inputs / f"{product}-{arch}"
            oci.require(
                not cell.is_symlink() and cell.is_dir(), "Native cell must be a regular directory"
            )
            oci.require(
                {path.name for path in cell.iterdir()} == {"image.oci.tar", "receipt.json"},
                "Native cell file inventory differs",
            )
            receipt_path = cell / "receipt.json"
            oci.require(
                not receipt_path.is_symlink()
                and receipt_path.is_file()
                and receipt_path.stat().st_size <= 1024 * 1024,
                "Unsafe native receipt",
            )
            receipt = oci.document(receipt_path.read_bytes())
            archive = cell / "image.oci.tar"
            checked = inspect_archive(archive, arch, expected)
            validate_receipt(receipt, expected, product, arch, inputs_digest, checked)
            receipts[f"{product}-{arch}"] = receipt
            archives[product][f"linux/{arch}"] = archive
    package.build_candidate(root, version, channel, output, containers=False)
    assembled = {}
    for product, asset in PRODUCTS.items():
        assembled[product] = oci.merge_archives(
            archives[product], output / asset, version, expected["revision"]
        )
        for item in assembled[product]["inputs"]:
            arch = item["platform"].split("/")[1]
            oci.require(
                {key: item[key] for key in ("sha256", "size")}
                == receipts[f"{product}-{arch}"]["archive"],
                "Archive changed during assembly",
            )
    (output / "native-build-evidence.json").write_bytes(
        oci.canonical({**expected, "cells": receipts, "assembly": assembled}) + b"\n"
    )
    assets = sorted(path for path in output.iterdir() if path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{file_identity(path)['sha256']}  {path.name}\n" for path in assets)
    )


def main():
    """Expose build and offline assembly to the reusable workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["build", "assemble"])
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--product", choices=PRODUCTS)
    parser.add_argument("--arch", choices=ARCHITECTURES)
    parser.add_argument("--inputs", type=Path, default=Path("native-inputs"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.operation == "build":
        if not args.product or not args.arch:
            parser.error("build requires --product and --arch")
        build(root, args.output.resolve(), args.product, args.arch, args.version, args.channel)
    else:
        assemble(root, args.inputs.absolute(), args.output.resolve(), args.version, args.channel)


if __name__ == "__main__":
    main()
