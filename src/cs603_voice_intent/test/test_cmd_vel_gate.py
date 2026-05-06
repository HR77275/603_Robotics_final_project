import sys
import types
import unittest
import math


class _Vector:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0


class _Twist:
    def __init__(self):
        self.linear = _Vector()
        self.angular = _Vector()


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
    def __init__(self):
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg)


class _Logger:
    def info(self, _msg):
        return None

    def warn(self, _msg):
        return None


class _Node:
    parameter_overrides = {}

    def __init__(self, _name):
        self.parameters = {}
        self.publisher = None
        self.subscriptions = []
        self.timers = []
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

    def create_timer(self, period_sec, callback):
        timer = {"period_sec": period_sec, "callback": callback}
        self.timers.append(timer)
        return timer

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

from cs603_voice_intent.cmd_vel_gate import CmdVelGate  # noqa: E402


def _raw_twist(linear_x=0.12, angular_z=0.4):
    msg = _Twist()
    msg.linear.x = linear_x
    msg.angular.z = angular_z
    return msg


class CmdVelGateTest(unittest.TestCase):
    def setUp(self):
        _Node.parameter_overrides = {}

    def tearDown(self):
        _Node.parameter_overrides = {}

    def make_node(self, **parameter_overrides):
        _Node.parameter_overrides = parameter_overrides
        return CmdVelGate()

    def assert_zero_twist(self, msg):
        self.assertEqual(msg.linear.x, 0.0)
        self.assertEqual(msg.linear.y, 0.0)
        self.assertEqual(msg.linear.z, 0.0)
        self.assertEqual(msg.angular.x, 0.0)
        self.assertEqual(msg.angular.y, 0.0)
        self.assertEqual(msg.angular.z, 0.0)

    def test_inactive_gate_blocks_raw_motion(self):
        node = self.make_node(enable_motion=True)

        node._on_raw_cmd(_raw_twist())

        self.assertEqual(len(node.publisher.messages), 1)
        self.assert_zero_twist(node.publisher.messages[-1])

    def test_enable_motion_false_blocks_even_when_active(self):
        node = self.make_node(enable_motion=False)

        node._on_active(_Bool(True))
        node._on_raw_cmd(_raw_twist())

        self.assertEqual(len(node.publisher.messages), 1)
        self.assert_zero_twist(node.publisher.messages[-1])

    def test_active_gate_passes_raw_motion_when_enabled(self):
        node = self.make_node(enable_motion=True)
        raw = _raw_twist(linear_x=0.08, angular_z=-0.2)

        node._on_active(_Bool(True))
        node._on_raw_cmd(raw)

        self.assertEqual(len(node.publisher.messages), 1)
        out = node.publisher.messages[-1]
        self.assertEqual(out.linear.x, 0.08)
        self.assertEqual(out.angular.z, -0.2)
        self.assertIsNot(out, raw)

    def test_active_gate_caps_raw_motion_when_enabled(self):
        node = self.make_node(enable_motion=True, max_linear_speed=0.2, max_angular_speed=0.6)
        raw = _raw_twist(linear_x=9.0, angular_z=-9.0)

        node._on_active(_Bool(True))
        node._on_raw_cmd(raw)

        out = node.publisher.messages[-1]
        self.assertEqual(out.linear.x, 0.2)
        self.assertEqual(out.angular.z, -0.6)

    def test_active_gate_zeroes_nonfinite_raw_motion(self):
        node = self.make_node(enable_motion=True)
        raw = _raw_twist(linear_x=math.nan, angular_z=math.inf)

        node._on_active(_Bool(True))
        node._on_raw_cmd(raw)

        self.assert_zero_twist(node.publisher.messages[-1])

    def test_stop_intent_disables_gate_and_zeroes_output(self):
        node = self.make_node(enable_motion=True)
        node._on_active(_Bool(True))
        node._on_raw_cmd(_raw_twist())

        node._on_intent(_String("CMD_STOP"))
        node._on_raw_cmd(_raw_twist())

        self.assertFalse(node.active)
        self.assert_zero_twist(node.publisher.messages[-1])

    def test_stale_raw_command_zeroes_output(self):
        node = self.make_node(enable_motion=True, stale_timeout_sec=0.1)
        node._on_active(_Bool(True))
        node._on_raw_cmd(_raw_twist())
        node._last_raw_time -= 1.0

        node._on_timer()

        self.assert_zero_twist(node.publisher.messages[-1])

    def test_stale_active_signal_zeroes_output(self):
        node = self.make_node(enable_motion=True, active_timeout_sec=0.1)
        node._on_active(_Bool(True))
        node._on_raw_cmd(_raw_twist())
        node._last_active_time -= 1.0

        node._on_timer()

        self.assertFalse(node.active)
        self.assert_zero_twist(node.publisher.messages[-1])


if __name__ == "__main__":
    unittest.main()
