#!/usr/bin/env bash
# Persistent DKMS driver + isolated WFB-NG runtime for Ubuntu 22.04 / 24.04.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chipset="${1:-8812eu}"
case "$chipset" in
    8812eu) branch=v5.15.0.1 ;;
    8812au) branch=v5.2.20 ;;
    *) echo 'Usage: sudo bash scripts/install_wfbng.sh [8812eu|8812au]' >&2; exit 1 ;;
esac
[[ "$EUID" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && ( "$VERSION_ID" == 22.04 || "$VERSION_ID" == 24.04 ) ]] || {
    echo 'Supported systems: Ubuntu 22.04 / 24.04.' >&2; exit 1;
}
case "$(uname -m)" in
    x86_64|aarch64) ;;
    *) echo 'Supported architectures: x86_64 / aarch64.' >&2; exit 1 ;;
esac
apt-get update
apt-get install -y dkms git build-essential pkg-config libpcap-dev libsodium-dev libevent-dev \
    python3 python3-dev python3-venv python3-pip python3-wheel python3-setuptools \
    python3-pyroute2 python3-twisted python3-serial python3-msgpack python3-jinja2 python3-yaml \
    iw iproute2 ethtool socat mokutil
kernel="$(uname -r)"
if [[ ! -f "/lib/modules/$kernel/build/Makefile" ]]; then
    apt-get install -y "linux-headers-$kernel" || {
        echo "Cannot install headers for $kernel. Install matching OEM/Jetson/Raspberry Pi headers, then rerun scripts/setup.sh." >&2
        exit 1
    }
fi
[[ -f "/lib/modules/$kernel/build/Makefile" ]] || { echo 'Matching kernel headers are missing.' >&2; exit 1; }
# Ubuntu 22.04 HWE kernels may require gcc-12 although build-essential installs
# gcc-11; use the compiler major recorded by the running kernel's headers.
gcc_version="$(sed -n 's/^CONFIG_GCC_VERSION=//p' "/lib/modules/$kernel/build/.config" 2>/dev/null || true)"
if [[ "$gcc_version" =~ ^[0-9]+$ && "$gcc_version" -gt 0 ]]; then
    gcc_major=$((gcc_version / 10000))
    if ! command -v "gcc-$gcc_major" >/dev/null; then
        apt-get install -y "gcc-$gcc_major"
    fi
fi
source_dir="/usr/src/ares-rtl$chipset"
if [[ ! -d "$source_dir/.git" ]]; then
    git clone --branch "$branch" --single-branch "https://github.com/svpcom/rtl$chipset.git" "$source_dir"
fi
cd "$source_dir"
# Both driver repositories provide correct DKMS identities; avoid their legacy
# dkms-install.sh scripts, which also change global IPv6 settings.
if [[ "$(uname -m)" == aarch64 ]] && ! grep -q 'ARCH=arm64' dkms.conf; then
    sed -i 's|KSRC=/lib/modules/${kernelver}/build"|KSRC=/lib/modules/${kernelver}/build ARCH=arm64"|' dkms.conf
