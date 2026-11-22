"""Observed door lifecycle after an authenticated held-solenoid command.

This tracks a reed contact, not the mechanical state of the lock or an item's
placement. A process restart intentionally forgets an unfinished workflow.
"""

import time
from dataclasses import dataclass


ACTIVE_PHASES = {"requested", "pulsing", "awaiting_open", "awaiting_close"}


@dataclass
class DoorWorkflow:
    open_timeout_seconds: float = 60.0
    close_timeout_seconds: float = 30.0
    open_timeout_policy: str = "continue_waiting"
    close_timeout_policy: str = "continue_waiting"
    command_id: str | None = None
    door: str | None = None
    phase: str = "idle"
    fault: str | None = None
    deadline: float = 0.0
    timeout_reported: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.open_timeout_seconds <= 300:
            raise ValueError("Door open timeout must be between 1 and 300 seconds")
        if not 5 <= self.close_timeout_seconds <= 600:
            raise ValueError("Door close timeout must be between 5 and 600 seconds")
        if self.open_timeout_policy not in {"continue_waiting", "abort"}:
            raise ValueError("Invalid door open timeout policy")
        if self.close_timeout_policy not in {"continue_waiting", "abort"}:
            raise ValueError("Invalid door close timeout policy")

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
        self.timeout_reported = False

    def pulsing(self) -> None:
        self.phase = "pulsing"

    def unlock_activated(self, now: float | None = None) -> None:
        # A reed may open immediately after activation. Keep that transition
        # instead of resetting the workflow to awaiting_open.
        if self.phase == "awaiting_close":
            return
        self.phase = "awaiting_open"
        self.deadline = (time.monotonic() if now is None else now) + self.open_timeout_seconds
        self.timeout_reported = False

    # Compatibility for older callers/tests while deployments roll together.
    pulse_finished = unlock_activated

    def fail(self, code: str) -> None:
        self.phase = "fault"
        self.fault = code
        self.deadline = 0.0

    def observe(self, observed: str, now: float | None = None) -> str | None:
        now = time.monotonic() if now is None else now
        if self.phase in {"pulsing", "awaiting_open"}:
            if observed == "open":
                self.phase = "awaiting_close"
                self.deadline = now + self.close_timeout_seconds
                self.timeout_reported = False
                return "workflow_door_opened"
            # The open timeout starts after the pulse ends. During the pulse
            # deadline is still zero, so a closed reed is expected.
            if (self.phase == "awaiting_open" and self.deadline > 0
                    and now >= self.deadline and not self.timeout_reported):
                self.timeout_reported = True
                if self.open_timeout_policy == "abort":
                    self.fail("door_open_timeout")
                else:
                    self.deadline = 0.0
                return "workflow_open_timeout"
        elif self.phase == "awaiting_close":
            if observed == "closed":
                self.phase = "completed"
                self.deadline = 0.0
                return "workflow_door_closed"
            if (self.deadline > 0 and now >= self.deadline
                    and not self.timeout_reported):
                self.timeout_reported = True
                if self.close_timeout_policy == "abort":
                    self.fail("door_close_timeout")
                else:
                    self.deadline = 0.0
                return "workflow_close_timeout"
        return None

    def snapshot(self) -> dict:
        return {"command_id": self.command_id, "door": self.door,
                "phase": self.phase, "fault": self.fault}
