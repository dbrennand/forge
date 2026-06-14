#!/usr/bin/env bash
# Smoke-test the runtime image by verifying forge user setup, environment, and workspace ownership.

set -euo pipefail

image="${1:-forge:test}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

mkdir -p "${tmp_dir}/workspace" "${tmp_dir}/codex" "${tmp_dir}/gh"
printf '{}\n' > "${tmp_dir}/codex/auth.json"

docker run --rm \
  --env "FORGE_HOST_UID=$(id -u)" \
  --env "FORGE_HOST_GID=$(id -g)" \
  --volume "${tmp_dir}/workspace:/workspace" \
  --volume "${tmp_dir}/codex:/home/forge/.codex" \
  --volume "${tmp_dir}/gh:/home/forge/.config/gh:ro" \
  "${image}" \
  /bin/bash -lc 'test "$(id -un)" = "forge" && test "$HOME" = "/home/forge" && test "$CODEX_HOME" = "/home/forge/.codex" && touch /workspace/smoke-owned'

if [[ "$(uname -s)" == "Linux" ]]; then
  owner="$(stat -c '%u:%g' "${tmp_dir}/workspace/smoke-owned")"
  expected="$(id -u):$(id -g)"
  if [[ "${owner}" != "${expected}" ]]; then
    echo "Expected workspace ownership ${expected}, got ${owner}" >&2
    exit 1
  fi
fi
