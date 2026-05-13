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
    follow_distance_m = LaunchConfiguration('follow_distance_m')
    approach_distance_m = LaunchConfiguration('approach_distance_m')
    require_fsm_active = LaunchConfiguration('require_fsm_active')
    enable_obstacle_avoidance = LaunchConfiguration('enable_obstacle_avoidance')
    range_topic = LaunchConfiguration('range_topic')
    obstacle_stop_distance_m = LaunchConfiguration('obstacle_stop_distance_m')
    obstacle_slow_distance_m = LaunchConfiguration('obstacle_slow_distance_m')

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
        DeclareLaunchArgument(
            'follow_distance_m',
            default_value='1.5',
            description='Target distance when /behavior_state is FOLLOWING.',
        ),
        DeclareLaunchArgument(
            'approach_distance_m',
            default_value='0.8',
            description='Target distance when /behavior_state is APPROACHING.',
        ),
        DeclareLaunchArgument(
            'require_fsm_active',
            default_value='true',
            description='Require /follow_target_active from the voice behavior FSM.',
        ),
        DeclareLaunchArgument(
            'enable_obstacle_avoidance',
            default_value='true',
            description='Use the front ToF range topic to slow or stop forward motion.',
        ),
        DeclareLaunchArgument(
            'range_topic',
            default_value='/range_0',
            description='Front ToF sensor_msgs/Range topic from robomaster_ros.',
        ),
        DeclareLaunchArgument(
            'obstacle_stop_distance_m',
            default_value='0.45',
            description=(
                'Stop forward motion when front ToF is at or below this distance.'
            ),
        ),
        DeclareLaunchArgument(
            'obstacle_slow_distance_m',
            default_value='0.9',
            description=(
                'Begin scaling down forward speed below this front ToF distance.'
            ),
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
                    'follow_distance_m': ParameterValue(follow_distance_m, value_type=float),
                    'approach_distance_m': ParameterValue(approach_distance_m, value_type=float),
                    'require_fsm_active': ParameterValue(require_fsm_active, value_type=bool),
                    'enable_obstacle_avoidance': ParameterValue(
                        enable_obstacle_avoidance,
                        value_type=bool,
                    ),
                    'range_topic': range_topic,
                    'obstacle_stop_distance_m': ParameterValue(
                        obstacle_stop_distance_m,
                        value_type=float,
                    ),
                    'obstacle_slow_distance_m': ParameterValue(
                        obstacle_slow_distance_m,
                        value_type=float,
                    ),
                },
            ],
        ),
    ])
