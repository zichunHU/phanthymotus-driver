"""MCP and ROS lifecycle for the vision2pose simulation card."""

import json
from pathlib import Path
from threading import RLock
from time import time

from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from common.vendor_runtime import action_schema, run_driver, tool

from .control import FollowSession
from .motion import JOINTS
from .physics import G1Simulation
from .pose_contract import OBSERVATION

ROOT = "/vision2pose"
SIMULATION = f"{ROOT}/simulation"
TARGETS = f"{ROOT}/joint_targets"
QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
STEP = 0.02


def port(topic, fmt):
    return {"topic": topic, "format": fmt}


INPUT_TOPIC = {"input_topic": {"type": "string", "title": "输入话题"}}
TOOLS = (
    tool(
        "vision2pose", "actuator", "将人体上半身动作映射为 G1 双臂与躯干目标，并驱动本机 MuJoCo",
        action_schema({"start": (["input_topic"], "接入三维骨架并预览"),
                       "calibrate": ([], "采集本轮中立姿态"),
                       "follow": ([], "启动或续接跟随"),
                       "pause": ([], "暂停跟随"), "stop": ([], "停止跟随与预览"),
                       "info": ([], "查看状态与仿真关节反馈")}, INPUT_TOPIC),
        topic_in=[port(OBSERVATION, "sensor/pose3d")],
        topic_out=[port(SIMULATION, "sensor/skeleton"), port(TARGETS, "data/json")],
    ),
    tool("model", "resource", "G1 关节预览模型"),
)


class SimulationCard:
    def __init__(self, config, ros):
        self.assets = Path(config["assets_dir"])
        self.robot = G1Simulation(self.assets / "g1" / "g1.xml")
        self.session = FollowSession(self.robot)
        self.urdf = Path(config["preview_urdf"]).read_text()
        self.node = ros.rclpy.create_node("motus_vision2pose", context=ros.ctx_core)
        ros.executor_core.add_node(self.node)
        self.lock = RLock()
        self.closed = False
        self.pose_subscription = None
        self.pose_topic = None
        self.frame_count = 0
        self.simulation = self.node.create_publisher(String, SIMULATION, QOS)
        self.targets = self.node.create_publisher(String, TARGETS, QOS)

    def start(self):
        self.node.create_timer(STEP, self._tick)

    def stop(self):
        with self.lock:
            self.session.bind(False)
            self.closed = True

    def get_tools(self):
        return TOOLS

    def _publish(self, publisher, value):
        publisher.publish(String(data=json.dumps(value, allow_nan=False, ensure_ascii=False)))

    def _observe(self, message, subscription_topic):
        with self.lock:
            if self.pose_topic != subscription_topic or self.closed:
                return
            try:
                self.session.observe(json.loads(message.data), time())
            except (TypeError, ValueError, KeyError):
                self.session.pause("invalid_pose_message")

    def _tick(self):
        with self.lock:
            if self.closed:
                return
            now = time()
            self.session.tick(now, STEP)
            command = self.session.command(now)
            if command is not None:
                self._publish(self.targets, command)
            self.frame_count += 1
            if self.frame_count % 5 == 0:
                self._publish(self.simulation, self.session.status(now))

    def dispatch(self, action, args):
        with self.lock:
            if args["_tool_name"] == "model":
                return {"urdf": self.urdf, "joint_names": list(JOINTS)}
            if action in ("start", "stop"):
                topic = args.get("input_topic") or OBSERVATION if action == "start" else None
                if topic != self.pose_topic:
                    if self.pose_subscription is not None:
                        self.node.destroy_subscription(self.pose_subscription)
                        self.pose_subscription = None
                    self.pose_topic = topic
                    self.session.bind(bool(topic))
                    if topic:
                        self.pose_subscription = self.node.create_subscription(
                            String, topic, lambda msg: self._observe(msg, topic), QOS,
                        )
            now = time()
            if action == "calibrate":
                self.session.calibrate(now)
            elif action == "follow":
                self.session.follow(now)
            elif action == "pause":
                self.session.pause("operator_pause")
            return {**self.session.status(now), "input_topic": self.pose_topic,
                    "topic_out": TOOLS[0]["topic_out"]}


def build(config, namespace, ros):
    return [SimulationCard(config, ros)]


if __name__ == "__main__":
    run_driver(__file__, "vision2pose-local", "motus-vision2pose", build)
