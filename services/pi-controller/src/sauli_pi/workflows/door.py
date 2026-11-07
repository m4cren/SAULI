"""Observed door lifecycle after a bounded solenoid command.

This tracks a reed contact, not the mechanical state of the lock or an item's
placement. A process restart intentionally forgets an unfinished workflow.
"""

import time
from dataclasses import dataclass


ACTIVE_PHASES = {"requested", "pulsing", "awaiting_open", "awaiting_close"}


@dataclass
class DoorWorkflow:
    open_timeout_seconds: float = 5.0
    close_timeout_seconds: float = 30.0
    command_id: str | None = None
    door: str | None = None
    phase: str = "idle"
    fault: str | None = None
    deadline: float = 0.0

    def __post_init__(self) -> None:
        if not 1 <= self.open_timeout_seconds <= 10:
            raise ValueError("Door open timeout must be between 1 and 10 seconds")
        if not 5 <= self.close_timeout_seconds <= 120:
            raise ValueError("Door close timeout must be between 5 and 120 seconds")

    def start(self, command_id: str, door: str, observed: str) -> None:
        if self.phase in ACTIVE_PHASES:
            raise ValueError("door_workflow_busy")
        if observed != "closed":
            raise ValueError("door_not_closed")
        self.command_id = command_id
        self.door = door
        self.phase = "requested"
        self.fault = None
        self.deadline = 0.0

    def pulsing(self) -> None:
        self.phase = "pulsing"

    def pulse_finished(self, now: float | None = None) -> None:
        self.phase = "awaiting_open"
        self.deadline = (time.monotonic() if now is None else now) + self.open_timeout_seconds

    def fail(self, code: str) -> None:
        self.phase = "fault"
        self.fault = code
        self.deadline = 0.0

    def observe(self, observed: str, now: float | None = None) -> str | None:
        now = time.monotonic() if now is None else now
        if self.phase == "awaiting_open":
            if observed == "open":
                self.phase = "awaiting_close"
                self.deadline = now + self.close_timeout_seconds
                return "workflow_door_opened"
            if now >= self.deadline:
                self.fail("door_open_timeout")
                return "workflow_open_timeout"
        elif self.phase == "awaiting_close":
            if observed == "closed":
                self.phase = "completed"
                self.deadline = 0.0
                return "workflow_door_closed"
            if now >= self.deadline:
                self.fail("door_close_timeout")
                return "workflow_close_timeout"
        return None

    def snapshot(self) -> dict:
        return {"command_id": self.command_id, "door": self.door,
                "phase": self.phase, "fault": self.fault}
