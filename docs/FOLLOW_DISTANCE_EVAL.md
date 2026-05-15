# Follow Distance Evaluation

Use this metric when testing whether the RoboMaster keeps a person in the
accepted `CMD_FOLLOW` distance band.

## Metric

Run 5 trials. Each trial records `/people/depth` for a fixed duration while the
FSM is in `FOLLOWING` or `FOLLOWING_AUTHORIZED`.

Primary score:

```text
hold_rate = samples with 1.4 <= depth_m <= 2.2 / valid depth samples
score_pct = 100 * hold_rate
```

Supporting metrics:

- `mae`: mean absolute distance error from 1.5 m.
- `rmse`: root mean squared distance error from 1.5 m.
- `bias`: signed mean error. Positive means the robot stayed too far away;
  negative means it stayed too close.
- `too_close`: worst distance below the accepted minimum.
- `too_far`: worst distance above the accepted maximum.
- `jitter`: mean absolute change between consecutive depth samples.
- `samples`: valid target samples over total `/people/depth` messages.

Default pass condition is mean hold rate >= 80% across the 5 trials.
The evaluator now also writes raw per-sample depths so future threshold changes
can be recomputed without rerunning the robot.

## Run

Start the robot driver and integration stack normally. Put the FSM into follow
mode:

```bash
ros2 param set /voice_intent_node stub_text "follow me"
```

Then run the evaluator:

```bash
cd ~/robomaster_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=23
export ROS_LOCALHOST_ONLY=0

ros2 run robomaster_follow_controller follow_distance_eval --ros-args \
  -p target_depth_m:=1.5 \
  -p min_depth_m:=1.4 \
  -p max_depth_m:=2.2 \
  -p trial_count:=5 \
  -p trial_duration_sec:=10.0 \
  -p settle_time_sec:=2.0 \
  -p output_csv:=/tmp/follow_distance_eval.csv \
  -p output_samples_csv:=/tmp/follow_distance_eval_samples.csv
```

For a specific tracked person:

```bash
ros2 run robomaster_follow_controller follow_distance_eval --ros-args \
  -p target_track_id:=3
```

If running without the behavior FSM, disable state gating:

```bash
ros2 run robomaster_follow_controller follow_distance_eval --ros-args \
  -p require_following_state:=false
```

## Recorded Results

Follow-distance evaluation runs should be stored under `docs/evaluations/`.
The May 14, 2026 trials are recorded in:

- `docs/evaluations/follow_distance_eval_2026-05-14.md`
- `docs/evaluations/follow_distance_eval_2026-05-14_trials.csv`
- `docs/evaluations/follow_distance_eval_2026-05-14_summary.csv`
