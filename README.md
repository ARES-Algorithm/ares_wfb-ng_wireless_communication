# ares_wfb-ng_wireless_communication

基于 WFB-NG 的通用双向 UDP 无线传输部署工程。应用将数据报发送到本地 UDP 端口，
对端从指定本地 UDP 地址接收。底层将应用负载视为不透明字节，不附加或解析业务协议。

本项目不再构建原 OAL1 C++ 应用，也不产生合成业务数据；实际无线收发由安装的 WFB-NG 完成。
原作者及贡献者保留在 Git 历史中，迁移前说明与部署记录位于 docs/history/。

## 接口

| 方向 | Stream ID | 发送应用的目标地址 | 接收应用绑定地址 |
|---|---|---|---|
| robot → controller | 0x03 | robot 127.0.0.1:5642 | controller 127.0.0.2:5642 |
| controller → robot | 0x81 | controller 127.0.0.1:5641 | robot 127.0.0.2:5641 |

robot/controller 仅表示链路两端的配置角色，不限制硬件和上层软件。
双方选择匹配的无线参数、流 ID、link_domain 和密钥。详见 [UDP 接口](docs/udp-interface.md)。

## 安装和部署

以下从仓库根目录执行。安装脚本会修改系统软件与驱动，部署脚本会切换无线配置和服务。

```bash
sudo bash scripts/install_wfbng.sh 8812eu
# 只在一端生成一套密钥，再通过可信方式分发给另一端；不要在两端各自生成。
bash scripts/gen_keys.sh /path/outside/repository/keys
# 检查 config/wifibroadcast-<role>.cfg 的频点、区域、功率、带宽与 FEC。
sudo bash scripts/deploy_radio.sh robot YOUR_WLAN /path/outside/repository/keys
# 另一端使用 controller YOUR_WLAN 和同一套密钥。
```

密钥最终安装为 /etc/drone.key 和 /etc/gs.key，权限 600。密钥已经在 /etc 时可省略最后一个参数。
setup_radio.sh 只安装配置、密钥和设置接口，不启动服务；deploy_radio.sh 完成无线 systemd 服务部署。
服务依赖仓库绝对路径；部署路径不能包含空格，移动仓库后重新部署。

默认配置沿用历史频点和区域设置，部署前将 wifi_region/wifi_channel 改为实际部署环境适用值。
wifi_txpower=None 表示不显式覆盖驱动默认功率。应用控制输入包频与包长；无线参数由配置控制。

## 服务与迁移

```bash
systemctl status oal-radio-robot.service
journalctl -u oal-radio-robot.service -f
# controller 端替换服务名中的 robot。
```

从旧版本迁移时，在原应用所属账户中停止并禁用旧 oal-robot/oal-controller/oal-monitor 用户服务；
如曾以系统服务安装旧应用，也应停止并禁用对应系统服务。部署前确认没有其他无线服务占用同一网卡。
旧应用二进制即使仍在磁盘上，本工程也不会启动它们。

旧 5601–5632 的控制、遥测、调试和测试流已经移除。历史配置与报告不代表当前接口。
部署备份目录由脚本输出，回退时恢复对应配置、密钥和服务单元，再重载并重启服务。

## 范围

只有 config/、scripts/、systemd/ 和文档需要部署，无须 CMake 编译。
不提供消息编解码、业务限频、分片、可靠重传或按序交付。消息格式及兼容性由两端应用约定。
原压力测试、仿真和报告工具已移除。实际验证范围见 [精简验证记录](docs/verification.md)。
