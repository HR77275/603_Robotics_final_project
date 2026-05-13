import subprocess
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

    def test_rejects_unknown_cmd_prefixed_payload(self):
        with self.assertRaises(ValueError):
            server.publish_intent(["/tmp/setup.bash"], "CMD_SPIN")

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
    def test_whisper_env_prepends_python_shims(self):
        env = server.whisper_subprocess_env()
        first_pythonpath = env["PYTHONPATH"].split(":")[0]

        self.assertEqual(Path(first_pythonpath).name, "python_shims")
        self.assertEqual(env["NUMBA_JIT_COVERAGE"], "0")


class WhisperBackendTest(unittest.TestCase):
    @mock.patch("server.run_whisper_cli", return_value="stop")
    def test_auto_backend_uses_existing_whisper_cli(self, cli_mock):
        with mock.patch.object(server, "STT_BACKEND", "auto"):
            self.assertEqual(server.run_whisper("/tmp/audio.webm"), "stop")
        cli_mock.assert_called_once_with("/tmp/audio.webm")

    def test_rejects_removed_backend_names(self):
        with mock.patch.object(server, "STT_BACKEND", "unsupported-backend"):
            with self.assertRaisesRegex(RuntimeError, "CS603_STT_BACKEND"):
                server.run_whisper("/tmp/audio.webm")


class VoiceProviderConfigTest(unittest.TestCase):
    def test_default_provider_is_free_browser_command_mode(self):
        with (
            mock.patch.object(server, "VOICE_PROVIDER", "browser-webspeech"),
            mock.patch.object(server, "OPENAI_API_KEY", ""),
            mock.patch.object(server, "EXTERNAL_REALTIME_URL", ""),
        ):
            config = server.voice_provider_config()

        self.assertEqual(config["activeProvider"], "browser-webspeech")
        self.assertEqual(config["intentEndpoint"], "/api/intent")
        self.assertEqual(config["publishIntentEndpoint"], "/api/publish_intent")
        providers = {provider["id"]: provider for provider in config["providers"]}
        self.assertTrue(providers["browser-webspeech"]["available"])
        self.assertEqual(providers["browser-webspeech"]["cost"], "free")
        self.assertFalse(providers["openai-realtime"]["available"])

    def test_openai_provider_reports_model_and_key_availability(self):
        with (
            mock.patch.object(server, "VOICE_PROVIDER", "openai-realtime"),
            mock.patch.object(server, "OPENAI_API_KEY", "sk-test"),
            mock.patch.object(server, "OPENAI_REALTIME_MODEL", "gpt-realtime-2"),
            mock.patch.object(server, "OPENAI_REALTIME_VOICE", "marin"),
        ):
            config = server.voice_provider_config()

        providers = {provider["id"]: provider for provider in config["providers"]}
        self.assertEqual(config["activeProvider"], "openai-realtime")
        self.assertTrue(providers["openai-realtime"]["available"])
        self.assertEqual(providers["openai-realtime"]["model"], "gpt-realtime-2")
        self.assertEqual(providers["openai-realtime"]["voice"], "marin")


class OpenAIRealtimeConfigTest(unittest.TestCase):
    def test_openai_session_config_has_duplex_audio_and_robot_tool(self):
        with (
            mock.patch.object(server, "OPENAI_REALTIME_MODEL", "gpt-realtime-2"),
            mock.patch.object(server, "OPENAI_REALTIME_VOICE", "marin"),
        ):
            config = server.build_openai_realtime_session_config()

        session = config["session"]
        self.assertEqual(session["type"], "realtime")
        self.assertEqual(session["model"], "gpt-realtime-2")
        self.assertEqual(session["audio"]["output"]["voice"], "marin")
        self.assertEqual(session["tool_choice"], "auto")
        tool = session["tools"][0]
        self.assertEqual(tool["name"], "publish_robot_intent")
        self.assertEqual(tool["parameters"]["properties"]["intent"]["enum"], sorted(server.ALLOWED_INTENTS))

    @mock.patch("server.urlopen")
    def test_client_secret_request_uses_server_side_key_only(self, urlopen_mock):
        response = mock.Mock()
        response.status = 200
        response.read.return_value = b'{"value":"ephemeral-test"}'
        urlopen_mock.return_value.__enter__.return_value = response

        data = server.create_openai_realtime_client_secret("sk-test", "safety-id")

        self.assertEqual(data["value"], "ephemeral-test")
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/realtime/client_secrets")
        self.assertNotIn("sk-test", str(data))


class PublishIntentPayloadTest(unittest.TestCase):
    @mock.patch("server.publish_intent")
    def test_publishes_direct_robot_intent_payload(self, publish_mock):
        publish_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="published",
            stderr="",
        )

        result = server.publish_robot_intent_payload(["/tmp/setup.bash"], "CMD_STOP", "openai-realtime")

        self.assertTrue(result["ok"])
        self.assertEqual(result["intent"], "CMD_STOP")
        self.assertEqual(result["provider"], "openai-realtime")
        publish_mock.assert_called_once_with(["/tmp/setup.bash"], "CMD_STOP")


if __name__ == "__main__":
    unittest.main()
