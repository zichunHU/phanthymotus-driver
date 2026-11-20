# 启元 Q1 探索版

`status` 是只读传感器卡。在 Motus 画布添加「启元 Q1 探索版 → status」并启动后，打开「查看数据流」可查看电池和当前运动模式。卡片每 0.5 秒向 Core 发布一次 JSON，默认话题为 `/primebot_q1/status`，格式为 `data/json`。

| 数据 | 真机接口 | 输出 |
| --- | --- | --- |
| 电池 | 订阅 `/aima/hal/bms/state`（`aimdk_msgs/msg/Bms`） | 电量百分比、电压 V、电流 A、输出功率 W、温度 °C、剩余容量 mAh、循环次数、厂商状态位。电流为负表示放电 |
| 运动模式 | 查询 `/aimdk_5Fmsgs/srv/GetMcAction`（`aimdk_msgs/srv/GetMcAction`） | 当前模式码、厂商描述、动作状态码、切换就绪标志和触发来源 |

`info` 返回卡片状态、输出话题与最近读数。`read` 读取当前快照，`start` 与 `stop` 控制画布输出。电池和运动模式独立标记新鲜度；`waiting` 表示尚待首条响应，`live` 表示 5 秒以内有读数，`stale` 保留过期样本与年龄，`unavailable` 表示查询超时或服务返回错误。

## 构建与运行

在驱动仓库根目录用仓库构建脚本构建 `primebot/q1`。部署到与 Q1 通信的 Linux 主机时，使用 [部署配置](deploy/service.yml)。镜像目标为 ARM64、ROS 2 Humble。容器包含启元 SDK 提交 `618d995d4362f981ab5945624f8be9343c2cb68b` 的完整 `aimdk_msgs` 包，随镜像编译。机器人侧在域 0 使用 SDK 的 Fast DDS 配置，Core 侧在域 42 使用 Motus 的本机 DDS 配置。驱动通过 15747 端口提供 MCP，沿用 X2 的公共运行时。机器人读取进程单独加载厂商 DDS 配置。[启元消息源码](https://github.com/PrimebotTech/primebot-q1-sdk/tree/618d995d4362f981ab5945624f8be9343c2cb68b/aimdk_msgs) · [X2 驱动](../../agibot/AimDK_X2/main.py)

在已接入 Q1 的 Linux ROS 环境加载启元工作空间后，可独立核对两种数据来源：

```bash
timeout 5 ros2 topic echo /aima/hal/bms/state --once
ros2 service call /aimdk_5Fmsgs/srv/GetMcAction aimdk_msgs/srv/GetMcAction '{}'
```

启元官方快速入门给出开发者模式、Ubuntu 22.04 / Humble 环境、网线直连和 BMS 读取步骤。服务类型、响应字段和状态码可查接口手册。[SDK 快速入门与集成指南](https://github.com/PrimebotTech/primebot-q1-sdk/blob/main/docs/zh/SDK快速入门与集成指南.md) · [接口说明](https://raw.githubusercontent.com/PrimebotTech/primebot-q1-sdk/main/docs/zh/接口说明.md)

本地集成测试及真机验证范围见[验证记录](验证记录.md)。
