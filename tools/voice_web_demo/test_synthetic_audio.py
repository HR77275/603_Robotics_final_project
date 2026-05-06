#!/usr/bin/env python3
"""Synthetic-audio round-trip test for the voice intent pipeline.

Uses macOS `say` to synthesize each phrase, runs the same Whisper CLI the
server uses, classifies the result, and prints a pass/fail table. No HTTP
server required, no human speech required.

Usage:
    python3 tools/voice_web_demo/test_synthetic_audio.py
    python3 tools/voice_web_demo/test_synthetic_audio.py --model base.en
    python3 tools/voice_web_demo/test_synthetic_audio.py --voice Samantha --rate 175
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = Path(__file__).parent
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(REPO_ROOT / "src" / "cs603_voice_intent"))

import server  # noqa: E402
from cs603_voice_intent.intent_classifier import classify_intent  # noqa: E402


@dataclass(frozen=True)
class Case:
    phrase: str
    expected_intent: str
    note: str = ""


CASES = (
    Case("follow me", "CMD_FOLLOW"),
    Case("stop", "CMD_STOP"),
    Case("halt", "CMD_STOP"),
    Case("come here", "CMD_APPROACH"),
    Case("approach me", "CMD_APPROACH"),
    Case("track me", "CMD_FOLLOW"),
    Case("freeze", "CMD_STOP"),
    Case("come along", "CMD_FOLLOW"),
    Case("hold on", "CMD_STOP"),
    Case("come over", "CMD_APPROACH"),
    Case("hey robot please stop right there", "CMD_STOP", "verbose phrase"),
    Case("robot please follow me down the hallway", "CMD_FOLLOW", "verbose phrase"),
)


def synthesize(text: str, out_path: str, voice: str, rate: int) -> None:
    """Use macOS `say` to write a WAV file. Errors out if `say` is unavailable."""
    cmd = [
        "say",
        text,
        "-v",
        voice,
        "-r",
        str(rate),
        "--data-format=LEF32@22050",
        "-o",
        out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"say failed for {text!r}: {proc.stderr.strip()}")


def run_pipeline(audio_path: str) -> tuple[str, str]:
    """Return (transcript, classified_intent) from whisper + classifier."""
    transcript = server.run_whisper(audio_path).strip()
    intent = classify_intent(transcript) if transcript else "CMD_UNKNOWN"
    return transcript, intent


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic audio test harness")
    parser.add_argument("--voice", default="Samantha", help="macOS say voice")
    parser.add_argument("--rate", type=int, default=175, help="words per minute")
    parser.add_argument(
        "--model",
        default=os.environ.get("CS603_WHISPER_MODEL", "base.en"),
        help="Whisper model (overrides CS603_WHISPER_MODEL env)",
    )
    parser.add_argument(
        "--whisper-bin",
        default=os.environ.get("CS603_WHISPER_BIN", "/opt/homebrew/bin/whisper"),
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep generated WAV files in /tmp/cs603_synth/",
    )
    args = parser.parse_args()

    os.environ["CS603_WHISPER_MODEL"] = args.model
    os.environ["CS603_WHISPER_BIN"] = args.whisper_bin
    server.WHISPER_MODEL = args.model
    server.WHISPER_BIN = args.whisper_bin

    if not os.path.exists(args.whisper_bin):
        print(f"FATAL: whisper binary not found at {args.whisper_bin}", file=sys.stderr)
        return 2
    if shutil.which("say") is None:
        print("FATAL: macOS `say` not found (this script is macOS-only)", file=sys.stderr)
        return 2

    work_dir = Path("/tmp/cs603_synth") if args.keep_audio else Path(tempfile.mkdtemp(prefix="cs603_synth_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"model={args.model} voice={args.voice} rate={args.rate} dir={work_dir}")
    print("-" * 88)
    print(f"{'phrase':40s} {'expected':14s} {'got':14s} {'transcript':30s} verdict")
    print("-" * 88)

    passes = 0
    fails = 0
    for case in CASES:
        slug = case.phrase.replace(" ", "_")[:30]
        wav_path = str(work_dir / f"{slug}.wav")
        try:
            synthesize(case.phrase, wav_path, args.voice, args.rate)
            transcript, intent = run_pipeline(wav_path)
        except Exception as exc:
            print(f"{case.phrase:40s} {case.expected_intent:14s} {'ERROR':14s} {str(exc)[:30]:30s} FAIL")
            fails += 1
            continue

        verdict = "OK" if intent == case.expected_intent else "FAIL"
        if verdict == "OK":
            passes += 1
        else:
            fails += 1
        transcript_short = transcript[:30].replace("\n", " ")
        print(f"{case.phrase:40s} {case.expected_intent:14s} {intent:14s} {transcript_short:30s} {verdict}")

    print("-" * 88)
    print(f"PASS={passes} FAIL={fails} TOTAL={len(CASES)}")

    if not args.keep_audio:
        shutil.rmtree(work_dir, ignore_errors=True)

    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
