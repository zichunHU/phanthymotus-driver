"""MCP and ROS lifecycle for the 3D Pose perception card."""

import json
from pathlib import Path
from threading import Condition, Thread
from time import time

from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from common.vendor_runtime import action_schema, run_driver, tool

from .perception import PoseDetector
from .pose_contract import CAMERA, OBSERVATION, OBSERVATION_SCHEMA, PREVIEW

QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
POSE_TOOL = {
    **tool(
        "pose_3d", "processor", "从 RGB 画面提取单人上半身与手部三维姿态",
        action_schema({
            "start": (["input_topic"], "接入 RGB 画面"),
            "stop": ([], "停止识别"),
            "info": ([], "查看输入状态"),
        }, {"input_topic": {"type": "string", "title": "输入话题"}}),
        topic_in=[{"topic": CAMERA, "format": "image/jpeg"}],
        topic_out=[
            {"topic": PREVIEW, "format": "sensor/pose2d"},
            {"topic": OBSERVATION, "format": "sensor/pose3d"},
        ],
    ),
    "title": "3D Pose",
}


class PoseCard:
    def __init__(self, config, ros):
        self.assets = Path(config["assets_dir"])
        self.node = ros.rclpy.create_node("motus_pose_3d", context=ros.ctx_core)
        ros.executor_core.add_node(self.node)
        self.frames = Condition()
        self.pending = None
        self.closed = False
        self.camera = None
        self.camera_topic = None
        self.camera_generation = 0
        self.last_observation = None
        self.observations = self.node.create_publisher(String, OBSERVATION, QOS)
        self.preview = self.node.create_publisher(String, PREVIEW, QOS)
        self.worker = Thread(target=self._infer, name="pose-3d-inference", daemon=True)

    def start(self):
        self.worker.start()

    def stop(self):
        with self.frames:
            self.closed = True
            self.frames.notify_all()
        self.worker.join()

    def get_tools(self):
        return (POSE_TOOL,)

    def _receive_image(self, image, generation):
        stamp = image.header.stamp
        captured = stamp.sec + stamp.nanosec / 1e9 or time()
        with self.frames:
            if generation == self.camera_generation:
                self.pending = bytes(image.data), captured, generation
                self.frames.notify()

    def _infer(self):
        detector = None
        previous_generation = None
        try:
            while True:
                with self.frames:
                    self.frames.wait_for(lambda: self.closed or self.pending is not None)
                    if self.closed:
                        return
                    jpeg, captured, generation = self.pending
                    self.pending = None
                try:
                    if detector is None:
                        detector = PoseDetector(self.assets)
                    if generation != previous_generation:
                        detector.center = None
                        previous_generation = generation
                    observation, preview = detector.detect(jpeg, captured)
                except (RuntimeError, ValueError, OSError) as exc:
                    observation = {"schema": OBSERVATION_SCHEMA, "capture_time_s": captured,
                                   "valid": False, "reason": str(exc)}
                    preview = None
                with self.frames:
                    if generation != self.camera_generation or self.closed:
                        continue
                    self.last_observation = observation
                    self.observations.publish(String(data=json.dumps(observation, allow_nan=False)))
                    if preview is not None:
                        self.preview.publish(String(data=json.dumps(preview, allow_nan=False)))
        finally:
            if detector is not None:
                detector.close()

    def dispatch(self, action, args):
        with self.frames:
            if action in ("start", "stop"):
                topic = (args.get("input_topic") or CAMERA) if action == "start" else None
                if topic != self.camera_topic:
                    self.camera_generation += 1
                    self.pending = None
                    self.last_observation = None
                    if self.camera is not None:
                        self.node.destroy_subscription(self.camera)
                        self.camera = None
                    self.camera_topic = topic
                    if topic:
                        generation = self.camera_generation
                        self.camera = self.node.create_subscription(
                            CompressedImage, topic, lambda msg: self._receive_image(msg, generation), QOS,
                        )
            return {"state": "running" if self.camera else "idle",
                    "input_topic": self.camera_topic,
                    "last_reason": self.last_observation["reason"] if self.last_observation else None,
                    "valid": bool(self.last_observation and self.last_observation["valid"]),
                    "topic_out": POSE_TOOL["topic_out"]}


def build(config, namespace, ros):
    return [PoseCard(config, ros)]


if __name__ == "__main__":
    run_driver(__file__, "pose-3d-local", POSE_TOOL["title"], build, category="perception")
