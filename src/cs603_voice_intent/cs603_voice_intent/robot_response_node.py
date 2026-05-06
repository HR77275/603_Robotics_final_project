"""Publish short robot/browser speech acknowledgements for voice state."""

from __future__ import annotations

import signal

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from cs603_voice_intent.speech_responses import speech_for_intent, speech_for_state


class RobotResponseNode(Node):
    """Maps /voice_intent and /behavior_state to /robot_speech text."""

    def __init__(self) -> None:
        super().__init__("robot_response_node")
        self.declare_parameter("intent_topic", "/voice_intent")
        self.declare_parameter("state_topic", "/behavior_state")
        self.declare_parameter("speech_topic", "/robot_speech")
        self.declare_parameter("repeat_same_state", False)

        intent_topic = str(self.get_parameter("intent_topic").value)
        state_topic = str(self.get_parameter("state_topic").value)
        speech_topic = str(self.get_parameter("speech_topic").value)
        self.repeat_same_state = bool(self.get_parameter("repeat_same_state").value)
        self._last_state = ""

        self.publisher = self.create_publisher(String, speech_topic, 10)
        self._intent_sub = self.create_subscription(
            String, intent_topic, self._on_intent, 10
        )
        self._state_sub = self.create_subscription(
            String, state_topic, self._on_state, 10
        )

        self.get_logger().info(
            f"robot_response_node up: intent={intent_topic} state={state_topic} "
            f"speech={speech_topic}"
        )

    def _on_intent(self, msg: String) -> None:
        self._publish_speech(speech_for_intent(msg.data))

    def _on_state(self, msg: String) -> None:
        state = (msg.data or "").strip()
        if not self.repeat_same_state and state == self._last_state:
            return
        self._last_state = state
        self._publish_speech(speech_for_state(state))

    def _publish_speech(self, text: str) -> None:
        if not text:
            return
        msg = String()
        msg.data = text
        self.publisher.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RobotResponseNode()

    def _shutdown(signum, _frame):
        node.get_logger().warn(f"signal {signum} received; shutting down response node")
        if rclpy.ok():
            rclpy.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
