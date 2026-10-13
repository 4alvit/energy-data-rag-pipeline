# Project release packaging and versions

The source tarball, RAG OCI archive and FCC OCI archive remain the release payloads. Each image is built and smoked on both native amd64 and arm64 Linux runners, then assembled without rebuilding. FCC keeps its pinned upstream package version and dependencies; the outer OCI label identifies this repository's integrated release, not a new upstream FCC release.

## Owned version fields

The root `version` uses the SemVer package projection, while `pyproject.toml` and the owned `energy-rag-pipeline` entry in `uv.lock` use PEP 440. RAG imports its installed distribution metadata. Every native cell and the assembly job download the same plan and apply it before fingerprinting inputs. Native receipts bind the plan digest, package version, Python version, source, run, attempt and overlaid snapshot digest. Assembly verifies all four cells and preserves `native-build-evidence.json` inside the final receipted payload set.

The complete selectors are in [the release policy](../.release-policy.json). Only owned package metadata is synchronized. Third-party dependency versions, lock hashes and independent component versions are preserved. The committed source contains a numeric `X.Y.Z` base; candidate overlays are build outputs and must not be committed.

## Candidate identity and stable compatibility

This repository explicitly retains `promote-bytes`. For base `1.2.3`, beta 7 has tag `v1.2.3-beta.7`, SemVer package identity `1.2.3-beta.7` and Python identity `1.2.3b7`. A nightly's full tag includes the frozen UTC timestamp/run/attempt; its Python version is `1.2.3.dev<run * 1000000 + attempt>`. RC 7 has tag `v1.2.3-rc.7`, while its embedded package version is already `1.2.3`. Stable promotion copies that accepted RC's bytes; it does not relabel or rebuild the payload. The manifest and plan retain the RC origin after promotion.

Source-archive filenames use the checked SemVer package identity. Python filenames follow their backend's PEP 440 spelling. Publication is identified by the full frozen tag, source SHA and checksums, not by an archive basename alone. No stable publication, deployment, package-registry import or acceptance approval is caused by preparing a version or running local tests.

## Preparation and build order

From clean current default-branch HEAD, use:

```sh
python3 scripts/version_plan.py check-base
python3 scripts/release.py prepare-version --dry-run
python3 scripts/release.py prepare-version --pr
```

The preparation command refreshes tags and preserves an existing unreleased base; explicit `--bump minor`, `--bump major` or `--version X.Y.Z` records intentional changes. Review every owned field and the release notes together. The allocator reserves the full candidate and counter on `release-version-state`; failed runs may leave gaps. Never reset that ledger to reuse an identity.

The release workflow uploads one `.release-plan.json` before building. Each build job downloads that exact artifact and runs `version_plan.py sync`, producing `.release-inputs.json`. The packager validates the requested base/channel against the saved plan and snapshots the overlaid tracked inputs. After package-specific checks and checksums, `stage_release_assets.py` copies final payloads into `release-assets/package` and creates `release-inputs-package.json`. The publisher requires complete declared artifact metadata and verifies every payload's size/hash against the receipt. A missing platform, mismatched package version, changed version input or uncovered payload prevents publication.

## Local reproduction and verification

A publishable local reproduction requires a disposable checkout of the manifest's exact source commit and its saved `version_plan` object as `.release-plan.json`. Do not invent a tag, sequence or native counter. Apply the saved plan before calling the adapter:

```sh
python3 scripts/version_plan.py sync --plan .release-plan.json
python3 scripts/release_version_adapter.py X.Y.Z beta
bash scripts/package-release.sh X.Y.Z beta
python3 scripts/stage_release_assets.py --target package --pattern 'release-dist/*'
```

Use the saved plan's actual base/channel. For Energy RAG the workflow uses `native_containers.py build` on each matching native runner and `native_containers.py assemble` with all four cell outputs; the generic package command is only an auxiliary local packaging path and does not reproduce native acceptance evidence. Without a plan, local packaging can check committed base metadata but cannot stage publishable assets. Do not treat such a development archive as a numbered beta or RC.

Run the release contracts with Python 3.12+ and the pinned workflow-contract dependencies:

```sh
python3 -m unittest discover -s .github/release-tests -p 'test_*.py'
python3 -m unittest discover -s .github/workflow-tests -p 'test_*.py'
```

From the toolkit checkout, `python3 scripts/install_release.py /path/to/this/repository --check` detects generated drift. Update the shared toolkit first, render again, then recheck project-specific adapters and tests. Do not edit vendored files directly. The pinned toolkit revision in the policy documents the reviewed source.

## Acceptance and recovery

The existing PostgreSQL/pgvector integration checks and four native image smoke tests remain required. RAG smoke disables HTTP lifespan and FCC smoke covers its offline default server; neither establishes production database, external LLM, ingestion-corpus or deployment acceptance. PR/merge-queue native validation explicitly supplies an empty plan input, builds the committed base, and uploads diagnostic assets without a publishable version receipt. Release runs always supply the allocator's plan and stage the final receipt.

A changed source, lockfile, packaging recipe or policy needs a new candidate and new acceptance. A failed build cannot be repaired by editing an uploaded archive, receipt or plan. Correct the source in a reviewed commit and request a fresh candidate; retain earlier evidence for diagnosis. Restore a previously accepted immutable artifact for operational rollback, with configuration/data compatibility reviewed separately. See [shared version-plan rules](VERSIONING.md) and [the release runbook](release-workflow.md) for allocation recovery, evidence retention and publication controls.
