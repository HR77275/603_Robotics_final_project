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

`mic_once` mode attempts one microphone recording and Whisper transcription:

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=mic_once -p whisper_model:=small
```

Docker Desktop may not expose the Mac microphone to the Linux container. If `mic_once` fails with no audio device, use `stdin` mode for robot-day testing and record the voice classification path separately on a host with microphone access.
