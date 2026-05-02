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
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
        if self.path != "/api/intent":
            self.send_error(404)
            return

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


def request_is_authorized(headers: Any, expected_token: str) -> bool:
    if not str(headers.get("Content-Type", "")).split(";", maxsplit=1)[0].strip() == "application/json":
        return False
    if not secrets.compare_digest(str(headers.get("X-CS603-Voice-Token", "")), expected_token):
        return False
    host = str(headers.get("Host", ""))
    return same_host_if_present(headers.get("Origin"), host) and same_host_if_present(headers.get("Referer"), host)


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
