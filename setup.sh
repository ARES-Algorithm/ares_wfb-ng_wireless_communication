#!/usr/bin/env bash
# Interactive installation/configuration entry point for Ubuntu 22.04 / 24.04.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
    --help|-h|--dry-run) exec /usr/bin/python3 "$repo_root/scripts/setup_wizard.py" "$@" ;;
esac
if [[ "$EUID" -ne 0 ]]; then
    exec sudo -- bash "$repo_root/setup.sh" "$@"
fi
# Do not inherit a Conda interpreter or environment into privileged installation.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
exec flock -n /run/lock/ares-wfb-setup.lock /usr/bin/python3 "$repo_root/scripts/setup_wizard.py" "$@"
