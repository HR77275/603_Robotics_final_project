# Voice Intent Runbook

This package is Soumik's CS603 final-project lane: spoken command text becomes ROS 2 intent messages on `/voice_intent`.

## Build In The Humble Container

```bash
docker cp src/cs603_voice_intent cs603_robomaster:/home/ubuntu/ros2_ws/src/
docker exec -it cs603_robomaster bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/ros2_ws
colcon build --packages-select cs603_voice_intent
source install/setup.bash
```

## Intent-Only Smoke Test

Terminal 1:

```bash
ros2 topic echo /voice_intent
```

Terminal 2:

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=stdin
```

Type one phrase per line:

```text
follow me
stop
come here
```

Expected messages:

```text
CMD_FOLLOW
CMD_STOP
CMD_APPROACH
```

## Robot Motion Demo

Only run this after the robot is connected, the area is clear, and emergency stop is ready.

```bash
ros2 launch cs603_voice_intent voice_demo.launch.py input_mode:=stdin enable_motion:=true
```

The bridge maps:

- `CMD_STOP` to zero `/cmd_vel`.
- `CMD_FOLLOW` to a short, slow forward command.
- `CMD_APPROACH` to a short, slow forward command.

Emergency stop:

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

## Whisper Mode

Two ways to run Whisper. Pick one.

### A. ROS-side `mic_once` (in-container)

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=mic_once -p whisper_model:=small
```

Docker Desktop may not expose the Mac microphone to the Linux container. If `mic_once` fails with no audio device, use `stdin` mode for robot-day testing or use the Mac-host web bridge below.

### B. Mac-host web bridge (recommended for live demo)

`tools/voice_web_demo/server.py` exposes `/api/transcribe`. The browser records audio with MediaRecorder, posts the blob to the Mac, the Mac runs `/opt/homebrew/bin/whisper` locally (no API key required), classifies the intent, and publishes on `/voice_intent` through the Docker container.

```bash
brew install openai-whisper ffmpeg
python3 tools/voice_web_demo/server.py --host 0.0.0.0 --port 8765 --allow-lan-publish --token cs603-demo-local
open http://127.0.0.1:8765
```

In the UI, click `Whisper: tap to record`, speak, click again to stop. Transcript appears, intent publishes automatically. The `Talk` / `Always off` buttons keep the browser-native Web Speech API path as a backup for environments where MediaRecorder is unavailable.

Configure model + binary via env vars if needed:

```bash
CS603_WHISPER_MODEL=base.en CS603_WHISPER_BIN=/opt/homebrew/bin/whisper python3 tools/voice_web_demo/server.py ...
```

Latency: cold first call is ~10–20 s on Apple Silicon (model load); subsequent calls drop to ~2–4 s for short clips with `tiny.en`. Use `base.en` or `small.en` for accuracy at the cost of latency.

### Handoff status (2026-05-02)

- ROS package built + topic verified (`/voice_intent` publishes `std_msgs/String` with the four contract codes).
- Mac-host web bridge `/api/transcribe` smoke-tested end-to-end against `tiny.en`.
- Object-trigger remains an explicitly labeled stub at `cs603_voice_intent/object_trigger_stub.py`. Real perception integration is the next handoff for whoever picks up the camera lane.
