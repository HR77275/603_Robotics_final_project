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
            DeclareLaunchArgument(
                "input_mode",
                default_value="param",
                description=(
                    "Input source for voice_intent_node. Use param with ros2 launch; "
                    "stdin is intended for ros2 run in an interactive terminal."
                ),
            ),
            DeclareLaunchArgument(
                "enable_motion",
                default_value="false",
                description="Set true only for a cleared physical robot motion test.",
            ),
            DeclareLaunchArgument(
                "stub_text",
                default_value="",
                description="Phrase to classify in param mode, e.g. 'follow me'.",
            ),
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
            Node(
                package="cs603_voice_intent",
                executable="behavior_fsm",
                name="behavior_fsm",
                output="screen",
            ),
        ]
    )
