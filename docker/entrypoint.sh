#!/usr/bin/env bash
# Remap the in-image forge account to the invoking host UID:GID, then drop privileges.

set -euo pipefail

readonly forge_user="forge"
readonly forge_home="/home/forge"

: "${FORGE_HOST_UID:?FORGE_HOST_UID must be set}"
: "${FORGE_HOST_GID:?FORGE_HOST_GID must be set}"

if [[ "${FORGE_HOST_UID}" == "0" || "${FORGE_HOST_GID}" == "0" ]]; then
  echo "Forge must be invoked as a non-root user." >&2
  exit 2
fi

current_uid="$(id -u "${forge_user}")"
current_gid="$(id -g "${forge_user}")"

existing_group="$(getent group "${FORGE_HOST_GID}" | cut -d: -f1 || true)"

if existing_user="$(getent passwd "${FORGE_HOST_UID}" | cut -d: -f1)"; then
  if [[ "${existing_user}" != "${forge_user}" ]]; then
    echo "Requested UID ${FORGE_HOST_UID} is already assigned to user ${existing_user}." >&2
    exit 2
  fi
fi

if [[ -n "${existing_group}" && "${existing_group}" != "${forge_user}" ]]; then
  usermod --gid "${FORGE_HOST_GID}" "${forge_user}"
elif [[ "${current_gid}" != "${FORGE_HOST_GID}" ]]; then
  groupmod --gid "${FORGE_HOST_GID}" "${forge_user}"
  usermod --gid "${FORGE_HOST_GID}" "${forge_user}"
fi

if [[ "${current_uid}" != "${FORGE_HOST_UID}" ]]; then
  usermod --uid "${FORGE_HOST_UID}" --gid "${FORGE_HOST_GID}" "${forge_user}"
fi

mkdir -p "${forge_home}" "${forge_home}/.config"
chown "${forge_user}:${forge_user}" "${forge_home}" "${forge_home}/.config"

exec gosu "${forge_user}" "$@"
