# Mac 有线真机联调

当前本地部署使用 Apple 芯片 Mac、Docker Desktop、`fourparadigm-intern-core-1` 容器和 `fourparadigm-intern_default` 网络。Mac 的 Q1 有线地址为 `10.1.1.99/24`，Q1 运控板为 `10.1.1.100`。检出本分支后，先进入仓库中的 `primebot/q1` 目录，再运行以下命令。电池消息由 Linux driver 解析。

## 本地构建

```bash
docker build --platform linux/arm64 \
  --build-arg ROS_BASE_IMAGE=bj-warehouse.tencentcloudcr.com/phanthy-motus/core:release.261118.56edda4 \
  -t primebot-q1:local .
```

## 启动有线回程与 driver

已能在画布看到实时电量时，可直接使用现有服务。以下为首次部署步骤。将有线网络位置切到 Q1。将下列 MOTUS_DIR 设置为本机包含 Core 部署和运行数据的 motus 目录。两个本地测试容器使用固定名称，首次创建后可以用 `docker start` 再次启动。

```bash
MOTUS_DIR="/path/to/motus"
Q1_DIR="$PWD"
mkdir -p "$MOTUS_DIR/.runtime/primebot-q1"
python3 "$Q1_DIR/tests/mac/dds_link.py" profile > "$MOTUS_DIR/.runtime/primebot-q1/fastdds.xml"

docker run -d --name primebot-q1-udp --network fourparadigm-intern_default \
  -p 127.0.0.1:17812:17810/udp -p 127.0.0.1:17813:17811/udp \
  -v "$Q1_DIR/tests/mac/dds_link.py:/link.py:ro" \
  primebot-q1:local /usr/bin/python3 /link.py ingress

docker run -d --name primebot-q1-local-status \
  --network container:fourparadigm-intern-core-1 --ipc container:fourparadigm-intern-core-1 \
  -v "$MOTUS_DIR/.runtime/primebot-q1/fastdds.xml:/q1-network.xml:ro" \
  -v "$MOTUS_DIR/phanthymotus/agent-core/deploy/dds-local.xml:/opt/phanthy-motus/dds-local.xml:ro" \
  -e Q1_FASTDDS_PROFILE=/q1-network.xml \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/opt/phanthy-motus/dds-local.xml \
  -e AGENT_CORE_URL=http://127.0.0.1:15678 primebot-q1:local

# 已由当前登录会话启动转发时，沿用该进程
if ! launchctl list local.motus.primebot-q1-discovery >/dev/null 2>&1; then
  python3 "$Q1_DIR/tests/mac/dds_link.py" discovery
fi
```

手动启动发现转发时，保持该终端运行。Mac 将 Q1 在域 0 的发现公告，以及返回到有线地址 17810/17811 的 RTPS 数据报送入 Docker。driver 的机器人侧使用此地址接收发现和回复，Core 侧继续通过回环网卡在域 42 发布画布数据。正常的 Linux 主机部署使用厂商提供的 DDS profile。[启元开发环境说明](https://github.com/PrimebotTech/primebot-q1-sdk/blob/main/docs/zh/SDK快速入门与集成指南.md)

在 [Motus 画布](http://127.0.0.1:15678) 添加启元 Q1 的 `status`，启动后点「查看数据流」。结束联调时在发现转发终端按 Ctrl-C，再执行：

```bash
docker stop primebot-q1-local-status primebot-q1-udp
```

再次接入时，先启动原 Core，再启动两个 Q1 容器，并重新运行 `dds_link.py discovery`。如重新创建了 Core 容器，需要重新创建共享其网络与 IPC 的 driver 容器。
