#!/usr/bin/env python3
"""WSL/Ubuntu web voice panel for the CS603 RoboMaster demo.

The server has one safety boundary: it publishes std_msgs/String intents only.
It never publishes /cmd_vel or starts the motion bridge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


WHISPER_BIN = os.environ.get("CS603_WHISPER_BIN", "whisper")
WHISPER_MODEL = os.environ.get("CS603_WHISPER_MODEL", "base.en")
STT_BACKEND = os.environ.get("CS603_STT_BACKEND", "auto").strip().lower()
VOICE_PROVIDER = os.environ.get("CS603_VOICE_PROVIDER", "browser-webspeech").strip().lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.environ.get("CS603_OPENAI_REALTIME_MODEL", "gpt-realtime-2").strip()
OPENAI_REALTIME_VOICE = os.environ.get("CS603_OPENAI_REALTIME_VOICE", "marin").strip()
OPENAI_REALTIME_CLIENT_SECRET_URL = "https://api.openai.com/v1/realtime/client_secrets"
EXTERNAL_REALTIME_URL = os.environ.get("CS603_EXTERNAL_REALTIME_URL", "").strip()
EXTERNAL_REALTIME_LABEL = os.environ.get("CS603_EXTERNAL_REALTIME_LABEL", "external-realtime").strip()
DEFAULT_WORKSPACE = Path(os.environ.get("ROBOMASTER_WS", "~/robomaster_ws")).expanduser()
DEFAULT_ROS_SETUP_FILES = (
    "/opt/ros/humble/setup.bash",
    os.environ.get("CS603_ROS_SETUP", str(DEFAULT_WORKSPACE / "install" / "setup.bash")),
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PATH = Path(__file__).with_name("index.html")
PYTHON_SHIMS_PATH = Path(__file__).with_name("python_shims")
VOICE_PACKAGE_PATH = REPO_ROOT / "cs603_voice_intent"
TOKEN_PLACEHOLDER = "__CS603_VOICE_DEMO_TOKEN__"

sys.path.insert(0, str(VOICE_PACKAGE_PATH))

from cs603_voice_intent.intent_classifier import (  # noqa: E402
    CMD_APPROACH,
    CMD_FOLLOW,
    CMD_STOP,
    CMD_UNKNOWN,
    classify_intent,
)


ALLOWED_INTENTS = {CMD_APPROACH, CMD_FOLLOW, CMD_STOP, CMD_UNKNOWN}
VOICE_PROVIDER_IDS = {"browser-webspeech", "local-whisper", "openai-realtime", "external-realtime"}
DEFAULT_OPENAI_REALTIME_INSTRUCTIONS = (
    "You are Sam, the CS603 DJI RoboMaster robot voice. Keep replies short, natural, "
    "and spoken. The robot only has four safe command intents: CMD_FOLLOW, CMD_STOP, "
    "CMD_APPROACH, and CMD_UNKNOWN. When the user asks the robot to follow, stop, "
    "or come closer, call publish_robot_intent with the matching intent. Do not invent "
    "other robot actions. If the user says stop, wait, emergency, or anything unsafe, "
    "prefer CMD_STOP."
)
OPENAI_REALTIME_INSTRUCTIONS = os.environ.get(
    "CS603_OPENAI_REALTIME_INSTRUCTIONS",
    DEFAULT_OPENAI_REALTIME_INSTRUCTIONS,
)


class VoiceIntentServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        ros_setup_files: list[str],
        token: str,
        allow_lan_publish: bool = False,
    ) -> None:
        super().__init__(server_address, VoiceIntentHandler)
        self.ros_setup_files = ros_setup_files
        self.token = token
        self.allow_lan_publish = allow_lan_publish


class VoiceIntentHandler(BaseHTTPRequestHandler):
    server: VoiceIntentServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            page = FRONTEND_PATH.read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, self.server.token)
            self._send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/api/health":
            self._send_json(self._health())
            return
        if self.path == "/api/voice/providers":
            self._send_json(voice_provider_config())
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/intent":
            self._handle_intent()
            return
        if self.path == "/api/publish_intent":
            self._handle_publish_intent()
            return
        if self.path == "/api/transcribe":
            self._handle_transcribe()
            return
        if self.path == "/api/realtime/openai/client-secret":
            self._handle_openai_realtime_client_secret()
            return
        self.send_error(404)

    def _handle_intent(self) -> None:
        try:
            if not request_is_authorized(self.headers, self.server.token):
                raise PermissionError("unauthorized voice intent request")
            if not publish_allowed(self.client_address[0], self.server.allow_lan_publish):
                raise PermissionError("LAN publish disabled; restart with --allow-lan-publish for phone demos")

            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8"))
            command_text = str(payload.get("transcript", "")).strip()
            if not command_text:
                raise ValueError("empty transcript")

            intent = classify_intent(command_text)
            result = publish_intent(self.server.ros_setup_files, intent)
            self._send_json(
                {
                    "ok": True,
                    "transcript": command_text,
                    "commandText": command_text,
                    "intent": intent,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                }
            )
        except Exception as exc:  # noqa: BLE001 - expose demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _handle_publish_intent(self) -> None:
        try:
            if not request_is_authorized(self.headers, self.server.token):
                raise PermissionError("unauthorized publish intent request")
            if not publish_allowed(self.client_address[0], self.server.allow_lan_publish):
                raise PermissionError("LAN publish disabled; restart with --allow-lan-publish for phone demos")

            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body.decode("utf-8") or "{}")
            intent = str(payload.get("intent", "")).strip()
            transcript = str(payload.get("transcript", "")).strip()
            provider = str(payload.get("provider", "unknown")).strip() or "unknown"
            if not intent and transcript:
                intent = classify_intent(transcript)
            if not intent:
                raise ValueError("empty intent")

            response = publish_robot_intent_payload(self.server.ros_setup_files, intent, provider)
            if transcript:
                response["transcript"] = transcript
                response["commandText"] = transcript
            self._send_json(response)
        except Exception as exc:  # noqa: BLE001 - expose demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _handle_transcribe(self) -> None:
        tmp_audio = ""
        try:
            if not token_header_ok(self.headers, self.server.token):
                raise PermissionError("unauthorized transcribe request")
            if not publish_allowed(self.client_address[0], self.server.allow_lan_publish):
                raise PermissionError("LAN publish disabled; restart with --allow-lan-publish for phone demos")

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("empty audio body")
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

            backend = resolve_stt_backend()
            total_started = time.perf_counter()
            stt_started = time.perf_counter()
            text = run_whisper_with_backend(tmp_audio, backend)
            stt_ms = elapsed_ms(stt_started)
            transcript = text.strip()
            response: dict[str, Any] = {
                "ok": True,
                "transcript": transcript,
                "model": WHISPER_MODEL,
                "sttBackend": backend,
                "sttMs": stt_ms,
            }

            if transcript:
                intent = classify_intent(transcript)
                try:
                    publish_started = time.perf_counter()
                    result = publish_intent(self.server.ros_setup_files, intent)
                    response.update(
                        {
                            "intent": intent,
                            "commandText": transcript,
                            "publishMs": elapsed_ms(publish_started),
                            "stdout": result.stdout[-2000:],
                            "stderr": result.stderr[-2000:],
                        }
                    )
                except Exception as pub_exc:  # noqa: BLE001 - keep transcript visible even if ROS publish fails
                    response["intent"] = intent
                    response["publish_error"] = str(pub_exc)

            response["totalMs"] = elapsed_ms(total_started)
            self._send_json(response)
        except Exception as exc:  # noqa: BLE001 - surface demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=500)
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except OSError:
                    pass

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _health(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                [
                    "bash",
                    "-lc",
                    build_ros_shell_command(
                        self.server.ros_setup_files,
                        "ros2 pkg prefix cs603_voice_intent",
                    ),
                ],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            ok = result.returncode == 0
            return {
                "ok": ok,
                "ros_setup_files": self.server.ros_setup_files,
                "stt_backend": resolve_stt_backend_quiet(),
                "stt_model": stt_model_label(resolve_stt_backend_quiet()),
                "error": "" if ok else (result.stderr or result.stdout).strip(),
            }
        except Exception as exc:  # noqa: BLE001 - demo health endpoint.
            return {"ok": False, "ros_setup_files": self.server.ros_setup_files, "error": str(exc)}

    def _handle_openai_realtime_client_secret(self) -> None:
        try:
            if not request_is_authorized(self.headers, self.server.token):
                raise PermissionError("unauthorized realtime request")
            _ = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            data = create_openai_realtime_client_secret(
                OPENAI_API_KEY,
                openai_safety_identifier(self.server.token),
            )
            self._send_json(data)
        except Exception as exc:  # noqa: BLE001 - expose demo-time failures.
            self._send_json({"ok": False, "error": str(exc)}, status=500)

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


def publish_intent(ros_setup_files: list[str], intent: str) -> subprocess.CompletedProcess[str]:
    if intent not in ALLOWED_INTENTS:
        raise ValueError(f"refusing unexpected intent {intent!r}")

    ros_command = build_ros_shell_command(
        ros_setup_files,
        f"ros2 topic pub --once /voice_intent std_msgs/msg/String '{{data: {intent}}}'",
    )
    result = subprocess.run(
        ["bash", "-lc", ros_command],
        text=True,
        capture_output=True,
        timeout=12,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


def publish_robot_intent_payload(ros_setup_files: list[str], intent: str, provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = publish_intent(ros_setup_files, intent)
    return {
        "ok": True,
        "intent": intent,
        "provider": provider,
        "publishMs": elapsed_ms(started),
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def build_ros_shell_command(ros_setup_files: list[str], command: str) -> str:
    source_parts = [
        f"test -f {quote_shell(path)} && source {quote_shell(path)}"
        for path in ros_setup_files
        if path
    ]
    return " && ".join(source_parts + [command])


def quote_shell(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def publish_allowed(client_host: str, allow_lan_publish: bool) -> bool:
    return allow_lan_publish or client_host == "::1" or client_host.startswith("127.")


def token_header_ok(headers: Any, expected_token: str) -> bool:
    if not secrets.compare_digest(str(headers.get("X-CS603-Voice-Token", "")), expected_token):
        return False
    host = str(headers.get("Host", ""))
    return same_host_if_present(headers.get("Origin"), host) and same_host_if_present(headers.get("Referer"), host)


def request_is_authorized(headers: Any, expected_token: str) -> bool:
    if not str(headers.get("Content-Type", "")).split(";", maxsplit=1)[0].strip() == "application/json":
        return False
    return token_header_ok(headers, expected_token)


def elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def resolve_stt_backend_quiet() -> str:
    try:
        return resolve_stt_backend()
    except RuntimeError:
        return "unavailable"


def stt_model_label(backend: str) -> str:
    return WHISPER_MODEL


def voice_provider_config() -> dict[str, Any]:
    active_provider = VOICE_PROVIDER if VOICE_PROVIDER in VOICE_PROVIDER_IDS else "browser-webspeech"
    return {
        "ok": True,
        "activeProvider": active_provider,
        "intentEndpoint": "/api/intent",
        "publishIntentEndpoint": "/api/publish_intent",
        "providers": [
            {
                "id": "browser-webspeech",
                "label": "Browser Web Speech",
                "mode": "command",
                "duplex": False,
                "available": True,
                "cost": "free",
            },
            {
                "id": "local-whisper",
                "label": "Local Whisper",
                "mode": "command",
                "duplex": False,
                "available": resolve_stt_backend_quiet() != "unavailable",
                "backend": resolve_stt_backend_quiet(),
                "model": WHISPER_MODEL,
                "cost": "free",
            },
            {
                "id": "openai-realtime",
                "label": "OpenAI Realtime",
                "mode": "duplex",
                "duplex": True,
                "available": bool(OPENAI_API_KEY),
                "model": OPENAI_REALTIME_MODEL,
                "voice": OPENAI_REALTIME_VOICE,
                "clientSecretEndpoint": "/api/realtime/openai/client-secret",
                "cost": "paid",
            },
            {
                "id": "external-realtime",
                "label": EXTERNAL_REALTIME_LABEL,
                "mode": "duplex",
                "duplex": True,
                "available": bool(EXTERNAL_REALTIME_URL),
                "url": EXTERNAL_REALTIME_URL,
                "cost": "provider-dependent",
            },
        ],
    }


def build_openai_realtime_session_config() -> dict[str, Any]:
    return {
        "session": {
            "type": "realtime",
            "model": OPENAI_REALTIME_MODEL,
            "instructions": OPENAI_REALTIME_INSTRUCTIONS,
            "audio": {
                "output": {
                    "voice": OPENAI_REALTIME_VOICE,
                },
            },
            "tool_choice": "auto",
            "tools": [
                {
                    "type": "function",
                    "name": "publish_robot_intent",
                    "description": (
                        "Publish one safe command intent to the CS603 DJI RoboMaster ROS bridge. "
                        "Use this only for robot movement or stop commands."
                    ),
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "intent": {
                                "type": "string",
                                "enum": sorted(ALLOWED_INTENTS),
                                "description": "The robot command intent to publish.",
                            },
                            "transcript": {
                                "type": "string",
                                "description": "Optional short phrase that caused the command.",
                            },
                        },
                        "required": ["intent"],
                    },
                }
            ],
        }
    }


def openai_safety_identifier(token: str) -> str:
    if os.environ.get("CS603_OPENAI_SAFETY_IDENTIFIER"):
        return os.environ["CS603_OPENAI_SAFETY_IDENTIFIER"]
    digest = hashlib.sha256(f"cs603:{token}".encode("utf-8")).hexdigest()[:32]
    return f"cs603-demo-{digest}"


def create_openai_realtime_client_secret(api_key: str, safety_identifier: str) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for CS603_VOICE_PROVIDER=openai-realtime")

    body = json.dumps(build_openai_realtime_session_config()).encode("utf-8")
    request = Request(
        OPENAI_REALTIME_CLIENT_SECRET_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": safety_identifier,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI Realtime client secret failed ({exc.code}): {detail[-800:]}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI Realtime client secret failed: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI Realtime client secret returned non-JSON response") from exc
    if not isinstance(data, dict) or "value" not in data:
        raise RuntimeError("OpenAI Realtime client secret response did not include value")
    return data


def resolve_stt_backend() -> str:
    if STT_BACKEND not in ("auto", "cli", "openai-whisper"):
        raise RuntimeError(
            "CS603_STT_BACKEND must be one of: auto, cli"
        )

    return "openai-whisper-cli"


def run_whisper(audio_path: str) -> str:
    return run_whisper_with_backend(audio_path, resolve_stt_backend())


def run_whisper_with_backend(audio_path: str, backend: str) -> str:
    return run_whisper_cli(audio_path)


def run_whisper_cli(audio_path: str) -> str:
    whisper_cmd = shutil.which(WHISPER_BIN) or (WHISPER_BIN if os.path.exists(WHISPER_BIN) else "")
    if not whisper_cmd:
        raise RuntimeError(f"whisper binary not found at {WHISPER_BIN}")
    out_dir = tempfile.mkdtemp(prefix="cs603_whisper_out_")
    try:
        cmd = [
            whisper_cmd,
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
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env=whisper_subprocess_env(),
        )
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


def whisper_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [str(PYTHON_SHIMS_PATH)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env.setdefault("NUMBA_JIT_COVERAGE", "0")
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="CS603 voice web demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VOICE_WEB_PORT", "8765")))
    parser.add_argument(
        "--ros-setup",
        action="append",
        default=[],
        help=(
            "ROS setup.bash to source before publishing. May be passed more than once. "
            "Defaults to /opt/ros/humble/setup.bash and CS603_ROS_SETUP or "
            "$ROBOMASTER_WS/install/setup.bash."
        ),
    )
    parser.add_argument(
        "--allow-lan-publish",
        action="store_true",
        help="Allow non-loopback clients, like a phone on the same router, to publish /voice_intent.",
    )
    parser.add_argument("--token", default=os.environ.get("CS603_VOICE_WEB_TOKEN"))
    args = parser.parse_args()

    token = args.token or secrets.token_urlsafe(24)
    ros_setup_files = args.ros_setup or [path for path in DEFAULT_ROS_SETUP_FILES if path]
    server = VoiceIntentServer((args.host, args.port), ros_setup_files, token, args.allow_lan_publish)
    print(f"Voice web demo: http://{args.host}:{args.port}")
    print("Publishing /voice_intent with local ros2 CLI after sourcing:")
    for path in ros_setup_files:
        print(f"  {path}")
    if args.allow_lan_publish:
        print("LAN publish enabled for phone demo. Keep motion bridge disabled unless the test area is clear.")
    server.serve_forever()


if __name__ == "__main__":
    main()
