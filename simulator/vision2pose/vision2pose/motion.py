"""Retarget one operator's torso, arm and palm directions to named joints."""

from dataclasses import dataclass
from math import atan2

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .pose_contract import SIDES
ARM_AXES = ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll")
ARM_NAMES = {
    side: tuple(f"{side}_{axis}_joint" for axis in ARM_AXES) for side in SIDES
}
WAIST = "waist_yaw_joint"
JOINTS = (WAIST,) + ARM_NAMES["left"] + ARM_NAMES["right"]


def unit(vector):
    length = np.linalg.norm(vector)
    if not np.isfinite(length) or length < 1e-6:
        raise ValueError("退化的骨段或掌面方向")
    return vector / length


def wrap(angle):
    return atan2(np.sin(angle), np.cos(angle))


def signed_angle(a, b, axis):
    a = unit(a - axis * np.dot(a, axis))
    b = unit(b - axis * np.dot(b, axis))
    return atan2(np.dot(np.cross(a, b), axis), np.dot(a, b))


def align(a, b):
    cross = np.cross(a, b)
    sine = np.linalg.norm(cross)
    cosine = np.clip(np.dot(a, b), -1.0, 1.0)
    if sine > 1e-6:
        return Rotation.from_rotvec(cross * (atan2(sine, cosine) / sine))
    if cosine > 0:
        return Rotation.identity()
    basis = np.eye(3)[np.argmin(abs(a))]
    return Rotation.from_rotvec(unit(np.cross(a, basis)) * np.pi)


@dataclass(frozen=True)
class Arm:
    upper: np.ndarray
    forearm: np.ndarray
    palm: np.ndarray | None


@dataclass(frozen=True)
class Pose:
    arms: dict[str, Arm]
    waist: float


def describe_pose(body, hands):
    """Camera-oriented body and hand positions, each with its own origin."""
    body = np.asarray(body, dtype=float)
    shoulders = body[[11, 12]]
    hips = body[[23, 24]]
    up = unit(shoulders.mean(axis=0) - hips.mean(axis=0))
    shoulder_left = shoulders[0] - shoulders[1]
    hip_left = hips[0] - hips[1]
    left = unit(shoulder_left - up * np.dot(shoulder_left, up))
    forward = unit(np.cross(left, up))
    torso = np.stack((forward, left, up))
    arms = {}
    for index, side in enumerate(SIDES):
        upper = unit(torso @ (body[13 + index] - shoulders[index]))
        forearm = unit(torso @ (body[15 + index] - body[13 + index]))
        palm = None
        if side in hands:
            try:
                hand = np.asarray(hands[side], dtype=float)
                lateral = unit(torso @ (hand[5] - hand[17]))
                palm = unit(lateral - forearm * np.dot(lateral, forearm))
            except (IndexError, TypeError, ValueError):
                palm = None
        arms[side] = Arm(upper, forearm, palm)
    return Pose(arms, signed_angle(hip_left, shoulder_left, up))


class Retargeter:
    def __init__(self, robot):
        self.robot = robot
        self.baseline = None

    def calibrate(self, pose, measured):
        self.baseline = pose
        self.reference = np.array(measured, dtype=float, copy=True)
        self.offsets = {}
        for side in SIDES:
            upper, forearm = self.robot.arm_directions(side, self.reference)
            human = pose.arms[side]
            self.offsets[side] = align(human.upper, upper), align(human.forearm, forearm)

    def solve(self, pose, previous):
        target = np.array(previous, dtype=float, copy=True)
        target[0] = self.reference[0] + wrap(pose.waist - self.baseline.waist)
        for side in SIDES:
            ix = self.robot.arm_indices[side]
            arm = pose.arms[side]
            base = self.baseline.arms[side]
            upper_offset, forearm_offset = self.offsets[side]
            upper_goal = upper_offset.apply(arm.upper)
            forearm_goal = forearm_offset.apply(arm.forearm)
            near = previous[ix[:4]]

            def error(angles):
                target[ix[:4]] = angles
                upper, forearm = self.robot.arm_directions(side, target)
                return np.concatenate((upper - upper_goal, forearm - forearm_goal,
                                       0.02 * (angles - near)))

            limits = self.robot.limits[ix[:4]]
            result = least_squares(
                error, np.clip(near, limits[:, 0], limits[:, 1]),
                bounds=(limits[:, 0], limits[:, 1]), max_nfev=18,
            )
            target[ix[:4]] = result.x
            if arm.palm is None:
                continue
            palm_at_zero_roll = align(base.forearm, arm.forearm).apply(base.palm)
            roll = signed_angle(palm_at_zero_roll, arm.palm, arm.forearm)
            target[ix[4]] = self.reference[ix[4]] + self.robot.wrist_sign[side] * roll
        return np.clip(target, self.robot.limits[:, 0], self.robot.limits[:, 1])
