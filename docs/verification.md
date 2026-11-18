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
