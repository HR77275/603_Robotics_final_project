import time
import signal

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String

from cs603_voice_intent.intent_classifier import CMD_APPROACH, CMD_FOLLOW, CMD_STOP

MAX_FORWARD_SPEED_MPS = 0.12
MAX_COMMAND_DURATION_SEC = 1.0


class VoiceCmdVelBridge(Node):
    """Optional safety-capped demo bridge from /voice_intent to /cmd_vel."""

    def __init__(self) -> None:
        super().__init__("voice_cmd_vel_bridge")
        self.declare_parameter("enable_motion", False)
        self.declare_parameter("intent_topic", "/voice_intent")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("follow_speed", 0.08)
        self.declare_parameter("approach_speed", 0.10)
        self.declare_parameter("command_duration_sec", 0.8)

        self.enable_motion = bool(self.get_parameter("enable_motion").value)
        intent_topic = self.get_parameter("intent_topic").value
        cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self.follow_speed = self._bounded_demo_value(
            "follow_speed",
            float(self.get_parameter("follow_speed").value),
            0.0,
            MAX_FORWARD_SPEED_MPS,
        )
        self.approach_speed = self._bounded_demo_value(
            "approach_speed",
            float(self.get_parameter("approach_speed").value),
            0.0,
            MAX_FORWARD_SPEED_MPS,
        )
        self.command_duration_sec = self._bounded_demo_value(
            "command_duration_sec",
            float(self.get_parameter("command_duration_sec").value),
            0.05,
            MAX_COMMAND_DURATION_SEC,
        )
        self._stop_at = 0.0

        self.publisher = self.create_publisher(Twist, cmd_vel_topic, 10)
        self.subscription = self.create_subscription(String, intent_topic, self._on_intent, 10)
        self.timer = self.create_timer(0.05, self._on_timer)

        if self.enable_motion:
            self.get_logger().warn("Motion bridge ENABLED. Keep the robot lifted or in a clear test area.")
        else:
            self.get_logger().info("Motion bridge disabled. Set enable_motion:=true for physical motion tests.")

    def _on_intent(self, msg: String) -> None:
        intent = msg.data.strip()
        if intent == CMD_STOP:
            self._stop_at = 0.0
            self._publish_stop()
            self.get_logger().info("CMD_STOP -> zero Twist")
            return

        if not self.enable_motion:
            self.get_logger().info(f"{intent} received; no motion because enable_motion is false.")
            return

        if intent == CMD_FOLLOW:
            self._publish_forward(self.follow_speed)
            self._stop_at = time.monotonic() + self.command_duration_sec
            self.get_logger().info(f"CMD_FOLLOW -> forward {self.follow_speed:.2f} m/s capped")
        elif intent == CMD_APPROACH:
            self._publish_forward(self.approach_speed)
            self._stop_at = time.monotonic() + self.command_duration_sec
            self.get_logger().info(f"CMD_APPROACH -> forward {self.approach_speed:.2f} m/s capped")
        else:
            self.get_logger().info(f"{intent} received; no bridge action.")

    def _on_timer(self) -> None:
        if self._stop_at and time.monotonic() >= self._stop_at:
            self._stop_at = 0.0
            self._publish_stop()

    def _publish_forward(self, speed: float) -> None:
        twist = Twist()
        twist.linear.x = speed
        self.publisher.publish(twist)

    def _publish_stop(self) -> None:
        self.publisher.publish(Twist())

    def _bounded_demo_value(self, name: str, value: float, minimum: float, maximum: float) -> float:
        bounded = min(max(value, minimum), maximum)
        if bounded != value:
            self.get_logger().warn(f"{name}={value:.3f} clamped to {bounded:.3f} for demo safety")
        return bounded


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceCmdVelBridge()

    def stop_and_shutdown(signum, _frame) -> None:
        if rclpy.ok():
            node.get_logger().warn(f"signal {signum} received; publishing zero Twist before shutdown")
            node._publish_stop()
            rclpy.shutdown()

    signal.signal(signal.SIGINT, stop_and_shutdown)
    signal.signal(signal.SIGTERM, stop_and_shutdown)

    try:
        rclpy.spin(node)
    finally:
        if rclpy.ok():
            node._publish_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
