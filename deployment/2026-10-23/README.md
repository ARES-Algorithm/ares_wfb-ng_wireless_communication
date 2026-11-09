# 双机部署记录（2026-10-23）

已完成机器人驱动、WFB-NG 与应用部署，并通过真实无线空口双向验证。

| 项目 | 机器人 | 遥控器（本机） |
|---|---|---|
| 主机 | ares@10.25.94.57 | gracekite-Laptop |
| 系统 | Ubuntu 22.04 / x86_64 / 6.8.0-138-generic | Ubuntu 24.04 / x86_64 / 7.0.0-38-generic |
| 专用无线网卡 | wlx140a022213a5 | wlx140a022213ac |
| WFB profile | robot | controller |
| 无线设置 | channel 165 / 5825 MHz / 20 MHz / oal-link | 相同 |
| 无线服务（系统级） | oal-radio-robot | oal-radio-controller |
| 应用服务（用户级） | oal-robot | oal-controller |
| 仓库路径 | /home/ares/omni-arm-link | /home/gracekite/Documents/MyFiles/RC_Projects/AlgoWorkspace-27/omni-arm-link |

机器人通过 DKMS 安装 realtek-rtl88x2eu/5.15.0.1~20230815，加载模块 8812eu。
WFB-NG 为 26.10.19.60646，两端使用本机已有源代码的相同版本。
密钥沿用仓库 config/keys 的既有密钥；机器人使用 /etc/drone.key，本机使用
/etc/gs.key（600 权限）。部署记录不包含密钥或登录密码。

无线服务已设置开机启动；用户应用已设置用户 systemd 默认目标启动。
应用当前正在运行：控制/遥测均为 200 Hz，遥控轴固定为零，关闭未同步时钟下的
单向延迟统计。机器人程序当前发送内置合成遥测，控制仅解码存储，尚无真实
传感器/电机接口，因此本次验收是通信栈与应用协议的验证。

## 验收

- 两端 CMake 构建成功，protocol_roundtrip 测试通过。
- 随机 340 字节负载、200 Hz、30 秒空口测试 PASS，详见 linktest/report.txt。
- 上行 TX/RX 5999/5958（丢包 0.683%）；下行 5958/5944（丢包 0.235%）。
- 往返 p50=9.997 ms、p95=14.977 ms、p99=15.047 ms、max=34.994 ms。
- FEC K/N=2/4，上行恢复 248 包、下行恢复 263 包，证明实际经过 WFB-NG。
- 测试后半程同时运行应用遥测与控制，统计包含这部分并行负载。
- 停止本机 oal-controller 后，机器人记录 entering SAFE state (control link lost)，
  超时配置为 500 ms；恢复服务后 safe_state=no。见 failsafe.log。
- 两端所有接口的 disable_ipv6 均为 0，见 verification.txt。

## 日常操作

本机查看收取的遥测与发送的控制统计：

```bash
journalctl --user -u oal-controller -f
systemctl status oal-radio-controller
```

机器人端查看控制帧和无线服务：

```bash
ssh ares@10.25.94.57
journalctl --user -u oal-robot -f
systemctl status oal-radio-robot
```

本机切换到交互控制（保持零轴，按 a/d/e/m/c/q）：

```bash
systemctl --user stop oal-controller
cd /home/gracekite/Documents/MyFiles/RC_Projects/AlgoWorkspace-27/omni-arm-link
scripts/run_controller.sh --interactive --no-auto-motion --no-measure-latency --print-rate 1
# 退出交互程序后恢复后台应用
systemctl --user start oal-controller
```

再次执行空口测试（需先正常 SSH 登录认证，或使用已认证的 SSH 复用连接）：

```bash
scripts/link_test_2host.sh run \
  --robot ares@10.25.94.57 --controller local \
  --robot-repo /home/ares/omni-arm-link \
  --duration 30 --rate 200 --size 340 \
  --robot-arg --random --controller-arg --random
```

## IPv6 约束

严禁在任何设备关闭 IPv6。此次发现上游 RTL8812EU 的 dkms-install.sh 会追加
全局禁用 IPv6 的 sysctl 配置，因此绕过该脚本，直接调用 dkms add/build/install，
并已同步修复仓库的 scripts/install_wfbng.sh。同时补全 Jinja2、YAML 运行依赖。

机器人 IPv6 始终保持启用。本机在本次部署前已有禁用配置，已从 /etc/sysctl.conf
移除禁用条目，并将所有接口恢复为启用；原配置备份在
/etc/sysctl.conf.oal-before-ipv6-restore。原有联网网卡持续使用，SSH 未迁移到专用电台。

上游来源：[RTL8812EU](https://github.com/svpcom/rtl8812eu)、
[WFB-NG](https://github.com/svpcom/wfb-ng)。
