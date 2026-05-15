from __future__ import annotations

import csv
import math
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from robomaster_perception_msgs.msg import PeopleDepth, PersonDepth
from std_msgs.msg import String

from robomaster_follow_controller.follow_distance_metrics import (
    DistanceSample,
    DistanceTrialMetrics,
    compute_trial_metrics,
    format_trial_metrics,
    mean_finite,
)


STATE_FOLLOWING = "FOLLOWING"
STATE_FOLLOWING_AUTHORIZED = "FOLLOWING_AUTHORIZED"

PHASE_WAITING = "waiting"
PHASE_SETTLING = "settling"
PHASE_ACTIVE = "active"
PHASE_DONE = "done"


class FollowDistanceEvalNode(Node):
    def __init__(self) -> None:
        super().__init__("follow_distance_eval")

        self.declare_parameter("people_depth_topic", "/people/depth")
        self.declare_parameter("state_topic", "/behavior_state")
        self.declare_parameter("target_depth_m", 1.5)
        self.declare_parameter("tolerance_m", 0.15)
        self.declare_parameter("min_depth_m", 1.4)
        self.declare_parameter("max_depth_m", 2.2)
        self.declare_parameter("trial_count", 5)
        self.declare_parameter("trial_duration_sec", 10.0)
        self.declare_parameter("settle_time_sec", 2.0)
        self.declare_parameter("target_track_id", -1)
        self.declare_parameter("min_confidence", 0.0)
        self.declare_parameter("require_following_state", True)
        self.declare_parameter(
            "allowed_states",
            [STATE_FOLLOWING, STATE_FOLLOWING_AUTHORIZED],
        )
        self.declare_parameter("pass_hold_rate_pct", 80.0)
        self.declare_parameter("output_csv", "")
        self.declare_parameter("output_samples_csv", "")
        self.declare_parameter("auto_shutdown", True)

        self.behavior_state = ""
        self.phase = PHASE_WAITING
        self.trial_index = 1
        self.phase_until_s = 0.0
        self.trial_start_s = 0.0
        self.trial_samples: list[DistanceSample] = []
        self.trial_message_count = 0
        self.metrics: list[DistanceTrialMetrics] = []
        self.samples_by_trial: list[tuple[int, list[DistanceSample]]] = []

        people_depth_topic = str(self.get_parameter("people_depth_topic").value)
        state_topic = str(self.get_parameter("state_topic").value)
        self.create_subscription(PeopleDepth, people_depth_topic, self.depth_cb, 10)
        self.create_subscription(String, state_topic, self.state_cb, 10)
        self.create_timer(0.2, self.timer_cb)

        min_depth_m, max_depth_m = self.depth_range
        self.get_logger().info(
            "follow_distance_eval ready: "
            f"target={self.target_depth_m:.2f}m "
            f"range={min_depth_m:.2f}-{max_depth_m:.2f}m "
            f"trials={self.trial_count} "
            f"duration={self.trial_duration_sec:.1f}s "
            f"depth_topic={people_depth_topic}"
        )

    @property
    def target_depth_m(self) -> float:
        return float(self.get_parameter("target_depth_m").value)

    @property
    def tolerance_m(self) -> float:
        return float(self.get_parameter("tolerance_m").value)

    @property
    def min_depth_m(self) -> float:
        return float(self.get_parameter("min_depth_m").value)

    @property
    def max_depth_m(self) -> float:
        return float(self.get_parameter("max_depth_m").value)

    @property
    def depth_range(self) -> tuple[float, float]:
        min_depth_m = self.min_depth_m
        max_depth_m = self.max_depth_m
        if min_depth_m > max_depth_m:
            return max_depth_m, min_depth_m
        return min_depth_m, max_depth_m

    @property
    def trial_count(self) -> int:
        return max(1, int(self.get_parameter("trial_count").value))

    @property
    def trial_duration_sec(self) -> float:
        return max(0.1, float(self.get_parameter("trial_duration_sec").value))

    @property
    def settle_time_sec(self) -> float:
        return max(0.0, float(self.get_parameter("settle_time_sec").value))

    def state_cb(self, msg: String) -> None:
        self.behavior_state = (msg.data or "").strip()

    def recording_allowed(self) -> bool:
        if not bool(self.get_parameter("require_following_state").value):
            return True

        allowed_states = {
            str(state).strip()
            for state in self.get_parameter("allowed_states").value
        }
        return self.behavior_state in allowed_states

    def depth_cb(self, msg: PeopleDepth) -> None:
        if self.phase == PHASE_DONE or not self.recording_allowed():
            return

        if self.phase == PHASE_WAITING:
            self.start_settle()

        if self.phase != PHASE_ACTIVE:
            return

        self.trial_message_count += 1
        target = self.select_target(msg)
        if target is None:
            return

        now_s = time.monotonic()
        self.trial_samples.append(
            DistanceSample(
                time_s=now_s - self.trial_start_s,
                depth_m=float(target.depth_m),
                track_id=int(target.track_id),
            )
        )

    def select_target(self, msg: PeopleDepth) -> PersonDepth | None:
        min_confidence = float(self.get_parameter("min_confidence").value)
        valid_people = [
            person for person in msg.people
            if math.isfinite(float(person.depth_m))
            and float(person.depth_m) > 0.0
            and float(person.confidence) >= min_confidence
        ]
        if not valid_people:
            return None

        target_track_id = int(self.get_parameter("target_track_id").value)
        if target_track_id >= 0:
            matches = [
                person for person in valid_people
                if int(person.track_id) == target_track_id
            ]
            return matches[0] if matches else None

        return min(valid_people, key=lambda person: float(person.depth_m))

    def timer_cb(self) -> None:
        now_s = time.monotonic()
        if self.phase == PHASE_DONE:
            return

        if self.phase == PHASE_SETTLING and now_s >= self.phase_until_s:
            self.start_trial(now_s)
            return

        if self.phase == PHASE_ACTIVE:
            elapsed_s = now_s - self.trial_start_s
            if elapsed_s >= self.trial_duration_sec:
                self.finish_trial()

    def start_settle(self) -> None:
        if self.settle_time_sec <= 0.0:
            self.start_trial(time.monotonic())
            return

        self.phase = PHASE_SETTLING
        self.phase_until_s = time.monotonic() + self.settle_time_sec
        self.get_logger().info(
            f"trial {self.trial_index}/{self.trial_count}: "
            f"settling for {self.settle_time_sec:.1f}s"
        )

    def start_trial(self, now_s: float) -> None:
        self.phase = PHASE_ACTIVE
        self.trial_start_s = now_s
        self.trial_samples = []
        self.trial_message_count = 0
        self.get_logger().info(
            f"trial {self.trial_index}/{self.trial_count}: recording"
        )

    def finish_trial(self) -> None:
        min_depth_m, max_depth_m = self.depth_range
        metrics = compute_trial_metrics(
            trial_index=self.trial_index,
            samples=self.trial_samples,
            target_depth_m=self.target_depth_m,
            tolerance_m=self.tolerance_m,
            min_depth_m=min_depth_m,
            max_depth_m=max_depth_m,
            duration_s=self.trial_duration_sec,
            message_count=self.trial_message_count,
        )
        self.metrics.append(metrics)
        self.samples_by_trial.append((self.trial_index, list(self.trial_samples)))
        self.get_logger().info(format_trial_metrics(metrics))

        if self.trial_index >= self.trial_count:
            self.finish_evaluation()
            return

        self.trial_index += 1
        self.start_settle()

    def finish_evaluation(self) -> None:
        self.phase = PHASE_DONE
        self.write_csv()
        self.write_samples_csv()
        self.log_summary()
        if bool(self.get_parameter("auto_shutdown").value):
            rclpy.shutdown()

    def write_csv(self) -> None:
        output_csv = str(self.get_parameter("output_csv").value).strip()
        if not output_csv:
            return

        path = Path(output_csv).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(DistanceTrialMetrics.__dataclass_fields__),
            )
            writer.writeheader()
            for metrics in self.metrics:
                writer.writerow(metrics.__dict__)
        self.get_logger().info(f"wrote follow distance metrics to {path}")

    def samples_csv_path(self) -> Path | None:
        output_samples_csv = str(
            self.get_parameter("output_samples_csv").value
        ).strip()
        if output_samples_csv:
            return Path(output_samples_csv).expanduser()

        output_csv = str(self.get_parameter("output_csv").value).strip()
        if not output_csv:
            return None

        metrics_path = Path(output_csv).expanduser()
        return metrics_path.with_name(f"{metrics_path.stem}_samples{metrics_path.suffix}")

    def write_samples_csv(self) -> None:
        path = self.samples_csv_path()
        if path is None:
            return

        min_depth_m, max_depth_m = self.depth_range
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "trial_index",
                    "sample_index",
                    "time_s",
                    "track_id",
                    "depth_m",
                    "target_depth_m",
                    "min_depth_m",
                    "max_depth_m",
                    "error_m",
                    "in_range",
                ],
            )
            writer.writeheader()
            for trial_index, samples in self.samples_by_trial:
                for sample_index, sample in enumerate(samples, start=1):
                    depth_m = float(sample.depth_m)
                    writer.writerow(
                        {
                            "trial_index": trial_index,
                            "sample_index": sample_index,
                            "time_s": f"{sample.time_s:.3f}",
                            "track_id": int(sample.track_id),
                            "depth_m": f"{depth_m:.3f}",
                            "target_depth_m": f"{self.target_depth_m:.3f}",
                            "min_depth_m": f"{min_depth_m:.3f}",
                            "max_depth_m": f"{max_depth_m:.3f}",
                            "error_m": f"{depth_m - self.target_depth_m:.3f}",
                            "in_range": min_depth_m <= depth_m <= max_depth_m,
                        }
                    )
        self.get_logger().info(f"wrote follow distance samples to {path}")

    def log_summary(self) -> None:
        min_depth_m, max_depth_m = self.depth_range
        mean_score = mean_finite([metrics.score_pct for metrics in self.metrics])
        mean_hold_rate = mean_finite(
            [100.0 * metrics.hold_rate for metrics in self.metrics]
        )
        mean_mae = mean_finite([metrics.mae_m for metrics in self.metrics])
        mean_rmse = mean_finite([metrics.rmse_m for metrics in self.metrics])
        mean_bias = mean_finite([metrics.bias_m for metrics in self.metrics])
        mean_jitter = mean_finite(
            [metrics.mean_abs_delta_m for metrics in self.metrics]
        )
        worst_score = min(
            [metrics.score_pct for metrics in self.metrics],
            default=float("nan"),
        )
        pass_hold_rate = float(self.get_parameter("pass_hold_rate_pct").value)
        passed = math.isfinite(mean_hold_rate) and mean_hold_rate >= pass_hold_rate

        self.get_logger().info(
            "follow distance evaluation summary: "
            f"target={self.target_depth_m:.2f}m "
            f"range={min_depth_m:.2f}-{max_depth_m:.2f}m "
            f"mean_score={mean_score:.1f}% "
            f"mean_hold_rate={mean_hold_rate:.1f}% "
            f"mean_mae={mean_mae:.2f}m "
            f"mean_rmse={mean_rmse:.2f}m "
            f"mean_bias={mean_bias:+.2f}m "
            f"mean_jitter={mean_jitter:.2f}m "
            f"worst_trial_score={worst_score:.1f}% "
            f"result={'PASS' if passed else 'FAIL'}"
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FollowDistanceEvalNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
