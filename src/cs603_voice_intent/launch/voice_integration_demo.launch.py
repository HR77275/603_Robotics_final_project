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
