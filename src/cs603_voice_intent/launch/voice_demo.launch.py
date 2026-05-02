from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    input_mode = LaunchConfiguration("input_mode")
    enable_motion = LaunchConfiguration("enable_motion")
    stub_text = LaunchConfiguration("stub_text")

    return LaunchDescription(
        [
            DeclareLaunchArgument("input_mode", default_value="stdin"),
            DeclareLaunchArgument("enable_motion", default_value="false"),
            DeclareLaunchArgument("stub_text", default_value=""),
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
                executable="voice_cmd_vel_bridge",
                name="voice_cmd_vel_bridge",
                output="screen",
                parameters=[
                    {
                        "enable_motion": enable_motion,
                    }
                ],
            ),
        ]
    )
