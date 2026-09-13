# energy-rag on k3s

Lean kustomize deploy for namespace `energy-rag` (postgres + api + mcp + fcc).

## Prerequisites

- kubectl pointed at the k3s cluster (server URL for your k3s API)
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

## Ingress / TLS

MCP Ingress host and ACME identity are **not** committed. Set GitHub Actions
Variables (or local `deploy/k3s/ingress.env` — gitignored; see
`ingress.env.example`):

| Variable | Purpose |
|----------|---------|
| `ACME_EMAIL` | Let's Encrypt account email (ClusterIssuer) |
| `DNS_ZONE` | Public DNS zone for Cloudflare DNS-01 |
| `K3S_DNS_SUFFIX` | Suffix for wildcard cert (`*.${K3S_DNS_SUFFIX}`) |
| `MCP_INGRESS_HOST` | Ingress host for MCP |

Templates in git use `${…}` placeholders; `deploy.sh` substitutes them before
`kubectl apply`.

One-time cluster setup (not in the namespaced kustomization):

```bash
# cert-manager (if missing)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.1/cert-manager.yaml

# Cloudflare API token Secret in cert-manager ns
# (Zone.DNS Edit on your public zone — use a token scoped to that zone only)
kubectl -n cert-manager create secret generic cloudflare-api-token \
  --from-literal=api-token="$CLOUDFLARE_DNS_API_TOKEN"

# Render + apply (requires the four variables above)
source deploy/k3s/ingress.env
./deploy/k3s/deploy.sh
```

Also apply the ClusterIssuer after rendering:

```bash
# deploy.sh applies the kustomization (includes Certificate + Ingress).
# ClusterIssuer is cluster-scoped; apply the rendered file once:
sed -e "s|\${ACME_EMAIL}|$ACME_EMAIL|g" -e "s|\${DNS_ZONE}|$DNS_ZONE|g" \
  deploy/k3s/clusterissuer-letsencrypt-cloudflare.yaml | kubectl apply -f -
```

Traefik should expose `:80`/`:443` on the node address your LAN/VPN clients use
(for example via `externalIPs` on the Traefik Service). Do **not** open world
`0.0.0.0/0:443` on the cloud security list toward that VIP.


## GitHub Actions runner (`gha-runner-fcc`)

Repo runner for `iot-project-builder-profile` (`runs-on: [self-hosted, fcc]`).
Talks to in-cluster FCC at `http://fcc.energy-rag.svc.cluster.local:8082`.

```bash
kubectl -n energy-rag create secret generic gha-runner-fcc \
  --from-literal=ACCESS_TOKEN=ghp_... \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f gha-runner-fcc.yaml
```

## Container filesystem permissions

The API, MCP, and FCC containers run as UID/GID 1000; PostgreSQL runs as
UID/GID 999. Their root filesystems are read-only, capabilities are dropped,
and privilege escalation is disabled. `/tmp` uses `emptyDir`, and PostgreSQL
also mounts writable socket storage at `/var/run/postgresql`.

Application data, model caches, FCC configuration, and PostgreSQL data retain
their existing volumes. Pod `fsGroup` grants the service group access when the
volume driver supports it; check existing PVC ownership during rollout. The
PostgreSQL image was locally verified with `initdb`, startup, readiness, and
shutdown using these restrictions and disposable storage. Existing cluster
PVC permissions and a live rollout still require operator verification.


The runner uses the pinned multi-architecture `myoung34/github-runner:ubuntu-noble`
image as UID 1001 / GID 121 with `RUN_AS_ROOT=false`, no privilege escalation,
and a read-only container root filesystem. A non-root init container copies the
image's runner installation and home directory into emptyDir volumes. Registration
state and diagnostics, the Python tool cache, home, temporary files and the existing
work directory remain writable. The same image digest is used for initialization
and execution; update both references together after validating its runner UID/GID.
No Docker socket or privileged container is needed by the current profile workflow.

The image entrypoint and Runner.Listener were verified offline under these
constraints, including writes to each mounted path and rejection of writes to the
root filesystem. Registration was stubbed and networking disabled for this check;
it did not register or replace the live runner. Production registration and a real
profile job must be checked during the separately approved deployment. Drain the
existing runner before applying this manifest; this change does not deploy it.
