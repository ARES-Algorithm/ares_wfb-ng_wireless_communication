# 一键交互安装与重复配置

目标系统为 Ubuntu 22.04 / 24.04，目标架构为 x86_64 / aarch64，网卡芯片为 RTL8812EU / RTL8812AU。
实机验证范围见 [验证说明](verification.md)。
从克隆后的仓库根目录执行：

```bash
./scripts/setup.sh
```

脚本使用系统 Python，并自动请求 sudo。网卡应作为专用无线网卡。
依赖下载需要网络；驱动编译需要当前运行内核的匹配头文件。
DKMS 每次构建前根据目标头文件适配 cfg80211 监听信道回调接口，兼容 Ubuntu HWE 的接口回移。
安装中断后可重新运行向导，选择“安装/修复驱动和 WFB-NG”。

应用接口在两端一致：发送到本机 `127.0.0.1:5642`，接收绑定本机 `127.0.0.1:5641`。

仅安装和配置、不启动无线服务：

```bash
./scripts/setup.sh --configure-only
```

该模式保存无线配置与密钥，并停止已有的 `wfb-radio.service`，保留其已有自启状态。

## 默认值

| 提示 | 无已有配置时的默认值 |
|---|---|
| 芯片 | 8812eu |
| 本机角色 | robot（另一端选择 controller） |
| 安装/修复驱动和 WFB-NG | 未完整安装时 y，检测到完整安装后 n |
| 信道/频率 | 165（5825 MHz）；也可直接输入 MHz |
| 区域 | CN |
| 功率 | None，沿用驱动默认；EU 接受 0–3150，AU 接受 -10000–0 的驱动参数 |
| 带宽 | 20 MHz，可选 20 / 40 |
| FEC | robot：K=8、N=12；controller：K=1、N=3；要求 1 ≤ K ≤ N ≤ 255 |
| 生成密钥 | 无密钥时 y；已有密钥时 n |
| 种子 | 空：随机；非空：确定性派生，需要输入两次 |
| 无线接口 | 匹配所选芯片 WFB 驱动的接口；已保存接口仍匹配时优先使用 |
| 启动并开机自启 | y |

功率数值直接传给 WFB/驱动，不是精确测量的射频输出功率。两端频点、带宽、密钥等参数需匹配。
区域代码格式和数值边界检查不代替网卡/驱动实际支持性；不支持的无线组合可能无法启动服务。
模板的 MCS 默认值为 1；应用控制业务发包频率。

FEC 默认从所选角色的无线模板读取。重跑同一角色时保留已配置值；切换角色时采用新角色模板的 FEC 默认值。
接口列表显示驱动名，默认选择匹配所选芯片的专用网卡；输入其他驱动的接口会提示重新选择。
向导允许覆盖 K/N；K 设置后，N 的取值至少等于 K。FEC 是本端发送参数，两端可采用不同值。

## 密钥与重跑

- 同一非空种子在两端生成相同的一套 drone.key/gs.key。
- 两端种子都留空会生成不同随机密钥；随机模式须生成一次后分发完整的 drone.key/gs.key 密钥对到另一端 /etc/ares-wfb-ng/keys/，再运行向导选择保留密钥。该目录权限为 0700，密钥文件为 0600。
- 种子隐藏输入，不存储到配置、状态或日志，不写入调用向导的命令行。上游 wfb_keygen 只支持 argv 输入，派生瞬间种子可能被同机有权限的进程观察。
- 完整密钥对保存在 /etc/ares-wfb-ng/keys/，目录权限 0700，文件权限 0600。
- robot 选择生成的 drone.key 内容，controller 选择 gs.key 内容，均安装为 /etc/wfb-ng/link.key，权限 0600。两端运行密钥的路径相同，内容互补。
- 重跑可保留整套密钥，切换角色时从私有目录选择相应内容；选择生成时更新整套密钥。
- 参数读取自 /etc/wifibroadcast.cfg；非秘密安装状态保存在 /etc/ares-wfb-ng/setup.json。
- 重跑默认保留已有密钥，读取当前无线参数，网卡和芯片等默认值沿用上次成功设置。
- 配置和密钥变更前备份到 /var/backups/wfb-config-*，服务单元也备份在同一个目录。
- 不修改仓库内的配置模板，不把设备密钥写入仓库。
- 选择不启动时，停止 wfb-radio.service 并保存配置，保留该服务已有的自启状态。下次开机会按保存的角色和参数运行。

