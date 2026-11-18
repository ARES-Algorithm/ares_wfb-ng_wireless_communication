# 上层应用 UDP 接口

## 本机发送与本机接收

robot 和 controller 两端采用相同的本地接口：

| 应用操作 | 地址 | Python 调用 |
|---|---|---|
| 发送数据给本机 WFB-NG | `127.0.0.1:5642` | `sendto(payload, ('127.0.0.1', 5642))` |
| 接收 WFB-NG 投递的对端数据 | `127.0.0.1:5641` | `bind(('127.0.0.1', 5641))` 后 `recvfrom()` |

`127.0.0.1` 始终指运行应用的这台设备。本文接口适用于应用和 WFB-NG 位于同一台设备的情况。

```text
设备 A 应用 → A 本机 127.0.0.1:5642 → 无线 → B 本机 127.0.0.1:5641 → 设备 B 应用
设备 B 应用 → B 本机 127.0.0.1:5642 → 无线 → A 本机 127.0.0.1:5641 → 设备 A 应用
```

## 一个应用同时发送和接收

下面代码可直接在两台设备上各运行一份，应用地址相同。
双方无线服务应处于运行状态，频点、带宽和链路配置匹配，密钥来自同一套密钥对。
发送 FEC 分别采用各自角色的设置。

```python
import socket
import time

bind_address = ('127.0.0.1', 5641)
send_target = ('127.0.0.1', 5642)

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(bind_address)
    sock.settimeout(0.1)
    next_send = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= next_send:
            sock.sendto(b'hello', send_target)
            next_send = now + 1.0
        try:
            payload, _ = sock.recvfrom(65535)
            print(payload)
        except socket.timeout:
            pass
```

每台设备运行一个接收进程绑定 5641。接收绑定和发送目标是两个独立设置。同一个 socket 可以按上述方式接收数据，并通过 `sendto()` 发送到本机 WFB-NG。
接收端 `recvfrom()` 返回的来源地址属于本地 UDP 投递过程；发送方向请始终使用配置表中的固定目标。

## 无线配置中的 Stream ID

Stream ID 由 WFB-NG 使用，用于配对无线发送流和接收流。应用只需使用 UDP 地址。

| 无线方向 | Stream ID | 发射端配置 | 接收端配置 |
|---|---|---|---|
| robot → controller | `0x03` | robot `data_tx` | controller `data_rx` |
| controller → robot | `0x81` | controller `data_tx` | robot `data_rx` |

应用负载自行定义；Stream ID 位于 WFB 的无线封装中。

## 修改端口

仓库中的 `config/wifibroadcast-robot.cfg` 和 `config/wifibroadcast-controller.cfg` 提供默认接口。
`data_tx` 的 `listen://` 地址供本机应用发送；`data_rx` 的 `connect://` 地址供 WFB-NG 投递给本机接收应用。

例如，将 robot 端应用发送目标改为 `127.0.0.1:6000`，需要将 robot 的 `data_tx.peer` 改为
`listen://127.0.0.1:6000`，并同步修改 robot 应用的发送目标。
本地 UDP 端口与无线 Stream ID 分别配置，两台设备上的 UDP 端口可以不同；无线方向对应的 Stream ID 必须匹配。

安装向导按所选角色从模板生成 `/etc/wifibroadcast.cfg`。持久调整端口可修改模板后运行 `./scripts/setup.sh` 应用，
或直接编辑已安装配置并重启对应无线服务。

## 传输与参数

- 单个 UDP 数据报作为一个应用传输单位，成功交付时保留负载字节与数据报边界。
- 丢包、重复、乱序的处理由上层应用决定；需要可靠性时应在应用协议中定义相应机制。
- 每个接收地址由一个应用绑定；多个消费者可通过上层应用进行分发。
- 应用控制每秒发送多少包及每包长度，两个方向共享实际射频资源。
- 数据报大小上限取决于 WFB-NG 版本、编译配置和网卡。小消息可从 1200 字节以内开始，目标环境中确认最大包长和吞吐。
- 无线频点、区域、功率、带宽与 FEC 通过安装向导设置；功率取值含义依赖驱动。
- 模板发送 FEC 为 robot K=8/N=12、controller K=1/N=3，MCS 为 1；实际运行参数以 `/etc/wifibroadcast.cfg` 为准。
