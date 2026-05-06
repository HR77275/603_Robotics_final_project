import queue
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
    def __init__(self, topic):
        self.topic = topic
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg)


class _Logger:
    def info(self, _message):
        return None

    def error(self, _message):
        return None


class _Node:
    parameter_overrides = {}

    def __init__(self, _name):
        self.parameters = {}
        self.publisher = None
        self.timer = None

    def declare_parameter(self, name, default):
        self.parameters[name] = self.parameter_overrides.get(name, default)

    def get_parameter(self, name):
        return _Parameter(self.parameters[name])

    def create_publisher(self, _msg_type, topic, _depth):
        self.publisher = _Publisher(topic)
        return self.publisher

    def create_timer(self, period_sec, callback):
        self.timer = {"period_sec": period_sec, "callback": callback}
        return self.timer

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
    fake_std_msgs_msg.String = _String
    fake_std_msgs.msg = fake_std_msgs_msg

    sys.modules["rclpy"] = fake_rclpy
    sys.modules["rclpy.node"] = fake_rclpy_node
    sys.modules["std_msgs"] = fake_std_msgs
    sys.modules["std_msgs.msg"] = fake_std_msgs_msg


_install_ros_fakes()

from cs603_voice_intent.voice_intent_node import VoiceIntentNode  # noqa: E402


class VoiceIntentNodeTest(unittest.TestCase):
    def setUp(self):
        _Node.parameter_overrides = {"input_mode": "param"}

    def tearDown(self):
        _Node.parameter_overrides = {}

    def make_node(self, **parameter_overrides):
        overrides = {"input_mode": "param"}
        overrides.update(parameter_overrides)
        _Node.parameter_overrides = overrides
        return VoiceIntentNode()

    def test_publish_transcript_writes_intent_message(self):
        node = self.make_node()

        node._publish_transcript("follow me")

        self.assertEqual(node.publisher.topic, "/voice_intent")
        self.assertEqual(node.publisher.messages[-1].data, "CMD_FOLLOW")
        self.assertTrue(node._published_once)

    def test_publish_unknown_false_suppresses_unknown_intent(self):
        node = self.make_node(publish_unknown=False)

        node._publish_transcript("bring me coffee")

        self.assertEqual(node.publisher.messages, [])
        self.assertFalse(node._published_once)

    def test_param_mode_publishes_changed_stub_text_once(self):
        node = self.make_node(stub_text="stop")

        node._on_timer()
        node._on_timer()

        self.assertEqual([msg.data for msg in node.publisher.messages], ["CMD_STOP"])

    def test_timer_drains_queued_transcripts(self):
        node = self.make_node()
        node._transcripts = queue.Queue()
        node._transcripts.put("follow me")
        node._transcripts.put("come here")

        node._on_timer()

        self.assertEqual(
            [msg.data for msg in node.publisher.messages],
            ["CMD_FOLLOW", "CMD_APPROACH"],
        )

    def test_exit_after_first_publish_raises_system_exit(self):
        node = self.make_node(exit_after_first_publish=True)
        node._transcripts.put("stop")

        with self.assertRaises(SystemExit) as exc:
            node._on_timer()

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(node.publisher.messages[-1].data, "CMD_STOP")

    def test_unsupported_input_mode_marks_fatal_and_exits(self):
        node = self.make_node(input_mode="bogus")

        self.assertTrue(node._fatal_error)

        with self.assertRaises(SystemExit) as exc:
            node._on_timer()

        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(node.publisher.messages, [])


if __name__ == "__main__":
    unittest.main()
