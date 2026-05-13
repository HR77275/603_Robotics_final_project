from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_config = PathJoinSubstitution([
        FindPackageShare('robomaster_perception'),
        'config',
        'perception.yaml',
    ])

    config_file = LaunchConfiguration('config_file')
    use_identity = LaunchConfiguration('use_identity')
    use_depth = LaunchConfiguration('use_depth')

    common_output = 'screen'

    nodes = [
        Node(
            package='robomaster_perception',
            executable='deepsort_tracker_node',
            name='deepsort_tracker_node',
            output=common_output,
            parameters=[config_file],
        ),
        Node(
            package='robomaster_perception',
            executable='tracking_overlay_node',
            name='tracking_overlay_node',
            output=common_output,
            parameters=[config_file],
        ),
        Node(
            package='robomaster_perception',
            executable='depth_estimator_node',
            name='depth_estimator_node',
            output=common_output,
            parameters=[config_file],
            condition=IfCondition(use_depth),
        ),
        Node(
            package='robomaster_perception',
            executable='face_identity_node',
            name='face_identity_node',
            output=common_output,
            parameters=[config_file],
            condition=IfCondition(use_identity),
        ),
    ]

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file',
            default_value=default_config,
            description='Path to the perception parameter YAML file.',
        ),
        DeclareLaunchArgument(
            'use_depth',
            default_value='false',
            description='Start depth estimation and ToF correction.',
        ),
        DeclareLaunchArgument(
            'use_identity',
            default_value='false',
            description='Start face identity recognition.',
        ),
        *nodes,
    ])
