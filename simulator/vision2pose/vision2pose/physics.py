"""A suspended G1 with torque-limited MuJoCo position actuators."""

from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np

from .motion import ARM_NAMES, JOINTS, SIDES, unit


def suspended_model(source: Path):
    root = ET.parse(source).getroot()
    active = set(JOINTS)
    world = root.find("worldbody")
    for body in world.iter("body"):
        for joint in list(body):
            if joint.tag in ("joint", "freejoint") and joint.get("name") not in active:
                body.remove(joint)
    actuators = root.find("actuator")
    for actuator in list(actuators):
        if actuator.get("joint") not in active:
            actuators.remove(actuator)
    keys = root.find("keyframe")
    if keys is not None:
        root.remove(keys)
    # Load upstream meshes from the installed asset directory.
    compiler = root.find("compiler")
    compiler.set("meshdir", str((source.parent / compiler.get("meshdir", "")).resolve()))
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


class G1Simulation:
    def __init__(self, source: Path):
        self.model = suspended_model(source)
        self.data = mujoco.MjData(self.model)
        self.fit = mujoco.MjData(self.model)
        self.ids = np.array([self.model.joint(name).id for name in JOINTS])
        self.address = self.model.jnt_qposadr[self.ids]
        self.dofs = self.model.jnt_dofadr[self.ids]
        active_actuators = {
            int(self.model.actuator_trnid[index, 0]): index
            for index in range(self.model.nu)
        }
        self.actuator = [active_actuators[joint_id] for joint_id in self.ids]
        self.limits = self.model.jnt_range[self.ids]
        self.arm_indices = {side: np.array([JOINTS.index(name) for name in ARM_NAMES[side]])
                            for side in SIDES}
        self.torso = self.model.body("torso_link").id
        self.target = np.zeros(len(JOINTS))
        self.target[self.arm_indices["left"][1]] = 0.15
        self.target[self.arm_indices["right"][1]] = -0.15
        self.target = np.clip(self.target, self.limits[:, 0], self.limits[:, 1])
        self.data.qpos[self.address] = self.target
        self.data.ctrl[self.actuator] = self.target
        mujoco.mj_forward(self.model, self.data)
        self.wrist_sign = {}
        for side in SIDES:
            _, forearm = self.arm_directions(side, self.target)
            idx = self.arm_indices[side][4]
            local_axis = self.fit.xmat[self.torso].reshape(3, 3).T @ self.fit.xaxis[self.ids[idx]]
            self.wrist_sign[side] = 1.0 if np.dot(local_axis, forearm) >= 0 else -1.0

    @property
    def position(self):
        return self.data.qpos[self.address]

    @property
    def velocity(self):
        return self.data.qvel[self.dofs]

    def arm_directions(self, side, reference):
        self.fit.qpos[self.address] = reference
        mujoco.mj_kinematics(self.model, self.fit)
        joints = self.ids[self.arm_indices[side]]
        shoulder, elbow, wrist = self.fit.xanchor[joints[[0, 3, 4]]]
        local = self.fit.xmat[self.torso].reshape(3, 3).T
        return unit(local @ (elbow - shoulder)), unit(local @ (wrist - elbow))

    def set_target(self, value):
        self.target = np.clip(value, self.limits[:, 0], self.limits[:, 1])
        self.data.ctrl[self.actuator] = self.target

    def hold(self):
        self.set_target(self.position)

    def advance(self, interval):
        steps = max(1, round(interval / self.model.opt.timestep))
        for _ in range(steps):
            mujoco.mj_step(self.model, self.data)
