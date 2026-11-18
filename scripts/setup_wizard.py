#!/usr/bin/env python3
"""Interactive, repeatable setup for transparent UDP wireless endpoints."""

import argparse
import ast
import configparser
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import warnings


ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/etc/ares-wfb-ng/setup.json')
PROFILE = Path('/etc/wifibroadcast.cfg')
KEYS = Path('/etc')


def run(command, **kwargs):
    # Commands may include secrets internally; do not print command arguments.
    return subprocess.run(command, check=True, **kwargs)


def ask(label, default, convert=str):
    while True:
        value = input('{} [{}]: '.format(label, default)).strip()
        try:
            return convert(value if value else str(default))
        except (ValueError, TypeError) as exc:
            print('输入无效：{}'.format(exc))


def choice(*values):
    def convert(value):
        if value not in values:
            raise ValueError('请选择 ' + '/'.join(values))
        return value
    return convert


def number(low, high):
    def convert(value):
        n = int(value)
        if not low <= n <= high:
            raise ValueError('范围为 {}–{}'.format(low, high))
        return n
    return convert


def yes_no(label, default):
    return ask(label + ' (y/n)', 'y' if default else 'n', choice('y', 'n')) == 'y'


def read_secret(label):
    # Refuse getpass's echoing fallback instead of accidentally showing a seed.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(label)
        except getpass.GetPassWarning:
            raise ValueError('当前终端无法隐藏输入；请在交互式终端运行 ./scripts/setup.sh') from None


def channel(value):
    n = int(value)
    if not (1 <= n <= 196 or 2300 <= n <= 7125):
        raise ValueError('输入信道号 1–196，或频率 MHz 2300–7125')
    return n


def region(value):
    value = value.upper()
    if not re.fullmatch('[A-Z]{2}', value):
        raise ValueError('输入两位国家/地区代码，例如 CN、US')
    # Match regulatory database country codes when the distro database exists.
    database = Path('/usr/share/iso-codes/json/iso_3166-1.json')
    if database.is_file():
        codes = {entry['alpha_2'] for entry in json.loads(database.read_text())['3166-1']}
        if value not in codes:
            raise ValueError('不是有效的国家/地区代码')
    return value


def power(value, chipset):
    if value.lower() in ('none', 'auto'):
        return None
    n = int(value)
    if chipset == '8812eu' and not 0 <= n <= 3150:
        raise ValueError('8812eu 使用 0–3150 的驱动功率参数，或 None')
    if chipset == '8812au' and not -10000 <= n <= 0:
        raise ValueError('8812au 使用非正驱动参数（例如 -2000），或 None')
    return n


def check_os(path=Path('/etc/os-release')):
    values = {}
    for line in path.read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key] = value.strip('"')
    if values.get('ID') != 'ubuntu' or values.get('VERSION_ID') not in ('22.04', '24.04'):
        raise ValueError('仅支持 Ubuntu 22.04 / 24.04')
    return values['VERSION_ID']


def existing_settings():
    saved = {}
    if STATE.is_file():
        saved = json.loads(STATE.read_text())
    if PROFILE.is_file():
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(str(PROFILE))
        for field, section, key in (
            ('channel', 'common', 'wifi_channel'), ('region', 'common', 'wifi_region'),
            ('power', 'common', 'wifi_txpower'), ('bandwidth', 'base', 'bandwidth'),
            ('fec_k', 'radio_base', 'fec_k'), ('fec_n', 'radio_base', 'fec_n'),
        ):
            if cfg.has_option(section, key):
                saved[field] = ast.literal_eval(cfg[section][key])
        for role in ('robot', 'controller'):
            if cfg.has_section(role):
                saved['role'] = role
    return saved


def interfaces():
    return sorted(p.name for p in Path('/sys/class/net').iterdir()
                  if (p / 'wireless').exists() or (p / 'phy80211').exists())


