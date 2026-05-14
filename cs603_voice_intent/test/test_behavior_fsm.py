"""Unit tests for the BehaviorFsm transition logic.

Tests are pure-Python and do not spin a real rclpy context. They exercise
INTENT_TO_STATE mapping and the no-op / unknown-intent branches.
"""

from __future__ import annotations

import pytest

from cs603_voice_intent.behavior_fsm import (
    INTENT_TO_STATE,
    STATE_APPROACHING,
    STATE_FOLLOWING,
    STATE_FOLLOWING_AUTHORIZED,
    STATE_IDLE,
    STATE_STOPPED,
    Transition,
)
from cs603_voice_intent.intent_classifier import (
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_FOLLOW_AUTHORIZED,
    CMD_STOP,
    CMD_UNKNOWN,
)


@pytest.mark.unit
class TestIntentToStateMapping:
    def test_follow_maps_to_following(self) -> None:
        assert INTENT_TO_STATE[CMD_FOLLOW] == STATE_FOLLOWING

    def test_authorized_follow_maps_to_authorized_following(self) -> None:
        assert (
            INTENT_TO_STATE[CMD_FOLLOW_AUTHORIZED]
            == STATE_FOLLOWING_AUTHORIZED
        )

    def test_stop_maps_to_stopped(self) -> None:
        assert INTENT_TO_STATE[CMD_STOP] == STATE_STOPPED

    def test_approach_maps_to_approaching(self) -> None:
        assert INTENT_TO_STATE[CMD_APPROACH] == STATE_APPROACHING

    def test_unknown_not_in_map(self) -> None:
        assert CMD_UNKNOWN not in INTENT_TO_STATE


@pytest.mark.unit
class TestTransitionDataclass:
    def test_transition_is_frozen(self) -> None:
        transition = Transition(prev=STATE_IDLE, next=STATE_FOLLOWING, intent=CMD_FOLLOW)
        with pytest.raises((AttributeError, TypeError)):
            transition.prev = STATE_STOPPED  # type: ignore[misc]

    def test_transition_records_all_fields(self) -> None:
        transition = Transition(prev=STATE_FOLLOWING, next=STATE_STOPPED, intent=CMD_STOP)
        assert transition.prev == STATE_FOLLOWING
        assert transition.next == STATE_STOPPED
        assert transition.intent == CMD_STOP


@pytest.mark.unit
class TestStateConstants:
    def test_states_are_distinct(self) -> None:
        states = {
            STATE_IDLE,
            STATE_FOLLOWING,
            STATE_FOLLOWING_AUTHORIZED,
            STATE_STOPPED,
            STATE_APPROACHING,
        }
        assert len(states) == 5
