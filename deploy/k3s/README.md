# energy-rag on k3s

Lean kustomize deploy for namespace `energy-rag` (postgres + api + mcp + fcc).

## Prerequisites

- kubectl pointed at the k3s cluster (server `https://192.168.151.21:6443`)
- StorageClass `local-path`
- Secret `energy-rag-secrets` (see below)
- Optional: `ghcr-pull` imagePullSecret if GHCR packages are private

## Secrets (names only — never commit values)

| Secret key | Used by |
|------------|---------|
| `POSTGRES_PASSWORD` | postgres |
| `DATABASE_URL` | api (`postgresql+asyncpg://rag:<pass>@postgres:5432/energy_rag`) |
| `OPENAI_API_KEY` | api (optional) |
| `ANTHROPIC_API_KEY` | api / fcc (optional) |
| `NVIDIA_NIM_API_KEY` | fcc (optional) |

Create (values never echoed):

```bash
# From Synology .env or local files — pipe into kubectl, do not print:
kubectl -n energy-rag create secret generic energy-rag-secrets \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=DATABASE_URL="postgresql+asyncpg://rag:${POSTGRES_PASSWORD}@postgres:5432/energy_rag" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
  --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
  --from-literal=NVIDIA_NIM_API_KEY="${NVIDIA_NIM_API_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

See `secret.example.yaml` for the schema.

GitHub Actions secrets (repo): `KUBECONFIG`, `POSTGRES_PASSWORD`, and optional API key secrets used by `.github/workflows/deploy-k3s.yml`.

## Apply

```bash
export KUBECONFIG=~/.kube/h7.yaml
kubectl apply -k deploy/k3s/
# or
TAG=v0.2.5 ./deploy/k3s/deploy.sh
```

## Redeploy (new image tag)

```bash
TAG=v0.2.5 ./deploy/k3s/deploy.sh
# or via GitHub Actions: workflow_dispatch on deploy-k3s.yml
```

## FCC admin (port-forward)

FCC runs **without** `hostNetwork`. Admin UI expects loopback:

```bash
kubectl -n energy-rag port-forward svc/fcc 8082:8082
# open http://127.0.0.1:8082/admin
```

## Services

| Service | Port |
|---------|------|
| postgres | 5432 |
| api | 8000 |
| mcp | 8800 |
| fcc | 8082 |
