"""Explicit calibration and following for the target robot interface."""

from math import exp

import numpy as np

from .motion import JOINTS, Retargeter, describe_pose
from .pose_contract import OBSERVATION_SCHEMA, SIDES

MAX_FRAME_AGE = 0.55
PART_NAMES = {
    "left_shoulder": "左肩", "right_shoulder": "右肩",
    "left_elbow": "左肘", "right_elbow": "右肘",
    "left_wrist": "左腕", "right_wrist": "右腕",
    "left_hip": "左髋", "right_hip": "右髋",
}
POSE_HINTS = {
    "person_not_visible": "画面中未检测到人，请选用示教者清楚入镜的画面。",
    "more_than_one_person": "画面中检测到多人，请只保留一位示教者。",
    "upper_body_occluded": "肩、肘、腕或髋部识别不完整，请让上半身到髋部完整入镜。",
}
PALM_NAMES = {"left": "左手", "right": "右手"}


class FollowSession:
    def __init__(self, robot):
        self.robot = robot
        self.retarget = Retargeter(robot)
        self.bound = False
        self.state = "idle"
        self.reason = None
        self.track = None
        self.calibrated_track = None
        self.pose = None
        self.capture_time = None
        self.desired = None
        self.missing_keypoints = []

    def bind(self, available):
        self.robot.hold()
        self.bound = available
        self.state = "preview" if available else "idle"
        self.reason = None
        self.pose = None
        self.track = None
        self.calibrated_track = None
        self.capture_time = None
        self.desired = None
        self.missing_keypoints = []

    def pause(self, reason):
        if self.state == "following":
            self.robot.hold()
            self.desired = None
            self.state = "paused"
        self.reason = reason

    def fresh(self, now):
        return self.pose is not None and self.capture_time is not None and (
            0 <= now - self.capture_time <= MAX_FRAME_AGE
        )

    def observe(self, message, now):
        if not self.bound or message.get("schema") != OBSERVATION_SCHEMA:
            return
        captured = float(message["capture_time_s"])
        if self.capture_time is not None and captured <= self.capture_time:
            return
        self.capture_time = captured
        self.pose = None
        self.missing_keypoints = message.get("missing_keypoints", [])
        if not 0 <= now - captured <= MAX_FRAME_AGE:
            self.pause("input_stale")
            return
        if not message.get("valid"):
            self.pause(message.get("reason") or "pose_unavailable")
            return
        self.track = message["track_id"]
        try:
            self.pose = describe_pose(message["body"], message["hands"])
        except (IndexError, KeyError, TypeError, ValueError):
            self.pause("pose_geometry_unavailable")
            return
        if self.calibrated_track is not None and self.calibrated_track != self.track:
            self.calibrated_track = None
            self.pause("operator_changed")
            if self.state == "calibrated":
                self.state = "preview"
            return
        if self.state == "following":
            self.desired = self.retarget.solve(self.pose, self.robot.target)

    def _observation_hint(self, now):
        if not self.bound:
            return "请先开启智能控制，接入姿态识别卡。"
        if self.fresh(now):
            return None
        if self.capture_time is None:
            return "还未收到姿态帧，请确认浏览器摄像头正在采集。"
        if not 0 <= now - self.capture_time <= MAX_FRAME_AGE:
            return "姿态帧已过期，请将 Motus 保持在前台，并确认输入画面正在传送。"
        if self.reason == "upper_body_occluded" and self.missing_keypoints:
            parts = "、".join(PART_NAMES[name] for name in self.missing_keypoints
                             if name in PART_NAMES)
            if parts:
                return f"未可靠识别到{parts}。请退后一点，让上半身到髋部完整入镜。"
        return POSE_HINTS.get(self.reason, "姿态暂不可用，请让上半身到髋部完整入镜。")

    def missing_palms(self):
        return [side for side in SIDES if self.pose.arms[side].palm is None]

    def calibration_hint(self, now):
        if self.state == "following":
            return "当前正在跟随，请先暂停再重新标定。"
        hint = self._observation_hint(now)
        if hint is not None:
            return hint
        missing = self.missing_palms()
        if missing:
            palms = "、".join(PALM_NAMES[side] for side in missing)
            return f"未可靠识别到{palms}。标定腕部滚转需要双掌清楚入镜。"
        return None

    def calibrate(self, now):
        hint = self.calibration_hint(now)
        if hint is not None:
            raise ValueError(hint)
        self.retarget.calibrate(self.pose, self.robot.position)
        self.calibrated_track = self.track
        self.state = "calibrated"
        self.reason = None

    def follow(self, now):
        hint = self._observation_hint(now)
        if hint is not None:
            raise ValueError(hint)
        if self.calibrated_track is None or self.track != self.calibrated_track:
            raise ValueError("请先为当前示教者执行中立姿态标定。")
        self.desired = self.retarget.solve(self.pose, self.robot.target)
        self.state = "following"
        self.reason = None

    def tick(self, now, interval):
        if self.state == "following":
            if not self.fresh(now):
                self.pause("input_stale")
            else:
                delta = (self.desired - self.robot.target) * (1 - exp(-interval / 0.12))
                self.robot.set_target(self.robot.target + np.clip(delta, -interval, interval))
        self.robot.advance(interval)

    def command(self, now):
        if self.state != "following":
            return None
        return {"schema": "motus.vision2pose.joint_targets/1", "timestamp_s": now,
                "source_capture_time_s": self.capture_time,
                "joint_names": list(JOINTS), "position_rad": self.robot.target.tolist()}

    def status(self, now):
        fresh = self.fresh(now)
        return {
            "state": self.state, "reason": self.reason, "observation_fresh": fresh,
            "missing_palms": self.missing_palms() if fresh else None,
            "capture_time_s": self.capture_time, "track_id": self.track,
            "calibrated": self.calibrated_track is not None,
            "calibration_hint": self.calibration_hint(now),
            "feedback_source": "mujoco",
            "joints": [{"name": name, "q": float(q), "dq": float(dq), "target_q": float(target)}
                       for name, q, dq, target in zip(
                           JOINTS, self.robot.position, self.robot.velocity, self.robot.target)],
            "simulation_time_s": self.robot.data.time,
            "contacts": self.robot.data.ncon,
        }
