"""Unit tests for the BehaviorFsm transition logic.

Tests are pure-Python and do not spin a real rclpy context. They exercise
INTENT_TO_STATE mapping and the no-op / unknown-intent branches.
"""

from __future__ import annotations

import sys
import types

import pytest


class _Bool:
    def __init__(self, data=False):
        self.data = data


class _String:
    def __init__(self, data=""):
        self.data = data


class _Parameter:
    def __init__(self, value):
        self.value = value


class _Publisher:
    def __init__(self, topic):
        self.topic = topic
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg)


class _Logger:
    def info(self, _message):
        return None

    def warn(self, _message):
        return None

    def debug(self, _message):
        return None


class _Node:
    parameter_overrides = {}

    def __init__(self, _name):
        self.parameters = {}
        self.timers = []

    def declare_parameter(self, name, default):
        self.parameters[name] = self.parameter_overrides.get(name, default)

    def get_parameter(self, name):
        return _Parameter(self.parameters[name])

    def create_publisher(self, _msg_type, topic, _depth):
        return _Publisher(topic)

    def create_subscription(self, _msg_type, topic, callback, _depth):
        return {"topic": topic, "callback": callback}

    def create_timer(self, period_sec, callback):
        timer = {"period_sec": period_sec, "callback": callback}
        self.timers.append(timer)
        return timer

    def get_logger(self):
        return _Logger()

    def destroy_node(self):
        return None


def _install_ros_fakes():
    fake_rclpy = types.ModuleType("rclpy")
    fake_rclpy.init = lambda args=None: None
    fake_rclpy.ok = lambda: False
    fake_rclpy.shutdown = lambda: None
    fake_rclpy.spin = lambda _node: None

    fake_rclpy_node = types.ModuleType("rclpy.node")
    fake_rclpy_node.Node = _Node
    fake_rclpy.node = fake_rclpy_node

    fake_std_msgs = types.ModuleType("std_msgs")
    fake_std_msgs_msg = types.ModuleType("std_msgs.msg")
    fake_std_msgs_msg.Bool = _Bool
    fake_std_msgs_msg.String = _String
    fake_std_msgs.msg = fake_std_msgs_msg

    sys.modules["rclpy"] = fake_rclpy
    sys.modules["rclpy.node"] = fake_rclpy_node
    sys.modules["std_msgs"] = fake_std_msgs
    sys.modules["std_msgs.msg"] = fake_std_msgs_msg


_install_ros_fakes()

from cs603_voice_intent.behavior_fsm import (
    INTENT_TO_STATE,
    STATE_APPROACHING,
    STATE_FOLLOWING,
    STATE_IDLE,
    STATE_STOPPED,
    Transition,
    BehaviorFsm,
)
from cs603_voice_intent.intent_classifier import (
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_STOP,
    CMD_UNKNOWN,
)


@pytest.mark.unit
class TestIntentToStateMapping:
    def test_follow_maps_to_following(self) -> None:
        assert INTENT_TO_STATE[CMD_FOLLOW] == STATE_FOLLOWING

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
        states = {STATE_IDLE, STATE_FOLLOWING, STATE_STOPPED, STATE_APPROACHING}
        assert len(states) == 4


class TestBehaviorFsmNode:
    def setup_method(self) -> None:
        _Node.parameter_overrides = {}

    def teardown_method(self) -> None:
        _Node.parameter_overrides = {}

    def test_follow_intent_publishes_following_and_active(self) -> None:
        node = BehaviorFsm()
        node._state_pub.messages.clear()
        node._follow_active_pub.messages.clear()

        node._on_intent(_String(CMD_FOLLOW))

        assert node.state == STATE_FOLLOWING
        assert node._state_pub.messages[-1].data == STATE_FOLLOWING
        assert node._follow_active_pub.messages[-1].data is True

    def test_stop_intent_publishes_stopped_and_inactive(self) -> None:
        node = BehaviorFsm()
        node._on_intent(_String(CMD_FOLLOW))

        node._on_intent(_String(CMD_STOP))

        assert node.state == STATE_STOPPED
        assert node._state_pub.messages[-1].data == STATE_STOPPED
        assert node._follow_active_pub.messages[-1].data is False

    def test_unknown_intent_does_not_change_state(self) -> None:
        node = BehaviorFsm()
        node._state_pub.messages.clear()
        node._follow_active_pub.messages.clear()

        node._on_intent(_String(CMD_UNKNOWN))

        assert node.state == STATE_IDLE
        assert node._state_pub.messages == []
        assert node._follow_active_pub.messages == []

    def test_heartbeat_republishes_current_state(self) -> None:
        node = BehaviorFsm()
        node._on_intent(_String(CMD_FOLLOW))
        node._state_pub.messages.clear()
        node._follow_active_pub.messages.clear()

        node._on_heartbeat()

        assert node._state_pub.messages[-1].data == STATE_FOLLOWING
        assert node._follow_active_pub.messages[-1].data is True

    def test_stop_method_publishes_stopped_and_inactive(self) -> None:
        node = BehaviorFsm()
        node._on_intent(_String(CMD_FOLLOW))

        node.stop()

        assert node.state == STATE_STOPPED
        assert node._state_pub.messages[-1].data == STATE_STOPPED
        assert node._follow_active_pub.messages[-1].data is False
