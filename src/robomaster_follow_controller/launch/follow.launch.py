from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_config = PathJoinSubstitution([
        FindPackageShare('robomaster_follow_controller'),
        'config',
        'follow.yaml',
    ])

    config_file = LaunchConfiguration('config_file')
    enable_motion = LaunchConfiguration('enable_motion')
    target_track_id = LaunchConfiguration('target_track_id')
    target_distance_m = LaunchConfiguration('target_distance_m')

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file',
            default_value=default_config,
            description='Path to follow controller parameter YAML file.',
        ),
        DeclareLaunchArgument(
            'enable_motion',
            default_value='true',
            description='Publish non-zero cmd_vel commands when true.',
        ),
        DeclareLaunchArgument(
            'target_track_id',
            default_value='-1',
            description='Track ID to follow, or -1 for the closest tracked person.',
        ),
        DeclareLaunchArgument(
            'target_distance_m',
            default_value='1.5',
            description='Desired following distance in meters.',
        ),
        Node(
            package='robomaster_follow_controller',
            executable='follow_node',
            name='follow_node',
            output='screen',
            parameters=[
                config_file,
                {
                    'enable_motion': ParameterValue(enable_motion, value_type=bool),
                    'target_track_id': ParameterValue(target_track_id, value_type=int),
                    'target_distance_m': ParameterValue(target_distance_m, value_type=float),
                },
            ],
        ),
    ])
