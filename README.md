# RoboMaster EP ROS 2 Humble Setup

This project uses a DJI RoboMaster EP with ROS 2 Humble on Ubuntu 22.04. It documents how to install the ROS driver, connect to the robot over Wi-Fi, view the camera stream, teleoperate the chassis, and control the arm/gripper.

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

## CS603 Voice Intent Quick Start

This section covers the current `cs603_voice_intent` package in a direct Ubuntu
22.04 or WSL Ubuntu 22.04 setup. It assumes the repository is checked out at:

```bash
export ROBOMASTER_WS="${ROBOMASTER_WS:-$HOME/robomaster_ws}"
export CS603_PROJECT="$ROBOMASTER_WS/src/603_Robotics_final_project"
```

### Requirements

- Ubuntu 22.04 or WSL Ubuntu 22.04
- ROS 2 Humble
- Python 3.10
- `colcon`
- `geometry_msgs`, `std_msgs`, `rclpy`, `launch`, and `launch_ros`
- Optional for microphone/Whisper testing: `ffmpeg`, `portaudio19-dev`,
  `openai-whisper`, `sounddevice`, and `numpy`
- Optional for physical robot motion: RoboMaster EP, `robomaster_ros`, robot
  network access, and a clear test area with emergency stop ready

### Install

Install ROS/package tooling:

```bash
sudo apt update
sudo apt install -y \
  python3-colcon-common-extensions \
  python3-pip \
  ffmpeg \
  portaudio19-dev \
  ros-humble-geometry-msgs \
  ros-humble-launch \
  ros-humble-launch-ros \
  ros-humble-rclpy \
  ros-humble-std-msgs
```

Install optional Whisper dependencies:

```bash
python3 -m pip install --user --upgrade pip setuptools wheel
python3 -m pip install --user openai-whisper sounddevice numpy
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Build the voice package:

```bash
source /opt/ros/humble/setup.bash
cd "$ROBOMASTER_WS"
colcon build --packages-select cs603_voice_intent
source "$ROBOMASTER_WS/install/setup.bash"
```

Every new terminal should source ROS and the workspace:

```bash
source /opt/ros/humble/setup.bash
source "${ROBOMASTER_WS:-$HOME/robomaster_ws}/install/setup.bash"
```

### Run Text Tests

Terminal 1:

```bash
ros2 topic echo /voice_intent
```

Terminal 2:

```bash
ros2 run cs603_voice_intent voice_intent_node --ros-args -p input_mode:=stdin
```

Type phrases such as:

```text
follow me
stop
come here
pick up the object
drop it
```

Expected intents are `CMD_FOLLOW`, `CMD_STOP`, `CMD_APPROACH`, `CMD_PICK`, and
`CMD_DROP`. The arm/gripper node acts on pick/drop only while
`/behavior_state` is `APPROACHING`.

For `ros2 launch`, use parameter mode instead of typing into the launch
terminal:

```bash
ros2 launch cs603_voice_intent voice_demo.launch.py input_mode:=param stub_text:="follow me"
ros2 param set /voice_intent_node stub_text "stop"
```

### Run Whisper/Web Voice Demo

Start the local WSL/Ubuntu web bridge:

```bash
cd "$CS603_PROJECT"
source /opt/ros/humble/setup.bash
source "$ROBOMASTER_WS/install/setup.bash"
python3 tools/voice_web_demo/server.py --host 0.0.0.0 --port 8765 --allow-lan-publish --token cs603-demo-local
```

Open this in the Windows or Ubuntu browser:

```text
http://127.0.0.1:8765
```

The browser records audio, the WSL server runs local Whisper, and the server
publishes classified intents on `/voice_intent`.

Useful knobs:

```bash
CS603_WHISPER_MODEL=tiny.en python3 tools/voice_web_demo/server.py
CS603_WHISPER_MODEL=base.en python3 tools/voice_web_demo/server.py
CS603_ROS_SETUP="$ROBOMASTER_WS/install/setup.bash" python3 tools/voice_web_demo/server.py
```

### Run Physical Robot Demo

Only enable motion after the RoboMaster driver is connected, the robot has room
to move, and the emergency stop command is ready. For obstacle avoidance, start
`robomaster_ros` with the front ToF sensor enabled so `/range_0` is publishing.

Bench-test the full voice/FSM/follow-controller path with fake perception and
motion disabled:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=false \
  use_fake_perception:=true \
  enable_motion:=false \
  input_mode:=param \
  stub_text:="follow me"
```

Run the real perception/FSM/follow stack with motion disabled:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  enable_motion:=false
```

Enable physical follow motion only after `/behavior_state`,
`/follow_target_active`, `/range_0`, and perception topics look correct. For
pick/drop behavior, also launch `robomaster_ros` with `arm:=true` and
`gripper:=true` and watch `/arm_gripper_status`:

```bash
ros2 launch cs603_voice_intent integration_demo.launch.py \
  start_perception:=true \
  use_depth:=true \
  enable_motion:=true
```

Emergency stop:

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

Obstacle avoidance is enabled by default in the follow controller. It slows
forward motion below `obstacle_slow_distance_m` and stops forward motion at
`obstacle_stop_distance_m` using the front ToF range topic.

Lost-target search is enabled by default in follow mode. If the robot is in
`FOLLOWING` and has no valid person track for `search_target_timeout_sec`
seconds, it rotates slowly in place at `search_angular_radps` until a person is
tracked again. It stays disabled in approach mode so pick/drop behavior is not
interrupted.

The arm/gripper pick-drop node is enabled by default in the integration launch.
It listens for `CMD_PICK` and `CMD_DROP`, but ignores them unless the behavior
FSM is already in `APPROACHING`. Tune the ground and carry poses with
`pick_x_m`, `pick_z_m`, `drop_x_m`, `drop_z_m`, `carry_x_m`, and `carry_z_m`.

More detailed voice notes live in
[`docs/VOICE_INTENT_RUNBOOK.md`](docs/VOICE_INTENT_RUNBOOK.md).

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
  tof_0:=true \
  tof_rate:=10 \
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
