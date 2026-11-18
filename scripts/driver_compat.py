#!/usr/bin/python3
"""Adapt the monitor callback to the target kernel's actual cfg80211 API."""

from pathlib import Path
import re
import sys


def adapt(source, headers):
    """Patch a DKMS build copy; tolerate repeated builds for different kernels."""
    header = (headers / 'include/net/cfg80211.h').read_text()
    callback = re.search(r'\(\*\s*set_monitor_channel\s*\)\s*\((.*?)\)\s*;',
                         header, re.DOTALL)
    if callback is None:
        raise ValueError('cannot find cfg80211_ops.set_monitor_channel in kernel headers')
    arguments = [re.sub(r'\s+', ' ', value.strip())
                 for value in callback[1].split(',')]
    expected = ['wiphy', 'cfg80211_chan_def']
    if len(arguments) == 3:
        expected.insert(1, 'net_device')
    if len(arguments) != len(expected) or any(
            not re.fullmatch(r'struct ' + kind + r'\s*\*\s*\w+', argument)
            for kind, argument in zip(expected, arguments)):
        raise ValueError(f'unsupported set_monitor_channel signature: {callback[1]}')
    path = source / 'os_dep/linux/ioctl_cfg80211.c'
    text = path.read_text()
    declaration = re.compile(
        r'static int cfg80211_rtw_set_monitor_channel\(.*?\)\s*\{', re.DOTALL)
    if len(declaration.findall(text)) != 1:
        raise ValueError('cannot identify the driver monitor callback unambiguously')
    params = ['struct wiphy *wiphy']
    if 'net_device' in expected:
        params.append('struct net_device *dev')
    params.append('struct cfg80211_chan_def *chandef')
    signature = ('static int cfg80211_rtw_set_monitor_channel(' +
                 ',\n\t'.join(params) + ')\n{')
    updated = declaration.sub(lambda _: signature, text, count=1)
    if updated != text:
        path.write_text(updated)
    print(f'ARES WFB: monitor callback adapted to {len(arguments)} kernel arguments',
          flush=True)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[A-Za-z0-9_.+-]+', sys.argv[1]):
        raise SystemExit('Usage: ares-driver-compat.py kernel-release')
    try:
        adapt(Path(__file__).resolve().parent,
              Path('/lib/modules') / sys.argv[1] / 'build')
    except (OSError, ValueError) as exc:
        raise SystemExit(f'ARES WFB driver compatibility check failed: {exc}')


if __name__ == '__main__':
    main()
