import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ObstacleAvoidanceConfig:
    enabled: bool = True
    stop_distance_m: float = 0.45
    slow_distance_m: float = 0.9
    min_forward_scale: float = 0.25
    turn_when_blocked: bool = True
    turn_angular_radps: float = 0.35
    turn_direction: float = 1.0


@dataclass(frozen=True)
class ObstacleAvoidanceResult:
    linear_x: float
    angular_z: float
    obstacle_detected: bool
    blocked: bool
    forward_scale: float


def valid_range(range_m, min_range_m=0.0, max_range_m=math.inf):
    if not math.isfinite(float(range_m)):
        return False

    range_m = float(range_m)
    min_range_m = float(min_range_m) if math.isfinite(float(min_range_m)) else 0.0
    max_range_m = float(max_range_m) if math.isfinite(float(max_range_m)) else math.inf

    if max_range_m > 0.0 and range_m > max_range_m:
        return False
    if min_range_m > 0.0 and range_m < min_range_m:
        return False
    return range_m >= 0.0


def clamp_unit(value):
    return max(0.0, min(1.0, float(value)))


def forward_scale(range_m, config):
    if not config.enabled or range_m is None:
        return 1.0, False, False

    stop_distance = max(0.0, float(config.stop_distance_m))
    slow_distance = max(stop_distance, float(config.slow_distance_m))
    range_m = float(range_m)

    if range_m <= stop_distance:
        return 0.0, True, True
    if range_m >= slow_distance:
        return 1.0, False, False

    if math.isclose(slow_distance, stop_distance):
        return 0.0, True, True

    ratio = (range_m - stop_distance) / (slow_distance - stop_distance)
    min_scale = clamp_unit(config.min_forward_scale)
    scale = min_scale + clamp_unit(ratio) * (1.0 - min_scale)
    return scale, True, False


def apply_obstacle_avoidance(linear_x, angular_z, range_m, config):
    scale, detected, blocked = forward_scale(range_m, config)

    linear_x = float(linear_x)
    angular_z = float(angular_z)

    if not config.enabled or linear_x <= 0.0:
        return ObstacleAvoidanceResult(linear_x, angular_z, detected, blocked, scale)

    if blocked:
        linear_x = 0.0
        if config.turn_when_blocked:
            turn_rate = abs(float(config.turn_angular_radps))
            if abs(angular_z) < turn_rate:
                direction = 1.0 if float(config.turn_direction) >= 0.0 else -1.0
                angular_z = direction * turn_rate
    else:
        linear_x *= scale

    return ObstacleAvoidanceResult(linear_x, angular_z, detected, blocked, scale)
