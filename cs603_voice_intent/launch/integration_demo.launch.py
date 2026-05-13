from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    input_mode = LaunchConfiguration("input_mode")
    stub_text = LaunchConfiguration("stub_text")
    enable_motion = LaunchConfiguration("enable_motion")
    start_perception = LaunchConfiguration("start_perception")
    use_fake_perception = LaunchConfiguration("use_fake_perception")
    use_depth = LaunchConfiguration("use_depth")
    use_identity = LaunchConfiguration("use_identity")
    target_track_id = LaunchConfiguration("target_track_id")
    follow_distance_m = LaunchConfiguration("follow_distance_m")
    approach_distance_m = LaunchConfiguration("approach_distance_m")
    enable_obstacle_avoidance = LaunchConfiguration("enable_obstacle_avoidance")
    range_topic = LaunchConfiguration("range_topic")
    obstacle_stop_distance_m = LaunchConfiguration("obstacle_stop_distance_m")
    obstacle_slow_distance_m = LaunchConfiguration("obstacle_slow_distance_m")
    enable_arm_gripper = LaunchConfiguration("enable_arm_gripper")
    pick_x_m = LaunchConfiguration("pick_x_m")
    pick_z_m = LaunchConfiguration("pick_z_m")
    carry_x_m = LaunchConfiguration("carry_x_m")
    carry_z_m = LaunchConfiguration("carry_z_m")
    drop_x_m = LaunchConfiguration("drop_x_m")
    drop_z_m = LaunchConfiguration("drop_z_m")
    gripper_power = LaunchConfiguration("gripper_power")

    perception_launch = PathJoinSubstitution(
        [
            FindPackageShare("robomaster_perception"),
            "launch",
            "perception.launch.py",
        ]
    )
    follow_launch = PathJoinSubstitution(
        [
            FindPackageShare("robomaster_follow_controller"),
            "launch",
            "follow.launch.py",
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "input_mode",
                default_value="param",
                description="Voice input mode: param, stdin, or mic_once.",
            ),
            DeclareLaunchArgument(
                "stub_text",
                default_value="",
                description="Phrase to classify when input_mode is param.",
            ),
            DeclareLaunchArgument(
                "enable_motion",
                default_value="false",
                description="Allow the PID follow controller to publish non-zero cmd_vel.",
            ),
            DeclareLaunchArgument(
                "start_perception",
                default_value="true",
                description="Start the real camera perception pipeline.",
            ),
            DeclareLaunchArgument(
                "use_fake_perception",
                default_value="false",
                description="Start fake /people/depth input for bench testing.",
            ),
            DeclareLaunchArgument(
                "use_depth",
                default_value="true",
                description="Enable depth estimation in the perception pipeline.",
            ),
            DeclareLaunchArgument(
                "use_identity",
                default_value="false",
                description="Enable face identity recognition in perception.",
            ),
            DeclareLaunchArgument(
                "target_track_id",
                default_value="-1",
                description="Track ID to follow, or -1 for closest valid target.",
            ),
            DeclareLaunchArgument(
                "follow_distance_m",
                default_value="1.5",
                description="Target distance for CMD_FOLLOW.",
            ),
            DeclareLaunchArgument(
                "approach_distance_m",
                default_value="0.8",
                description="Target distance for CMD_APPROACH.",
            ),
            DeclareLaunchArgument(
                "enable_obstacle_avoidance",
                default_value="true",
                description=(
                    "Use the front ToF range topic to slow or stop follow motion."
                ),
            ),
            DeclareLaunchArgument(
                "range_topic",
                default_value="/range_0",
                description="Front ToF sensor_msgs/Range topic from robomaster_ros.",
            ),
            DeclareLaunchArgument(
                "obstacle_stop_distance_m",
                default_value="0.45",
                description=(
                    "Stop forward motion when front ToF is at or below this distance."
                ),
            ),
            DeclareLaunchArgument(
                "obstacle_slow_distance_m",
                default_value="0.9",
                description=(
                    "Begin scaling down forward speed below this front ToF distance."
                ),
            ),
            DeclareLaunchArgument(
                "enable_arm_gripper",
                default_value="true",
                description="Start the approach-gated arm/gripper pick-drop node.",
            ),
            DeclareLaunchArgument(
                "pick_x_m",
                default_value="0.16",
                description="Arm x target for ground pickup, in meters.",
            ),
            DeclareLaunchArgument(
                "pick_z_m",
                default_value="-0.08",
                description="Arm z target for ground pickup, in meters.",
            ),
            DeclareLaunchArgument(
                "carry_x_m",
                default_value="0.10",
                description="Arm x target after pickup/drop, in meters.",
            ),
            DeclareLaunchArgument(
                "carry_z_m",
                default_value="0.10",
                description="Arm z target after pickup/drop, in meters.",
            ),
            DeclareLaunchArgument(
                "drop_x_m",
                default_value="0.16",
                description="Arm x target for ground drop, in meters.",
            ),
            DeclareLaunchArgument(
                "drop_z_m",
                default_value="-0.08",
                description="Arm z target for ground drop, in meters.",
            ),
            DeclareLaunchArgument(
                "gripper_power",
                default_value="0.7",
                description="Gripper open/close power in [0, 1].",
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
                executable="behavior_fsm",
                name="behavior_fsm",
                output="screen",
            ),
            Node(
                package="cs603_voice_intent",
                executable="arm_gripper_node",
                name="arm_gripper_node",
                output="screen",
                condition=IfCondition(enable_arm_gripper),
                parameters=[
                    {
                        "pick_x_m": ParameterValue(pick_x_m, value_type=float),
                        "pick_z_m": ParameterValue(pick_z_m, value_type=float),
                        "carry_x_m": ParameterValue(carry_x_m, value_type=float),
                        "carry_z_m": ParameterValue(carry_z_m, value_type=float),
                        "drop_x_m": ParameterValue(drop_x_m, value_type=float),
                        "drop_z_m": ParameterValue(drop_z_m, value_type=float),
                        "gripper_power": ParameterValue(
                            gripper_power,
                            value_type=float,
                        ),
                    }
                ],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(perception_launch),
                launch_arguments={
                    "use_depth": use_depth,
                    "use_identity": use_identity,
                }.items(),
                condition=IfCondition(start_perception),
            ),
            Node(
                package="robomaster_follow_controller",
                executable="fake_perception",
                name="fake_perception",
                output="screen",
                condition=IfCondition(use_fake_perception),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(follow_launch),
                launch_arguments={
                    "enable_motion": enable_motion,
                    "target_track_id": target_track_id,
                    "follow_distance_m": follow_distance_m,
                    "approach_distance_m": approach_distance_m,
                    "require_fsm_active": "true",
                    "enable_obstacle_avoidance": enable_obstacle_avoidance,
                    "range_topic": range_topic,
                    "obstacle_stop_distance_m": obstacle_stop_distance_m,
                    "obstacle_slow_distance_m": obstacle_slow_distance_m,
                }.items(),
            ),
        ]
    )
