#!/usr/bin/env bash
# Shared application launcher; invoked by run_{robot,controller,monitor}.sh.
set -euo pipefail
role="$1"
shift
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bin_var="OAL_${role^^}_BIN"
bin="${!bin_var:-${repo_root}/build/oal_${role}}"
config="${OAL_CONFIG:-/etc/omni-arm-link/link.conf}"
[[ -f "${config}" ]] || config="${repo_root}/config/link.conf"
if [[ ! -x "${bin}" ]]; then
    echo "error: ${bin} not found, build with: cmake -S . -B build && cmake --build build" >&2
    exit 1
fi
exec "${bin}" --config "${config}" "$@"
