import math

from robomaster_follow_controller.follow_distance_metrics import (
    DistanceSample,
    compute_trial_metrics,
)


def sample(time_s, depth_m, track_id=1):
    return DistanceSample(time_s=time_s, depth_m=depth_m, track_id=track_id)


def test_perfect_distance_hold_scores_full_credit():
    metrics = compute_trial_metrics(
        trial_index=1,
        samples=[
            sample(0.0, 1.5),
            sample(0.5, 1.5),
            sample(1.0, 1.5),
        ],
        target_depth_m=1.5,
        tolerance_m=0.15,
        duration_s=1.0,
        message_count=3,
    )

    assert metrics.score_pct == 100.0
    assert metrics.hold_rate == 1.0
    assert metrics.mae_m == 0.0
    assert metrics.rmse_m == 0.0
    assert metrics.valid_sample_ratio == 1.0


def test_hold_rate_counts_samples_inside_tolerance_band():
    metrics = compute_trial_metrics(
        trial_index=1,
        samples=[
            sample(0.0, 1.50),
            sample(0.5, 1.64),
            sample(1.0, 1.70),
            sample(1.5, 1.30),
        ],
        target_depth_m=1.5,
        tolerance_m=0.15,
        duration_s=2.0,
        message_count=5,
    )

    assert metrics.hold_rate == 0.5
    assert metrics.score_pct == 50.0
    assert metrics.sample_count == 4
    assert metrics.valid_sample_ratio == 0.8
    assert math.isclose(metrics.max_too_far_m, 0.05, abs_tol=1e-9)
    assert math.isclose(metrics.max_too_close_m, 0.05, abs_tol=1e-9)


def test_hold_rate_can_use_asymmetric_acceptance_range():
    metrics = compute_trial_metrics(
        trial_index=1,
        samples=[
            sample(0.0, 1.35),
            sample(0.5, 1.40),
            sample(1.0, 1.90),
            sample(1.5, 2.20),
            sample(2.0, 2.30),
        ],
        target_depth_m=1.5,
        tolerance_m=0.15,
        min_depth_m=1.4,
        max_depth_m=2.2,
        duration_s=2.0,
        message_count=5,
    )

    assert metrics.hold_rate == 0.6
    assert metrics.score_pct == 60.0
    assert math.isclose(metrics.max_too_close_m, 0.05, abs_tol=1e-9)
    assert math.isclose(metrics.max_too_far_m, 0.10, abs_tol=1e-9)


def test_empty_trial_reports_zero_score_and_nan_error_metrics():
    metrics = compute_trial_metrics(
        trial_index=1,
        samples=[],
        target_depth_m=1.5,
        tolerance_m=0.15,
        duration_s=2.0,
        message_count=4,
    )

    assert metrics.score_pct == 0.0
    assert metrics.sample_count == 0
    assert metrics.valid_sample_ratio == 0.0
    assert math.isnan(metrics.mae_m)
    assert math.isnan(metrics.rmse_m)
