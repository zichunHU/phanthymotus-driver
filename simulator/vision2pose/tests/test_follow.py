from pathlib import Path
import unittest

import numpy as np
import mujoco
from scipy.spatial.transform import Rotation

from vision2pose.control import FollowSession
from vision2pose.motion import JOINTS, align, unit
from vision2pose.pose_contract import OBSERVATION_SCHEMA, SIDES
from vision2pose.physics import G1Simulation

MODEL = Path(__file__).resolve().parents[1] / ".runtime/assets/g1/g1.xml"


class FollowTest(unittest.TestCase):
    def setUp(self):
        self.robot = G1Simulation(MODEL)
        self.session = FollowSession(self.robot)
        self.session.bind(True)
        self.reference = self.robot.position

    def observation(self, captured, target=None, track=1):
        target = self.reference if target is None else target
        yaw = target[0] - self.reference[0]
        torso = Rotation.from_rotvec(np.array([0, 0, yaw]))
        body = np.zeros((33, 3))
        body[23:25] = [[0, 0.15, 0], [0, -0.15, 0]]
        body[11:13] = torso.apply([[0, 0.20, 0.50], [0, -0.20, 0.50]])
        hands = {}
        for index, side in enumerate(SIDES):
            upper, forearm = self.robot.arm_directions(side, target)
            _, base_forearm = self.robot.arm_directions(side, self.reference)
            lateral = np.array([0, 1, 0])
            base_palm = unit(lateral - np.dot(lateral, base_forearm) * base_forearm)
            palm = align(base_forearm, forearm).apply(base_palm)
            roll_idx = self.robot.arm_indices[side][4]
            roll = (target[roll_idx] - self.reference[roll_idx]) * self.robot.wrist_sign[side]
            palm = Rotation.from_rotvec(roll * forearm).apply(palm)
            body[13 + index] = body[11 + index] + 0.28 * torso.apply(upper)
            body[15 + index] = body[13 + index] + 0.25 * torso.apply(forearm)
            hand = np.zeros((21, 3))
            hand[5] = 0.03 * torso.apply(palm)
            hand[17] = -hand[5]
            hands[side] = hand.tolist()
        return {"schema": OBSERVATION_SCHEMA, "capture_time_s": captured, "valid": True,
                "body": body.tolist(), "hands": hands, "track_id": track}

    def begin(self, stamp=10.):
        self.session.observe(self.observation(stamp), stamp)
        self.session.calibrate(stamp)
        self.session.follow(stamp)

    def test_real_physics_follows_bilateral_arm_and_waist_targets(self):
        self.assertEqual(self.robot.model.nq, len(JOINTS))
        self.assertEqual(self.robot.model.nu, len(JOINTS))
        self.assertTrue(self.robot.model.actuator_forcelimited.all())
        self.begin()
        desired = self.reference + np.array([0.23, -0.16, 0.14, 0.11, 0.31, 0.31,
                                            -0.09, -0.12, -0.10, 0.18, -0.22])
        for step in range(1, 91):
            stamp = 10 + 0.02 * step
            if step == 1 or step % 5 == 0:
                self.session.observe(self.observation(stamp, desired), stamp)
            self.session.tick(stamp, 0.02)
        command = self.session.command(stamp)
        self.assertEqual(command["joint_names"], list(JOINTS))
        self.assertGreater(self.robot.data.time, 1.7)
        np.testing.assert_allclose(self.robot.target[[0, 5, 10]], desired[[0, 5, 10]], atol=0.04)
        np.testing.assert_allclose(self.robot.position[[0, 5, 10]], desired[[0, 5, 10]], atol=0.07)
        self.assertGreater(self.robot.position[4], self.reference[4] + 0.2)
        self.assertGreater(self.robot.position[9], self.reference[9] + 0.1)
        for side in SIDES:
            np.testing.assert_allclose(
                self.robot.arm_directions(side, self.robot.target),
                self.robot.arm_directions(side, desired),
                atol=0.06,
            )

    def test_torso_and_shoulder_can_contact_in_suspended_model(self):
        self.robot.fit.qpos[self.robot.address] = [
            0.854, -3.015, 0.131, -0.706, -0.433, 0.374,
            -0.582, -1.1, -1.521, 1.701, 1.173,
        ]
        mujoco.mj_forward(self.robot.model, self.robot.fit)
        self.assertGreater(self.robot.fit.ncon, 0)

    def test_loss_pauses_then_requires_explicit_resume(self):
        self.begin()
        self.session.observe({"schema": OBSERVATION_SCHEMA, "capture_time_s": 10.1,
                              "valid": False, "reason": "upper_body_occluded"}, 10.1)
        self.assertEqual(self.session.state, "paused")
        self.assertIsNone(self.session.command(10.1))
        self.session.observe(self.observation(10.2), 10.2)
        self.assertIsNone(self.session.command(10.2))
        self.session.follow(10.2)
        self.session.tick(11., 0.02)
        self.assertEqual(self.session.reason, "input_stale")

    def test_follow_accepts_body_when_both_palms_drop_after_calibration(self):
        self.session.observe(self.observation(10.0), 10.0)
        self.session.calibrate(10.0)
        frame = self.observation(10.1)
        frame["hands"].clear()
        self.session.observe(frame, 10.1)
        self.session.follow(10.1)
        self.assertEqual(self.session.status(10.1)["missing_palms"], ["left", "right"])
        self.assertIsNotNone(self.session.command(10.1))

    def test_missing_palm_holds_only_its_wrist_until_recovery(self):
        self.begin()
        desired = self.reference + np.array(
            [0.2, 0, 0, 0, 0.25, 0.34, 0, 0, 0, 0.25, 0.29]
        )
        for step in range(1, 41):
            stamp = 10 + step * 0.02
            frame = self.observation(stamp, desired)
            del frame["hands"]["left"]
            self.session.observe(frame, stamp)
            self.session.tick(stamp, 0.02)
        self.assertEqual(self.session.state, "following")
        self.assertEqual(self.session.status(stamp)["missing_palms"], ["left"])
        self.assertAlmostEqual(self.robot.target[5], self.reference[5])
        self.assertGreater(self.robot.target[10], self.reference[10] + 0.20)
        self.assertGreater(self.robot.target[0], self.reference[0] + 0.15)
        self.assertGreater(self.robot.target[4], self.reference[4] + 0.17)
        self.assertGreater(self.robot.target[9], self.reference[9] + 0.17)

        stamp += 0.02
        self.session.observe(self.observation(stamp, desired), stamp)
        self.session.tick(stamp, 0.02)
        self.assertEqual(self.session.status(stamp)["missing_palms"], [])
        self.assertGreater(self.robot.target[5], self.reference[5])
        self.assertLessEqual(self.robot.target[5] - self.reference[5], 0.02 + 1e-9)

    def test_initial_calibration_needs_both_palms(self):
        frame = self.observation(10.0)
        del frame["hands"]["right"]
        self.session.observe(frame, 10.0)
        with self.assertRaisesRegex(ValueError, "右手"):
            self.session.calibrate(10.0)

    def test_new_person_requires_new_calibration(self):
        self.begin()
        self.session.observe(self.observation(10.1, track=2), 10.1)
        with self.assertRaises(ValueError):
            self.session.follow(10.1)
        self.session.calibrate(10.1)
        self.session.follow(10.1)
        self.assertEqual(self.session.state, "following")

    def test_calibration_reports_unreliable_joints(self):
        self.session.observe({
            "schema": OBSERVATION_SCHEMA, "capture_time_s": 10.0,
            "valid": False, "reason": "upper_body_occluded",
            "missing_keypoints": ["left_hip", "right_hip"],
        }, 10.0)
        with self.assertRaisesRegex(ValueError, "左髋、右髋"):
            self.session.calibrate(10.0)


if __name__ == "__main__":
    unittest.main()
