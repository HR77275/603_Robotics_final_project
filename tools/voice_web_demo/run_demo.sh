#!/usr/bin/env bash
# CS603 voice web demo — one-command launcher.
#
# Usage:
#   bash tools/voice_web_demo/run_demo.sh           # auto-detect platform
#   bash tools/voice_web_demo/run_demo.sh --help    # show options
#
# What it does:
#   - Linux  -> native ROS publish (no Docker). Sources $ROS_WS or
#              $HOME/robomaster_ws/install/setup.bash by default.
#   - macOS  -> Docker mode through container $CS603_ROS_CONTAINER
#              (default cs603_robomaster_sdkports).
#   - Verifies whisper is installed (PATH or $CS603_WHISPER_BIN).
#   - Honors $CS603_VOICE_WEB_HOST, $CS603_VOICE_WEB_PORT.
#
# Override anything via env vars or pass extra flags through to server.py.

set -euo pipefail

usage() {
    cat <<USAGE
CS603 voice web demo launcher

Environment variables:
  CS603_VOICE_WEB_HOST     Host to bind (default 127.0.0.1)
  CS603_VOICE_WEB_PORT     Port to bind (default 8765)
  CS603_ROS_CONTAINER      Docker container name (Mac only)
  CS603_ROS_SETUP          Path to install/setup.bash (Linux native default)
  CS603_WHISPER_BIN        Whisper binary (default: shutil.which or Homebrew)
  ROS_WS                   ROS workspace root (Linux); used as ROS_SETUP fallback

Examples:
  # Linux teammate, defaults
  bash tools/voice_web_demo/run_demo.sh

  # Mac, Docker
  bash tools/voice_web_demo/run_demo.sh

  # Linux with custom workspace
  ROS_WS=\$HOME/ros2_ws bash tools/voice_web_demo/run_demo.sh

  # Pass extra flags through (--allow-lan-publish, --token, etc.)
  bash tools/voice_web_demo/run_demo.sh --allow-lan-publish

Open http://\$CS603_VOICE_WEB_HOST:\$CS603_VOICE_WEB_PORT after start.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="${REPO_ROOT}/tools/voice_web_demo/server.py"

if [[ ! -f "${SERVER}" ]]; then
    echo "error: server.py not found at ${SERVER}" >&2
    exit 1
fi

HOST="${CS603_VOICE_WEB_HOST:-127.0.0.1}"
PORT="${CS603_VOICE_WEB_PORT:-8765}"

# whisper presence check (don't fail; bridge surfaces a clear error at run time)
if [[ -z "${CS603_WHISPER_BIN:-}" ]] && ! command -v whisper >/dev/null 2>&1; then
    cat >&2 <<WARN
warning: whisper binary not found on PATH and CS603_WHISPER_BIN is unset.
The /api/transcribe endpoint will return an error until whisper is installed.

Install (macOS):     brew install openai-whisper ffmpeg
Install (Ubuntu):    sudo apt install ffmpeg && python3 -m pip install --user openai-whisper
Or set:              export CS603_WHISPER_BIN=/full/path/to/whisper

Continuing — typed text via /api/intent still works.
WARN
fi

OS_NAME="$(uname -s)"
EXTRA_ARGS=("$@")

if [[ "${OS_NAME}" == "Linux" ]]; then
    # Resolve ROS workspace setup path
    if [[ -z "${CS603_ROS_SETUP:-}" ]]; then
        if [[ -n "${ROS_WS:-}" && -f "${ROS_WS}/install/setup.bash" ]]; then
            export CS603_ROS_SETUP="${ROS_WS}/install/setup.bash"
        elif [[ -f "${HOME}/robomaster_ws/install/setup.bash" ]]; then
            export CS603_ROS_SETUP="${HOME}/robomaster_ws/install/setup.bash"
        elif [[ -f "${HOME}/ros2_ws/install/setup.bash" ]]; then
            export CS603_ROS_SETUP="${HOME}/ros2_ws/install/setup.bash"
        else
            cat >&2 <<HINT
warning: could not auto-detect a ROS workspace setup.bash.
Set CS603_ROS_SETUP or ROS_WS before running for ROS publish to work.
The bridge will start and the browser will show ROS DOWN until ROS is reachable.
HINT
        fi
    fi
    echo "Starting voice bridge in NATIVE mode."
    echo "  ROS setup: ${CS603_ROS_SETUP:-<unset>}"
    exec python3 "${SERVER}" \
        --host "${HOST}" --port "${PORT}" --ros-mode native "${EXTRA_ARGS[@]}"
elif [[ "${OS_NAME}" == "Darwin" ]]; then
    CONTAINER="${CS603_ROS_CONTAINER:-cs603_robomaster_sdkports}"
    echo "Starting voice bridge in DOCKER mode."
    echo "  Container: ${CONTAINER}"
    exec python3 "${SERVER}" \
        --host "${HOST}" --port "${PORT}" \
        --ros-mode docker --container "${CONTAINER}" "${EXTRA_ARGS[@]}"
else
    echo "warning: unrecognized OS '${OS_NAME}', defaulting to native ROS." >&2
    exec python3 "${SERVER}" \
        --host "${HOST}" --port "${PORT}" --ros-mode native "${EXTRA_ARGS[@]}"
fi
