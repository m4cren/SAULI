"""One owner for ESP UART reads/writes; no implicit simulation fallback."""

import asyncio
import time
from datetime import UTC, datetime
from .protocol import FrameDecoder, encode_frame


class EspLink:
    def __init__(self, port: str = "/dev/serial0", baud: int = 115200):
        self.port = port
        self.baud = baud
        self.serial = None
        self.decoder = FrameDecoder()
        self._write_lock = asyncio.Lock()
        self.last_seen = 0.0
        self.last_message: dict | None = None
        self.last_telemetry: dict | None = None
        self.last_telemetry_at = 0.0
        self.telemetry_at: str | None = None
        self.boot_id: str | None = None
        self.error: str | None = None

    def connect(self) -> None:
        import serial
        self.serial = serial.Serial(self.port, self.baud, timeout=0.25,
                                    write_timeout=0.25, rtscts=False, xonxoff=False)
        self.decoder = FrameDecoder()
        self.last_seen = 0.0
        self.last_message = None
        self.last_telemetry = None
        self.last_telemetry_at = 0.0
        self.telemetry_at = None
        self.boot_id = None
        self.error = None

    async def read(self) -> list[dict]:
        if self.serial is None:
            return []
        try:
            data = await asyncio.to_thread(self.serial.read, 512)
        except Exception:
            self.close()
            self.error = "serial_read_failed"
            return []
        messages = self.decoder.feed(data)
        for message in messages:
            self.last_seen = time.monotonic()
            self.last_message = message
            if message["type"] == "hello":
                next_boot = message.get("boot_id")
                if next_boot != self.boot_id:
                    self.last_telemetry = None
                    self.last_telemetry_at = 0.0
                    self.telemetry_at = None
                self.boot_id = next_boot
            if message["type"] == "telemetry":
                self.last_telemetry = message
                self.last_telemetry_at = self.last_seen
                self.telemetry_at = datetime.now(UTC).isoformat()
        return messages

    async def send(self, message: dict) -> None:
        if self.serial is None:
            raise ConnectionError("ESP not connected")
        payload = encode_frame(message)
        async with self._write_lock:
            try:
                await asyncio.to_thread(self.serial.write, payload)
            except Exception:
                self.close()
                self.error = "serial_write_failed"
                raise ConnectionError("ESP serial write failed") from None

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
            finally:
                self.serial = None

    def snapshot(self) -> dict:
        age = time.monotonic() - self.last_seen if self.last_seen else None
        telemetry_age = (time.monotonic() - self.last_telemetry_at
                         if self.last_telemetry_at else None)
        return {"connection": "offline" if self.serial is None else
                "stale" if age is None or age > 10 else "online",
                "last_seen_seconds_ago": round(age, 1) if age is not None else None,
                "frame_errors": self.decoder.dropped,
                "error": self.error,
                "boot_id": self.boot_id,
                "telemetry_at": self.telemetry_at if telemetry_age is not None and telemetry_age <= 5 else None,
                "telemetry": self.last_telemetry if self.serial is not None and
                telemetry_age is not None and telemetry_age <= 5 else None}
