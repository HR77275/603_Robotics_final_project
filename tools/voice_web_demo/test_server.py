import os
import subprocess
import unittest
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


class SpeechAckTest(unittest.TestCase):
    def test_web_ack_text_for_intent(self):
        self.assertEqual(server.speech_for_intent("CMD_FOLLOW"), "Following.")
        self.assertEqual(server.speech_for_intent("CMD_STOP"), "Stopped.")
        self.assertEqual(server.speech_for_intent("CMD_UNKNOWN"), "I did not understand.")


class FrontendAssetsTest(unittest.TestCase):
    def test_index_uses_external_css_and_js(self):
        html = server.render_index_html("demo-token")

        self.assertIn('href="/static/style.css"', html)
        self.assertIn('src="/static/app.js"', html)
        self.assertIn('id="liveBtn"', html)
        self.assertIn('id="whisperBtn"', html)
        self.assertLess(len(html.splitlines()), 140)

    def test_app_js_gets_demo_token(self):
        script = server.render_app_js("demo-token")

        self.assertIn('const demoToken = "demo-token";', script)
        self.assertNotIn(server.TOKEN_PLACEHOLDER, script)
        self.assertIn("browser microphone requires localhost or HTTPS", script)


class RoutingTest(unittest.TestCase):
    def test_request_path_ignores_query_string(self):
        self.assertEqual(server.request_path("/static/app.js?v=1"), "/static/app.js")
        self.assertEqual(server.request_path("/api/health"), "/api/health")


class ErrorStatusTest(unittest.TestCase):
    def test_permissions_are_403(self):
        self.assertEqual(server.status_for_exception(PermissionError("no")), 403)

    def test_bad_input_is_400(self):
        self.assertEqual(server.status_for_exception(ValueError("bad")), 400)

    def test_runtime_failures_are_500(self):
        self.assertEqual(server.status_for_exception(RuntimeError("docker failed")), 500)


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


class JsonUploadLimitTest(unittest.TestCase):
    def test_accepts_json_body_under_limit(self):
        headers = {"Content-Length": "128"}

        self.assertEqual(server.parse_json_content_length(headers, max_bytes=256), 128)

    def test_rejects_json_body_over_limit(self):
        with self.assertRaisesRegex(ValueError, "json body too large"):
            server.parse_json_content_length({"Content-Length": "4096"}, max_bytes=256)


class PublishIntentTest(unittest.TestCase):
    def test_rejects_non_intent_payload(self):
        with self.assertRaises(ValueError):
            server.publish_intent("container", "follow me")

    @mock.patch("server.subprocess.run")
    def test_rejects_unknown_cmd_intent_before_docker_exec(self, run_mock):
        with self.assertRaises(ValueError):
            server.publish_intent("container", "CMD_DANCE")

        run_mock.assert_not_called()

    @mock.patch("server.subprocess.run")
    def test_publishes_intent_through_docker_exec(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="published",
            stderr="",
        )

        result = server.publish_intent("cs603_robomaster_sdkports", "CMD_STOP")

        self.assertEqual(result.stdout, "published")
        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertEqual(args[:3], ["docker", "exec", "cs603_robomaster_sdkports"])
        self.assertIn("/voice_intent", args[-1])
        self.assertIn("CMD_STOP", args[-1])

    @mock.patch("server.subprocess.run")
    def test_surfaces_docker_publish_failure(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="docker failed",
        )

        with self.assertRaisesRegex(RuntimeError, "docker failed"):
            server.publish_intent("cs603_robomaster_sdkports", "CMD_STOP")


class AudioUploadLimitTest(unittest.TestCase):
    def test_accepts_audio_body_under_limit(self):
        headers = {"Content-Length": "1024"}

        self.assertEqual(server.parse_audio_content_length(headers, max_bytes=2048), 1024)

    def test_rejects_empty_audio_body(self):
        with self.assertRaisesRegex(ValueError, "empty audio body"):
            server.parse_audio_content_length({"Content-Length": "0"}, max_bytes=2048)

    def test_rejects_audio_body_over_limit(self):
        with self.assertRaisesRegex(ValueError, "audio body too large"):
            server.parse_audio_content_length({"Content-Length": "4096"}, max_bytes=2048)

    def test_rejects_invalid_audio_body_length(self):
        with self.assertRaisesRegex(ValueError, "invalid audio body length"):
            server.parse_audio_content_length({"Content-Length": "not-a-number"}, max_bytes=2048)


