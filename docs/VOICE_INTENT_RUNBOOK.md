# Voice Intent Runbook

This package is Soumik's CS603 final-project lane: spoken command text becomes ROS 2 intent messages on `/voice_intent`.

## Build In The Humble Container

Robot-day rule: verify the live container name and ROS workspace path before
copying, building, or publishing. On this Mac, the verified current container is
`cs603_robomaster_sdkports`; the older `cs603_robomaster` container is stopped.
Use one container for robot-day work unless the team explicitly rebuilds the
environment. The examples below use `cs603_robomaster_sdkports` and `~/ros2_ws`.

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker exec -it cs603_robomaster_sdkports bash
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

## Legacy Direct Motion Demo

This launches the old direct voice-to-`/cmd_vel` bridge. Keep it for isolated
voice package testing only. Do not use it in the integrated camera-follow path
because the follow controller also publishes velocity commands.

Only run this after the robot is connected, the area is clear, and emergency
stop is ready.

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

## Integrated Follow Gate Demo

Use this path when Himanshu's follow controller is present. It routes the follow
controller to `/cmd_vel_follow_raw` and lets Soumik's gate publish final
`/cmd_vel`.

Safe dry-run, no final motion:

```bash
ros2 launch cs603_voice_intent voice_integration_demo.launch.py \
  input_mode:=stdin \
  launch_follow_controller:=false \
  gate_enable_motion:=false
```

After the camera/follow packages are available, launch the follow controller
through the gate:

```bash
ros2 launch cs603_voice_intent voice_integration_demo.launch.py \
  input_mode:=stdin \
  launch_follow_controller:=true \
  follow_enable_motion:=true \
  gate_enable_motion:=false
```

For a lifted-robot or floor test only after the area is clear, switch the final
gate on:

```bash
ros2 launch cs603_voice_intent voice_integration_demo.launch.py \
  input_mode:=stdin \
  launch_follow_controller:=true \
  follow_enable_motion:=true \
  gate_enable_motion:=true
```

Topic checklist:

```bash
ros2 topic echo /voice_intent
ros2 topic echo /follow_target_active
ros2 topic echo /people/depth
ros2 topic echo /cmd_vel_follow_raw
ros2 topic echo /cmd_vel
ros2 topic echo /robot_speech
```

Manual dry-run without the camera package:

Terminal 1:

```bash
ros2 run cs603_voice_intent behavior_fsm
```

Terminal 2:

```bash
ros2 run cs603_voice_intent cmd_vel_gate --ros-args -p enable_motion:=false
```

Terminal 3:

```bash
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_FOLLOW}"
ros2 topic pub --once /cmd_vel_follow_raw geometry_msgs/msg/Twist "{linear: {x: 0.05}}"
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_STOP}"
```

Expected result with `enable_motion:=false`: `/cmd_vel` remains zero. With
`enable_motion:=true` and `/follow_target_active` true, fresh raw Twist messages
pass through. `CMD_STOP` must immediately zero `/cmd_vel`.

## Whisper Mode

Two ways to run Whisper. Pick one.

### A. ROS-side `mic_once` (in-container)

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=mic_once -p whisper_model:=small
```

Docker Desktop may not expose the Mac microphone to the Linux container. If `mic_once` fails with no audio device, use `stdin` mode for robot-day testing or use the Mac-host web bridge below.

### Native (Linux) ROS publish

Himanshu (or anyone on Ubuntu 22.04 with ROS Humble built natively) skips Docker:

```bash
bash tools/voice_web_demo/run_demo.sh
```

The launcher detects Linux and starts the bridge with `--ros-mode native`. It
sources `$ROS_WS/install/setup.bash` or falls back to
`$HOME/robomaster_ws/install/setup.bash` (or `$HOME/ros2_ws/install/setup.bash`).
Override explicitly with `CS603_ROS_SETUP=/full/path/to/install/setup.bash`.

Manual equivalent if you don't want the launcher:

```bash
CS603_ROS_SETUP=$HOME/robomaster_ws/install/setup.bash \
  python3 tools/voice_web_demo/server.py \
    --host 127.0.0.1 --port 8765 --ros-mode native
```

The browser pill reads `ROBOT LINK OK (NATIVE)` once `ros2 node list` runs
without error in the bridge's environment. If it reads `BRIDGE ALIVE, ROS DOWN
(NATIVE)`, the workspace was not sourced — fix `CS603_ROS_SETUP` and refresh.

### B. Mac-host web bridge (recommended for live demo)

`tools/voice_web_demo/server.py` exposes `/api/transcribe`. The browser records audio with MediaRecorder, posts the blob to the Mac, the Mac runs `/opt/homebrew/bin/whisper` locally (no API key required), classifies the intent, publishes on `/voice_intent` through the Docker container, and speaks a short browser ACK.

```bash
brew install openai-whisper ffmpeg
python3 tools/voice_web_demo/server.py --host 127.0.0.1 --port 8765 --container cs603_robomaster_sdkports
open http://127.0.0.1:8765
```

Use `--host 0.0.0.0 --allow-lan-publish` only when a teammate device must reach
the bridge and final robot motion is disabled, or after the test area is clear
and the emergency stop is ready. This flag is not strong authentication: any
LAN client that can load the page receives the demo token. Browser microphone
capture over LAN also requires HTTPS; for normal voice testing, use Comet on
the Mac at `http://127.0.0.1:8765`.

In the UI, click `Tap to listen` for continuous voice mode. For a cleaner
single-utterance test, open `Settings`, click `Whisper: tap to record`, speak,
then click again to stop. Transcript appears, intent publishes automatically,
and the browser speaks a short ACK.

Configure model + binary via env vars if needed:

```bash
CS603_WHISPER_MODEL=base.en CS603_WHISPER_BIN=/opt/homebrew/bin/whisper python3 tools/voice_web_demo/server.py ...
```

Latency: cold first call is ~10–20 s on Apple Silicon (model load); subsequent calls drop to ~2–4 s for short clips with `tiny.en`. Use `base.en` or `small.en` for accuracy at the cost of latency.

### Handoff status (2026-05-02)

- ROS package built + topic verified (`/voice_intent` publishes `std_msgs/String` with the four contract codes).
- Mac-host web bridge `/api/transcribe` smoke-tested end-to-end against `tiny.en`.
- Object-trigger remains an explicitly labeled stub at `cs603_voice_intent/object_trigger_stub.py`. Real perception integration is the next handoff for whoever picks up the camera lane.
