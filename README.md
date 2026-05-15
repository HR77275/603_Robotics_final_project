# CS603 Final Project

This repository contains the CS603 project code:

- `cs603_voice_intent`: voice/text intent classification, FSM, web voice UI, and arm/gripper sequencing.
- `robomaster_perception`: person tracking, depth estimation, face identity, and tracking overlay.
- `robomaster_follow_controller`: FSM-gated person-following controller and follow-distance evaluator.

This README assumes ROS 2 Humble, `robomaster_ros`, and the RoboMaster Python
stack are already installed in `~/robomaster_ws`. The project-specific packages
and model assets below are still required for a reproducible run.

## Project-Specific Setup

Run these once after the base ROS/RoboMaster workspace is available:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

sudo apt install -y ffmpeg portaudio19-dev python3-opencv

python3 -m pip install --user --upgrade pip setuptools wheel
python3 -m pip install --user torch torchvision
python3 -m pip install --user \
  numpy openai-whisper sounddevice "coverage>=7.6"
python3 -m pip install --user \
  -r src/603_Robotics_final_project/src/robomaster_perception/requirements-ml.txt
```

Install a CUDA-enabled PyTorch build instead of the generic `torch torchvision`
command when the depth model should run on the GPU. If running CPU-only, keep the
same packages but change the perception config to use `device: cpu` and
`embedder_gpu: false`.

The first perception or voice run downloads several model assets into the user
cache. Preload them while internet access is available:

```bash
python3 -c "import whisper; whisper.load_model('base.en'); whisper.load_model('small')"
python3 -c "from transformers import AutoImageProcessor, AutoModelForDepthEstimation; m='depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf'; AutoImageProcessor.from_pretrained(m); AutoModelForDepthEstimation.from_pretrained(m)"
python3 -c "from insightface.app import FaceAnalysis; app=FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1, det_size=(640, 640))"
python3 -c "from deep_sort_realtime.deepsort_tracker import DeepSort; DeepSort(embedder='mobilenet', embedder_gpu=False)"
```

For `CMD_FOLLOW_AUTHORIZED`, build the face identity database after adding images:

```bash
cd ~/robomaster_ws/src/603_Robotics_final_project
mkdir -p face_db/images/Person_A face_db/embeddings
# Add clear face images under face_db/images/Person_A/

cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 run robomaster_perception enroll_faces \
  --image-dir src/603_Robotics_final_project/face_db/images \
  --output src/603_Robotics_final_project/face_db/embeddings/face_db.npz
```

## Environment

Use this setup in every terminal:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

export ROS_DOMAIN_ID=23
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

For the physical RoboMaster EP used in the demo:

```bash
export ROBOMASTER_LOCAL_IP=<LOCAL_IP>
export ROBOMASTER_ROBOT_IP=<ROBOT_IP>
export ROBOMASTER_SERIAL=<SERIAL_NUM>
```

## Compile

Build the full project:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
```

Build only the project packages after local edits:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select \
  robomaster_perception_msgs \
  robomaster_perception \
  robomaster_follow_controller \
  cs603_voice_intent
source install/setup.bash
```

If only voice/FSM/web/arm code changed:

```bash
colcon build --packages-select cs603_voice_intent
source install/setup.bash
```

If only following/evaluation code changed:

```bash
colcon build --packages-select robomaster_follow_controller
source install/setup.bash
```

## Standard Run

### Terminal 1: Robot Driver

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

export ROS_DOMAIN_ID=23
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROBOMASTER_LOCAL_IP=<LOCAL_IP>
export ROBOMASTER_ROBOT_IP=<ROBOT_IP>

ros2 launch robomaster_ros main.launch \
  model:=ep \
  conn_type:=sta \
  serial_number:=<SERIAL_NUM> \
  chassis_timeout:=0.5 \
  camera:=true \
  video_raw:=1 \
  vision_targets:='["person"]' \
  tof_0:=true \
  tof_rate:=10 \
  arm:=true \
  gripper:=true
```

### Terminal 2: Integration Stack

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

export ROS_DOMAIN_ID=23
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  use_identity:=false \
  enable_motion:=true \
  enable_arm_gripper:=true \
  input_mode:=param \
  stub_text:="" \
  arm_control_mode:=topic \
  follow_distance_m:=1.5 \
  approach_distance_m:=0.8 \
  gripper_power:=0.7
```

### Terminal 3: Web Voice UI

```bash
cd ~/robomaster_ws/src/603_Robotics_final_project
source /opt/ros/humble/setup.bash
source ~/robomaster_ws/install/setup.bash

export ROS_DOMAIN_ID=23
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

python3 tools/voice_web_demo/server.py \
  --host 0.0.0.0 \
  --port 8765 \
  --allow-lan-publish \
  --token cs603-demo-local
