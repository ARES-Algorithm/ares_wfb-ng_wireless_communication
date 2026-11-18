# ares_wfb-ng_wireless_communication

基于 WFB-NG 的双向 UDP 无线传输工程，提供驱动安装、密钥生成、无线配置与开机自启。
应用把 UDP 数据报交给本机 WFB-NG，对端 WFB-NG 将负载投递给对端应用。
应用负责定义消息格式，WFB-NG 负责无线封装、加密和 FEC。

项目贡献者及代码来源可通过 Git 提交历史追溯。

## 安装

在两台设备上分别克隆本项目，从仓库根目录执行：

```bash
./scripts/setup.sh
```

一端选择 `robot`，另一端选择 `controller`。这两个名称表示链路角色，可用于不同硬件和应用框架。
向导提供芯片、网卡、密钥种子、频点、区域、功率、带宽与 FEC 设置，并部署无线服务。
两端输入相同的非空种子，可以得到匹配的一套密钥；随机生成时，将同一套密钥分发到另一端。

已有配置时，向导显示当前参数作为默认值。修改参数或生成密钥时，再次执行同一命令。

```bash
./scripts/setup.sh --dry-run  # 交互预览
```

目标系统为 Ubuntu 22.04 / 24.04。完整默认值、安装条件及配置路径见 [安装说明](docs/setup.md)。

## 上层应用怎么收发

**所有下表地址都是运行该应用的设备自己的回环地址。** 应用向本机 WFB-NG 发送，
由无线链路将数据传到另一台设备。

| 你的应用运行在哪台设备 | 发送：`sendto()` 的目标地址 | 接收：`bind()` 的本机地址 | 收到谁的数据 |
|---|---|---|---|
| 配置为 `robot` 的设备 | `127.0.0.1:5642` | `127.0.0.2:5641` | controller 端应用 |
| 配置为 `controller` 的设备 | `127.0.0.1:5641` | `127.0.0.2:5642` | robot 端应用 |

例如，robot 应用发送 `b'hello'`：

```text
robot 设备                                      controller 设备
应用 sendto(127.0.0.1:5642)
          ↓
      本机 WFB-NG ────────── 无线 ──────────→ 本机 WFB-NG
                                                   ↓
                                  应用 bind(127.0.0.2:5642) 后 recvfrom()
```

在 **controller 设备**启动接收应用：

```python
import socket

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(('127.0.0.2', 5642))
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

controller 向 robot 发送时，目标使用本机 `127.0.0.1:5641`，robot 接收端绑定本机 `127.0.0.2:5641`。

`127.0.0.1` 和 `127.0.0.2` 都是 Linux 回环地址，通常可直接使用。WFB-NG 根据配置在两者之间完成本地数据交接。
完整双向示例、端口修改方法与传输约定见 [UDP 接口](docs/udp-interface.md)。

## 服务管理

robot 设备：

```bash
systemctl status oal-radio-robot.service
journalctl -u oal-radio-robot.service -f
```

controller 设备：

```bash
systemctl status oal-radio-controller.service
journalctl -u oal-radio-controller.service -f
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
