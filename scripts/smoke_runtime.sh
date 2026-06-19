#!/usr/bin/env bash
# Smoke-test the runtime image by verifying forge user setup, environment, and workspace ownership.

set -euo pipefail

image="${1:-forge:test}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

mkdir -p "${tmp_dir}/workspace" "${tmp_dir}/codex/forge" "${tmp_dir}/gh"
printf '{}\n' > "${tmp_dir}/codex/auth.json"
cat > "${tmp_dir}/codex/forge/config.toml" <<'EOF'
model = "gpt-5.5"

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "ai-guardian --ide codex"
timeout = 30

[[hooks.PreToolUse]]
matcher = ".*"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "ai-guardian --ide codex"
timeout = 30
statusMessage = "Checking tool permissions..."

[[hooks.PermissionRequest]]
matcher = ".*"

[[hooks.PermissionRequest.hooks]]
type = "command"
command = "ai-guardian --ide codex"
timeout = 30
statusMessage = "Checking approval request..."

[[hooks.PostToolUse]]
matcher = ".*"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "ai-guardian --ide codex"
timeout = 30
statusMessage = "Scanning tool output..."
EOF

docker run --rm \
  --env "FORGE_HOST_UID=$(id -u)" \
  --env "FORGE_HOST_GID=$(id -g)" \
  --env "CODEX_HOME=/home/forge/.codex/forge" \
  --volume "${tmp_dir}/workspace:/workspace" \
  --volume "${tmp_dir}/codex:/home/forge/.codex" \
  --volume "${tmp_dir}/gh:/home/forge/.config/gh:ro" \
  "${image}" \
  /bin/bash -lc 'test "$(id -un)" = "forge" && test "$HOME" = "/home/forge" && test "$CODEX_HOME" = "/home/forge/.codex/forge" && command -v codex >/dev/null && command -v ai-guardian >/dev/null && command -v bwrap >/dev/null && command -v gitleaks >/dev/null && command -v rg >/dev/null && command -v uv >/dev/null && codex --version >/tmp/codex-version.txt 2>&1 && grep -Eq "[0-9]+\\.[0-9]+\\.[0-9]+" /tmp/codex-version.txt && test -d /home/forge/.cache/ai-guardian && test -d /home/forge/.config/ai-guardian && test -d /home/forge/.local/state/ai-guardian && test -f /home/forge/.codex/forge/config.toml && grep -q "ai-guardian --ide codex" /home/forge/.codex/forge/config.toml && ai-guardian --ide codex </dev/null >/tmp/ai-guardian-hook.txt 2>&1 && grep -q "AI Guardian v" /tmp/ai-guardian-hook.txt && touch /workspace/smoke-owned'

if [[ "$(uname -s)" == "Linux" ]]; then
  owner="$(stat -c '%u:%g' "${tmp_dir}/workspace/smoke-owned")"
  expected="$(id -u):$(id -g)"
  if [[ "${owner}" != "${expected}" ]]; then
    echo "Expected workspace ownership ${expected}, got ${owner}" >&2
    exit 1
  fi
fi
