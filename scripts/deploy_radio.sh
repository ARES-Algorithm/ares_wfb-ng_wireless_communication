#!/usr/bin/env bash
# Install configuration and a radio-only system service; never starts application traffic.
# Usage: sudo bash scripts/deploy_radio.sh robot|controller wlan [keys-directory] [profile-file]
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
role="${1:-}"
wlan="${2:-}"
keys_src="${3:-/etc}"
profile="${4:-}"
case "$role" in
    robot) other=controller ;;
    controller) other=robot ;;
    *) echo 'Usage: sudo bash scripts/deploy_radio.sh robot|controller wlan [keys-directory] [profile-file]' >&2; exit 1 ;;
esac
[[ "$EUID" == 0 && -n "$wlan" && $# -le 4 ]] || {
    echo 'Run as root and specify a wireless interface.' >&2; exit 1;
}
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Paths are substituted into unquoted systemd ExecStart fields.
[[ "$repo_root" =~ ^[a-zA-Z0-9_./-]+$ && "$wlan" =~ ^[a-zA-Z0-9_.:-]+$ ]] || {
    echo 'Repository path and interface must not contain whitespace or shell/systemd metacharacters.' >&2; exit 1;
}
[[ -x "$repo_root/scripts/wfb_server.sh" ]]
for key in drone.key gs.key; do
    [[ -f "$keys_src/$key" ]] || { echo "Missing $keys_src/$key" >&2; exit 1; }
done
ip link show "$wlan" >/dev/null
# A system service needs a system-wide installation; user-local PATH is not inherited.
command -v wfb-server >/dev/null || { echo 'Install wfb-server system-wide first.' >&2; exit 1; }
backup="$(mktemp -d /var/backups/wfb-service-XXXXXXXX)"
for unit in "oal-radio-$role.service" "oal-radio-$other.service"; do
    if [[ -f "/etc/systemd/system/$unit" ]]; then cp -a "/etc/systemd/system/$unit" "$backup/"; fi
done
if systemctl cat "oal-radio-$other.service" >/dev/null 2>&1; then
    systemctl disable --now "oal-radio-$other.service"
fi
systemctl stop "oal-radio-$role.service" 2>/dev/null || true
bash "$repo_root/scripts/setup_radio.sh" "$role" "$wlan" "$keys_src" "$profile"
python3 - "$repo_root/systemd/oal-radio-$role.service" "$repo_root" "$wlan" \
    "/etc/systemd/system/oal-radio-$role.service" <<'PY'
from pathlib import Path
import sys
source, repo, wlan, destination = sys.argv[1:]
Path(destination).write_text(Path(source).read_text().replace('@REPO_ROOT@', repo).replace('@WLAN@', wlan))
PY
chmod 644 "/etc/systemd/system/oal-radio-$role.service"
systemctl daemon-reload
systemctl enable --now "oal-radio-$role.service"
systemctl is-active "oal-radio-$role.service"
echo "Radio service installed. Previous service units: $backup"