非特权预览时，私有密钥目录的状态以实际提权检查为准。

只预览、不安装、不写文件、不操作网卡、不读取种子：

```bash
./scripts/setup.sh --dry-run
```

在“开始应用上述设置”确认之前取消或结束输入，会退出向导并保留当前系统状态。
开始安装后，网络中断、输入结束或子命令失败可能留下已完成的安装步骤；再次运行向导可继续检查和修复。
配置写入后若启动失败，使用输出的备份恢复，或重新运行向导修正参数。

## Ubuntu 兼容处理

- 使用系统 /usr/bin/python3，按 Ubuntu 22.04 的 Python 3.10 和 24.04 的 Python 3.12 编写。
- 固定 WFB-NG wfb-ng-24.08，包含上游 Python 3.12 兼容修复。
- WFB Python 包装在 /opt/ares-wfb-ng/venv，使用系统 apt 的依赖；不向系统 Python 执行 pip install，不使用 --break-system-packages。
- 安装无线二进制和入口到 /usr/local/bin，配置 bin_dir 与之匹配；不安装或启动上游默认业务服务。
- 驱动使用 DKMS AUTOINSTALL，写入 /etc/modules-load.d/ares-wfb.conf 开机加载。
- 检查当前内核头文件，缺失时尝试安装 linux-headers-$(uname -r)。OEM/Jetson 内核需提供发行方匹配的头文件。
- 根据内核头文件的 GCC 版本补装编译器，覆盖 Ubuntu 22.04 HWE 内核和默认 GCC 不一致的情况。
- DKMS 源配置按目标内核选择已安装的对应 GCC；内核升级仍需要匹配头文件、可用编译器及驱动对该内核的支持。
- Secure Boot 启用时，如果 DKMS 签名密钥未被固件信任，需要完成 MOK 登记并重启，脚本不能代替固件确认。模块加载失败会停止并提示。
- 如果网卡已由另一个驱动绑定，向导会拒绝使用；重新插拔或重启后再次运行。不会强行卸载正在使用的网卡驱动。
- EU 驱动的功率控制选项写入 /etc/modprobe.d/ares-wfb.conf；修改模块选项后，重新加载模块或重启即可生效。

上游参考：[24.08 发布说明](https://github.com/svpcom/wfb-ng/releases/tag/wfb-ng-24.08)、[EU 功率说明](https://github.com/svpcom/rtl8812eu)。

Ubuntu 24.04、ARM64、驱动安装及重启验证的执行情况见 [验证说明](verification.md)。

## scripts 文件职责

| 文件 | 职责 |
|---|---|
| setup.sh | 用户入口、sudo 提权、并发锁、固定系统 Python |
| setup_wizard.py | 交互、参数校验、配置生成、密钥生成与状态保存 |
| install_wfbng.sh | apt 依赖、DKMS 驱动、隔离 WFB 运行环境 |
| deploy_radio.sh | 统一备份、网卡配置、密钥/配置安装和服务管理 |

`deploy_radio.sh --configure-only` 安装配置并停止 wfb-radio.service，保留该服务的自启状态。
默认调用会安装配置、启动 wfb-radio.service 并设置开机自启。切换角色时更新同一个服务的角色参数。
两端统计端口均为 8002，API 端口均为 8102，服务名称均为 wfb-radio.service。
systemd 服务直接通过 `/usr/local/bin/wfb-server` 启动，使用已安装的无线配置和密钥。
