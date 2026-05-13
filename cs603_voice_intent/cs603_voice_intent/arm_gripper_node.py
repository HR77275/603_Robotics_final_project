from __future__ import annotations

import signal
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

from cs603_voice_intent.arm_gripper_sequence import (
    GRIPPER_CLOSE,
    GRIPPER_OPEN,
    STEP_ARM,
    STEP_GRIPPER,
    ArmPose,
    ManipulationConfig,
    ManipulationStep,
    build_manipulation_sequence,
    is_manipulation_intent,
    should_accept_manipulation,
)
from cs603_voice_intent.behavior_fsm import STATE_IDLE
from cs603_voice_intent.intent_classifier import CMD_DROP, CMD_PICK
from robomaster_msgs.action import GripperControl, MoveArm


class ArmGripperNode(Node):
    """Runs pick/drop arm sequences only while the behavior FSM is APPROACHING."""

    def __init__(self) -> None:
        super().__init__("arm_gripper_node")

        self.declare_parameter("intent_topic", "/voice_intent")
        self.declare_parameter("state_topic", "/behavior_state")
        self.declare_parameter("status_topic", "/arm_gripper_status")
        self.declare_parameter("move_arm_action", "move_arm")
        self.declare_parameter("gripper_action", "gripper")
        self.declare_parameter("action_server_timeout_sec", 2.0)
        self.declare_parameter("arm_relative", False)
        self.declare_parameter("pick_x_m", 0.16)
        self.declare_parameter("pick_z_m", -0.08)
        self.declare_parameter("carry_x_m", 0.10)
        self.declare_parameter("carry_z_m", 0.10)
        self.declare_parameter("drop_x_m", 0.16)
        self.declare_parameter("drop_z_m", -0.08)
        self.declare_parameter("gripper_power", 0.7)

        self.behavior_state = STATE_IDLE
        self.busy = False
        self.active_intent = ""
        self.sequence: tuple[ManipulationStep, ...] = ()
        self.step_index = 0

        intent_topic = str(self.get_parameter("intent_topic").value)
        state_topic = str(self.get_parameter("state_topic").value)
        status_topic = str(self.get_parameter("status_topic").value)

        self.status_pub = self.create_publisher(String, status_topic, 10)
        self.create_subscription(String, intent_topic, self.intent_cb, 10)
        self.create_subscription(String, state_topic, self.state_cb, 10)

        self.arm_client = ActionClient(
            self,
            MoveArm,
            str(self.get_parameter("move_arm_action").value),
        )
        self.gripper_client = ActionClient(
            self,
            GripperControl,
            str(self.get_parameter("gripper_action").value),
        )

        self.get_logger().info(
            "arm_gripper_node up: "
            f"intent={intent_topic} state={state_topic} status={status_topic}"
        )

    def state_cb(self, msg: String) -> None:
        self.behavior_state = (msg.data or "").strip() or STATE_IDLE

    def intent_cb(self, msg: String) -> None:
        intent = (msg.data or "").strip()
        if not is_manipulation_intent(intent):
            return

        if self.busy:
            self.publish_status(f"IGNORED {intent}: manipulator busy")
            return

        if not should_accept_manipulation(intent, self.behavior_state):
            self.publish_status(
                f"IGNORED {intent}: behavior_state={self.behavior_state}"
            )
            return

        self.sequence = build_manipulation_sequence(intent, self.config())
        if not self.sequence:
            self.publish_status(f"IGNORED {intent}: no manipulation sequence")
            return

        self.busy = True
        self.active_intent = intent
        self.step_index = 0
        self.publish_status(f"STARTED {intent}")
        self.start_next_step()

    def config(self) -> ManipulationConfig:
        return ManipulationConfig(
            pick_pose=ArmPose(
                float(self.get_parameter("pick_x_m").value),
                float(self.get_parameter("pick_z_m").value),
            ),
            carry_pose=ArmPose(
                float(self.get_parameter("carry_x_m").value),
                float(self.get_parameter("carry_z_m").value),
            ),
            drop_pose=ArmPose(
                float(self.get_parameter("drop_x_m").value),
                float(self.get_parameter("drop_z_m").value),
            ),
            arm_relative=bool(self.get_parameter("arm_relative").value),
            gripper_power=float(self.get_parameter("gripper_power").value),
        )

    def start_next_step(self) -> None:
        if self.step_index >= len(self.sequence):
            self.finish_sequence(success=True)
            return

        step = self.sequence[self.step_index]
        self.publish_status(f"STEP {self.active_intent}: {step.name}")

        if step.kind == STEP_ARM:
            self.send_arm_goal(step)
        elif step.kind == STEP_GRIPPER:
            self.send_gripper_goal(step)
        else:
            self.finish_sequence(success=False, detail=f"unknown step {step.kind}")

    def send_arm_goal(self, step: ManipulationStep) -> None:
        if step.pose is None:
            self.finish_sequence(success=False, detail=f"{step.name} missing pose")
            return

        if not self.wait_for_action_server(self.arm_client, "move_arm"):
            return

        goal = MoveArm.Goal()
        goal.x = float(step.pose.x_m)
        goal.z = float(step.pose.z_m)
        goal.relative = bool(self.config().arm_relative)

        future = self.arm_client.send_goal_async(goal)
        future.add_done_callback(
            lambda done, step_name=step.name: self.goal_response_cb(
                done,
                "move_arm",
                step_name,
            )
        )

    def send_gripper_goal(self, step: ManipulationStep) -> None:
        if not self.wait_for_action_server(self.gripper_client, "gripper"):
            return

        goal = GripperControl.Goal()
        goal.power = max(0.0, min(1.0, float(self.config().gripper_power)))

        if step.gripper_target == GRIPPER_OPEN:
            goal.target_state = GripperControl.Goal.OPEN
        elif step.gripper_target == GRIPPER_CLOSE:
            goal.target_state = GripperControl.Goal.CLOSE
        else:
            self.finish_sequence(
                success=False,
                detail=f"{step.name} unknown target {step.gripper_target}",
            )
            return

        future = self.gripper_client.send_goal_async(goal)
        future.add_done_callback(
            lambda done, step_name=step.name: self.goal_response_cb(
                done,
                "gripper",
                step_name,
            )
        )

    def wait_for_action_server(self, client: ActionClient, name: str) -> bool:
        timeout = float(self.get_parameter("action_server_timeout_sec").value)
        if client.wait_for_server(timeout_sec=timeout):
            return True

        self.finish_sequence(success=False, detail=f"{name} action server unavailable")
        return False

    def goal_response_cb(self, future: Any, action_name: str, step_name: str) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # pragma: no cover - defensive ROS callback guard.
            self.finish_sequence(success=False, detail=f"{action_name} goal error: {exc}")
            return

        if not goal_handle.accepted:
            self.finish_sequence(success=False, detail=f"{action_name} rejected {step_name}")
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda done: self.result_cb(done, action_name, step_name)
        )

    def result_cb(self, future: Any, action_name: str, step_name: str) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - defensive ROS callback guard.
            self.finish_sequence(success=False, detail=f"{action_name} result error: {exc}")
            return

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            detail = f"{action_name} {step_name} failed with status {result.status}"
            self.finish_sequence(success=False, detail=detail)
            return

        self.step_index += 1
        self.start_next_step()

    def finish_sequence(self, success: bool, detail: str = "") -> None:
        intent = self.active_intent or "UNKNOWN"
        if success:
            if intent == CMD_PICK:
                self.publish_status("DONE CMD_PICK: object lifted")
            elif intent == CMD_DROP:
                self.publish_status("DONE CMD_DROP: object released")
            else:
                self.publish_status(f"DONE {intent}")
        else:
            suffix = f": {detail}" if detail else ""
            self.publish_status(f"FAILED {intent}{suffix}")

        self.busy = False
        self.active_intent = ""
        self.sequence = ()
        self.step_index = 0

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ArmGripperNode()

    def _shutdown(signum, _frame):
        node.get_logger().warn(f"signal {signum} received; shutting down arm node")
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
