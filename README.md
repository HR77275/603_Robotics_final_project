# RoboMaster EP ROS 2 Humble Setup

This project uses a DJI RoboMaster EP with ROS 2 Humble on Ubuntu 22.04. It documents how to install the ROS driver, connect to the robot over Wi-Fi, view the camera stream, teleoperate the chassis, and control the arm/gripper.

## Voice Intent Lane (Soumik)

This branch (`feature/whisper-web-bridge`) adds the voice control path. You speak
into a microphone, the robot understands a small set of commands, and motion is
routed safely so it does not fight the camera-follow controller.

### What you can say

| Phrase                 | Intent code      | Robot behavior                        |
| ---------------------- | ---------------- | ------------------------------------- |
| "follow me", "come"    | `CMD_FOLLOW`     | enter follow mode (gate opens)        |
| "stop", "freeze"       | `CMD_STOP`       | zero `/cmd_vel` immediately           |
| "come here"            | `CMD_APPROACH`   | short forward nudge                   |
| (anything else)        | `CMD_UNKNOWN`    | ignored, no motion                    |

### Pipeline at a glance

```
[ Browser mic ]                              [ Mac host ]
      |                                           |
      | MediaRecorder blob (POST /api/transcribe) |
      | -----------------------------------------> |
      |                                           |
      |                                  /opt/homebrew/bin/whisper
      |                                  (local, no API key)
      |                                           |
      |                                  intent_classifier.py
      |                                  -> CMD_FOLLOW / CMD_STOP / ...
      |                                           |
      |                                  docker exec ros2 topic pub
      |                                           v
      |                                   ROS 2 Humble container
      |                                           |
      |                                   /voice_intent (std_msgs/String)
      |                                           |
      |                                   behavior_fsm
      |                                  (state: idle | follow | stopped)
      |                                           |
      |                          /follow_target_active (Bool)
      |                                           |
      |                                   cmd_vel_gate
      |  raw follow Twist  ->  /cmd_vel_follow_raw  ->  gate  ->  /cmd_vel
      |                                           |
      | (browser ACK: "Following you" / "Stopping") <-- /robot_speech
      | <----------------------------------------- |
```

Topics in one line:

```
voice -> /voice_intent -> behavior_fsm -> /follow_target_active
follow controller -> /cmd_vel_follow_raw -> cmd_vel_gate -> /cmd_vel
```

### Why a gate?

The camera-follow node also publishes velocity. If both it and the voice node
wrote to `/cmd_vel`, they would fight. The gate is the single writer of
`/cmd_vel`. It only forwards the follow controller's raw Twist when:

1. `behavior_fsm` says follow is active (after a `CMD_FOLLOW`), AND
2. a fresh raw Twist has arrived recently (stale messages are dropped), AND
3. `enable_motion` is true (default off; opt in only on robot day).

Any `CMD_STOP` immediately zeros `/cmd_vel` regardless of state.

### What's in this lane

```
src/cs603_voice_intent/
  cs603_voice_intent/
    voice_intent_node.py     # stdin or whisper -> /voice_intent
    intent_classifier.py     # text -> CMD_* code
    behavior_fsm.py          # /voice_intent -> /follow_target_active
    cmd_vel_gate.py          # gates final /cmd_vel
    robot_response_node.py   # /voice_intent -> /robot_speech text
    speech_responses.py      # phrase table
  launch/
    voice_demo.launch.py             # legacy direct voice -> /cmd_vel
    voice_integration_demo.launch.py # gated integration with follow lane
  test/                              # 50+ unit tests, all passing

tools/voice_web_demo/
  server.py        # Mac-host /api/transcribe + /api/intent endpoints
  index.html       # tap-to-listen / Live VAD UI, ACK speech
  app.js, style.css
  test_*.py        # bridge + synthetic audio coverage
```

### Run the tests (no ROS needed)

```bash
PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=src/cs603_voice_intent:tools/voice_web_demo \
  python3 -m pytest -p no:cacheprovider -q
```

Expected: `68 passed`.

### Run the host web bridge (live demo)

```bash
brew install openai-whisper ffmpeg
PYTHONPATH=src/cs603_voice_intent:tools/voice_web_demo \
  python3 tools/voice_web_demo/server.py \
    --host 127.0.0.1 --port 8765 \
    --container cs603_robomaster_sdkports
open http://127.0.0.1:8765
```

Tap `Tap to listen`, speak a phrase, see the transcript and intent. The bridge
publishes to `/voice_intent` inside the running ROS Humble container.

### Build inside the ROS Humble container

```bash
docker exec -it cs603_robomaster_sdkports bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/ros2_ws
colcon build --packages-select cs603_voice_intent
source install/setup.bash
```

Full robot-day checklist (topics, dry-run, motion enable):
[`docs/VOICE_INTENT_RUNBOOK.md`](docs/VOICE_INTENT_RUNBOOK.md).

### What is verified vs not verified

Verified:

- Local pytest: 68 passed.
- ROS Humble Docker build: `colcon build` clean.
- ROS Humble Docker test: `colcon test` clean.
- `ros2 launch ... --show-args` for the integration launch file.
- `/voice_intent` smoke: stdin phrase -> correct `CMD_*` published.
- `/cmd_vel` gate smoke: raw Twist gated by FSM, `CMD_STOP` zeros instantly.
- Web bridge smoke: `/api/transcribe` round-trip with `tiny.en`.
- Local merge with `feature/camera_detection`: only `.gitignore` conflicts
  (trivial union resolution); my `face_db/` ignore rules pre-folded so the
  conflict surface is one set of overlapping lines.

Not yet verified (needs robot day):

- Live human voice reliability over a real microphone in the demo room.
- Real robot floor motion through the gate.
- Camera-follow integration end-to-end (depends on the
  `feature/camera_detection` branch being merged and `robomaster_ros`
  submodule initialized).

### Integrating with `feature/camera_detection`

Branches forked from the same `main` commit. Coupling between my package and
the perception/follow packages is **topic-level only**:

- My `cmd_vel_gate` subscribes to `/cmd_vel_follow_raw` (Twist).
- My integration launch spawns the teammate's `follow_node` with
  `cmd_vel_topic` overridden to `/cmd_vel_follow_raw` so the gate is the
  single writer of `/cmd_vel`.
- My package.xml has zero build-time dependency on the teammate's packages.
  Either package builds standalone in its own workspace.

Merge sequence for whoever integrates:

```bash
git checkout main
git pull
git checkout -b integration/voice-and-camera
git merge feature/camera_detection      # adds perception + follow + msgs
git merge feature/whisper-web-bridge    # adds voice; .gitignore conflict only
# resolve .gitignore as union of both rule sets
git submodule update --init --recursive  # picks up robomaster_ros
```

Then build everything in the ROS Humble workspace:

```bash
colcon build --packages-select \
    robomaster_perception_msgs \
    robomaster_perception \
    robomaster_follow_controller \
    cs603_voice_intent
source install/setup.bash
```

### What's still in progress (not in this PR)

This PR is the voice lane core: voice -> intent -> FSM -> gate -> cmd_vel,
plus the Mac-host Whisper web bridge. Planned follow-up work that is **not**
in this PR — it lands in a separate branch off `main` after this merges:

- **Mission-control web dashboard.** Extend `tools/voice_web_demo/` to also
  consume teammate's perception output and render the robot's view in the
  browser:
  - Live camera feed with bbox overlay (`/perception/tracking_debug_image`).
  - Tracked people list with names + distance
    (`/people/tracks` + `/people/identities` + `/people/depth`).
  - Live FSM state badge and last-heard transcript.
  - Live `/cmd_vel` linear/angular bars.
  - Big red E-STOP button (HTTP fallback alongside voice).
  - Click-to-select follow target (sets `target_track_id` on `follow_node`).
- **Whisper accuracy tuning.** Current default model is `base.en`. Bumping
  to `small.en` or `medium.en` is an env-var change
  (`CS603_WHISPER_MODEL=small.en`); no code edit. Decision pending after
  live-mic test on demo hardware.

Reviewers: please flag anything you'd like me to fix in this PR vs. defer to
the dashboard branch. Issues unrelated to the voice-lane core are fair game
to defer.

## Why ROS 2 Humble

ROS 2 Humble is used because it is the ROS 2 distribution built for Ubuntu 22.04. Foxy was built around Ubuntu 20.04 and is now end-of-life, so Humble is a better choice for a current Ubuntu 22.04 development machine.

References:

- ROS 2 Foxy EOL: https://docs.ros.org/en/foxy/Releases/End-of-Life.html
- ROS 2 Humble Ubuntu 22.04 support: https://docs.ros.org/en/humble/Releases/Release-Humble-Hawksbill.html

## Environment

- Ubuntu 22.04
- ROS 2 Humble
- DJI RoboMaster EP
- Workspace: `~/robomaster_ws`

## Install ROS 2 Humble

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y locales software-properties-common curl gnupg lsb-release

sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

sudo add-apt-repository universe -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-desktop ros-dev-tools

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
echo $ROS_DISTRO
ros2 doctor --report
```

## Install Dependencies

```bash
sudo apt update
sudo apt install -y \
  python3-colcon-common-extensions \
  python3-pip \
  build-essential \
  cmake \
  ninja-build \
  python3-dev \
  libopus-dev \
  nasm \
  netcat-openbsd \
  ros-humble-xacro \
  ros-humble-cv-bridge \
  ros-humble-robot-state-publisher \
  ros-humble-joint-state-publisher \
  ros-humble-joy \
  ros-humble-joy-teleop \
  ros-humble-teleop-twist-keyboard \
  ros-humble-rqt-image-view

python3 -m pip install --user --upgrade pip setuptools wheel packaging scikit-build-core cmake ninja
python3 -m pip install --user --force-reinstall "numpy==1.24.4"
python3 -m pip install --user -U pyyaml numpy-quaternion
```

## Install vcpkg and RoboMaster SDK

```bash
sudo apt install -y curl zip unzip tar

