from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class DistanceSample:
    time_s: float
    depth_m: float
    track_id: int


@dataclass(frozen=True)
class DistanceTrialMetrics:
    trial_index: int
    target_depth_m: float
    tolerance_m: float
    min_depth_m: float
    max_depth_m: float
    duration_s: float
    message_count: int
    sample_count: int
    valid_sample_ratio: float
    mean_depth_m: float
    hold_rate: float
    mae_m: float
    rmse_m: float
    bias_m: float
    std_error_m: float
    max_too_close_m: float
    max_too_far_m: float
    mean_abs_delta_m: float
    max_abs_delta_m: float
    score_pct: float


def _nan_metrics(
    trial_index: int,
    target_depth_m: float,
    tolerance_m: float,
    min_depth_m: float,
    max_depth_m: float,
    duration_s: float,
    message_count: int,
) -> DistanceTrialMetrics:
    return DistanceTrialMetrics(
        trial_index=trial_index,
        target_depth_m=target_depth_m,
        tolerance_m=tolerance_m,
        min_depth_m=min_depth_m,
        max_depth_m=max_depth_m,
        duration_s=duration_s,
        message_count=message_count,
        sample_count=0,
        valid_sample_ratio=0.0,
        mean_depth_m=float("nan"),
        hold_rate=0.0,
        mae_m=float("nan"),
        rmse_m=float("nan"),
        bias_m=float("nan"),
        std_error_m=float("nan"),
        max_too_close_m=float("nan"),
        max_too_far_m=float("nan"),
        mean_abs_delta_m=float("nan"),
        max_abs_delta_m=float("nan"),
        score_pct=0.0,
    )


def compute_trial_metrics(
    *,
    trial_index: int,
    samples: Sequence[DistanceSample],
    target_depth_m: float,
    tolerance_m: float,
    duration_s: float,
    message_count: int,
    min_depth_m: float | None = None,
    max_depth_m: float | None = None,
) -> DistanceTrialMetrics:
    if min_depth_m is None or not math.isfinite(float(min_depth_m)):
        min_depth_m = target_depth_m - tolerance_m
    if max_depth_m is None or not math.isfinite(float(max_depth_m)):
        max_depth_m = target_depth_m + tolerance_m
    min_depth_m = float(min_depth_m)
    max_depth_m = float(max_depth_m)
    if min_depth_m > max_depth_m:
        min_depth_m, max_depth_m = max_depth_m, min_depth_m

    if not samples:
        return _nan_metrics(
            trial_index,
            target_depth_m,
            tolerance_m,
            min_depth_m,
            max_depth_m,
            duration_s,
            message_count,
        )

    depths = [float(sample.depth_m) for sample in samples]
    errors = [depth - target_depth_m for depth in depths]
    abs_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    bias = mean(errors)
    std_error = math.sqrt(mean([(error - bias) ** 2 for error in errors]))
    deltas = [
        abs(depths[index] - depths[index - 1])
        for index in range(1, len(depths))
    ]

    hold_rate = sum(
        1 for depth in depths if min_depth_m <= depth <= max_depth_m
    ) / len(depths)

    return DistanceTrialMetrics(
        trial_index=trial_index,
        target_depth_m=target_depth_m,
        tolerance_m=tolerance_m,
        min_depth_m=min_depth_m,
        max_depth_m=max_depth_m,
        duration_s=duration_s,
        message_count=message_count,
        sample_count=len(samples),
        valid_sample_ratio=(
            len(samples) / message_count if message_count > 0 else 0.0
        ),
        mean_depth_m=mean(depths),
        hold_rate=hold_rate,
        mae_m=mean(abs_errors),
        rmse_m=math.sqrt(mean(squared_errors)),
        bias_m=bias,
        std_error_m=std_error,
        max_too_close_m=max(0.0, min_depth_m - min(depths)),
        max_too_far_m=max(0.0, max(depths) - max_depth_m),
        mean_abs_delta_m=mean(deltas) if deltas else 0.0,
        max_abs_delta_m=max(deltas) if deltas else 0.0,
        score_pct=100.0 * hold_rate,
    )


def finite_values(values: Sequence[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def mean_finite(values: Sequence[float]) -> float:
    finite = finite_values(values)
    if not finite:
        return float("nan")
    return mean(finite)


def format_trial_metrics(metrics: DistanceTrialMetrics) -> str:
    return (
        f"trial={metrics.trial_index} "
        f"score={metrics.score_pct:.1f}% "
        f"hold_rate={100.0 * metrics.hold_rate:.1f}% "
        f"range={metrics.min_depth_m:.2f}-{metrics.max_depth_m:.2f}m "
        f"mean_depth={metrics.mean_depth_m:.2f}m "
        f"mae={metrics.mae_m:.2f}m "
        f"rmse={metrics.rmse_m:.2f}m "
        f"bias={metrics.bias_m:+.2f}m "
        f"too_close={metrics.max_too_close_m:.2f}m "
        f"too_far={metrics.max_too_far_m:.2f}m "
        f"jitter={metrics.mean_abs_delta_m:.2f}m "
        f"samples={metrics.sample_count}/{metrics.message_count}"
    )