fi
package_name="$(sed -n 's/^PACKAGE_NAME="\([^"]*\)"/\1/p' dkms.conf)"
package_version="$(sed -n 's/^PACKAGE_VERSION="\([^"]*\)"/\1/p' dkms.conf)"
module_name="$(sed -n 's/^BUILT_MODULE_NAME\[0\]=["\x27]*\([^"\x27]*\)["\x27]*$/\1/p' dkms.conf)"
[[ -n "$package_name" && -n "$package_version" && -n "$module_name" ]] || {
    echo 'Cannot parse upstream dkms.conf.' >&2; exit 1;
}
# Read the complete status before testing it. With pipefail, grep -q can
# close the pipe early and make dkms exit 141 even for an installed driver.
dkms_registered_state="$(dkms status -m "$package_name" -v "$package_version")"
if [[ -z "$dkms_registered_state" ]]; then
    dkms add "$source_dir"
fi
# Apply compiler selection to the registered source (it may predate this clone).
registered_conf="/var/lib/dkms/$package_name/$package_version/source/dkms.conf"
if ! grep -q '# ares-wfb kernel compiler' "$registered_conf"; then
    cat >> "$registered_conf" <<'DKMS_COMPILER'
# ares-wfb kernel compiler: evaluated separately for each kernel by DKMS.
wfb_kernel="${kernelver:-$(uname -r)}"
wfb_gcc_version=$(sed -n 's/^CONFIG_GCC_VERSION=//p' "/lib/modules/$wfb_kernel/build/.config" 2>/dev/null)
if [ -n "$wfb_gcc_version" ] && [ "$wfb_gcc_version" -gt 0 ]; then
    wfb_gcc_major=$((wfb_gcc_version / 10000))
    if command -v "gcc-$wfb_gcc_major" >/dev/null 2>&1; then
        MAKE="$MAKE CC=gcc-$wfb_gcc_major"
    fi
fi
DKMS_COMPILER
fi
# DKMS may already point at a source copy created by an earlier installation.
# Install the hook into that registered source so kernel autoinstall uses it too.
registered_source="$(dirname "$registered_conf")"
if ! grep -q '# ares-wfb cfg80211 compatibility' "$registered_conf"; then
    if grep -Eq '^[[:space:]]*PRE_BUILD=' "$registered_conf"; then
        echo "Existing PRE_BUILD in $registered_conf; review it before adding the ARES compatibility hook." >&2
        exit 1
    fi
    cat >> "$registered_conf" <<'DKMS_COMPAT'
# ares-wfb cfg80211 compatibility: detect the target headers at each build.
PRE_BUILD="ares-driver-compat.py ${kernelver}"
DKMS_COMPAT
fi
install -m 755 "$script_dir/driver_compat.py" "$registered_source/ares-driver-compat.py"
dkms_state="$(dkms status -m "$package_name" -v "$package_version" -k "$kernel")"
if ! grep -Eq ': (built|installed)' <<< "$dkms_state"; then
    if dkms build -m "$package_name" -v "$package_version" -k "$kernel"; then
        :
    else
        build_status=$?
        build_log="/var/lib/dkms/$package_name/$package_version/build/make.log"
        echo "Driver build failed; compiler log: $build_log" >&2
        [[ ! -f "$build_log" ]] || tail -n 60 "$build_log" >&2
        exit "$build_status"
    fi
fi
if ! grep -q ': installed' <<< "$dkms_state"; then
    dkms install -m "$package_name" -v "$package_version" -k "$kernel"
fi
install -d /etc/modprobe.d
if [[ "$chipset" == 8812eu ]]; then
    printf '%s\n' 'options 8812eu rtw_tx_pwr_by_rate=0 rtw_tx_pwr_lmt_enable=0' > /etc/modprobe.d/ares-wfb.conf
else
    # AU power control is implemented by its WFB-patched driver.
    printf '%s\n' '# WFB-patched 8812au driver' > /etc/modprobe.d/ares-wfb.conf
fi
depmod -a "$kernel"
if ! modprobe "$module_name"; then
    echo "Cannot load $module_name. If Secure Boot is enabled, enroll the DKMS signing MOK and reboot; otherwise inspect dmesg. Then rerun scripts/setup.sh." >&2
    exit 1
fi
install -d /etc/modules-load.d
printf '%s\n' "$module_name" > /etc/modules-load.d/ares-wfb.conf

# Fixed release supports Python 3.12 (Ubuntu 24.04). A system-site-packages venv
# uses distro Twisted/pyroute2, without pip modifying the OS-managed interpreter.
runtime=/opt/ares-wfb-ng
install -d "$runtime"
if [[ ! -d "$runtime/source/.git" ]]; then
    git clone --branch wfb-ng-24.08 --single-branch https://github.com/svpcom/wfb-ng.git "$runtime/source"
fi
cd "$runtime/source"
[[ "$(git describe --tags --exact-match HEAD)" == wfb-ng-24.08 ]] || {
    echo 'Unexpected WFB source version; expected wfb-ng-24.08.' >&2; exit 1;
}
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
    echo 'WFB source has local changes; review them before reinstalling.' >&2; exit 1;
}
# The pinned release exports VERSION from Makefile variables; it has no
# "version" target. Compute metadata explicitly so failures stop before pip.
wfb_commit="$(git rev-parse HEAD)"
wfb_timestamp="$(git show -s --format=%ct "$wfb_commit")"
wfb_branch="$(git rev-parse --abbrev-ref HEAD)"
wfb_version="$(/usr/bin/python3 ./version.py "$wfb_timestamp" "$wfb_branch")"
[[ -n "$wfb_version" && -n "$wfb_commit" ]] || {
    echo 'Cannot determine WFB-NG package version and commit.' >&2; exit 1;
}
make -j"$(nproc)" VERSION="$wfb_version" COMMIT="$wfb_commit" all_bin
# An upgraded /usr/bin/python3 can make an old venv report the new version even
# though its site-packages directory is still named for the old interpreter.
python_version="$(/usr/bin/python3 -c 'import sys; print("%s.%s" % sys.version_info[:2])')"
if [[ -d "$runtime/venv" ]] && \
   [[ "$(cat "$runtime/venv/.system-python-version" 2>/dev/null || true)" != "$python_version" ]]; then
    mv "$runtime/venv" "$runtime/venv.old-$(date +%s)"
fi
/usr/bin/python3 -m venv --system-site-packages "$runtime/venv"
printf '%s\n' "$python_version" > "$runtime/venv/.system-python-version"
# 24.08 setup.py has absolute system data_files. Build its Python wheel from
# a temporary copy with data_files removed, and install radio binaries explicitly.
staging="$(mktemp -d /tmp/ares-wfb-build-XXXXXXXX)"
trap 'rm -rf "$staging"' EXIT
git archive HEAD | tar -x -C "$staging"
/usr/bin/python3 - "$staging/setup.py" <<'PYBUILD'
import ast
from pathlib import Path
import sys
path = Path(sys.argv[1])
tree = ast.parse(path.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'setup':
        for keyword in node.keywords:
            if keyword.arg == 'data_files':
                keyword.value = ast.List(elts=[], ctx=ast.Load())
path.write_text(ast.unparse(ast.fix_missing_locations(tree)) + '\n')
PYBUILD
VERSION="$wfb_version" COMMIT="$wfb_commit" SOURCE_DATE_EPOCH="$wfb_timestamp" \
    "$runtime/venv/bin/python3" -m pip install --no-deps --no-build-isolation --ignore-installed "$staging"
for binary in wfb_tx wfb_rx wfb_keygen wfb_tx_cmd; do
    install -m 755 "$binary" "/usr/local/bin/$binary"
done
for entry in wfb-server wfb-cli; do
    printf '#!/usr/bin/env bash\nexec /opt/ares-wfb-ng/venv/bin/%s "$@"\n' "$entry" > "/usr/local/bin/$entry"
    chmod 755 "/usr/local/bin/$entry"
done
"$runtime/venv/bin/python3" -c 'import wfb_ng.server, twisted, pyroute2'
echo "Installed $module_name with DKMS AUTOINSTALL and boot loading; WFB-NG runtime is ready."
