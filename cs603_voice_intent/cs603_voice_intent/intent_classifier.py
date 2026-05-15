import re

CMD_APPROACH = "CMD_APPROACH"
CMD_DROP = "CMD_DROP"
CMD_FOLLOW = "CMD_FOLLOW"
CMD_FOLLOW_AUTHORIZED = "CMD_FOLLOW_AUTHORIZED"
CMD_PICK = "CMD_PICK"
CMD_STOP = "CMD_STOP"
CMD_UNKNOWN = "CMD_UNKNOWN"

_COMMAND_PATTERNS = (
    (
        CMD_STOP,
        (
            r"\bstop\b",
            r"\bhalt\b",
            r"\bfreeze\b",
            r"\bpause\b",
            r"\bwait\b",
            r"\bhold\b",
            r"\bstay\b",
            r"\bemergency\b",
            r"\bcancel\b",
            r"\bred light\b",
        ),
    ),
    (
        CMD_PICK,
        (
            r"\bpick\b",
            r"\bpick up\b",
            r"\bgrab\b",
            r"\bgrasp\b",
            r"\btake it\b",
            r"\bcollect\b",
        ),
    ),
    (
        CMD_DROP,
        (
            r"\bdrop\b",
            r"\bput down\b",
            r"\brelease\b",
            r"\blet go\b",
            r"\bplace it down\b",
        ),
    ),
    (
        CMD_APPROACH,
        (
            r"\bcome here\b",
            r"\bcome to me\b",
            r"\bcome over\b",
            r"\bcome closer\b",
            r"\bapproach\b",
            r"\bmove closer\b",
            r"\btowards me\b",
        ),
    ),
    (
        CMD_FOLLOW_AUTHORIZED,
        (
            r"\bfollow authorized\b",
            r"\bfollow authorised\b",
            r"\bfollow authorized person\b",
            r"\bfollow authorised person\b",
            r"\bfollow recognized\b",
            r"\bfollow recognised\b",
            r"\bfollow known\b",
            r"\bfollow approved\b",
            r"\bauthorized follow\b",
            r"\bauthorised follow\b",
        ),
    ),
    (
        CMD_FOLLOW,
        (
            r"\bfollow\b",
            r"\bfollow me\b",
            r"\bcome along\b",
            r"\bstart following\b",
            r"\btrack me\b",
            r"\bresume\b",
            r"\bgreen light\b",
            r"\bgo\b",
        ),
    ),
)


def normalize_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_intent(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return CMD_UNKNOWN

    for command, patterns in _COMMAND_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, normalized):
                return command

    return CMD_UNKNOWN
