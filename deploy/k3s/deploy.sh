#!/usr/bin/env bash
# Apply energy-rag kustomize manifests and roll out image TAG.
# Usage:
#   export KUBECONFIG=...
#   # TLS/Ingress (required when applying ClusterIssuer/Certificate/Ingress):
#   source deploy/k3s/ingress.env   # or export ACME_EMAIL DNS_ZONE K3S_DNS_SUFFIX MCP_INGRESS_HOST
#   TAG=v0.2.5 ./deploy/k3s/deploy.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="${TAG:-latest}"
KUBECTL="${KUBECTL:-kubectl}"

if [[ -f "${DIR}/ingress.env" ]]; then
  # shellcheck disable=SC1091
  source "${DIR}/ingress.env"
fi

need_tls_vars() {
  [[ -n "${ACME_EMAIL:-}" && -n "${DNS_ZONE:-}" && -n "${K3S_DNS_SUFFIX:-}" && -n "${MCP_INGRESS_HOST:-}" ]]
}

render_tls() {
  local out="$1"
  mkdir -p "${out}"
  for f in clusterissuer-letsencrypt-cloudflare.yaml certificate-k3s-tls.yaml ingress-mcp.yaml; do
    # Only substitute known placeholders; leave the rest of YAML alone.
    sed \
      -e "s|\${ACME_EMAIL}|${ACME_EMAIL}|g" \
      -e "s|\${DNS_ZONE}|${DNS_ZONE}|g" \
      -e "s|\${K3S_DNS_SUFFIX}|${K3S_DNS_SUFFIX}|g" \
      -e "s|\${MCP_INGRESS_HOST}|${MCP_INGRESS_HOST}|g" \
      "${DIR}/${f}" > "${out}/${f}"
  done
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# Base kustomization without TLS resources that need substitution —
# apply core stack via kustomize, then rendered TLS/Ingress separately.
# (kustomization still lists certificate/ingress; we render a temp overlay)

cp "${DIR}/kustomization.yaml" "${TMP}/"
# copy all resources referenced by kustomization
while IFS= read -r res; do
  [[ -z "$res" ]] && continue
  cp "${DIR}/${res}" "${TMP}/"
done < <(awk '/^- /{print $2}' "${DIR}/kustomization.yaml")

if need_tls_vars; then
  render_tls "${TMP}"
  echo "Applying kustomize with TLS/Ingress rendered from env (TAG=${TAG})..."
else
  echo "WARN: ACME_EMAIL/DNS_ZONE/K3S_DNS_SUFFIX/MCP_INGRESS_HOST unset — applying without substituting placeholders."
  echo "      Set them (or source deploy/k3s/ingress.env) before ClusterIssuer/Certificate/Ingress can work."
fi

"${KUBECTL}" apply -k "${TMP}"

if need_tls_vars; then
  echo "Applying ClusterIssuer (cluster-scoped)..."
  "${KUBECTL}" apply -f "${TMP}/clusterissuer-letsencrypt-cloudflare.yaml"
fi

"${KUBECTL}" -n energy-rag set image deployment/api \
  "api=ghcr.io/4alvit/energy-data-rag-pipeline:${TAG}"
"${KUBECTL}" -n energy-rag set image deployment/mcp \
  "mcp=ghcr.io/4alvit/energy-data-rag-pipeline:${TAG}"
"${KUBECTL}" -n energy-rag set image deployment/fcc \
  "fcc=ghcr.io/4alvit/free-claude-code:${TAG}"

"${KUBECTL}" -n energy-rag rollout restart deployment/api deployment/mcp deployment/fcc
"${KUBECTL}" -n energy-rag rollout status deployment/postgres --timeout=180s || true
"${KUBECTL}" -n energy-rag rollout status deployment/api --timeout=600s || true
"${KUBECTL}" -n energy-rag get pods -o wide
