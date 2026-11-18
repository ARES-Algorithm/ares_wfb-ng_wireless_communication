#!/usr/bin/env bash
# Single deployment implementation: backup, configuration, keys, NIC and service.
# Usage: sudo bash scripts/deploy_radio.sh [--configure-only] robot|controller wlan [keys-directory] [profile-file]
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
usage() {
    echo 'Usage: sudo bash scripts/deploy_radio.sh [--configure-only] robot|controller wlan [keys-directory] [profile-file]'
}
configure_only=false
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
if [[ "${1:-}" == --configure-only ]]; then configure_only=true; shift; fi
role="${1:-}"
wlan="${2:-}"
keys_src="${3:-/etc}"
case "$role" in
    robot) other=controller ;;
    controller) other=robot ;;
    *) usage >&2; exit 1 ;;
esac
[[ "$EUID" == 0 && -n "$wlan" && $# -le 4 ]] || {
    echo 'Run as root and specify a wireless interface.' >&2; exit 1;
}
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="${4:-$repo_root/config/wifibroadcast-$role.cfg}"
[[ "$wlan" =~ ^[a-zA-Z0-9_.:-]+$ ]] || { echo 'Invalid wireless interface.' >&2; exit 1; }
[[ -f "$profile" ]] || { echo "Missing $profile" >&2; exit 1; }
for key in drone.key gs.key; do
    [[ -f "$keys_src/$key" && "$(stat -c %s "$keys_src/$key")" == 64 ]] || {
        echo "Missing or invalid 64-byte key: $keys_src/$key" >&2; exit 1;
    }
done
ip link show "$wlan" >/dev/null
[[ -x /usr/local/bin/wfb-server ]] || { echo 'Install WFB-NG using scripts/setup.sh first.' >&2; exit 1; }
# Validate the supplied configuration before stopping services or replacing files.
region="$(/usr/bin/python3 - "$profile" "$role" <<'PY'
import ast
import configparser
import re
import sys
cfg = configparser.ConfigParser(interpolation=None)
cfg.read(sys.argv[1])
if not cfg.has_section(sys.argv[2]):
    raise SystemExit('Profile does not contain the requested role')
region = ast.literal_eval(cfg['common']['wifi_region'])
if not isinstance(region, str) or not re.fullmatch('[A-Za-z]{2}', region):
    raise SystemExit('wifi_region must be a two-letter country code')
print(region.upper())
PY
)"
backup="$(mktemp -d /var/backups/wfb-config-XXXXXXXX)"
for target in /etc/wifibroadcast.cfg /etc/drone.key /etc/gs.key \
    "/etc/systemd/system/oal-radio-$role.service" \
    "/etc/systemd/system/oal-radio-$other.service"; do
    if [[ -f "$target" ]]; then cp -a "$target" "$backup/"; fi
done
echo "Previous configuration, keys and service units: $backup"
# A role switch must not leave the opposite service enabled for the next boot.
if systemctl cat "oal-radio-$other.service" >/dev/null 2>&1; then
    systemctl disable --now "oal-radio-$other.service"
fi
if systemctl cat "oal-radio-$role.service" >/dev/null 2>&1; then
    systemctl stop "oal-radio-$role.service"
fi
install -m 644 "$profile" /etc/wifibroadcast.cfg
for key in drone.key gs.key; do
    if [[ "$keys_src/$key" -ef "/etc/$key" ]]; then
        chmod 600 "/etc/$key"
    else
        install -m 600 "$keys_src/$key" "/etc/$key"
    fi
done
ip link set "$wlan" up
ip link set "$wlan" mtu 2312 || true
ip link set "$wlan" txqueuelen 1000
iw reg set "$region"
/usr/bin/python3 - "$repo_root/systemd/oal-radio-$role.service" "$wlan" \
    "/etc/systemd/system/oal-radio-$role.service" <<'PY'
from pathlib import Path
import sys
source, wlan, destination = sys.argv[1:]
Path(destination).write_text(Path(source).read_text().replace('@WLAN@', wlan))
PY
chmod 644 "/etc/systemd/system/oal-radio-$role.service"
systemctl daemon-reload
if "$configure_only"; then
    echo 'Configuration installed; radio service stopped. Existing enabled state for this role is preserved.'
else
    systemctl enable --now "oal-radio-$role.service"
    systemctl is-active "oal-radio-$role.service"
    echo 'Radio service configured, started and enabled for boot.'
fi
