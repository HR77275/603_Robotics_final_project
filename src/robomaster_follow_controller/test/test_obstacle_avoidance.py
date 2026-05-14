import pytest

from robomaster_follow_controller.obstacle_avoidance import (
    ObstacleAvoidanceConfig,
    apply_obstacle_avoidance,
    valid_range,
)


def test_valid_range_rejects_invalid_sensor_values():
    assert valid_range(0.4, 0.1, 3.0)
    assert not valid_range(float("nan"), 0.1, 3.0)
    assert not valid_range(0.05, 0.1, 3.0)
    assert not valid_range(4.0, 0.1, 3.0)


def test_clear_path_keeps_command_unchanged():
    config = ObstacleAvoidanceConfig(stop_distance_m=0.45, slow_distance_m=0.9)

    result = apply_obstacle_avoidance(0.18, 0.2, 1.2, config)

    assert result.linear_x == 0.18
    assert result.angular_z == 0.2
    assert not result.obstacle_detected
    assert not result.blocked


def test_slow_zone_scales_forward_motion():
    config = ObstacleAvoidanceConfig(
        stop_distance_m=0.4,
        slow_distance_m=0.8,
        min_forward_scale=0.25,
    )

    result = apply_obstacle_avoidance(0.2, 0.0, 0.6, config)

    assert result.linear_x == pytest.approx(0.125)
    assert result.angular_z == 0.0
    assert result.obstacle_detected
    assert not result.blocked


def test_stop_zone_blocks_forward_motion_and_turns():
    config = ObstacleAvoidanceConfig(
        stop_distance_m=0.45,
        slow_distance_m=0.9,
        turn_angular_radps=0.35,
        turn_direction=-1.0,
    )

    result = apply_obstacle_avoidance(0.18, 0.0, 0.3, config)

    assert result.linear_x == 0.0
    assert result.angular_z == -0.35
    assert result.obstacle_detected
    assert result.blocked


def test_reverse_motion_is_not_suppressed_by_front_obstacle():
    config = ObstacleAvoidanceConfig(stop_distance_m=0.45, slow_distance_m=0.9)

    result = apply_obstacle_avoidance(-0.1, 0.0, 0.2, config)

    assert result.linear_x == -0.1
    assert result.angular_z == 0.0
    assert result.obstacle_detected
    assert result.blocked