def runtime_ready(chipset):
    marker = Path('/opt/ares-wfb-ng/venv/.system-python-version')
    boot = Path('/etc/modules-load.d/ares-wfb.conf')
    module = '8812eu' if chipset == '8812eu' else '88XXau_wfb'
    if not marker.is_file() or marker.read_text().strip() != '{}.{}'.format(*sys.version_info[:2]):
        return False
    if not boot.is_file() or module not in boot.read_text().splitlines():
        return False
    if not all(os.access('/usr/local/bin/' + name, os.X_OK)
               for name in ('wfb_keygen', 'wfb_tx', 'wfb_rx', 'wfb-server')):
        return False
    if not shutil.which('dkms'):
        return False
    result = subprocess.run(['dkms', 'status', '-k', os.uname().release],
                            capture_output=True, text=True)
    identity = 'realtek-rtl88x2eu' if chipset == '8812eu' else 'realtek-rtl88xxau'
    return result.returncode == 0 and any(identity in line and ': installed' in line
                                         for line in result.stdout.splitlines())


def render_profile(settings):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(str(ROOT / 'config' / ('wifibroadcast-' + settings['role'] + '.cfg')))
    for section, key, value in (
        ('common', 'wifi_channel', settings['channel']),
        ('common', 'wifi_region', settings['region']),
        ('common', 'wifi_txpower', settings['power']),
        ('base', 'bandwidth', settings['bandwidth']),
        ('radio_base', 'fec_k', settings['fec_k']),
        ('radio_base', 'fec_n', settings['fec_n']),
    ):
        cfg[section][key] = repr(value)
    return cfg


def write_state(settings):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.setup-', dir=str(STATE.parent))
    try:
        os.fchmod(fd, 0o644)  # Non-secret defaults must also be readable by --dry-run.
        with os.fdopen(fd, 'w') as file:
            json.dump(settings, file, indent=2)
            file.write('\n')
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def generate_keys(directory, seed):
    directory.mkdir(mode=0o700)
    command = ['wfb_keygen']
    if seed:
        command.append(seed)
    # Upstream accepts the seed via argv only; run() deliberately never logs it.
    old_umask = os.umask(0o077)
    try:
        run(command, cwd=str(directory))
    finally:
        os.umask(old_umask)
    for name in ('drone.key', 'gs.key'):
        path = directory / name
        if path.stat().st_size != 64:
            raise ValueError('生成的密钥大小不正确，未安装配置')
        path.chmod(0o600)


