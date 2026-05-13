import sys
import types
import unittest
from unittest.mock import patch


class _Vector:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0


class _Twist:
    def __init__(self):
        self.linear = _Vector()
        self.angular = _Vector()


class _String:
    def __init__(self, data=""):
        self.data = data


class _Bool:
    def __init__(self, data=False):
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
    def __init__(self):
        self.records = []

    def info(self, message):
        self.records.append(("info", message))

    def warn(self, message):
        self.records.append(("warn", message))


class _Node:
    parameter_overrides = {}

    def __init__(self, name):
        self.name = name
        self._parameters = dict(self.parameter_overrides)
        self._logger = _Logger()

    def declare_parameter(self, name, default_value):
        self._parameters.setdefault(name, default_value)

    def get_parameter(self, name):
        return _Parameter(self._parameters[name])

    def create_publisher(self, _msg_type, topic, _depth):
        return _Publisher(topic)

    def create_subscription(self, _msg_type, topic, callback, _depth):
        return {"topic": topic, "callback": callback}

    def create_timer(self, period_sec, callback):
        return {"period_sec": period_sec, "callback": callback}

    def get_logger(self):
        return self._logger

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

    fake_geometry_msgs = types.ModuleType("geometry_msgs")
    fake_geometry_msgs_msg = types.ModuleType("geometry_msgs.msg")
    fake_geometry_msgs_msg.Twist = _Twist
    fake_geometry_msgs.msg = fake_geometry_msgs_msg

    fake_std_msgs = types.ModuleType("std_msgs")
    fake_std_msgs_msg = types.ModuleType("std_msgs.msg")
    fake_std_msgs_msg.Bool = _Bool
    fake_std_msgs_msg.String = _String
    fake_std_msgs.msg = fake_std_msgs_msg

    sys.modules["rclpy"] = fake_rclpy
    sys.modules["rclpy.node"] = fake_rclpy_node
    sys.modules["geometry_msgs"] = fake_geometry_msgs
    sys.modules["geometry_msgs.msg"] = fake_geometry_msgs_msg
    sys.modules["std_msgs"] = fake_std_msgs
    sys.modules["std_msgs.msg"] = fake_std_msgs_msg


_install_ros_fakes()

from cs603_voice_intent.intent_classifier import CMD_APPROACH, CMD_FOLLOW, CMD_STOP  # noqa: E402
from cs603_voice_intent import voice_cmd_vel_bridge as bridge_module  # noqa: E402
from cs603_voice_intent.voice_cmd_vel_bridge import VoiceCmdVelBridge  # noqa: E402


def _intent_msg(intent):
    return _String(intent)


class VoiceCmdVelBridgeSafetyTest(unittest.TestCase):
    def setUp(self):
        _Node.parameter_overrides = {}

    def tearDown(self):
        _Node.parameter_overrides = {}

    def make_node(self, **parameter_overrides):
        _Node.parameter_overrides = parameter_overrides
        return VoiceCmdVelBridge()

    def assert_zero_twist(self, twist):
        self.assertEqual(twist.linear.x, 0.0)
        self.assertEqual(twist.linear.y, 0.0)
        self.assertEqual(twist.linear.z, 0.0)
        self.assertEqual(twist.angular.x, 0.0)
        self.assertEqual(twist.angular.y, 0.0)
        self.assertEqual(twist.angular.z, 0.0)

    def test_motion_disabled_by_default_does_not_publish_forward_intents(self):
        node = self.make_node()

        node._on_intent(_intent_msg(CMD_FOLLOW))
        node._on_intent(_intent_msg(CMD_APPROACH))

        self.assertFalse(node.enable_motion)
        self.assertEqual(node.publisher.topic, "/cmd_vel")
        self.assertEqual(node.publisher.messages, [])
        self.assertEqual(node._stop_at, 0.0)

    def test_stop_intent_publishes_only_zero_twist_and_clears_deadline(self):
        node = self.make_node()
        node._stop_at = 123.0

        node._on_intent(_intent_msg(CMD_STOP))

        self.assertEqual(len(node.publisher.messages), 1)
        self.assert_zero_twist(node.publisher.messages[0])
        self.assertEqual(node._stop_at, 0.0)

    def test_unknown_intent_does_not_publish_even_when_motion_enabled(self):
        node = self.make_node(enable_motion=True)

        node._on_intent(_intent_msg("CMD_DANCE"))

        self.assertEqual(node.publisher.messages, [])

    def test_motion_enabled_uses_capped_forward_speeds(self):
        node = self.make_node(enable_motion=True)

        node._on_intent(_intent_msg(CMD_FOLLOW))
        node._on_intent(_intent_msg(CMD_APPROACH))

        self.assertEqual(len(node.publisher.messages), 2)
        self.assertEqual(node.publisher.messages[0].linear.x, 0.08)
        self.assertEqual(node.publisher.messages[1].linear.x, 0.10)
        self.assertEqual(node.publisher.messages[0].angular.z, 0.0)
        self.assertEqual(node.publisher.messages[1].angular.z, 0.0)

    def test_unsafe_motion_parameters_are_clamped(self):
        node = self.make_node(
            enable_motion=True,
            follow_speed=1.5,
            approach_speed=-0.2,
            command_duration_sec=5.0,
        )

        node._on_intent(_intent_msg(CMD_FOLLOW))
        node._on_intent(_intent_msg(CMD_APPROACH))

        self.assertEqual(node.follow_speed, 0.12)
        self.assertEqual(node.approach_speed, 0.0)
        self.assertEqual(node.command_duration_sec, 1.0)
        self.assertEqual(node.publisher.messages[0].linear.x, 0.12)
        self.assertEqual(node.publisher.messages[1].linear.x, 0.0)

    def test_timer_publishes_zero_twist_after_command_deadline(self):
        node = self.make_node(enable_motion=True)

        with patch.object(bridge_module.time, "monotonic", side_effect=[10.0, 10.9]):
            node._on_intent(_intent_msg(CMD_FOLLOW))
            node._on_timer()

        self.assertEqual(len(node.publisher.messages), 2)
        self.assertEqual(node.publisher.messages[0].linear.x, 0.08)
        self.assert_zero_twist(node.publisher.messages[1])
        self.assertEqual(node._stop_at, 0.0)


if __name__ == "__main__":
    unittest.main()
