import math

from robomaster_follow_controller.follow_node import depth_scaled_linear_limit


def test_depth_scaled_limit_uses_base_limit_near_target():
    assert depth_scaled_linear_limit(
        depth_error=0.1,
        base_limit=0.18,
        far_limit=0.30,
        start_error=0.25,
        full_error=0.90,
    ) == 0.18


def test_depth_scaled_limit_increases_for_far_target():
    limit = depth_scaled_linear_limit(
        depth_error=0.575,
        base_limit=0.18,
        far_limit=0.30,
        start_error=0.25,
        full_error=0.90,
    )

    assert math.isclose(limit, 0.24, abs_tol=1e-9)


def test_depth_scaled_limit_caps_at_far_limit():
    assert depth_scaled_linear_limit(
        depth_error=1.2,
        base_limit=0.18,
        far_limit=0.30,
        start_error=0.25,
        full_error=0.90,
    ) == 0.30


def test_depth_scaled_limit_can_be_disabled():
    assert depth_scaled_linear_limit(
        depth_error=1.2,
        base_limit=0.18,
        far_limit=0.30,
        start_error=0.25,
        full_error=0.90,
        enabled=False,
    ) == 0.18

