# RoboMaster Perception Development Guide

This `src/` folder contains the ROS 2 packages used for the RoboMaster EP perception stack. The current pipeline uses the RoboMaster built-in person detector, DeepSORT tracking, monocular depth estimation, optional ToF correction, and optional face identity association.

## Package Layout

- `robomaster_ros/`: upstream RoboMaster ROS driver package. Keep this as an external dependency or submodule.
- `robomaster_perception_msgs/`: custom messages for tracked people, person depth, and identity results.
- `robomaster_perception/`: perception nodes, launch files, and parameter config.
- `robomaster_follow_controller/`: PID follow controller that consumes perception depth/tracking output and publishes `/cmd_vel`.
- `robomaster_vision_overlay/`: earlier/simple overlay utility retained for reference.

## Main Topics

Inputs:

- `/camera/image_color` (`sensor_msgs/msg/Image`): robot camera feed.
- `/vision` (`robomaster_msgs/msg/Detection`): built-in RoboMaster detections.
- `/range_0` (`sensor_msgs/msg/Range`): front ToF sensor, when enabled.

Outputs:

- `/people/tracks` (`robomaster_perception_msgs/msg/TrackedPeople`): tracked full-body person boxes.
- `/people/depth` (`robomaster_perception_msgs/msg/PeopleDepth`): depth estimate per tracked person.
- `/people/identities` (`robomaster_perception_msgs/msg/PeopleIdentities`): optional face identity per track ID.
- `/perception/tracking_debug_image` (`sensor_msgs/msg/Image`): camera feed with bbox, track ID, name, and depth overlay.
- `/cmd_vel` (`geometry_msgs/msg/Twist`): follow controller velocity command output.


## Fresh Setup Dependencies

Install ROS/apt dependencies from the workspace root:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

Install PyTorch for the target machine. For the RTX 3060 setup used here, CUDA 11.8 wheels worked:

```bash
python3 -m pip install --user   torch==2.7.1+cu118   torchvision==0.22.1+cu118   --index-url https://download.pytorch.org/whl/cu118
```

Install the remaining ML dependencies:

```bash
python3 -m pip install --user -r src/robomaster_perception/requirements-ml.txt
python3 -m pip install --user --force-reinstall "numpy==1.24.4"
```

`numpy==1.24.4` is important for ROS 2 Humble compatibility with `cv_bridge` and SciPy packages. Avoid NumPy 2.x in this workspace.

Install Torchreid/OSNet for stronger DeepSORT appearance embeddings:

```bash
cd ~
git clone https://github.com/KaiyangZhou/deep-person-reid.git
cd deep-person-reid
python3 -m pip install --user --no-build-isolation --no-deps .
```

If the Torchreid install fails because of optional Cython extensions, disable the extension build in `deep-person-reid/setup.py` by changing `ext_modules=cythonize(ext_modules)` to `ext_modules=[]`, then rerun the install command.

## Build

From the workspace root:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select robomaster_perception_msgs robomaster_perception robomaster_follow_controller
source install/setup.bash
```

If ROS cannot discover the custom message package, restart the daemon:

```bash
ros2 daemon stop
ros2 daemon start
```


## RoboMaster ROS Submodule

This workspace uses `src/robomaster_ros` as a git submodule. The driver may need a small direct-IP connection patch so the environment variables below can be used reliably on networks where automatic discovery is unreliable:

```bash
export ROBOMASTER_LOCAL_IP=<laptop_or_host_ip>
export ROBOMASTER_ROBOT_IP=<robot_ip>
```

Recommended setup for reproducibility:

1. Fork `https://github.com/jeguzzi/robomaster_ros` into the project owner's GitHub account.
2. Commit the direct-IP patch inside that fork.
3. Point this workspace submodule to the fork and commit the submodule pointer in the parent repo.

Fresh clone command:

```bash
git clone --recurse-submodules <project_repo_url>
```

If the repo was already cloned without submodules:

