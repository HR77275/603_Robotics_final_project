# CS603 Final Project Agent Rules

These rules apply to this repository and to any agent working on the CS603 RoboMaster final project from this checkout.

## Mission Boundary

- Keep one active deliverable at a time. Park side quests in a handoff note under `/Users/soumikbhatta/Projects2.0/docs/` only when needed.
- This repo is the code and runbook home for the DJI RoboMaster EP final project.
- The written deliverable source of truth is the submitted D1/D2 Overleaf checkout. Use it only for project-scope evidence and do not copy private paper text into commits unless the user explicitly asks.
- Never print, commit, copy, or expose Overleaf remotes, tokens, credentials, `.env` files, private auth material, or private submission text beyond the minimum needed to justify work.

## Soumik-Owned Lane

- The submitted D2 workload assigns Soumik to voice commands using Whisper and object-triggered behaviors.
- The minimum defensible implementation is a ROS 2 voice-intent path that publishes command intent on `/voice_intent`.
- Expected command intents are `CMD_FOLLOW`, `CMD_STOP`, `CMD_APPROACH`, and `CMD_UNKNOWN` unless the report or integration code establishes a different contract.
- Object-trigger behavior must be either implemented against real perception topics or clearly marked as a stub/demo placeholder. Do not claim it is complete without a real run.

## Evidence-First Workflow

- Before changing behavior, read the local README and relevant source file. Read D1/D2 submission text when the change depends on project promises, ownership, or report claims.
- For urgent safety fixes, stop/control commands, or lab-unblocking diagnostics, act from live robot state and document the evidence afterward.
- Use `context-mode` to index or retrieve large local docs when they would otherwise bloat chat context.
- Use Context7 or official upstream docs for ROS 2, OpenCV, Whisper, Docker, or RoboMaster behavior when local docs are incomplete.
- From `/Users/soumikbhatta` or this course tree, run shell commands through `rtk proxy` unless a tool directly edits files or an urgent robot stop/control command must be sent immediately.
- No broad machine-wide scans. Scope searches to this repo, the CS603 course folder, the Docker container, or a named path.

## Robot Safety

- Do not command physical motion unless the user has powered the robot, confirmed the test area is clear, and asked for a motion test.
- Before robot launch, verify the current container name, ROS workspace path, network mode, robot IP, and emergency stop command from live state.
- Keep the chassis emergency stop command visible during motion tests:

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once
```

- For arm or gripper tests, also keep the relevant RoboMaster text-SDK stop/open/close command from the README visible before motion begins.
- Do not claim teleop, camera, arm, gripper, voice control, or object-trigger behavior works unless it was verified in the current run or explicitly labeled as prior evidence.

## Git Rules

- Work on a `feature/` or `fix/` branch unless the user explicitly asks otherwise.
- Read files before editing them. Use `apply_patch` for manual edits.
- Keep commits small, factual, and reviewable.
- Before every commit:
  - Run `git status --short --branch`.
  - Review `git diff --check` and the staged or unstaged diff.
  - Run the smallest relevant verification command for the change.
  - Run an adversarial code review (reviewer/checker pass) before committing.
  - Fix or explicitly document any reviewer finding before committing.
- Do not commit generated junk, secrets, large demo videos, build outputs, Docker layers, or Overleaf credentials.

## Verification Before Completion

- For ROS/package code, prefer `colcon build` and a direct `ros2 run` or `ros2 topic` smoke test when the environment is available.
- For Python-only nodes, at minimum run import/compile checks and any local tests.
- For docs-only changes, run `git diff --check` and inspect the rendered Markdown structure by reading the file back.
- Final status must say what was verified and what remains unverified.
