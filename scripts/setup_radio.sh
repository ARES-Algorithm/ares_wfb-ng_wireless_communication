#!/usr/bin/env bash
# Configure a transparent UDP wireless endpoint; does not start services.
# Usage: sudo bash scripts/setup_radio.sh robot|controller wlan [keys-directory]
set -euo pipefail
role="${1:-}"
wlan="${2:-}"
keys_src="${3:-/etc}"
case "$role" in
    robot|controller) ;;
    *) echo 'Usage: sudo bash scripts/setup_radio.sh robot|controller wlan [keys-directory]' >&2; exit 1 ;;
esac
[[ "$EUID" == 0 && -n "$wlan" && $# -le 3 ]] || {
    echo 'Run as root and specify a wireless interface.' >&2; exit 1;
}
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_src="$repo_root/config/wifibroadcast-$role.cfg"
[[ -f "$config_src" ]] || { echo "Missing $config_src" >&2; exit 1; }
# Check all inputs before changing the installed profile.
for key in drone.key gs.key; do
    [[ -f "$keys_src/$key" ]] || { echo "Missing $keys_src/$key" >&2; exit 1; }
done
ip link show "$wlan" >/dev/null
region="$(python3 - "$config_src" <<'PY'
import ast
import configparser
import sys
cfg = configparser.ConfigParser(interpolation=None)
cfg.read(sys.argv[1])
region = ast.literal_eval(cfg['common']['wifi_region'])
if not isinstance(region, str) or len(region) != 2 or not region.isalpha():
    raise SystemExit('wifi_region must be a two-letter country code')
print(region.upper())
PY
)"
backup="$(mktemp -d /var/backups/wfb-config-XXXXXXXX)"
for target in /etc/wifibroadcast.cfg /etc/drone.key /etc/gs.key; do
    if [[ -f "$target" ]]; then cp -a "$target" "$backup/"; fi
done
install -m 644 "$config_src" /etc/wifibroadcast.cfg
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
echo "Configured $role on $wlan. Previous configuration: $backup"
echo 'Wireless services have not been started.'
