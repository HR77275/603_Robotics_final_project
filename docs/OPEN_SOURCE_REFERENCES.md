# Open-Source References

This project is glue code around existing RoboMaster and ROS voice-control patterns.

## Robot Driver

- `jeguzzi/robomaster_ros` is the primary ROS 2 driver reference for DJI RoboMaster EP/S1.
  It provides ROS 2 launch files, camera topics, and standard `geometry_msgs/Twist`
  control through `/cmd_vel`.
  - Repo: https://github.com/jeguzzi/robomaster_ros
  - Docs: https://jeguzzi.github.io/robomaster_ros/

## Official DJI SDK

- `dji-sdk/RoboMaster-SDK` is the official DJI Python SDK and sample-code source for
  RoboMaster EP. We use it as the source of truth for SDK connection, camera stream,
  and vision examples.
  - Repo: https://github.com/dji-sdk/RoboMaster-SDK
  - Developer guide: https://robomaster-dev.readthedocs.io/

## Browser Voice-Control Pattern

- `UbiquityRobotics/speech_commands` shows the older but directly relevant browser
  pattern: click microphone, use Web Speech recognition, optional wake word, and
  command a robot through a ROS bridge.
  - Repo: https://github.com/UbiquityRobotics/speech_commands

## ROS 2 Voice-to-Motion Pattern

- `WakifRajin/ROS2-voice-assisted-bot` is a ROS 2 Humble example that maps spoken
  commands to robot movement through `/cmd_vel`.
  - Repo: https://github.com/WakifRajin/ROS2-voice-assisted-bot

## Modern Offline Speech Option

- `mgonzs13/whisper_ros` is a ROS 2 speech-to-text package based on Whisper-style
  transcription. It is a better future replacement for browser STT if offline voice
  recognition is required.
  - Repo: https://github.com/mgonzs13/whisper_ros

## Browser Audio Capture

- The current WSL web demo uses browser `MediaRecorder` to capture microphone
  audio, posts that audio to the local Python server, and transcribes it with
  OpenAI Whisper running locally in Ubuntu.
  - MediaRecorder docs: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder
  - Whisper repo: https://github.com/openai/whisper

## Speaker Identification Out Of Scope

The current demo does not perform speaker identification. It accepts normal
command phrases such as `follow me`, `stop`, and `come over`. Real speaker ID
would require raw audio capture plus a speaker-embedding model and enrollment
flow, so it is intentionally out of scope for the fast demo path.
