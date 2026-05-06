#!/usr/bin/env python3
"""Host-side web voice panel for the CS603 RoboMaster demo.

The server has one safety boundary: it publishes std_msgs/String intents only.
It never publishes /cmd_vel or starts the motion bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


WHISPER_BIN_DEFAULT = "/opt/homebrew/bin/whisper"
ROS_SETUP_DEFAULT = "/home/ubuntu/ros2_ws/install/setup.bash"


def resolve_whisper_bin() -> str:
    """Resolve the whisper binary path.

    Order: explicit CS603_WHISPER_BIN env var > PATH lookup via shutil.which >
    macOS Homebrew default. The Homebrew default is kept as a final fallback so
    the missing-binary error message at runtime is consistent and self-explanatory.
    """
    explicit = os.environ.get("CS603_WHISPER_BIN")
    if explicit:
        return explicit
    found = shutil.which("whisper")
    if found:
        return found
    return WHISPER_BIN_DEFAULT


WHISPER_BIN = resolve_whisper_bin()
WHISPER_MODEL = os.environ.get("CS603_WHISPER_MODEL", "base.en")
ROS_SETUP_PATH = os.environ.get("CS603_ROS_SETUP", ROS_SETUP_DEFAULT)
MAX_AUDIO_UPLOAD_BYTES = int(os.environ.get("CS603_MAX_AUDIO_UPLOAD_BYTES", str(12 * 1024 * 1024)))
MAX_JSON_UPLOAD_BYTES = int(os.environ.get("CS603_MAX_JSON_UPLOAD_BYTES", "4096"))


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PATH = Path(__file__).with_name("index.html")
STYLE_PATH = Path(__file__).with_name("style.css")
APP_JS_PATH = Path(__file__).with_name("app.js")
VOICE_PACKAGE_PATH = REPO_ROOT / "src" / "cs603_voice_intent"
TOKEN_PLACEHOLDER = "__CS603_VOICE_DEMO_TOKEN__"

sys.path.insert(0, str(VOICE_PACKAGE_PATH))

from cs603_voice_intent.intent_classifier import (  # noqa: E402
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_STOP,
    CMD_UNKNOWN,
    classify_intent,
)
from cs603_voice_intent.speech_responses import speech_for_intent  # noqa: E402


ALLOWED_INTENTS = {CMD_APPROACH, CMD_FOLLOW, CMD_STOP, CMD_UNKNOWN}


class VoiceIntentServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        container: str,
        token: str,
        allow_lan_publish: bool = False,
        ros_mode: str = "docker",
    ) -> None:
        super().__init__(server_address, VoiceIntentHandler)
        self.container = container
        self.token = token
        self.allow_lan_publish = allow_lan_publish
        self.ros_mode = ros_mode  # "docker" or "native"


class VoiceIntentHandler(BaseHTTPRequestHandler):
    server: VoiceIntentServer

    def do_GET(self) -> None:  # noqa: N802
        path = request_path(self.path)
        if path == "/":
            page = render_index_html(self.server.token)
            self._send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/static/style.css":
            self._send_bytes(STYLE_PATH.read_bytes(), "text/css; charset=utf-8")
            return
        if path == "/static/app.js":
            script = render_app_js(self.server.token)
            self._send_bytes(script.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if path == "/api/health":
            self._send_json(self._health())
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = request_path(self.path)
        if path == "/api/intent":
            self._handle_intent()
            return
        if path == "/api/transcribe":
            self._handle_transcribe()
            return
        self.send_error(404)

    def _handle_intent(self) -> None:
        try:
            if not request_is_authorized(self.headers, self.server.token):
                raise PermissionError("unauthorized voice intent request")
            if not publish_allowed(self.client_address[0], self.server.allow_lan_publish):
                raise PermissionError("LAN publish disabled; restart with --allow-lan-publish for phone demos")

            body = self.rfile.read(parse_json_content_length(self.headers))
            payload = json.loads(body.decode("utf-8"))
            command_text = str(payload.get("transcript", "")).strip()
            if not command_text:
                raise ValueError("empty transcript")

            intent = classify_intent(command_text)
            speech = speech_for_intent(intent)
            result = publish_intent(self.server.container, intent, mode=self.server.ros_mode)
            self._send_json(
                {
                    "ok": True,
                    "transcript": command_text,
                    "commandText": command_text,
                    "intent": intent,
                    "speech": speech,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                }
            )
        except Exception as exc:  # noqa: BLE001 - expose demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=status_for_exception(exc))

    def _handle_transcribe(self) -> None:
        tmp_audio = ""
        try:
            if not token_header_ok(self.headers, self.server.token):
                raise PermissionError("unauthorized transcribe request")
            if not publish_allowed(self.client_address[0], self.server.allow_lan_publish):
                raise PermissionError("LAN publish disabled; restart with --allow-lan-publish for phone demos")

            length = parse_audio_content_length(self.headers)
            data = self.rfile.read(length)

            ext = ".webm"
            ctype = str(self.headers.get("Content-Type", "")).lower()
            if "wav" in ctype:
                ext = ".wav"
            elif "ogg" in ctype:
                ext = ".ogg"
            elif "mp4" in ctype:
                ext = ".m4a"

            fd, tmp_audio = tempfile.mkstemp(suffix=ext, prefix="cs603_voice_")
            os.close(fd)
            with open(tmp_audio, "wb") as fh:
                fh.write(data)

            text = run_whisper(tmp_audio)
            transcript = text.strip()
            response: dict[str, Any] = {
                "ok": True,
                "transcript": transcript,
                "model": WHISPER_MODEL,
            }

            if transcript:
                response.update(
                    publish_transcribed_text(
                        self.server.container,
                        transcript,
                        publish_func=lambda c, i: publish_intent(c, i, mode=self.server.ros_mode),
                    )
                )

            self._send_json(response, status=200 if response.get("ok", False) else 500)
        except Exception as exc:  # noqa: BLE001 - surface demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=status_for_exception(exc))
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except OSError:
                    pass

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _health(self) -> dict[str, Any]:
        if self.server.ros_mode == "native":
            return _native_ros_health()
        return _docker_ros_health(self.server.container)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def publish_intent(
    container: str,
    intent: str,
    *,
    mode: str = "docker",
) -> subprocess.CompletedProcess[str]:
    """Publish a CMD_* intent to /voice_intent.

    Two modes:
      - "docker": run via `docker exec <container> bash -lc ...` (Soumik's Mac).
      - "native": run via `bash -lc ...` directly on the host (Himanshu's Linux).

    Both paths source /opt/ros/humble/setup.bash and the workspace pointed at
    by $CS603_ROS_SETUP (default /home/ubuntu/ros2_ws/install/setup.bash).
    """
    if intent not in ALLOWED_INTENTS:
        raise ValueError(f"refusing unexpected intent {intent!r}")
    if mode not in ("docker", "native"):
        raise ValueError(f"unknown ros_mode {mode!r}; use 'docker' or 'native'")

    ros_command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {shlex.quote(ROS_SETUP_PATH)} && "
        f"ros2 topic pub --once /voice_intent std_msgs/msg/String '{{data: {intent}}}'"
    )
    if mode == "docker":
        argv = ["docker", "exec", container, "bash", "-lc", ros_command]
    else:
        argv = ["bash", "-lc", ros_command]
    result = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        timeout=12,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


def _docker_ros_health(container: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        ok = result.returncode == 0 and result.stdout.strip() == "true"
        return {
            "ok": ok,
            "mode": "docker",
            "container": container,
            "error": "" if ok else (result.stderr or result.stdout).strip(),
        }
    except Exception as exc:  # noqa: BLE001 - demo health endpoint.
        return {"ok": False, "mode": "docker", "container": container, "error": str(exc)}


def _native_ros_health() -> dict[str, Any]:
    probe = (
        "source /opt/ros/humble/setup.bash && "
        f"source {shlex.quote(ROS_SETUP_PATH)} && "
        "ros2 node list"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", probe],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        ok = result.returncode == 0
        return {
            "ok": ok,
            "mode": "native",
            "ros_setup": ROS_SETUP_PATH,
            "error": "" if ok else (result.stderr or result.stdout).strip(),
        }
    except Exception as exc:  # noqa: BLE001 - demo health endpoint.
        return {"ok": False, "mode": "native", "ros_setup": ROS_SETUP_PATH, "error": str(exc)}


def publish_transcribed_text(
    container: str,
    transcript: str,
    publish_func=publish_intent,
) -> dict[str, Any]:
    intent = classify_intent(transcript)
    speech = speech_for_intent(intent)
    response: dict[str, Any] = {
        "ok": True,
        "intent": intent,
        "commandText": transcript,
        "speech": speech,
    }
    try:
        result = publish_func(container, intent)
    except Exception as pub_exc:  # noqa: BLE001 - keep transcript visible even if ROS publish fails
        response["ok"] = False
        response["publish_error"] = str(pub_exc)
        return response

    response["stdout"] = result.stdout[-2000:]
    response["stderr"] = result.stderr[-2000:]
    return response


def parse_audio_content_length(headers: Any, max_bytes: int = MAX_AUDIO_UPLOAD_BYTES) -> int:
    try:
        length = int(headers.get("Content-Length", "0"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid audio body length") from exc
    if length <= 0:
        raise ValueError("empty audio body")
    if length > max_bytes:
        raise ValueError(f"audio body too large: {length} > {max_bytes} bytes")
    return length


def parse_json_content_length(headers: Any, max_bytes: int = MAX_JSON_UPLOAD_BYTES) -> int:
    try:
        length = int(headers.get("Content-Length", "0"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid json body length") from exc
    if length <= 0:
        raise ValueError("empty json body")
    if length > max_bytes:
        raise ValueError(f"json body too large: {length} > {max_bytes} bytes")
    return length


def publish_allowed(client_host: str, allow_lan_publish: bool) -> bool:
    return allow_lan_publish or client_host == "::1" or client_host.startswith("127.")


def request_path(raw_path: str) -> str:
    return urlparse(raw_path).path


def status_for_exception(exc: Exception) -> int:
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return 400
    return 500


def token_header_ok(headers: Any, expected_token: str) -> bool:
    if not secrets.compare_digest(str(headers.get("X-CS603-Voice-Token", "")), expected_token):
        return False
    host = str(headers.get("Host", ""))
    return same_host_if_present(headers.get("Origin"), host) and same_host_if_present(headers.get("Referer"), host)


def request_is_authorized(headers: Any, expected_token: str) -> bool:
    if not str(headers.get("Content-Type", "")).split(";", maxsplit=1)[0].strip() == "application/json":
        return False
    return token_header_ok(headers, expected_token)


def run_whisper(audio_path: str) -> str:
    if not os.path.exists(WHISPER_BIN):
        raise RuntimeError(f"whisper binary not found at {WHISPER_BIN}")
    out_dir = tempfile.mkdtemp(prefix="cs603_whisper_out_")
    try:
        cmd = [
            WHISPER_BIN,
            audio_path,
            "--model", WHISPER_MODEL,
            "--language", "en",
            "--task", "transcribe",
            "--fp16", "False",
            "--temperature", "0.0",
            "--no_speech_threshold", "0.6",
            "--logprob_threshold", "-1.0",
            "--condition_on_previous_text", "False",
            "--output_dir", out_dir,
            "--output_format", "txt",
            "--verbose", "False",
        ]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "whisper failed").strip()[-1500:])
        base = os.path.splitext(os.path.basename(audio_path))[0]
        txt_path = os.path.join(out_dir, base + ".txt")
        if not os.path.exists(txt_path):
            return ""
        with open(txt_path, encoding="utf-8") as fh:
            return fh.read()
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def same_host_if_present(url: str | None, host: str) -> bool:
    if not url:
        return True
    parsed = urlparse(str(url))
    return parsed.netloc == host


def render_index_html(token: str) -> str:
    return FRONTEND_PATH.read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, token)


def render_app_js(token: str) -> str:
    return APP_JS_PATH.read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, token)


def resolve_ros_mode(arg_mode: str, container: str | None) -> str:
    """Resolve auto -> docker if a container was given, else native."""
    if arg_mode == "auto":
        return "docker" if container else "native"
    return arg_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="CS603 voice web demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VOICE_WEB_PORT", "8765")))
    parser.add_argument(
        "--container",
        default=os.environ.get("CS603_ROS_CONTAINER"),
        help="Docker container name to publish through. Omit for native ROS publish.",
    )
    parser.add_argument(
        "--ros-mode",
        choices=("auto", "docker", "native"),
        default=os.environ.get("CS603_ROS_MODE", "auto"),
        help="auto picks docker if --container is set, else native (host ros2).",
    )
    parser.add_argument(
        "--allow-lan-publish",
        action="store_true",
        help="Allow non-loopback clients, like a phone on the same router, to publish /voice_intent.",
    )
    parser.add_argument("--token", default=os.environ.get("CS603_VOICE_WEB_TOKEN"))
    args = parser.parse_args()

    token = args.token or secrets.token_urlsafe(24)
    ros_mode = resolve_ros_mode(args.ros_mode, args.container)
    container = args.container or ""
    if ros_mode == "docker" and not container:
        parser.error("--ros-mode=docker requires --container <name>")
    server = VoiceIntentServer(
        (args.host, args.port),
        container,
        token,
        args.allow_lan_publish,
        ros_mode=ros_mode,
    )
    print(f"Voice web demo: http://{args.host}:{args.port}")
    if ros_mode == "docker":
        print(f"Publishing /voice_intent through Docker container: {container}")
    else:
        print(f"Publishing /voice_intent natively. ROS setup: {ROS_SETUP_PATH}")
    if args.allow_lan_publish:
        print(
            "LAN publish enabled. This is not strong authentication; keep final motion "
            "disabled unless the test area is clear. Browser mic over LAN also needs HTTPS."
        )
    server.serve_forever()


if __name__ == "__main__":
    main()