```

Open:

```text
http://127.0.0.1:8765
```

## Command Flow

The voice/web path publishes `/voice_intent`. The FSM converts that into
`/behavior_state` and `/follow_target_active`. The follow controller moves only
when the FSM allows it.

Useful command phrases:

| Phrase | Intent | Behavior |
| --- | --- | --- |
| `follow me` | `CMD_FOLLOW` | Follow closest tracked person at follow distance. |
| `follow authorized` | `CMD_FOLLOW_AUTHORIZED` | Follow recognized person only. |
| `come here` | `CMD_APPROACH` | Approach to pickup/drop distance. |
| `stop` | `CMD_STOP` | Stop chassis motion. |
| `pick up` | `CMD_PICK` | Run pickup sequence when stopped or approaching. |
| `drop it` | `CMD_DROP` | Run drop sequence when stopped or approaching. |

Send commands without speech:

```bash
ros2 param set /voice_intent_node stub_text "follow me"
ros2 param set /voice_intent_node stub_text "come here"
ros2 param set /voice_intent_node stub_text "stop"
ros2 param set /voice_intent_node stub_text "pick up"
ros2 param set /voice_intent_node stub_text "drop it"
```

Publish direct intent messages:

```bash
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_FOLLOW}"
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_APPROACH}"
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_STOP}"
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_PICK}"
ros2 topic pub --once /voice_intent std_msgs/msg/String "{data: CMD_DROP}"
```

## Pickup And Drop

Pickup/drop is intentionally gated by the FSM. Use:

```bash
ros2 param set /voice_intent_node stub_text "come here"
ros2 param set /voice_intent_node stub_text "stop"
ros2 param set /voice_intent_node stub_text "pick up"
```

Drop flow:

```bash
ros2 param set /voice_intent_node stub_text "stop"
ros2 param set /voice_intent_node stub_text "drop it"
```

The arm sequence uses fixed poses from `integration_demo.launch.py`. Place the
object where the configured pickup pose can reach it.

## Monitoring

```bash
ros2 topic echo /voice_intent
ros2 topic echo /behavior_state
ros2 topic echo /follow_target_active
ros2 topic echo /cmd_vel
ros2 topic echo /arm_gripper_status
ros2 topic echo /people/depth
```

View the tracking overlay:

```bash
ros2 run rqt_image_view rqt_image_view
```

Select:

```text
/perception/tracking_debug_image
```

Check topic rates:

```bash
ros2 topic hz /camera/image_color
ros2 topic hz /people/tracks
ros2 topic hz /people/depth
ros2 topic hz /perception/tracking_debug_image
```

Emergency stop:

```bash
ros2 param set /voice_intent_node stub_text "stop"
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

## Follow Distance Evaluation

Run the evaluator while the robot is following a person:

```bash
ros2 param set /voice_intent_node stub_text "follow me"

ros2 run robomaster_follow_controller follow_distance_eval --ros-args \
  -p target_depth_m:=1.5 \
  -p min_depth_m:=1.4 \
  -p max_depth_m:=2.2 \
  -p trial_count:=5 \
  -p trial_duration_sec:=10.0 \
  -p settle_time_sec:=2.0 \
  -p output_csv:=/tmp/follow_distance_eval.csv \
  -p output_samples_csv:=/tmp/follow_distance_eval_samples.csv
```

The summary CSV stores per-trial scores. The samples CSV stores raw depth samples
so later thresholds can be recomputed without another robot run.

More detail: [`docs/FOLLOW_DISTANCE_EVAL.md`](docs/FOLLOW_DISTANCE_EVAL.md).

## Bench Tests Without Robot Motion

Run the integration stack with fake perception and motion disabled:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=false \
  use_fake_perception:=true \
  enable_motion:=false \
  enable_arm_gripper:=false \
  input_mode:=param \
  stub_text:="follow me"
```

Watch the output:

```bash
ros2 topic echo /voice_intent
ros2 topic echo /behavior_state
ros2 topic echo /cmd_vel
```

Run the real perception stack with motion disabled:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  use_identity:=false \
  enable_motion:=false
```

## Troubleshooting Checks

Confirm all terminals are on the same ROS graph:

```bash
echo $ROS_DOMAIN_ID
echo $ROS_LOCALHOST_ONLY
echo $RMW_IMPLEMENTATION
ros2 node list
ros2 topic list
```

If `rqt_image_view` opens but no image appears, check:

```bash
ros2 topic info /perception/tracking_debug_image -v
ros2 topic hz /perception/tracking_debug_image
```

If voice commands publish but the robot does not move, check:

```bash
ros2 topic echo /behavior_state
ros2 topic echo /follow_target_active
ros2 topic echo /cmd_vel
```

If pickup/drop is ignored, check:

```bash
ros2 topic echo /behavior_state
ros2 topic echo /arm_gripper_status
```

`CMD_PICK` and `CMD_DROP` run only when the FSM is `APPROACHING` or `STOPPED`.
