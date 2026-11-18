# 透明 UDP 精简验证 — 2026-11-19

已完成的静态检查：

- scripts/*.sh 全部通过 bash -n。
- 两端配置可解析，仅包含 data_tx/data_rx，两端 stream ID 配对、profiles 引用正确。
- 两份 systemd 模板可替换仓库路径和网卡名，启动目标仅为 wfb_server.sh。
- 自有 C++ 应用、CMake、测试工具及旧业务配置已移除；旧资料归档于 docs/history。
- git diff --check 通过。

运行环境限制：

- 当前沙箱创建 UDP socket 返回 PermissionError: Operation not permitted，不能在这里完成任意字节负载回环或端到端验证。
- 未运行安装、网卡设置和服务部署脚本，未修改 /etc 或现有无线服务。
- 未进行实机无线吞吐、双向数据交付、功率与丢包测试。

在两台实际设备部署后，应由外部 UDP 应用检查双向端口、负载字节一致性和数据报边界。
本工程不再内置测试发包程序。历史测试报告只适用于历史版本。

## 交互安装向导 — 2026-11-19

新增 setup.sh / scripts/setup_wizard.py，并调整安装器支持 Ubuntu 22.04 / 24.04：

- 六项临时模拟验证通过：系统版本识别、参数范围与双端配置生成、无效输入重试、dry-run 无副作用、首次应用/重跑保留密钥与状态、应用前取消。
- 相同公开测试种子的两次实际 wfb_keygen 结果一致；不同种子不同；文件均为 64 字节、0600。
- 在本机 Ubuntu 22.04 / Python 3.10 实际运行 --help 和全默认 --dry-run，未修改系统配置。
- 向导可通过 Python 3.10 和 3.12 的语法解析；这不等于在 Python 3.12 上执行过。
- 从本地上游 Git 提取 wfb-ng-24.08，按安装器方式构建 Python wheel 成功，检查不包含绝对路径的系统 data_files。
- 动态 DKMS 编译器片段在本机 6.8 HWE 内核头文件上选出 gcc-12。
- Bash 语法与 git diff --check 通过。验证代码放在 /tmp，未恢复底层测试目录。

未在当前受限环境执行 apt 安装、DKMS 编译安装、modprobe、重启或服务配置。
Ubuntu 24.04、ARM64 和实际网卡上的完整首次安装/重跑仍需现场验证，不能宣称已经实机全兼容。
