from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
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

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file',
            default_value=default_config,
            description='Path to the perception parameter YAML file.',
        ),
        Node(
            package='robomaster_perception',
            executable='deepsort_tracker_node',
            name='deepsort_tracker_node',
            output='screen',
            parameters=[config_file],
        ),
        Node(
            package='robomaster_perception',
            executable='tracking_overlay_node',
            name='tracking_overlay_node',
            output='screen',
            parameters=[config_file],
        ),
    ])
