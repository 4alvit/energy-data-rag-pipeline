# Local CI

Run `bash scripts/ci.sh` with Python 3.12+, uv 0.12.7 and a local Docker daemon. Dependencies are installed from `uv.lock`. The test helper provisions a disposable pgvector database on a random loopback port, applies `sql/init.sql`, runs pytest and removes only its own container and volume. It does not use your application database configuration.

`bash scripts/ci.sh lint` runs lint and format checks. `bash scripts/ci.sh test` runs only tests after installing locked dependencies. An explicitly supplied `TEST_DATABASE_URL` must point to a loopback database named `energy_rag_test`; provision and migrate that disposable database first. GitHub CI supplies its service container this way.

`bash scripts/ci.sh security` runs Bandit and Trivy. Candidate packages use `bash scripts/package-release.sh X.Y.Z rc`; the version must match committed metadata. OCI builds preserve amd64 and arm64 and require Buildx with QEMU for cross-platform builds. No local command above deploys or publishes.
