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

Ubuntu 22.04 / 24.04 克隆后从仓库根目录运行：

```bash
./setup.sh
```

向导引导完成 DKMS 驱动安装、WFB-NG 安装、密钥种子输入、角色/网卡选择，
以及频点、区域、功率、带宽、FEC 配置，最后部署无线服务并设置开机自启。
再次运行同一命令可选择保留或重新生成密钥、修改配置；所有提示都有默认值。
同一链路两端输入相同非空种子；种子留空则随机生成，需分发同一套密钥。

```bash
./setup.sh --dry-run  # 只交互预览，不安装或修改系统
```

无已有配置时默认 EU、robot、信道165、区域CN、驱动默认功率、20MHz、FEC 2/4；重跑沿用已安装配置。
细节、默认值、系统路径、Secure Boot 与内核兼容限制见 [安装向导说明](docs/setup.md)。
底层脚本仍可单独调用，向导是推荐入口。服务使用仓库绝对路径，移动仓库后重新运行。

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
