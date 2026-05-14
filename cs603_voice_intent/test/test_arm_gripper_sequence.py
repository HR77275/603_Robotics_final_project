from cs603_voice_intent.arm_gripper_sequence import (
    GRIPPER_CLOSE,
    GRIPPER_OPEN,
    STEP_ARM,
    STEP_GRIPPER,
    ManipulationConfig,
    build_manipulation_sequence,
    should_accept_manipulation,
    should_continue_after_step_failure,
)
from cs603_voice_intent.behavior_fsm import (
    STATE_APPROACHING,
    STATE_FOLLOWING,
    STATE_STOPPED,
)
from cs603_voice_intent.intent_classifier import CMD_DROP, CMD_PICK, CMD_STOP


def test_pick_and_drop_are_accepted_in_approach_or_stop_mode():
    assert should_accept_manipulation(CMD_PICK, STATE_APPROACHING)
    assert should_accept_manipulation(CMD_DROP, STATE_APPROACHING)
    assert should_accept_manipulation(CMD_PICK, STATE_STOPPED)
    assert should_accept_manipulation(CMD_DROP, STATE_STOPPED)
    assert not should_accept_manipulation(CMD_PICK, STATE_FOLLOWING)
    assert not should_accept_manipulation(CMD_STOP, STATE_APPROACHING)


def test_pick_sequence_opens_lowers_closes_and_lifts():
    sequence = build_manipulation_sequence(CMD_PICK, ManipulationConfig())

    assert [step.kind for step in sequence] == [
        STEP_GRIPPER,
        STEP_ARM,
        STEP_GRIPPER,
        STEP_ARM,
    ]
    assert sequence[0].gripper_target == GRIPPER_OPEN
    assert sequence[1].name == "lower_to_pick_pose"
    assert sequence[2].gripper_target == GRIPPER_CLOSE
    assert sequence[3].name == "lift_to_carry_pose"


def test_drop_sequence_lowers_opens_and_returns_to_carry_height():
    sequence = build_manipulation_sequence(CMD_DROP, ManipulationConfig())

    assert [step.kind for step in sequence] == [STEP_ARM, STEP_GRIPPER, STEP_ARM]
    assert sequence[0].name == "lower_to_drop_pose"
    assert sequence[1].gripper_target == GRIPPER_OPEN
    assert sequence[2].name == "return_to_carry_pose"


def test_unknown_manipulation_sequence_is_empty():
    assert build_manipulation_sequence(CMD_STOP, ManipulationConfig()) == ()


def test_pick_can_continue_after_close_reports_object_contact_failure():
    sequence = build_manipulation_sequence(CMD_PICK, ManipulationConfig())

    assert should_continue_after_step_failure(
        CMD_PICK,
        sequence[2],
        ManipulationConfig(),
    )
    assert not should_continue_after_step_failure(
        CMD_DROP,
        sequence[2],
        ManipulationConfig(),
    )
    assert not should_continue_after_step_failure(
        CMD_PICK,
        sequence[2],
        ManipulationConfig(continue_after_gripper_close_failure=False),
    )
