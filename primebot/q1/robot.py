"""Read Q1 telemetry on the vendor Fast DDS network."""
import os
import time
from pathlib import Path


def battery_state(msg):
    return {
        "percentage": msg.remaining_capacity_percentage,
        "voltage_v": msg.voltage / 1000,
        "current_a": msg.current / 1000,
        "power_w": msg.power / 1000,
        "temperature_c": round(msg.temperature, 2),
        "remaining_capacity_mah": msg.remaining_capacity,
        "cycle_count": msg.cycle_count,
        "status_bits": msg.status,
    }


def read_robot(domain, output, stopping):
    from ament_index_python.packages import get_package_share_directory
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from aimdk_msgs.msg import Bms
    from aimdk_msgs.srv import GetMcAction

    profile = Path(get_package_share_directory("aimdk_msgs")) / "config/fastdds_profiles.xml"
    for key in ("FASTRTPS_DEFAULT_PROFILES_FILE", "FASTDDS_DEFAULT_PROFILES_FILE"):
        os.environ[key] = os.environ.get("Q1_FASTDDS_PROFILE", str(profile))
    rclpy.init(domain_id=domain)
    node = rclpy.create_node("primebot_q1_status_reader", start_parameter_services=False)
    node.create_subscription(
        Bms, "/aima/hal/bms/state",
        lambda msg: output.send(("battery", time.monotonic(), battery_state(msg))),
        qos_profile_sensor_data,
    )
    client = node.create_client(GetMcAction, "/aimdk_5Fmsgs/srv/GetMcAction")
    pending = None
    last_request = float("-inf")
    try:
        while not stopping.is_set() and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
            now = time.monotonic()
            if pending is not None and pending.done():
                response = pending.result()
                if response.header.code == 0:
                    info = response.info
                    output.send(("motion", now, {
                        "mode": info.current_action.value, "description": info.action_desc,
                        "status": info.status.value, "switch_ready": info.switch_ready,
                        "source": info.source,
                    }))
                else:
                    output.send(("motion", now, {"error": "service_error", "code": response.header.code}))
                pending = None
            if pending is not None and now - last_request >= 2:
                client.remove_pending_request(pending)
                output.send(("motion", now, {"error": "timeout"}))
                pending = None
            if now - last_request >= 2 and client.service_is_ready():
                request = GetMcAction.Request()
                request.request.header.stamp = node.get_clock().now().to_msg()
                pending = client.call_async(request)
                last_request = now
    finally:
        output.close()
        node.destroy_node()
        rclpy.try_shutdown()
