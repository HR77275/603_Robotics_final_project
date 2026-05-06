"""Gate teammate follow-controller velocity before it reaches /cmd_vel."""

from __future__ import annotations

import signal
import time
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool, String


CMD_STOP = "CMD_STOP"


def zero_twist() -> Twist:
    """Create an explicit zero Twist for chassis stop commands."""

    return Twist()


def copy_twist(src: Twist) -> Twist:
    """Copy Twist fields so the gate owns the outbound message instance."""

    out = Twist()
    out.linear.x = src.linear.x
    out.linear.y = src.linear.y
    out.linear.z = src.linear.z
    out.angular.x = src.angular.x
    out.angular.y = src.angular.y
    out.angular.z = src.angular.z
    return out


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


class CmdVelGate(Node):
    """Final /cmd_vel gate controlled by /follow_target_active and CMD_STOP."""

    def __init__(self) -> None:
        super().__init__("cmd_vel_gate")
        self.declare_parameter("enable_motion", False)
        self.declare_parameter("active_topic", "/follow_target_active")
        self.declare_parameter("raw_cmd_vel_topic", "/cmd_vel_follow_raw")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("intent_topic", "/voice_intent")
        self.declare_parameter("stale_timeout_sec", 0.5)
        self.declare_parameter("active_timeout_sec", 1.0)
        self.declare_parameter("control_period_sec", 0.05)
        self.declare_parameter("max_linear_speed", 0.20)
        self.declare_parameter("max_angular_speed", 0.60)

        self.enable_motion = bool(self.get_parameter("enable_motion").value)
        self.active_topic = str(self.get_parameter("active_topic").value)
        self.raw_cmd_vel_topic = str(self.get_parameter("raw_cmd_vel_topic").value)
        self.cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)
        self.intent_topic = str(self.get_parameter("intent_topic").value)
        self.stale_timeout_sec = float(self.get_parameter("stale_timeout_sec").value)
        self.active_timeout_sec = float(self.get_parameter("active_timeout_sec").value)
        control_period_sec = float(self.get_parameter("control_period_sec").value)
        self.max_linear_speed = abs(float(self.get_parameter("max_linear_speed").value))
        self.max_angular_speed = abs(float(self.get_parameter("max_angular_speed").value))

        self.active = False
        self._last_active_time = 0.0
        self._last_raw: Twist | None = None
        self._last_raw_time = 0.0

        self.publisher = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self._active_sub = self.create_subscription(
            Bool, self.active_topic, self._on_active, 10
        )
        self._raw_sub = self.create_subscription(
            Twist, self.raw_cmd_vel_topic, self._on_raw_cmd, 10
        )
        self._intent_sub = self.create_subscription(
            String, self.intent_topic, self._on_intent, 10
        )
        self._timer = self.create_timer(control_period_sec, self._on_timer)

        self.get_logger().info(
            "cmd_vel_gate up: "
            f"raw={self.raw_cmd_vel_topic} final={self.cmd_vel_topic} "
            f"active={self.active_topic} enable_motion={self.enable_motion}"
        )

    def _on_active(self, msg: Bool) -> None:
        self.active = bool(msg.data)
        self._last_active_time = time.monotonic() if self.active else 0.0
        if not self.active:
            self._publish_stop()

    def _on_intent(self, msg: String) -> None:
        intent = (msg.data or "").strip()
        if intent == CMD_STOP:
            self.active = False
            self._publish_stop()

    def _on_raw_cmd(self, msg: Twist) -> None:
        self._last_raw = copy_twist(msg)
        self._last_raw_time = time.monotonic()
        self._publish_gate_output()

    def _on_timer(self) -> None:
        if self._active_is_stale():
            self.active = False
            self._publish_stop()
            return
        if not self.active or not self.enable_motion:
            self._publish_stop()
            return
        if self._raw_is_stale():
            self._publish_stop()

    def _publish_gate_output(self) -> None:
        if self._active_is_stale():
            self.active = False
            self._publish_stop()
            return
        if not self.active or not self.enable_motion:
            self._publish_stop()
            return
        if self._last_raw is None or self._raw_is_stale():
            self._publish_stop()
            return
        self.publisher.publish(self._sanitize_twist(self._last_raw))

    def _publish_stop(self) -> None:
        self.publisher.publish(zero_twist())

    def _sanitize_twist(self, src: Twist) -> Twist:
        values = (
            src.linear.x,
            src.linear.y,
            src.linear.z,
            src.angular.x,
            src.angular.y,
            src.angular.z,
        )
        if not all(math.isfinite(float(value)) for value in values):
            return zero_twist()

        out = Twist()
        out.linear.x = _clamp(float(src.linear.x), self.max_linear_speed)
        out.linear.y = _clamp(float(src.linear.y), self.max_linear_speed)
        out.linear.z = _clamp(float(src.linear.z), self.max_linear_speed)
        out.angular.x = _clamp(float(src.angular.x), self.max_angular_speed)
        out.angular.y = _clamp(float(src.angular.y), self.max_angular_speed)
        out.angular.z = _clamp(float(src.angular.z), self.max_angular_speed)
        return out

    def _raw_is_stale(self) -> bool:
        if self._last_raw_time <= 0.0:
            return True
        return (time.monotonic() - self._last_raw_time) > self.stale_timeout_sec

    def _active_is_stale(self) -> bool:
        if not self.active:
            return False
        if self.active_timeout_sec <= 0.0:
            return False
        if self._last_active_time <= 0.0:
            return True
        return (time.monotonic() - self._last_active_time) > self.active_timeout_sec

    def stop(self) -> None:
        """Publish one last zero Twist before node shutdown."""

        self.active = False
        self._publish_stop()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CmdVelGate()

    def _shutdown(signum, _frame):
        node.get_logger().warn(f"signal {signum} received; publishing stop")
        node.stop()
        if rclpy.ok():
            rclpy.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        rclpy.spin(node)
    finally:
        if rclpy.ok():
            node.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
