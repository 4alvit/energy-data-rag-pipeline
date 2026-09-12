#!/usr/bin/env bash
# Apply energy-rag kustomize manifests and roll out image TAG.
# Usage:
#   export KUBECONFIG=...
#   # TLS/Ingress (required when applying ClusterIssuer/Certificate/Ingress):
#   source deploy/k3s/ingress.env   # or export ACME_EMAIL DNS_ZONE K3S_DNS_SUFFIX MCP_INGRESS_HOST
#   TAG=0.2.5 VERIFIED_IMAGES_FILE=/tmp/verified-images.json ./deploy/k3s/deploy.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="${TAG:?Set the approved stable X.Y.Z version}"
[[ "$TAG" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo "Invalid stable version" >&2; exit 1; }
: "${VERIFIED_IMAGES_FILE:?Run scripts/verified_images.py for this stable release first}"
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
  echo "ACME_EMAIL/DNS_ZONE/K3S_DNS_SUFFIX/MCP_INGRESS_HOST are required before deployment" >&2
  exit 1
fi

# Set approved digests in the rendered configuration BEFORE the first apply.
python3 "${DIR}/../../scripts/pin-deployment-images.py" "$VERIFIED_IMAGES_FILE" "${TMP}/kustomization.yaml" "$TAG"
"${KUBECTL}" apply -k "${TMP}"

if need_tls_vars; then
  echo "Applying ClusterIssuer (cluster-scoped)..."
  "${KUBECTL}" apply -f "${TMP}/clusterissuer-letsencrypt-cloudflare.yaml"
fi

for deployment in postgres api mcp fcc; do
  "${KUBECTL}" -n energy-rag rollout status "deployment/$deployment" --timeout=600s
done
"${KUBECTL}" -n energy-rag get pods -o wide
