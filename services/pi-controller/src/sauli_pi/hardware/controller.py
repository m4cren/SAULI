"""Single-owner, fail-closed Pi GPIO adapter. This does not claim a lock state."""

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PinMap:
    medium_reed: int = 8
    pocket_reed: int = 7
    main_light: int = 24
    buzzer: int = 17
    medium_solenoid: int = 23
    pocket_solenoid: int = 27
    pocket_light_gate: int = 16
    medium_light_gate: int = 20


class DoorInput:
    def __init__(self, closed_level: int, debounce_seconds: float = 0.05):
        if closed_level not in (0, 1):
            raise ValueError("closed_level must be 0 or 1")
        self.closed_level = closed_level
        self.debounce_seconds = debounce_seconds
        self.raw_level: int | None = None
        self.stable_level: int | None = None
        self.changed_at = 0.0

    def update(self, level: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if level != self.raw_level:
            self.raw_level = level
            self.changed_at = now
        if self.stable_level is None or now - self.changed_at >= self.debounce_seconds:
            self.stable_level = level

    def snapshot(self) -> dict:
        return {"raw_level": self.raw_level,
                "door": "unknown" if self.stable_level is None else
                "closed" if self.stable_level == self.closed_level else "open"}


class GPIOController:
    OUTPUTS = {
        "main_light": 24, "buzzer": 17, "medium_solenoid": 23,
        "pocket_solenoid": 27, "pocket_light_gate": 16, "medium_light_gate": 20,
    }
    INPUTS = {"medium": 8, "pocket": 7}

    def __init__(self, *, simulation: bool, closed_level: dict[str, int],
                 active_high: dict[str, bool], pulse_seconds: float = 0.35,
                 pin_factory=None, allow_outputs: bool = False):
        if not 0.05 <= pulse_seconds <= 1.0:
            raise ValueError("Solenoid pulse must be between 0.05 and 1 second")
        if set(closed_level) != set(self.INPUTS):
            raise ValueError("Both reed polarities must be configured")
        if set(active_high) != set(self.OUTPUTS):
            raise ValueError("All output polarities must be configured")
        self.simulation = simulation
        self.closed_level = closed_level
        self.active_high = active_high
        self.pulse_seconds = pulse_seconds
        self.pin_factory = pin_factory
        self.allow_outputs = allow_outputs
        self.doors = {name: DoorInput(closed_level[name]) for name in self.INPUTS}
        self.outputs = {name: False for name in self.OUTPUTS}
        self._inputs = {}
        self._outputs = {}
        self._pulse_lock = asyncio.Lock()

    def open(self) -> None:
        if self.simulation:
            for door in self.doors.values():
                door.update(1)
            return
        # Imported only when real hardware mode is explicitly selected.
        from gpiozero import DigitalInputDevice, DigitalOutputDevice
        try:
            for name, pin in self.INPUTS.items():
                self._inputs[name] = DigitalInputDevice(
                    pin, pull_up=True, bounce_time=0.05, pin_factory=self.pin_factory)
            if self.allow_outputs:
                for name, pin in self.OUTPUTS.items():
                    self._outputs[name] = DigitalOutputDevice(
                        pin, active_high=self.active_high[name], initial_value=False,
                        pin_factory=self.pin_factory)
            self.sample_inputs()
        except Exception:
            self.close()
            raise

    def sample_inputs(self) -> None:
        if self.simulation:
            return
        for name, device in self._inputs.items():
            self.doors[name].update(int(bool(device.pin.state)))

    def set_simulated_door(self, name: str, level: int) -> None:
        if not self.simulation or name not in self.doors or level not in (0, 1):
            raise ValueError("Simulation-only door change rejected")
        self.doors[name].update(level)

    def set_output(self, name: str, enabled: bool) -> None:
        if name not in self.OUTPUTS or name.endswith("solenoid"):
            raise ValueError("Output not allowlisted for steady state")
        if not self.simulation and not self.allow_outputs:
            raise ValueError("Output polarity has not been verified")
        if not self.simulation:
            device = self._outputs[name]
            device.on() if enabled else device.off()
        self.outputs[name] = enabled

    async def pulse(self, door: str) -> None:
        if door not in self.INPUTS:
            raise ValueError("Unknown door")
        if not self.simulation and not self.allow_outputs:
            raise ValueError("Output polarity has not been verified")
        name = f"{door}_solenoid"
        async with self._pulse_lock:
            try:
                if not self.simulation:
                    self._outputs[name].on()
                self.outputs[name] = True
                await asyncio.sleep(self.pulse_seconds)
            finally:
                if not self.simulation:
                    self._outputs[name].off()
                self.outputs[name] = False

    def snapshot(self) -> dict:
        return {"mode": "simulation" if self.simulation else "real",
                "doors": {name: door.snapshot() for name, door in self.doors.items()},
                "outputs": self.outputs.copy(),
                "lock_feedback": "unavailable"}

    def close(self) -> None:
        for name, device in self._outputs.items():
            device.off()
            self.outputs[name] = False
        for device in [*self._inputs.values(), *self._outputs.values()]:
            device.close()
        self._inputs.clear()
        self._outputs.clear()
