# vision2pose · G1 本机仿真

**浏览器摄像头或本地视频 → 3D Pose → vision2pose → MuJoCo**

**3D Pose** 从单人 RGB 画面估计上半身和手部三维姿态。**vision2pose** 以手动标定的中立姿态为参考，驱动吊挂的宇树 G1 仿真模型。模型保留完整下半身，双侧肩、肘、腕滚转和腰偏航共 11 个自由度参与物理仿真。

## 启动本机环境

需要 Apple Silicon Mac 或 ARM64 Linux、Docker Compose、Python 3。把两个工作树放在同一父目录。配套 Core 版本是 [phanthymotus@ca805e8](https://github.com/zichunHU/phanthymotus/commit/ca805e88e13e201db809624ee5189b04ffb17a86)。

```bash
git clone --branch feat/g1-vision2pose https://github.com/zichunHU/phanthymotus.git
git clone --branch feat/g1-vision2pose https://github.com/zichunHU/phanthymotus-driver.git
cd phanthymotus-driver/simulator/vision2pose
bash run_local.sh start
```

启动脚本下载固定版本的 MediaPipe 模型和 MuJoCo Menagerie G1 模型，用锁定依赖的镜像运行 Core、3D Pose 和仿真服务。模型、环境缓存和画布数据写入 `.runtime/`。如果 Core 放在其他位置，设置 `PHANTHYMOTUS_CORE` 为其绝对路径。如果本机已占用 15678，启动时设置其他宿主机端口，例如 `MOTUS_PORT=15679 bash run_local.sh start`。

用 `bash run_local.sh status` 查看三个服务的状态，`bash run_local.sh logs` 查看日志，`bash run_local.sh stop` 停止服务。

## 配置画布与演示

1. 打开 [Motus 画布](http://127.0.0.1:15678)。添加浏览器摄像头 `remote_camera`、感知分区的 **3D Pose**，以及 **MOTUS-VISION2POSE** 下的 `vision2pose`。
2. 将摄像头的 `image/jpeg` 连到 **3D Pose**，再将 **3D Pose** 的 `sensor/pose3d` 连到 `vision2pose`。它的另一个输出 `sensor/pose2d` 可从卡片的「查看数据流」打开。
3. 使用本地视频时，在画布顶部点「视频输入 → 选择视频」，把预览停在一帧躯干朝前、双掌和髋部清楚可见的中立姿态。使用摄像头时，面向镜头自然站立，双手与躯干稍微分开。
4. 开启智能控制，在 `vision2pose` 手动执行 `calibrate`，再执行 `follow`。使用视频时，随后点播放。在同一张卡点「查看数据流」可观察 G1 仿真关节反馈。
5. 演示结束后点「停止智能控制」。切换输入后重新启动，并在新的画面上标定。

## 本机验证与接口

```bash
python3 prepare_assets.py
UV_CACHE_DIR=.runtime/uv-cache uv run --locked python -m unittest discover -s tests -v
```

运行本机测试需安装 uv。测试覆盖两侧上肢和腰偏航、碰撞接触、遮挡与续接、跟踪身份变化和帧龄控制。

| 接口 | 数据 |
| --- | --- |
| `pose_3d` | **3D Pose** 的 MCP 调用标识符 |
| `/vision2pose/person` | 人体和手部的二维骨架预览 |
| `/vision2pose/observation` | 带采集时间的三维姿态观测 |
| `/vision2pose/joint_targets` | 带关节名和源帧时间的弧度目标 |
| `/vision2pose/simulation` | MuJoCo 关节位置、速度和跟随状态 |

适用范围、失跟行为和现场验收事项见 [运行边界与验证](docs/运行边界与验证.md)。数据接口见 [ROS 关节目标 ADR](docs/adr/0001-pose-to-actuator-contract.md)。

人体和手部识别使用 MediaPipe，仿真模型来自 MuJoCo Menagerie。 [姿态模型](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) · [手部模型](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker) · [G1 模型](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1)
