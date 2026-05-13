import os
import queue
import sys
import tempfile
import threading
import wave

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from cs603_voice_intent.intent_classifier import classify_intent


class VoiceIntentNode(Node):
    """Publish classified voice commands as std_msgs/String on /voice_intent."""

    def __init__(self) -> None:
        super().__init__("voice_intent_node")
        self.declare_parameter("input_mode", "stdin")
        self.declare_parameter("topic", "/voice_intent")
        self.declare_parameter("stub_text", "")
        self.declare_parameter("publish_unknown", True)
        self.declare_parameter("poll_period_sec", 0.2)
        self.declare_parameter("exit_after_first_publish", False)
        self.declare_parameter("record_seconds", 3.0)
        self.declare_parameter("sample_rate", 16000)
        self.declare_parameter("whisper_model", "small")

        self.input_mode = self.get_parameter("input_mode").value
        topic = self.get_parameter("topic").value
        poll_period = float(self.get_parameter("poll_period_sec").value)
        self.publish_unknown = bool(self.get_parameter("publish_unknown").value)
        self.exit_after_first_publish = bool(self.get_parameter("exit_after_first_publish").value)
        self._published_once = False
        self._last_stub_text = ""
        self._fatal_error = False
        self._transcripts: queue.Queue[str] = queue.Queue()

        self.publisher = self.create_publisher(String, topic, 10)
        self.timer = self.create_timer(poll_period, self._on_timer)

        if self.input_mode == "stdin":
            thread = threading.Thread(target=self._read_stdin, daemon=True)
            thread.start()
            self.get_logger().info("stdin mode: type phrases like 'follow me', 'stop', or 'come here'.")
        elif self.input_mode == "param":
            self.get_logger().info("param mode: set stub_text or pass it at launch to publish a test intent.")
        elif self.input_mode == "mic_once":
            thread = threading.Thread(target=self._record_and_transcribe_once, daemon=True)
            thread.start()
            self.get_logger().info("mic_once mode: recording one microphone clip for Whisper transcription.")
        else:
            self.get_logger().error(f"Unsupported input_mode={self.input_mode!r}; use stdin, param, or mic_once.")

    def _read_stdin(self) -> None:
        while rclpy.ok():
            line = sys.stdin.readline()
            if line == "":
                self.get_logger().warn(
                    "stdin closed; for interactive text input run this node with ros2 run, "
                    "or use ros2 launch input_mode:=param and set stub_text."
                )
                return
            self._transcripts.put(line.strip())

    def _record_and_transcribe_once(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            import whisper
        except ImportError as exc:
            self.get_logger().error(f"mic_once requires numpy, sounddevice, and whisper: {exc}")
            self._fatal_error = True
            return

        seconds = float(self.get_parameter("record_seconds").value)
        sample_rate = int(self.get_parameter("sample_rate").value)
        model_name = self.get_parameter("whisper_model").value
        wav_path = ""

        try:
            self.get_logger().info(f"Recording {seconds:.1f}s at {sample_rate} Hz.")
            audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()
            audio_i16 = np.clip(audio[:, 0], -1.0, 1.0)
            audio_i16 = (audio_i16 * 32767.0).astype(np.int16)
            wav_path = self._write_wav(audio_i16, sample_rate)
            model = whisper.load_model(model_name)
            result = model.transcribe(wav_path)
            self._transcripts.put(str(result.get("text", "")).strip())
        except Exception as exc:  # noqa: BLE001 - surface demo-time hardware/audio failures.
            self.get_logger().error(f"mic_once transcription failed: {exc}")
            self._fatal_error = True
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)

    @staticmethod
    def _write_wav(audio_i16, sample_rate: int) -> str:
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_i16.tobytes())
        return path

    def _on_timer(self) -> None:
        if self.input_mode == "param":
            text = str(self.get_parameter("stub_text").value).strip()
            if text and text != self._last_stub_text:
                self._last_stub_text = text
                self._publish_transcript(text)

        while not self._transcripts.empty():
            self._publish_transcript(self._transcripts.get())

        if self.exit_after_first_publish and self._published_once:
            raise SystemExit(0)

        if self.input_mode == "mic_once" and self._fatal_error:
            raise SystemExit(1)

    def _publish_transcript(self, transcript: str) -> None:
        intent = classify_intent(transcript)
        if intent == "CMD_UNKNOWN" and not self.publish_unknown:
            self.get_logger().info(f"ignored unknown transcript={transcript!r}")
            return
        msg = String()
        msg.data = intent
        self.publisher.publish(msg)
        self._published_once = True
        self.get_logger().info(f"transcript={transcript!r} intent={intent}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceIntentNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
