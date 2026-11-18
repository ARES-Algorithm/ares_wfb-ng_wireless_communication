# ares_wfb-ng_wireless_communication

基于 WFB-NG 的双向 UDP 无线传输工程，提供驱动安装、密钥生成、无线配置与开机自启。
应用把 UDP 数据报交给本机 WFB-NG，对端 WFB-NG 将负载投递给对端应用。
应用负责定义消息格式，WFB-NG 负责无线封装、加密和 FEC。

目标系统为 Ubuntu 22.04 / 24.04。

## 安装

在两台设备上分别克隆本项目，从仓库根目录执行：

```bash
./scripts/setup.sh
```

一端选择 `robot`，另一端选择 `controller`。这两个名称表示链路角色，可用于不同硬件和应用框架。
向导提供芯片、网卡、密钥种子、频点、区域、功率、带宽与 FEC 设置，并部署无线服务。
两端输入相同的非空种子，可以得到匹配的一套密钥；随机生成时，将同一套密钥分发到另一端。

已有配置时，向导显示当前参数作为默认值。修改参数或生成密钥时，再次执行同一命令。

完整默认值、安装条件及配置路径见 [安装说明](docs/setup.md)。

## 上层应用怎么收发

**所有下表地址都是运行该应用的设备自己的回环地址。** 应用向本机 WFB-NG 发送，
由无线链路将数据传到另一台设备。

两端应用使用相同地址：

| 应用操作 | 本机地址 | Python 调用 |
|---|---|---|
| 发送到无线链路 | `127.0.0.1:5642` | `sock.sendto(payload, ('127.0.0.1', 5642))` |
| 接收对端数据 | `127.0.0.1:5641` | `sock.bind(('127.0.0.1', 5641))` 后 `recvfrom()` |

例如，robot 应用发送 `b'hello'`：

```text
robot 设备                                      controller 设备
应用 sendto(127.0.0.1:5642)
          ↓
      本机 WFB-NG ────────── 无线 ──────────→ 本机 WFB-NG
                                                   ↓
                                  应用 bind(127.0.0.1:5641) 后 recvfrom()
```

在 **controller 设备**启动接收应用：

```python
import socket

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(('127.0.0.1', 5641))
    while True:
        payload, _ = sock.recvfrom(65535)
        print(payload)
```

在 **robot 设备**发送数据：

```python
import socket

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.sendto(b'hello', ('127.0.0.1', 5642))
```

controller 向 robot 发送也使用本机 `127.0.0.1:5642`，robot 接收端绑定本机 `127.0.0.1:5641`。
每台设备上的 WFB-NG 监听 5642，应用监听 5641。

完整双向示例、端口修改方法与传输约定见 [UDP 接口](docs/udp-interface.md)。

## 链路角色

两端具有相同的发送与接收能力，应用端口、默认频点、带宽、功率和 MCS 一致，FEC 按方向配置。
角色用于选择互补的密钥内容、无线流和默认发送 FEC；运行路径和管理命令统一：

| 配置项 | robot | controller |
|---|---|---|
| 默认发送 FEC | K=8、N=12 | K=1、N=3 |
| 运行密钥路径 | /etc/wfb-ng/link.key | /etc/wfb-ng/link.key |
| 无线发送 Stream ID | 0x03 | 0x81 |
| 无线接收 Stream ID | 0x81 | 0x03 |
| WFB 统计端口 | 8002 | 8002 |
| WFB API 端口 | 8102 | 8102 |
| 服务名称 | wfb-radio | wfb-radio |

robot 的 FEC 默认面向较大数据流，controller 的 FEC 默认面向小包控制流。
向导将密钥对保存在本机私有目录 `/etc/ares-wfb-ng/keys/`，
按角色选择对应内容安装到 `/etc/wfb-ng/link.key`；该路径相同，两端内容互补。
两端各自为本端发送方向设置 FEC，接收端由 WFB-NG 会话获取对端纠错参数。
一条链路两端分别选择 robot 和 controller。上层应用的消息类型和发送频率由应用决定。

## 服务管理

两端使用相同命令：

```bash
systemctl status wfb-radio.service
journalctl -u wfb-radio.service -f
```

无线服务通过 `/usr/local/bin/wfb-server` 启动。配置、密钥和服务单元的备份路径在部署时输出。
恢复备份后，执行 `sudo systemctl daemon-reload` 并重启对应服务。

## 项目结构

```text
config/       双端无线配置模板
scripts/      交互入口、向导、依赖安装与统一部署
systemd/      无线服务模板
docs/         安装、UDP 接口和验证范围
```

数据报边界与负载字节是应用接口的一部分；可靠重传、排序、去重和大消息分片由上层应用负责。
当前验证范围见 [验证说明](docs/verification.md)。
