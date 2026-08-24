# Release & Multi-Arch Images

## Versioning policy (three sources of truth)

1. `pyproject.toml` → `version`
2. root **`version`** file (read by deploy.sh and dashboards)
3. git tag `v<version>` (triggers the release pipeline)

All three must carry the same string. Bump with:

```bash
uv version 0.3.0 && printf '0.3.0\n' > version
git add pyproject.toml uv.lock version CHANGELOG.md
git commit -m "chore(release): v0.3.0"
```

## Release runbook

```bash
# 0. main is green on CI, PRs merged, CHANGELOG updated

# 1. Bump versions (see above), merge via PR

# 2. Tag & push
git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin vX.Y.Z
```

The tag push triggers two workflows:

- **release.yml** — full tests against pgvector service, build sdist/wheel,
  create GitHub Release with artifacts.
- **docker-publish.yml** — multi-platform image build and push to GHCR.

## Multi-arch Docker images

`.github/workflows/docker-publish.yml` builds for `linux/amd64` **and**
`linux/arm64` using QEMU + Buildx with GHA layer cache, SBOM and provenance
attestations, then verifies the manifest contains both platforms.

Images (`ghcr.io/4alvit/energy-data-rag-pipeline`):

| Trigger | Tags |
|---|---|
| tag `v1.2.3` | `1.2.3`, `1.2`, `1` |
| push to `main` | `main` |
| workflow_dispatch | per metadata-action defaults |

Why arm64 matters here: Synology NAS units are commonly arm64; building
natively-targeted images avoids slow QEMU execution at runtime and works out
of the box with Container Manager.

### Verifying a release image

```bash
docker buildx imagetools inspect ghcr.io/4alvit/energy-data-rag-pipeline:X.Y.Z
# expect: linux/amd64 + linux/arm64 entries

docker pull --platform linux/arm64 \
  ghcr.io/4alvit/energy-data-rag-pipeline:X.Y.Z
```

### Local reproduction of CI build

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t energy-rag:local .
```

(Apple Silicon docker desktop runs arm64 natively; amd64 via Rosetta/QEMU.)

## Consuming releases elsewhere

Any machine with docker:

```bash
export TAG=X.Y.Z POSTGRES_PASSWORD=... OLLAMA_BASE_URL=http://host:11434
docker compose -f deploy/docker-compose.prod.yml up -d
```

GHCR package visibility must be public (or configure
`docker login ghcr.io` with a PAT having `read:packages`).

## Post-release checklist

- [ ] GitHub Release exists with wheel/sdist attached
- [ ] GHCR shows both architectures for the new tag
- [ ] `deploy/deploy.sh status` healthy on Synology after upgrade
- [ ] `/health` reports correct new version string
