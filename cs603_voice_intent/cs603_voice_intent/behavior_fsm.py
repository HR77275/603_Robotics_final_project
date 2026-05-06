"""Behavior FSM consuming /voice_intent and publishing /behavior_state.

States: IDLE, FOLLOWING, STOPPED, APPROACHING.
Default is safe: no /cmd_vel published. PID follow controller (separate node)
subscribes to /follow_target which this FSM publishes only when FOLLOWING or
APPROACHING. Optional speaker ACK via /sound/play_sound_id service.
"""

from __future__ import annotations

import signal
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from cs603_voice_intent.intent_classifier import (
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_STOP,
    CMD_UNKNOWN,
)


STATE_IDLE = "IDLE"
STATE_FOLLOWING = "FOLLOWING"
STATE_STOPPED = "STOPPED"
STATE_APPROACHING = "APPROACHING"

INTENT_TO_STATE = {
    CMD_FOLLOW: STATE_FOLLOWING,
    CMD_STOP: STATE_STOPPED,
    CMD_APPROACH: STATE_APPROACHING,
}


@dataclass(frozen=True)
class Transition:
    """One FSM transition record for logging and tests."""

    prev: str
    next: str
    intent: str


class BehaviorFsm(Node):
    """Plain rclpy FSM. No /cmd_vel published; emits /behavior_state and /follow_target_active."""

    def __init__(self) -> None:
        super().__init__("behavior_fsm")
        self.declare_parameter("intent_topic", "/voice_intent")
        self.declare_parameter("state_topic", "/behavior_state")
        self.declare_parameter("follow_active_topic", "/follow_target_active")
        self.declare_parameter("initial_state", STATE_IDLE)
        self.declare_parameter("publish_unknown_state", False)

        intent_topic = str(self.get_parameter("intent_topic").value)
        state_topic = str(self.get_parameter("state_topic").value)
        follow_active_topic = str(self.get_parameter("follow_active_topic").value)
        self.state: str = str(self.get_parameter("initial_state").value)
        self.publish_unknown_state = bool(self.get_parameter("publish_unknown_state").value)

        self._intent_sub = self.create_subscription(
            String, intent_topic, self._on_intent, 10
        )
        self._state_pub = self.create_publisher(String, state_topic, 10)
        self._follow_active_pub = self.create_publisher(Bool, follow_active_topic, 10)
        self._publish_state(reason="startup")

        self.get_logger().info(
            f"behavior_fsm up: intent={intent_topic} state={state_topic} "
            f"initial={self.state}"
        )

    def _on_intent(self, msg: String) -> None:
        intent = (msg.data or "").strip()
        if intent == CMD_UNKNOWN or intent not in INTENT_TO_STATE:
            self.get_logger().info(f"ignored intent={intent!r}; state stays {self.state}")
            return

        next_state = INTENT_TO_STATE[intent]
        if next_state == self.state:
            self.get_logger().info(f"intent={intent} no-op; already {self.state}")
            return

        transition = Transition(prev=self.state, next=next_state, intent=intent)
        self.state = next_state
        self.get_logger().info(
            f"FSM: {transition.prev} -> {transition.next} (cause={transition.intent})"
        )
        self._publish_state(reason=intent)

    def _publish_state(self, reason: str) -> None:
        msg = String()
        msg.data = self.state
        self._state_pub.publish(msg)

        active = Bool()
        active.data = self.state in (STATE_FOLLOWING, STATE_APPROACHING)
        self._follow_active_pub.publish(active)

        self.get_logger().debug(
            f"published state={self.state} follow_active={active.data} reason={reason}"
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BehaviorFsm()

    def _shutdown(signum, _frame):
        node.get_logger().warn(f"signal {signum} received; shutting down FSM")
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