cd ~
git clone https://github.com/microsoft/vcpkg.git
cd ~/vcpkg
./bootstrap-vcpkg.sh

echo 'export VCPKG_ROOT="$HOME/vcpkg"' >> ~/.bashrc
echo 'export PATH="$VCPKG_ROOT:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Install the SDK and media codec:

```bash
python3 -m pip install --user git+https://github.com/jeguzzi/RoboMaster-SDK.git

python3 -m pip install --user --no-build-isolation \
  'rm-libmedia-codec @ git+https://github.com/jeguzzi/RoboMaster-SDK.git#subdirectory=lib/libmedia_codec'
```

Verify:

```bash
python3 -c "import robomaster; print('robomaster SDK OK')"
python3 -c "import libmedia_codec; print('libmedia_codec OK')"
python3 -c "import cv_bridge; print('cv_bridge OK')"
```

## Build robomaster_ros

```bash
mkdir -p ~/robomaster_ws/src
cd ~/robomaster_ws/src
git clone https://github.com/jeguzzi/robomaster_ros.git

cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash

echo "source ~/robomaster_ws/install/setup.bash" >> ~/.bashrc
```

## Connect to the Robot

Connect the RoboMaster EP and laptop to the same Wi-Fi network. Find the robot IP from the router admin page or the DJI RoboMaster app.

Check connectivity:

```bash
ping <ROBOT_IP>
printf "command;version;" | nc -w 5 <ROBOT_IP> 40923
```

## Direct IP Workaround

If RoboMaster discovery fails but ping and the text SDK work, set the robot and laptop IPs explicitly:

```bash
export ROBOMASTER_LOCAL_IP=<LAPTOP_IP>
export ROBOMASTER_ROBOT_IP=<ROBOT_IP>
```

Patch `~/robomaster_ws/src/robomaster_ros/robomaster_ros/robomaster_ros/client.py` so discovery is skipped when `ROBOMASTER_ROBOT_IP` is set.

Add near the imports:

```python
import os
import robomaster.config
```

Replace `wait_for_robot` with:

```python
def wait_for_robot(serial_number: Optional[str]) -> None:
    robot_ip = os.environ.get("ROBOMASTER_ROBOT_IP")
    local_ip = os.environ.get("ROBOMASTER_LOCAL_IP")

    if robot_ip:
        robomaster.config.ROBOT_IP_STR = robot_ip
    if local_ip:
        robomaster.config.LOCAL_IP_STR = local_ip

    if robot_ip:
        return

    found = False
    while not found:
        try:
            found = robomaster.conn.scan_robot_ip(user_sn=serial_number)
        except OSError:
            pass
        if not found:
            time.sleep(random.uniform(1.0, 2.0))
```

Rebuild:

```bash
cd ~/robomaster_ws
colcon build --packages-select robomaster_ros
source install/setup.bash
```

## Launch Robot Driver

```bash
export ROBOMASTER_LOCAL_IP=<LAPTOP_IP>
export ROBOMASTER_ROBOT_IP=<ROBOT_IP>

ros2 launch robomaster_ros main.launch \
  model:=ep \
  conn_type:=sta \
  serial_number:=<ROBOT_SERIAL_NUMBER> \
  chassis_timeout:=0.5 \
  arm:=true \
  gripper:=true
```

Successful logs should include:

```text
Found a robot
Connected
Enabled modules: Battery, Camera, Chassis, LED, Speaker, Gimbal, Blaster
```

## Camera Feed

```bash
ros2 run rqt_image_view rqt_image_view
```

Select:

```text
/camera/image_raw
```

## Keyboard Teleop

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/cmd_vel
```

Useful keys:

```text
i = forward
, = backward
j = rotate left
l = rotate right
k = stop
```

Emergency stop command:

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

## Arm and Gripper

The ROS arm/gripper actions may abort on some setups even when the hardware works. The RoboMaster text SDK can be used directly.

Open gripper:

```bash
printf "command;robotic_gripper open 4;" | nc -w 3 <ROBOT_IP> 40923
```

Close gripper:

```bash
printf "command;robotic_gripper close 4;" | nc -w 3 <ROBOT_IP> 40923
```

Move arm forward 1 cm:

```bash
printf "command;robotic_arm move x 1 y 0;" | nc -w 3 <ROBOT_IP> 40923
```

Move arm up 1 cm:

```bash
printf "command;robotic_arm move x 0 y 1;" | nc -w 3 <ROBOT_IP> 40923
```

Move arm down 1 cm:

```bash
printf "command;robotic_arm move x 0 y -1;" | nc -w 3 <ROBOT_IP> 40923
```

Recenter arm:

```bash
printf "command;robotic_arm recenter;" | nc -w 5 <ROBOT_IP> 40923
```

Stop arm:

```bash
printf "command;robotic_arm stop;" | nc -w 3 <ROBOT_IP> 40923
```

## Common Checks

List ROS topics:

```bash
ros2 topic list
```

Check camera rate:

```bash
ros2 topic hz /camera/image_raw
```

Check arm position:

```bash
ros2 topic echo /arm_position --once
```
