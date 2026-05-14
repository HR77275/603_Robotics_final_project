from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from cs603_voice_intent.intent_classifier import CMD_DROP, CMD_PICK


STEP_ARM = "arm"
STEP_GRIPPER = "gripper"

GRIPPER_OPEN = "open"
GRIPPER_CLOSE = "close"

STATE_APPROACHING = "APPROACHING"


@dataclass(frozen=True)
class ArmPose:
    x_m: float
    z_m: float


@dataclass(frozen=True)
class ManipulationConfig:
    pick_pose: ArmPose = ArmPose(0.16, -0.08)
    carry_pose: ArmPose = ArmPose(0.10, 0.10)
    drop_pose: ArmPose = ArmPose(0.16, -0.08)
    arm_relative: bool = False
    gripper_power: float = 0.7
    continue_after_gripper_close_failure: bool = True


@dataclass(frozen=True)
class ManipulationStep:
    kind: str
    name: str
    pose: ArmPose | None = None
    gripper_target: str | None = None


def is_manipulation_intent(intent: str) -> bool:
    return intent in (CMD_PICK, CMD_DROP)


def should_accept_manipulation(intent: str, behavior_state: str) -> bool:
    return is_manipulation_intent(intent) and behavior_state == STATE_APPROACHING


def build_manipulation_sequence(
    intent: str,
    config: ManipulationConfig,
) -> Tuple[ManipulationStep, ...]:
    if intent == CMD_PICK:
        return (
            ManipulationStep(STEP_GRIPPER, "open_gripper", gripper_target=GRIPPER_OPEN),
            ManipulationStep(STEP_ARM, "lower_to_pick_pose", pose=config.pick_pose),
            ManipulationStep(STEP_GRIPPER, "close_gripper", gripper_target=GRIPPER_CLOSE),
            ManipulationStep(STEP_ARM, "lift_to_carry_pose", pose=config.carry_pose),
        )

    if intent == CMD_DROP:
        return (
            ManipulationStep(STEP_ARM, "lower_to_drop_pose", pose=config.drop_pose),
            ManipulationStep(STEP_GRIPPER, "open_gripper", gripper_target=GRIPPER_OPEN),
            ManipulationStep(STEP_ARM, "return_to_carry_pose", pose=config.carry_pose),
        )

    return ()


def should_continue_after_step_failure(
    intent: str,
    step: ManipulationStep,
    config: ManipulationConfig,
) -> bool:
    return (
        bool(config.continue_after_gripper_close_failure)
        and intent == CMD_PICK
        and step.kind == STEP_GRIPPER
        and step.gripper_target == GRIPPER_CLOSE
    )
