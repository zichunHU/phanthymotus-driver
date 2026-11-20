"""Run inside the Q1 driver image on isolated DDS domains."""
import json
import sys
import time
import unittest
from pathlib import Path

from aimdk_msgs.msg import Bms
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.vendor_runtime import DualDomainROS2, DriverBundle
from status import StatusCard


class StatusTest(unittest.TestCase):
    def test_robot_to_canvas(self):
        ros = DualDomainROS2(87, 88)
        vendor = Node("test_q1", context=ros.ctx_robot)
        canvas = Node("test_canvas", context=ros.ctx_core)
        ros.executor_robot.add_node(vendor)
        ros.executor_core.add_node(canvas)
        pub = vendor.create_publisher(Bms, "/aima/hal/bms/state", qos_profile_sensor_data)

        frames = []
        canvas.create_subscription(String, "/test_q1/status",
                                   lambda msg: frames.append(json.loads(msg.data)), 5)
        card = StatusCard("test_q1", ros, 87)
        ros.start_spin()
        bundle = DriverBundle([card])

        def call(action):
            return bundle.dispatch("status", {"action": action})

        try:
            bundle.start_all()
            self.assertEqual(call("info")["data"]["battery"]["state"], "waiting")
            self.assertEqual(call("start")["topic_out"], [{"topic": "/test_q1/status", "format": "data/json"}])
            sample = Bms(remaining_capacity_percentage=73, voltage=51450, current=-260,
                         power=13377, temperature=30.25, remaining_capacity=3390,
                         cycle_count=2, cycle_total_capacity=8625, status=4)
            deadline = time.monotonic() + 14
            while time.monotonic() < deadline:
                pub.publish(sample)
                if frames and frames[-1]["battery"]["state"] == "live":
                    break
                time.sleep(0.1)
            self.assertTrue(frames)
            data = frames[-1]
            self.assertEqual(set(data), {"battery"})
            expected = {"percentage": 73, "voltage_v": 51.45, "current_a": -0.26,
                        "power_w": 13.377, "temperature_c": 30.25,
                        "remaining_capacity_mah": 3390, "cycle_count": 2, "cycle_total_capacity_mah": 8625, "status_bits": 4}
            self.assertEqual({k: data["battery"][k] for k in expected}, expected)
            self.assertEqual(call("stop")["state"], "idle")
            time.sleep(0.6)
            stopped_count = len(frames)
            time.sleep(5.2)
            self.assertEqual(len(frames), stopped_count)
            self.assertEqual(call("read")["data"]["battery"]["state"], "stale")
            call("start")
            deadline = time.monotonic() + 3
            while len(frames) == stopped_count and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertGreater(len(frames), stopped_count)
        finally:
            bundle.stop_all()
            vendor.destroy_node()
            canvas.destroy_node()
            ros.shutdown()


if __name__ == "__main__":
    unittest.main()
