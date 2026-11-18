# 上层应用 UDP 接口

## 本机发送与本机接收

首先确认运行应用的设备在安装向导中选择了哪个角色，再按对应行使用地址：

| 本机角色 | 本机应用发送数据时填写的目标地址 | 本机应用接收数据时绑定的地址 |
|---|---|---|
| robot | `sendto(payload, ('127.0.0.1', 5642))` | `bind(('127.0.0.2', 5641))` |
| controller | `sendto(payload, ('127.0.0.1', 5641))` | `bind(('127.0.0.2', 5642))` |

发送时的 `127.0.0.1` 指本机 WFB-NG 的 UDP 监听端口。接收时的 `127.0.0.2` 指本机应用的 UDP 监听地址。
两者都是 Linux 回环地址，通常由系统直接提供。本文接口适用于应用和 WFB-NG 位于同一台设备的情况。

robot 发送的数据最终到达 controller 的 `127.0.0.2:5642`；
controller 发送的数据最终到达 robot 的 `127.0.0.2:5641`。
这一步跨设备传输由 WFB-NG 和无线网卡完成。

## 一个应用同时发送和接收

下面代码在两端各运行一份：robot 设备设 `ROLE = 'robot'`，controller 设备设 `ROLE = 'controller'`。
双方无线服务应处于运行状态，参数及密钥匹配。

```python
import socket
import time

ROLE = 'robot'  # controller 设备改为 'controller'
ENDPOINTS = {
    'robot': (('127.0.0.2', 5641), ('127.0.0.1', 5642)),
    'controller': (('127.0.0.2', 5642), ('127.0.0.1', 5641)),
}
bind_address, send_target = ENDPOINTS[ROLE]

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(bind_address)
    sock.settimeout(0.1)
    next_send = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= next_send:
            sock.sendto(('hello from ' + ROLE).encode(), send_target)
            next_send = now + 1.0
        try:
            payload, _ = sock.recvfrom(65535)
            print(payload)
        except socket.timeout:
            pass
```

接收绑定和发送目标是两个独立设置。同一个 socket 可以按上述方式接收数据，并通过 `sendto()` 发送到本机 WFB-NG。
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
- 模板 FEC 为 K=2、N=4，MCS 为 1；实际运行参数以 `/etc/wifibroadcast.cfg` 为准。
