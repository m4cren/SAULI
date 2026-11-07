"""Bounded SAULI ESP UART framing. Each frame is one UTF-8 JSON object."""

import json

VERSION = 1
MAX_FRAME = 4096
ALLOWED_TYPES = {"hello", "status", "ping", "pong", "telemetry", "command", "ack", "error"}


class FrameError(ValueError):
    pass


def encode_frame(message: dict) -> bytes:
    if message.get("v") != VERSION or message.get("type") not in ALLOWED_TYPES:
        raise FrameError("Unsupported protocol message")
    encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    if len(encoded) > MAX_FRAME:
        raise FrameError("Frame too long")
    return encoded


class FrameDecoder:
    def __init__(self):
        self.buffer = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[dict]:
        self.buffer.extend(data)
        result = []
        while b"\n" in self.buffer:
            index = self.buffer.index(10)
            line = bytes(self.buffer[:index]).strip()
            del self.buffer[:index + 1]
            if not line or len(line) > MAX_FRAME:
                self.dropped += 1
                continue
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.dropped += 1  # ESP boot chatter or malformed frame.
                continue
            if (not isinstance(value, dict) or value.get("v") != VERSION or
                    value.get("type") not in ALLOWED_TYPES):
                self.dropped += 1
                continue
            result.append(value)
        if len(self.buffer) > MAX_FRAME:
            self.buffer.clear()
            self.dropped += 1
        return result
