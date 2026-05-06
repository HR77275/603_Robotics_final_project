"""Small spoken acknowledgements for the CS603 voice demo."""

from __future__ import annotations


INTENT_SPEECH = {
    "CMD_FOLLOW": "Following.",
    "CMD_STOP": "Stopped.",
    "CMD_APPROACH": "Approaching.",
    "CMD_UNKNOWN": "I did not understand.",
}

STATE_SPEECH = {
    "IDLE": "Ready.",
    "FOLLOWING": "Following.",
    "STOPPED": "Stopped.",
    "APPROACHING": "Approaching.",
}


def speech_for_intent(intent: str) -> str:
    """Return the browser/ROS ACK text for an intent code."""

    normalized = (intent or "").strip()
    return INTENT_SPEECH.get(normalized, "I did not understand.")


def speech_for_state(state: str) -> str:
    """Return the browser/ROS ACK text for a behavior state."""

    normalized = (state or "").strip()
    return STATE_SPEECH.get(normalized, "")
