import sys
import types
import unittest


class _String:
    def __init__(self, data=""):
        self.data = data


class _Parameter:
    def __init__(self, value):
        self.value = value


class _Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg)


class _Logger:
    def info(self, _msg):
        return None


class _Node:
    parameter_overrides = {}

    def __init__(self, _name):
        self.parameters = {}
        self.publisher = None
        self.subscriptions = []
        self._logger = _Logger()

    def declare_parameter(self, name, default):
        self.parameters[name] = self.parameter_overrides.get(name, default)

    def get_parameter(self, name):
        return _Parameter(self.parameters[name])

    def create_publisher(self, _msg_type, _topic, _depth):
        self.publisher = _Publisher()
        return self.publisher

    def create_subscription(self, msg_type, topic, callback, depth):
        sub = {
            "msg_type": msg_type,
            "topic": topic,
            "callback": callback,
            "depth": depth,
        }
        self.subscriptions.append(sub)
        return sub

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

    fake_std_msgs = types.ModuleType("std_msgs")
    fake_std_msgs_msg = types.ModuleType("std_msgs.msg")
    fake_std_msgs_msg.String = _String
    fake_std_msgs.msg = fake_std_msgs_msg

    sys.modules["rclpy"] = fake_rclpy
    sys.modules["rclpy.node"] = fake_rclpy_node
    sys.modules["std_msgs"] = fake_std_msgs
    sys.modules["std_msgs.msg"] = fake_std_msgs_msg


_install_ros_fakes()

from cs603_voice_intent.robot_response_node import (  # noqa: E402
    RobotResponseNode,
    speech_for_intent,
    speech_for_state,
)


class RobotResponseNodeTest(unittest.TestCase):
    def setUp(self):
        _Node.parameter_overrides = {}

    def tearDown(self):
        _Node.parameter_overrides = {}

    def make_node(self, **parameter_overrides):
        _Node.parameter_overrides = parameter_overrides
        return RobotResponseNode()

    def test_speech_for_intent(self):
        self.assertEqual(speech_for_intent("CMD_FOLLOW"), "Following.")
        self.assertEqual(speech_for_intent("CMD_STOP"), "Stopped.")
        self.assertEqual(speech_for_intent("CMD_APPROACH"), "Approaching.")
        self.assertEqual(speech_for_intent("CMD_UNKNOWN"), "I did not understand.")

    def test_speech_for_state(self):
        self.assertEqual(speech_for_state("FOLLOWING"), "Following.")
        self.assertEqual(speech_for_state("STOPPED"), "Stopped.")
        self.assertEqual(speech_for_state("APPROACHING"), "Approaching.")
        self.assertEqual(speech_for_state("IDLE"), "Ready.")

    def test_publishes_ack_for_intent(self):
        node = self.make_node()

        node._on_intent(_String("CMD_FOLLOW"))

        self.assertEqual(node.publisher.messages[-1].data, "Following.")

    def test_publishes_ack_for_state(self):
        node = self.make_node()

        node._on_state(_String("STOPPED"))

        self.assertEqual(node.publisher.messages[-1].data, "Stopped.")

    def test_suppresses_duplicate_state_by_default(self):
        node = self.make_node()

        node._on_state(_String("FOLLOWING"))
        node._on_state(_String("FOLLOWING"))

        self.assertEqual(len(node.publisher.messages), 1)


if __name__ == "__main__":
    unittest.main()
