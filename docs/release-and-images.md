# Release images

The [release runbook](release-workflow.md) describes the guarded beta → RC → stable
workflow. Update `pyproject.toml`, the root `version` file and the editable project
version in `uv.lock` together through a reviewed PR. The release workflow creates
tags after validation; do not create release tags manually.

## Native container builds

`release-build.yml` builds four independent cells: RAG and FCC on
`ubuntu-24.04` (AMD64) and `ubuntu-24.04-arm` (ARM64). Each cell builds only its
runner's architecture. No QEMU or intermediate registry publication is required.
The pinned Dockerfiles, hash-locked dependencies and tracked source snapshot
remain the build inputs.

Every cell exports an OCI archive with BuildKit provenance and SBOM. A bounded
validator checks the archive's blob digests, descriptor sizes, platform, image
labels, filesystem layers and attestation subjects. Skopeo materializes the native
image into the local Docker daemon for smoke testing. Its config digest and
filesystem diff IDs must match the original archive, which remains unchanged.

Both images run as their default non-root user with networking disabled:

- RAG loads the packaged native dependencies and console entrypoint, then serves
  `/health/live` and `/openapi.json` through its real Uvicorn application with
  lifespan disabled. This checks image packaging and HTTP startup, not database,
  model download or inference readiness. Existing CI still exercises PostgreSQL.
- FCC starts its real default `fcc-server` command and lifespan, checks its console
  version and waits for `/health`. This does not exercise an external LLM provider.

Offline assembly requires all four cells from the same source, input fingerprint,
version, workflow run and attempt. It preserves these release asset names, each
containing `linux/amd64` and `linux/arm64` plus their attestations:

- `energy-data-rag-pipeline-container.oci.tar`
- `energy-rag-fcc-container.oci.tar`

The tracked source archive, `native-build-evidence.json` and `SHA256SUMS` accompany
them. Evidence records the original native archive hashes, tested image identities,
runner architectures, tool versions and timings. The OCI merge helper and its
regression suite originate from the reviewed EventLog native release adapter
(commit `09f1ed1425cc7d266281fdd5dcf9800ca22abfa1`).

## Required gates and retries

The policy includes `native-validation.yml`, so PRs and merge-queue commits must
complete all native builds and assembly before the required CI gate succeeds.
Release pushes, scheduled nightlies and manual releases use the same native build
through the mandatory Release gate; they do not run a duplicate matrix inside CI.
Unknown entry workflows or events fail closed.

Artifact names and receipts bind the exact workflow attempt. After a transient
runner, network or GitHub service failure, use **Re-run all jobs**. Re-running only
failed jobs cannot reuse successful native cells from an earlier attempt. Preserve
the failed attempt's logs and diagnose deterministic failures before retrying.

Stable promotion copies verified RC bytes without rebuilding. GitHub releases do
not deploy production or automatically push these containers to GHCR. The separate
verified-container publication procedure in the runbook keeps the existing target
repositories and requires an explicit operator action.
