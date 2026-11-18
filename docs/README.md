# Documentation

A retrieval-augmented generation pipeline over Victron Energy documentation, with
an HTTP API, an MCP server and the release tooling that ships it as images.

## Overview

- [Documentation index](index.md) — the project's own entry point for the RAG pipeline.
- [Architecture](architecture.md) — the component diagram and how the stages connect.
- [Configuration](configuration.md) — the environment variables that configure the service.
- [API reference](api-reference.md) — the HTTP endpoints on the default port.

## Pipeline

- [Ingestion and chunking](ingestion-and-chunking.md) — how PDFs are loaded and split.
- [Corpus enrichment](corpus-enrichment.md) — building a corpus from official Victron material.
- [MCP integration](mcp-integration.md) — the MCP server the pipeline ships.
- [Troubleshooting](troubleshooting.md) — starting with an unreachable database.

## Deployment

- [Deployment (Docker and Synology)](deployment-synology.md) — the compose path and its `.env` file.
- [Local CI](local-ci.md) — running `scripts/ci.sh` with the required toolchain.
- [Release images](release-and-images.md) — the guarded beta → RC → stable runbook.
- [Project release packaging and versions](release-packaging.md) — the tarball and the two OCI archives.

## Release operation and evidence

- [CI orchestration](CI-ORCHESTRATION.md) — how quality gate and release pipeline divide the events.
- [CI and release operations](release-workflow.md) — `.release-policy.json` and the required status.
- [Version plans and manifest synchronization](VERSIONING.md) — the versioning opt-in.
- [Release helper TLS profile](RELEASE_TLS_PROFILE.md) — the qualified `gh` transport profile.
- [TLS certificate key policy](tls-policy.md) — the verification applied to owned HTTPS clients.
- [Release-candidate fuzz testing](fuzzing.md) — the illustrated RC fuzzing process and its rollout results.
- [Release read recovery and rerun validation](release-read-safety.md) — the two fixes carried from the shared release toolkit.
- [Early final-build runner check](runner-preflight.md) — why the runner check runs before the final build.
- [OpenSSF Best Practices evidence](openssf-evidence.md) — the evidence index for the self-assessment.
