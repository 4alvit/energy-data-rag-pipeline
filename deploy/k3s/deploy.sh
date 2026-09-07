#!/usr/bin/env bash
# Apply energy-rag kustomize manifests and roll out image TAG.
# Usage:
#   export KUBECONFIG=~/.kube/h7.yaml
#   TAG=v0.2.5 ./deploy/k3s/deploy.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="${TAG:-latest}"
KUBECTL="${KUBECTL:-kubectl}"

echo "Applying kustomize (TAG=${TAG})..."
"${KUBECTL}" apply -k "${DIR}"

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