```bash
git submodule update --init --recursive
```

Check submodule state before pushing:

```bash
git submodule status
git -C src/robomaster_ros status --short
```

The second command should be empty. If it shows modified files, commit them inside the `robomaster_ros` fork first, then commit the updated submodule pointer in this parent repo.

## Start The Robot Driver

Run the driver first, with camera, person detection, and ToF enabled. Replace the placeholders with the local values for your robot/network.

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

export ROBOMASTER_LOCAL_IP=<laptop_or_host_ip>
export ROBOMASTER_ROBOT_IP=<robot_ip>

ros2 launch robomaster_ros main.launch   model:=ep   conn_type:=sta   serial_number:=<robot_serial_number>   camera:=true   vision:=true   vision_targets:='["person"]'   tof_0:=true   tof_rate:=10
```

Check that detections are available:

```bash
ros2 topic echo /vision --once --no-daemon
```

## Start Perception

Recommended first test: tracking and overlay only.

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch robomaster_perception tracking.launch.py
```

View the overlay:

```bash
ros2 run rqt_image_view rqt_image_view /perception/tracking_debug_image
```

Start tracking plus depth:

```bash
ros2 launch robomaster_perception perception.launch.py use_depth:=true use_identity:=false
```

Start the full pipeline:

```bash
ros2 launch robomaster_perception perception.launch.py use_depth:=true use_identity:=true
```


## Follow Controller

The follow controller is in `robomaster_follow_controller`. It subscribes to:

- `/people/depth` (`robomaster_perception_msgs/msg/PeopleDepth`) for target depth and normalized bbox center.
- `/perception/tracking_debug_image` (`sensor_msgs/msg/Image`) to stay synchronized with the annotated camera stream.

It publishes:

- `/cmd_vel` (`geometry_msgs/msg/Twist`) for chassis motion.

Start it after the robot driver and perception pipeline are running:

```bash
ros2 launch robomaster_follow_controller follow.launch.py
```

Safer dry run, publishing only zero velocity commands while checking that the node starts:

```bash
ros2 launch robomaster_follow_controller follow.launch.py enable_motion:=false
```

Follow a specific track ID instead of the closest person:

```bash
ros2 launch robomaster_follow_controller follow.launch.py target_track_id:=3 target_distance_m:=1.5
```

Local controller test without the robot/perception stack:

```bash
# Terminal 1
ros2 run robomaster_follow_controller fake_perception

# Terminal 2
ros2 launch robomaster_follow_controller follow.launch.py enable_motion:=false

# Terminal 3
ros2 topic echo /cmd_vel --once --no-daemon
```

Tune PID and speed limits in `robomaster_follow_controller/config/follow.yaml`.

## Face Identity Workflow

Face recognition is only used to associate a name with a tracker ID. The robot should still follow or reason about the full-body tracked box, not the face box.

Create one folder per identity:

```bash
mkdir -p face_db/images/<person_name>
```

Add face images into that folder, then build the embedding database:

```bash
ros2 run robomaster_perception enroll_faces   --image-dir face_db/images   --output face_db/embeddings/face_db.npz
```

Private face images and generated embeddings are ignored by git by default.

## Useful Debug Commands

```bash
ros2 topic hz /camera/image_color --no-daemon
ros2 topic echo /vision --once --no-daemon
ros2 topic echo /people/tracks --once --no-daemon
ros2 topic echo /people/depth --once --no-daemon
ros2 topic echo /people/identities --once --no-daemon
ros2 topic hz /perception/tracking_debug_image --no-daemon
```

## Development Notes

- Keep robot IP addresses, serial numbers, personal images, and generated embeddings out of commits.
- Tune parameters in `robomaster_perception/config/perception.yaml`.
- `tracking.launch.py` is the stable baseline. Enable depth and identity only after tracking is working.
- If tracking works manually but not through launch, test nodes incrementally: tracker and overlay first, then depth, then identity.
