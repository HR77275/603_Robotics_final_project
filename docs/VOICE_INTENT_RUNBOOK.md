# Voice Intent Runbook

This package is Soumik's CS603 final-project lane: spoken command text becomes ROS 2 intent messages on `/voice_intent`.

## Build In WSL Ubuntu 22.04

```bash
export ROBOMASTER_WS="${ROBOMASTER_WS:-$HOME/robomaster_ws}"
source /opt/ros/humble/setup.bash
cd "$ROBOMASTER_WS"
colcon build --packages-select cs603_voice_intent
source install/setup.bash
```

Every terminal that uses this package needs both setup files:

```bash
source /opt/ros/humble/setup.bash
export ROBOMASTER_WS="${ROBOMASTER_WS:-$HOME/robomaster_ws}"
source "$ROBOMASTER_WS/install/setup.bash"
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

`stdin` mode is meant for `ros2 run`. Do not use the launch terminal as a
text prompt; `ros2 launch` does not forward your typed lines to the child node
like an interactive shell command.

## Launch-Based Text Test

For `ros2 launch`, use `param` mode:

```bash
ros2 launch cs603_voice_intent voice_demo.launch.py input_mode:=param stub_text:="follow me"
```

To send more phrases while the launch is still running:

```bash
ros2 param set /voice_intent_node stub_text "stop"
ros2 param set /voice_intent_node stub_text "come here"
```

## Robot Motion Demo

Only run this after the robot is connected, the area is clear, and emergency stop is ready.

```bash
ros2 launch cs603_voice_intent voice_demo.launch.py input_mode:=param stub_text:="follow me" enable_motion:=true
```

The bridge maps:

- `CMD_STOP` to zero `/cmd_vel`.
- `CMD_FOLLOW` to a short, slow forward command.
- `CMD_APPROACH` to a short, slow forward command.

Emergency stop:

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

## Voice + Camera Integration Demo

The integration launch wires voice intent to the behavior FSM, then lets the FSM
gate the PID follow controller:

```text
/voice_intent -> /behavior_state + /follow_target_active -> follow_node -> /cmd_vel
```

Bench test with fake perception and no physical motion:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=false \
  use_fake_perception:=true \
  enable_motion:=false \
  input_mode:=param \
  stub_text:="follow me"
```

Watch the FSM and command topics:

```bash
ros2 topic echo /behavior_state
ros2 topic echo /follow_target_active
ros2 topic echo /cmd_vel
```

Send more voice intents while launch is running:

```bash
ros2 param set /voice_intent_node stub_text "come here"
ros2 param set /voice_intent_node stub_text "stop"
```

Real camera/perception path, still motion-disabled:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  enable_motion:=false
```

Only after verifying perception, FSM state, and emergency stop, enable physical
motion:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  enable_motion:=true
```

## Whisper Setup On WSL

Install the system audio/build tools and the Python packages in Ubuntu 22.04:

```bash
sudo apt update
sudo apt install -y ffmpeg portaudio19-dev python3-pip
python3 -m pip install --user --upgrade pip setuptools wheel
python3 -m pip install --user openai-whisper sounddevice numpy
```

Make sure the user-local Python scripts directory is on `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
which whisper
```

Quick Whisper check:

```bash
whisper --help
python3 -c "import whisper, sounddevice; print('whisper + sounddevice OK')"
```

If Whisper fails with `AttributeError: module 'coverage' has no attribute
'types'`, your WSL Python has an older `coverage` package visible to Numba. The
web bridge disables Numba coverage for Whisper subprocesses automatically. For
your shell, either upgrade the user package or remove the unused user package:

```bash
python3 -m pip install --user --upgrade coverage
# or, if pip installed it in your user site:
python3 -m pip uninstall coverage
```

If `sounddevice` cannot see a microphone from WSL, use the web bridge below.
The browser records audio through Windows, then posts it to the WSL server.

## Whisper Mode

Two ways to run Whisper. Pick one.

### A. ROS-side `mic_once`

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=mic_once -p whisper_model:=small
```

This records one short clip from the WSL-visible microphone, transcribes it,
classifies it, and publishes one `/voice_intent` message. If WSL cannot access
the microphone, use `stdin` mode for text tests or the browser web bridge below.

### B. WSL Web Bridge (recommended for live demo)

`tools/voice_web_demo/server.py` exposes `/api/transcribe`. A browser records
audio with MediaRecorder, posts the blob to the WSL server, WSL runs local STT
with no API key, classifies the intent, and publishes directly to local ROS 2
with `ros2 topic pub`. The UI logs STT/ROS latency and speaks a short command
acknowledgement through browser speech synthesis.

```bash
export ROBOMASTER_WS="${ROBOMASTER_WS:-$HOME/robomaster_ws}"
cd "$ROBOMASTER_WS/src/603_Robotics_final_project"
source /opt/ros/humble/setup.bash
source "$ROBOMASTER_WS/install/setup.bash"
CS603_STT_BACKEND=auto \
python3 tools/voice_web_demo/server.py --host 0.0.0.0 --port 8765 --allow-lan-publish --token cs603-demo-local
```

Open this URL from the Windows browser:

```text
http://127.0.0.1:8765
```

In the UI, click `tap to listen`, speak, and pause. The transcript appears and
the intent publishes automatically.

Configure model, binary, or workspace setup via env vars if needed:

```bash
CS603_STT_BACKEND=auto \
CS603_WHISPER_MODEL=base.en \
CS603_WHISPER_BIN=whisper \
CS603_ROS_SETUP="$ROBOMASTER_WS/install/setup.bash" \
python3 tools/voice_web_demo/server.py --host 0.0.0.0 --port 8765
```

Latency: check the web UI log after each utterance. It prints backend, STT
milliseconds, ROS publish milliseconds, and total request milliseconds. The
current checked-in free/local path uses the existing `openai-whisper` CLI. If the
team decides to pay for OpenAI Realtime for the final demo, keep that as a
separate branch/PR instead of mixing it into this local bridge.

### Handoff status

- ROS package built + topic verified (`/voice_intent` publishes `std_msgs/String` with the four contract codes).
- WSL web bridge `/api/transcribe` publishes with local `ros2 topic pub`.
- Object-trigger remains an explicitly labeled stub at `cs603_voice_intent/object_trigger_stub.py`. Real perception integration is the next handoff for whoever picks up the camera lane.
