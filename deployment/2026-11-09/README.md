# arespi 实机通信部署（2026-11-09）

本机是遥控器，机器人为 arespi@10.166.241.115。
已先修复机器人端安装脚本、配置与密钥，再启动机器人无线服务和应用；本机沿用既有服务。
两端应用与无线服务均保持运行并设置开机启动，机器人用户已启用 linger。

| 项目 | 机器人 | 本机遥控器 |
|---|---|---|
| 项目目录 | /home/arespi/omni-arm-link | /home/gracekite/Documents/MyFiles/RC_Projects/AlgoWorkspace-27/omni-arm-link |
| 专用网卡 | wlx140a022213a5 | wlx140a022213ac |
| 系统无线服务 | oal-radio-robot | oal-radio-controller |
| 用户应用服务 | oal-robot | oal-controller |
| 信道 | 165 / 5825 MHz / 20 MHz | 相同 |
| link_domain | oal-link | 相同 |

机器人原 /etc/wifibroadcast.cfg 错配为 controller，已改为 robot。
两端仓库密钥原本不一致，已备份机器人密钥并同步本机既有密钥到机器人仓库及 /etc。
机器人已存在全局 disable_ipv6=1 配置，已改为 0，并恢复所有当前接口的 IPv6。
原配置备份：/etc/sysctl.conf.oal-before-20261109；密钥备份：config/keys.bak-20261109。
原安装脚本备份：scripts/install_wfbng.sh.before-20261109。
机器人安装脚本沿用本机已修复版本：8812EU 直接调用 DKMS，绕过禁用 IPv6 的上游辅助脚本，保留 ARM64 修正并补全 Jinja2/YAML 依赖。本次未重装驱动。
现有 wlan0 和本机 wlp0s20f3 继续提供 SSH/联网。

## 验收结果

- 两端构建及 protocol_roundtrip 测试通过。
- 真实 WFB 空口、随机 340 B、200 Hz、30 秒测试 PASS，同时运行应用控制和遥测。
- 上行 5999/5951，丢包 0.800%；下行 5951/5875，丢包 1.277%。
- RTT p50=10.006 ms，p95=15.031 ms，p99=15.170 ms，max=30.071 ms。
- 测试流 FEC K/N=2/4，上下行分别恢复 701/735 包。
- 停止遥控应用后，机器人按 500 ms 配置进入 SAFE；重启后 resuming normal operation，safe_state=no。
- 两端所有接口 disable_ipv6 均为 0。

证据见 linktest/report.txt、failsafe.log、verification-controller.txt 和 verification-robot.txt。
报告中的 Lost 为序号间隙统计，Loss % 按各方向 TX/RX 计算，两者口径不同。

当前为真实无线硬件上的通信测试：机器人仍发送程序内置合成遥测，接收控制仅解码保存，未接入电机/真实传感器。遥控轴保持零，单向时延统计已关闭，使用 RTT 验证延迟。

## 查看与交互测试

本机实时查看遥测：

```bash
journalctl --user -u oal-controller -f
```

机器人实时查看收到的控制：

```bash
ssh arespi@10.166.241.115
journalctl --user -u oal-robot -f
```

本机切换到键盘交互；以下设置使按键即时送入程序，退出时恢复终端设置：

```bash
systemctl --user stop oal-controller
cd /home/gracekite/Documents/MyFiles/RC_Projects/AlgoWorkspace-27/omni-arm-link
(
  saved_stty="$(stty -g)"
  trap 'stty "$saved_stty"' EXIT
  stty -icanon min 1 time 0
  scripts/run_controller.sh --interactive --no-auto-motion --no-measure-latency --print-rate 1
)
# a=使能，d=禁用，e=切换急停，m=切换模式，c=校准标志，q=退出
# 退出后恢复后台发送：
systemctl --user start oal-controller
```

严禁关闭 IPv6；不要运行上游 RTL8812EU 的 dkms-install.sh。

## 后续调整：持续互传、按需抓取

当前两端已启用重构后的 build 二进制，并使用 continuous/ 下的用户服务配置：
业务保持独立持续互发，--print-rate 0 --log-level warn，日常仅记录告警。
运行无线服务未重启，IPv6 未禁用。

日常测试改用 scripts/capture_link.py，按需读取 WFB-NG 统计，不额外注入无线测试流；
旧 link_test.sh / link_test_2host.sh 保留为显式主动压力/RTT 测试。

本次采集 30 秒，实际计数窗口约 29 秒，结果位于 passive-capture/：
- 控制 TX/RX 200.00/198.66 帧/s，应用帧速率 102.401/101.712 kbit/s。
- 遥测 TX/RX 200.00/199.93 帧/s，应用帧速率 588.801/588.589 kbit/s。
- RX 有效负载速率分别 57.213/543.805 kbit/s。
- 接收端 FEC 后损失率分别 0.672%/0.034%，这是正常业务流的本地窗口统计。
- 调试约 4.93 帧/s；额外 test_up/test_down 流空闲，未添加探测负载。

以上数据不能与先前额外负载下的 test_up/test_down 丢包率直接等同，流与 FEC 参数不同。
抓取结束后业务服务继续运行，采集进程退出。详细使用方法见项目 README 的
“持续互传与按需抓取”。