class TranscribePublishResponseTest(unittest.TestCase):
    def test_publish_failure_marks_response_not_ok(self):
        def fail_publish(_container, _intent):
            raise RuntimeError("docker failed")

        response = server.publish_transcribed_text(
            "container",
            "follow me",
            publish_func=fail_publish,
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["intent"], "CMD_FOLLOW")
        self.assertEqual(response["speech"], "Following.")
        self.assertEqual(response["publish_error"], "docker failed")


class RosModeTest(unittest.TestCase):
    @mock.patch("server.subprocess.run")
    def test_publish_intent_docker_mode_uses_docker_exec(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        server.publish_intent("my-container", "CMD_STOP", mode="docker")
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[:3], ["docker", "exec", "my-container"])

    @mock.patch("server.subprocess.run")
    def test_publish_intent_native_mode_skips_docker(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        server.publish_intent("", "CMD_STOP", mode="native")
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[0], "bash")
        self.assertNotIn("docker", argv[:2])
        # Same bash command body in both modes.
        self.assertIn("/voice_intent", argv[-1])
        self.assertIn("CMD_STOP", argv[-1])

    def test_publish_intent_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "unknown ros_mode"):
            server.publish_intent("c", "CMD_STOP", mode="kubernetes")

    def test_resolve_ros_mode_auto_picks_docker_when_container_set(self):
        self.assertEqual(server.resolve_ros_mode("auto", "my-container"), "docker")

    def test_resolve_ros_mode_auto_picks_native_when_no_container(self):
        self.assertEqual(server.resolve_ros_mode("auto", None), "native")
        self.assertEqual(server.resolve_ros_mode("auto", ""), "native")

    def test_resolve_ros_mode_explicit_overrides_auto(self):
        self.assertEqual(server.resolve_ros_mode("native", "ignored"), "native")
        self.assertEqual(server.resolve_ros_mode("docker", "x"), "docker")

    @mock.patch("server.subprocess.run")
    def test_native_health_reports_mode_and_setup_path(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess([], 0, "/foo\n/bar", "")
        result = server._native_ros_health()
        self.assertEqual(result["mode"], "native")
        self.assertTrue(result["ok"])
        self.assertIn("ros_setup", result)

    @mock.patch("server.subprocess.run")
    def test_native_health_failure_surfaces_stderr(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess([], 1, "", "ros2: command not found")
        result = server._native_ros_health()
        self.assertEqual(result["mode"], "native")
        self.assertFalse(result["ok"])
        self.assertIn("ros2", result["error"])


class RosSetupPathTest(unittest.TestCase):
    @mock.patch("server.subprocess.run")
    def test_publish_intent_uses_configured_ros_setup_path(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(server, "ROS_SETUP_PATH", "/custom/ros/setup.bash"):
            server.publish_intent("container", "CMD_STOP")

        bash_command = run_mock.call_args.args[0][-1]
        self.assertIn("source /custom/ros/setup.bash", bash_command)
        self.assertNotIn("/home/ubuntu/ros2_ws/install/setup.bash", bash_command)

    def test_resolve_whisper_bin_prefers_explicit_env_var(self):
        with mock.patch.dict(os.environ, {"CS603_WHISPER_BIN": "/explicit/whisper"}):
            self.assertEqual(server.resolve_whisper_bin(), "/explicit/whisper")

    def test_resolve_whisper_bin_falls_back_to_path_lookup(self):
        env = {k: v for k, v in os.environ.items() if k != "CS603_WHISPER_BIN"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("server.shutil.which", return_value="/usr/local/bin/whisper"):
            self.assertEqual(server.resolve_whisper_bin(), "/usr/local/bin/whisper")

    def test_resolve_whisper_bin_falls_back_to_homebrew_default(self):
        env = {k: v for k, v in os.environ.items() if k != "CS603_WHISPER_BIN"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("server.shutil.which", return_value=None):
            self.assertEqual(server.resolve_whisper_bin(), server.WHISPER_BIN_DEFAULT)


if __name__ == "__main__":
    unittest.main()
