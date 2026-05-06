"""Integrated voice + follow-controller launch for robot day.

This launch is the integration point between the voice lane (this package) and
the camera/perception/follow lane on `feature/camera_detection`. It assumes the
two branches have been merged and `colcon build` has been run for both
packages in the same workspace.

Pipeline started by this launch:

    voice_intent_node  ->  /voice_intent
                                |
                                v
                         behavior_fsm
                                |
                                v
                  /follow_target_active (Bool)
                                |
                                v
    [ teammate's follow_node ] ->  /cmd_vel_follow_raw
                                |
                                v
                         cmd_vel_gate  ->  /cmd_vel  ->  robot wheels

Integration contract enforced here:

* The teammate's `follow_node` is spawned with `cmd_vel_topic` overridden to
  `/cmd_vel_follow_raw` so the gate is the single writer of `/cmd_vel`.
* `follow_enable_motion` defaults to False so the teammate node never drives
  the chassis on its own when launched through this file.
* `gate_enable_motion` defaults to False so even with the gate active and the
  FSM in FOLLOWING, no Twist is forwarded until motion is explicitly enabled.

To run the gated integration without final motion (safe dry-run):

    ros2 launch cs603_voice_intent voice_integration_demo.launch.py \\
        input_mode:=stdin \\
        launch_follow_controller:=true \\
        follow_enable_motion:=false \\
        gate_enable_motion:=false

To run the integration with the teammate node publishing real raw velocity but
gate still blocking final motion (recommended pre-floor test):

    ... follow_enable_motion:=true gate_enable_motion:=false

Floor test only after the area is clear and emergency stop is ready:

    ... follow_enable_motion:=true gate_enable_motion:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    input_mode = LaunchConfiguration("input_mode")
    stub_text = LaunchConfiguration("stub_text")
    gate_enable_motion = LaunchConfiguration("gate_enable_motion")
    launch_follow_controller = LaunchConfiguration("launch_follow_controller")
    follow_enable_motion = LaunchConfiguration("follow_enable_motion")
    raw_cmd_vel_topic = LaunchConfiguration("raw_cmd_vel_topic")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")
    people_depth_topic = LaunchConfiguration("people_depth_topic")

    return LaunchDescription(
        [
            DeclareLaunchArgument("input_mode", default_value="stdin"),
            DeclareLaunchArgument("stub_text", default_value=""),
            DeclareLaunchArgument("gate_enable_motion", default_value="false"),
            DeclareLaunchArgument("launch_follow_controller", default_value="false"),
            DeclareLaunchArgument("follow_enable_motion", default_value="false"),
            DeclareLaunchArgument("raw_cmd_vel_topic", default_value="/cmd_vel_follow_raw"),
            DeclareLaunchArgument("cmd_vel_topic", default_value="/cmd_vel"),
            DeclareLaunchArgument("people_depth_topic", default_value="/people/depth"),
            Node(
                package="cs603_voice_intent",
                executable="voice_intent_node",
                name="voice_intent_node",
                output="screen",
                parameters=[
                    {
                        "input_mode": input_mode,
                        "stub_text": stub_text,
                    }
                ],
            ),
            Node(
                package="cs603_voice_intent",
                executable="behavior_fsm",
                name="behavior_fsm",
                output="screen",
            ),
            Node(
                package="cs603_voice_intent",
                executable="cmd_vel_gate",
                name="cmd_vel_gate",
                output="screen",
                parameters=[
                    {
                        "enable_motion": ParameterValue(gate_enable_motion, value_type=bool),
                        "raw_cmd_vel_topic": raw_cmd_vel_topic,
                        "cmd_vel_topic": cmd_vel_topic,
                    }
                ],
            ),
            Node(
                package="cs603_voice_intent",
                executable="robot_response_node",
                name="robot_response_node",
                output="screen",
            ),
            Node(
                package="robomaster_follow_controller",
                executable="follow_node",
                name="follow_node",
                output="screen",
                condition=IfCondition(launch_follow_controller),
                parameters=[
                    {
                        "enable_motion": ParameterValue(follow_enable_motion, value_type=bool),
                        "cmd_vel_topic": raw_cmd_vel_topic,
                        "people_depth_topic": people_depth_topic,
                    }
                ],
            ),
        ]
    )