def validate_interface(name, chipset):
    if not re.fullmatch('[A-Za-z0-9_.:-]+', name) or name not in interfaces():
        raise ValueError('无线接口不存在，请检查网卡，必要时重新插拔后再次运行 scripts/setup.sh')
    module = Path('/sys/class/net') / name / 'device/driver/module'
    expected = '8812eu' if chipset == '8812eu' else '88xxau_wfb'
    if not module.exists() or module.resolve().name.lower() != expected:
        raise ValueError('该接口未使用已安装的 WFB 驱动；重新插拔网卡或重启后再运行 scripts/setup.sh')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Ubuntu 22.04/24.04 交互式无线安装与配置')
    parser.add_argument('--dry-run', action='store_true', help='交互预览，不安装、不写文件、不启动服务')
    args = parser.parse_args(argv)
    version = check_os()
    if not args.dry_run and os.geteuid() != 0:
        parser.error('请通过根目录 ./scripts/setup.sh 运行，或使用 sudo')
    print('Ubuntu {}，Python {}.{}；回车接受方括号中的默认值。'.format(
        version, sys.version_info.major, sys.version_info.minor))
    print('首次安装会安装系统软件与 DKMS 驱动；无线网卡应为专用网卡。')
    saved = existing_settings()
    settings = {}
    settings['chipset'] = ask('网卡芯片', saved.get('chipset', '8812eu'), choice('8812eu', '8812au'))
    settings['role'] = ask('本机角色', saved.get('role', 'robot'), choice('robot', 'controller'))
    install = yes_no('安装/修复驱动和 WFB-NG', not runtime_ready(settings['chipset']))
    settings['channel'] = ask('无线信道号，或直接输入频率 MHz（165=5825 MHz）',
                              saved.get('channel', 165), channel)
    settings['region'] = ask('部署区域', saved.get('region', 'CN'), region)
    print('功率 None=驱动默认；数值为驱动原始参数，不能当作精确实测 dBm。')
    try:
        previous_power = power(str(saved.get('power', 'None')), settings['chipset'])
    except ValueError:
        previous_power = None
    settings['power'] = ask('发射功率', previous_power,
                            lambda value: power(value, settings['chipset']))
    settings['bandwidth'] = ask('带宽 MHz', saved.get('bandwidth', 20),
                                lambda value: int(choice('20', '40')(value)))
    settings['fec_k'] = ask('FEC K（数据包数）', saved.get('fec_k', 2), number(1, 255))
    settings['fec_n'] = ask('FEC N（总包数，含冗余）', max(saved.get('fec_n', 4), settings['fec_k']),
                            number(settings['fec_k'], 255))
    have_keys = all((KEYS / name).is_file() and (KEYS / name).stat().st_size == 64
                    for name in ('drone.key', 'gs.key'))
    regenerate = yes_no('重新生成密钥' if have_keys else '生成密钥（首次需要）', not have_keys)
    if not regenerate and not have_keys:
        raise ValueError('没有已有密钥；请重新运行并选择生成')
    seed = ''
    if regenerate and not args.dry_run:
        print('两端输入相同非空种子可生成相同的一套密钥。默认留空=随机生成，需将同一套密钥分发到另一端。')
        while True:
            seed = read_secret('密钥种子 [留空随机，不保存种子]: ')
            if not seed or read_secret('再次输入种子: ') == seed:
                break
            print('两次种子不一致，请重试。')
    start = yes_no('应用后启动/重启无线服务并设置开机自启（n=仅配置，已有无线服务会停止）', True)
    print('配置预览：' + json.dumps(settings, ensure_ascii=False))
    print('密钥：{}；安装：{}；启动：{}'.format('重新生成' if regenerate else '保留', install, start))
    if args.dry_run:
        print('预览模式不读取密钥种子。')
        cards = interfaces()
        ask('无线接口（仅预览）', saved.get('interface', cards[0] if cards else 'wlan0'))
        print('预览结束：未修改文件、安装软件或启动服务。')
        return 0
    if not yes_no('开始应用上述设置', True):
        print('已取消，未应用设置。')
        return 0
    if install:
        run(['bash', str(ROOT / 'scripts/install_wfbng.sh'), settings['chipset']])
    elif not runtime_ready(settings['chipset']):
        raise ValueError('未检测到完整的系统级 WFB 安装及当前内核 DKMS 驱动，请选择安装/修复')
    cards = interfaces()
    if not cards:
        raise ValueError('未检测到无线网卡。驱动安装若已完成，请重新插拔网卡或重启后再次运行')
    print('无线接口：' + ', '.join(cards))
    settings['interface'] = ask('使用哪个无线接口', saved.get('interface', cards[0]))
    validate_interface(settings['interface'], settings['chipset'])
    with tempfile.TemporaryDirectory(prefix='ares-wfb-setup-') as directory:
        staging = Path(directory)
        key_dir = staging / 'keys'
        if regenerate:
            generate_keys(key_dir, seed)
            seed = ''
        else:
            key_dir = KEYS
        profile = staging / 'wifibroadcast.cfg'
        with profile.open('w') as file:
            render_profile(settings).write(file)
        command = ['bash', str(ROOT / 'scripts/deploy_radio.sh')]
        if not start:
            command.append('--configure-only')
        command.extend([settings['role'], settings['interface'], str(key_dir), str(profile)])
        run(command)
        write_state(settings)
    print('完成。密钥=/etc/drone.key、/etc/gs.key；配置=/etc/wifibroadcast.cfg。')
    print('重新运行 ./scripts/setup.sh 可修改参数或重新生成密钥；请同步更新通信另一端。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print('\n输入中断，安装可能未完成；可重新运行 ./scripts/setup.sh。', file=sys.stderr)
        raise SystemExit(130)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # CalledProcessError.cmd can contain secrets; deliberately omit it.
        message = '子命令执行失败，退出码 {}'.format(exc.returncode) if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print('设置失败：' + message, file=sys.stderr)
        raise SystemExit(1)
