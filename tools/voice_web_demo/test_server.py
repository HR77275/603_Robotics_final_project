import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import server


class PublishAccessTest(unittest.TestCase):
    def test_loopback_clients_can_publish_by_default(self):
        self.assertTrue(server.publish_allowed("127.0.0.1", False))
        self.assertTrue(server.publish_allowed("127.4.5.6", False))
        self.assertTrue(server.publish_allowed("::1", False))

    def test_lan_clients_require_explicit_flag(self):
        self.assertFalse(server.publish_allowed("10.0.0.18", False))
        self.assertTrue(server.publish_allowed("10.0.0.18", True))


class RequestAuthorizationTest(unittest.TestCase):
    def test_accepts_same_origin_json_with_token(self):
        headers = {
            "Content-Type": "application/json",
            "X-CS603-Voice-Token": "demo-token",
            "Host": "10.0.0.18:8765",
            "Origin": "http://10.0.0.18:8765",
            "Referer": "http://10.0.0.18:8765/",
        }

        self.assertTrue(server.request_is_authorized(headers, "demo-token"))

    def test_rejects_missing_token(self):
        headers = {"Content-Type": "application/json", "Host": "127.0.0.1:8765"}

        self.assertFalse(server.request_is_authorized(headers, "demo-token"))

    def test_rejects_cross_origin_even_with_token(self):
        headers = {
            "Content-Type": "application/json",
            "X-CS603-Voice-Token": "demo-token",
            "Host": "127.0.0.1:8765",
            "Origin": "http://evil.example",
        }

        self.assertFalse(server.request_is_authorized(headers, "demo-token"))

    def test_rejects_simple_form_posts(self):
        headers = {
            "Content-Type": "text/plain",
            "X-CS603-Voice-Token": "demo-token",
            "Host": "127.0.0.1:8765",
        }

        self.assertFalse(server.request_is_authorized(headers, "demo-token"))


class PublishIntentTest(unittest.TestCase):
    def test_rejects_non_intent_payload(self):
        with self.assertRaises(ValueError):
            server.publish_intent(["/tmp/setup.bash"], "follow me")

    @mock.patch("server.subprocess.run")
    def test_publishes_intent_through_local_ros2_cli(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="published",
            stderr="",
        )

        result = server.publish_intent(
            ["/opt/ros/humble/setup.bash", "/tmp/custom_robomaster_ws/install/setup.bash"],
            "CMD_STOP",
        )

        self.assertEqual(result.stdout, "published")
        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertEqual(args[:2], ["bash", "-lc"])
        self.assertIn("/voice_intent", args[-1])
        self.assertIn("CMD_STOP", args[-1])
        self.assertIn("/opt/ros/humble/setup.bash", args[-1])
        self.assertIn("/tmp/custom_robomaster_ws/install/setup.bash", args[-1])

    @mock.patch("server.subprocess.run")
    def test_surfaces_ros2_publish_failure(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="ros2 failed",
        )

        with self.assertRaisesRegex(RuntimeError, "ros2 failed"):
            server.publish_intent(["/tmp/setup.bash"], "CMD_STOP")

    def test_build_ros_shell_command_sources_setup_files(self):
        command = server.build_ros_shell_command(
            ["/opt/ros/humble/setup.bash", "/tmp/custom_robomaster_ws/install/setup.bash"],
            "ros2 topic list",
        )

        self.assertIn("source '/opt/ros/humble/setup.bash'", command)
        self.assertIn("source '/tmp/custom_robomaster_ws/install/setup.bash'", command)
        self.assertTrue(command.endswith("ros2 topic list"))


class WhisperEnvironmentTest(unittest.TestCase):
    def test_prepare_whisper_import_prepends_python_shims(self):
        original_path = list(sys.path)
        try:
            sys.path = [path for path in sys.path if Path(path).name != "python_shims"]
            server.prepare_whisper_import()

            self.assertEqual(Path(sys.path[0]).name, "python_shims")
            self.assertEqual(server.os.environ["NUMBA_JIT_COVERAGE"], "0")
        finally:
            sys.path = original_path

    def test_transcriber_loads_model_once(self):
        fake_whisper = types.ModuleType("whisper")
        fake_model = mock.Mock()
        fake_model.transcribe.return_value = {"text": " follow me "}
        fake_whisper.load_model = mock.Mock(return_value=fake_model)

        with mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
            transcriber = server.WhisperTranscriber("tiny.en")
            self.assertEqual(transcriber.transcribe("/tmp/a.webm"), " follow me ")
            self.assertEqual(transcriber.transcribe("/tmp/b.webm"), " follow me ")

        fake_whisper.load_model.assert_called_once_with("tiny.en")
        self.assertEqual(fake_model.transcribe.call_count, 2)


if __name__ == "__main__":
    unittest.main()
