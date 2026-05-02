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
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


WHISPER_BIN = os.environ.get("CS603_WHISPER_BIN", "/opt/homebrew/bin/whisper")
WHISPER_MODEL = os.environ.get("CS603_WHISPER_MODEL", "base.en")


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PATH = Path(__file__).with_name("index.html")
VOICE_PACKAGE_PATH = REPO_ROOT / "src" / "cs603_voice_intent"
TOKEN_PLACEHOLDER = "__CS603_VOICE_DEMO_TOKEN__"

sys.path.insert(0, str(VOICE_PACKAGE_PATH))

from cs603_voice_intent.intent_classifier import classify_intent  # noqa: E402


class VoiceIntentServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        container: str,
        token: str,
        allow_lan_publish: bool = False,
    ) -> None:
        super().__init__(server_address, VoiceIntentHandler)
        self.container = container
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
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/intent":
            self._handle_intent()
            return
        if self.path == "/api/transcribe":
            self._handle_transcribe()
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
            result = publish_intent(self.server.container, intent)
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

            text = run_whisper(tmp_audio)
            transcript = text.strip()
            response: dict[str, Any] = {
                "ok": True,
                "transcript": transcript,
                "model": WHISPER_MODEL,
            }

            if transcript:
                intent = classify_intent(transcript)
                try:
                    result = publish_intent(self.server.container, intent)
                    response.update(
                        {
                            "intent": intent,
                            "commandText": transcript,
                            "stdout": result.stdout[-2000:],
                            "stderr": result.stderr[-2000:],
                        }
                    )
                except Exception as pub_exc:  # noqa: BLE001 - keep transcript visible even if ROS publish fails
                    response["intent"] = intent
                    response["publish_error"] = str(pub_exc)

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
                ["docker", "inspect", "-f", "{{.State.Running}}", self.server.container],
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            ok = result.returncode == 0 and result.stdout.strip() == "true"
            return {
                "ok": ok,
                "container": self.server.container,
                "error": "" if ok else (result.stderr or result.stdout).strip(),
            }
        except Exception as exc:  # noqa: BLE001 - demo health endpoint.
            return {"ok": False, "container": self.server.container, "error": str(exc)}

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


def publish_intent(container: str, intent: str) -> subprocess.CompletedProcess[str]:
    if not intent.startswith("CMD_"):
        raise ValueError(f"refusing unexpected intent {intent!r}")

    ros_command = (
        "source /opt/ros/humble/setup.bash && "
        "source /home/ubuntu/ros2_ws/install/setup.bash && "
        f"ros2 topic pub --once /voice_intent std_msgs/msg/String '{{data: {intent}}}'"
    )
    result = subprocess.run(
        ["docker", "exec", container, "bash", "-lc", ros_command],
        text=True,
        capture_output=True,
        timeout=12,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


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


def main() -> None:
    parser = argparse.ArgumentParser(description="CS603 voice web demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VOICE_WEB_PORT", "8765")))
    parser.add_argument(
        "--container",
        default=os.environ.get("CS603_ROS_CONTAINER", "cs603_robomaster_sdkports"),
    )
    parser.add_argument(
        "--allow-lan-publish",
        action="store_true",
        help="Allow non-loopback clients, like a phone on the same router, to publish /voice_intent.",
    )
    parser.add_argument("--token", default=os.environ.get("CS603_VOICE_WEB_TOKEN"))
    args = parser.parse_args()

    token = args.token or secrets.token_urlsafe(24)
    server = VoiceIntentServer((args.host, args.port), args.container, token, args.allow_lan_publish)
    print(f"Voice web demo: http://{args.host}:{args.port}")
    print(f"Publishing /voice_intent through Docker container: {args.container}")
    if args.allow_lan_publish:
        print("LAN publish enabled for phone demo. Keep motion bridge disabled unless the test area is clear.")
    server.serve_forever()


if __name__ == "__main__":
    main()
