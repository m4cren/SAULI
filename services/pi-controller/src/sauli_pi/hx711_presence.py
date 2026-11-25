"""Workflow-scoped HX711 changes. Never infer occupancy from boot-tared zero.

This is intentionally independent of the switch path. ESP raw counts are used
only as a sensor-health check; calibrated signed grams are used for detection.
All state comes from a signed direct-unlock grant, and all twelve slots must be
ready before the door can be unlocked.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SlotChange:
    baseline: float
    expected: bool
    present: bool
    candidate: bool | None = None
    samples: int = 0
    delta: float = 0.0


class HX711PresenceSession:
    """Convert stable signed changes into the existing boolean presence contract."""

    def __init__(self, expected: dict[str, bool], telemetry: dict, *,
                 threshold_g: float = 5.0, restore_g: float = 2.0,
                 stable_samples: int = 2, boot_id: str,
                 slot_thresholds_g: dict[str, float] | None = None):
        self.boot_id = boot_id
        self.threshold_g = threshold_g
        self.slot_thresholds_g = slot_thresholds_g or {}
        self.restore_g = restore_g
        self.stable_samples = stable_samples
        self.last_seq: int | None = None
        self.invalid = False
        rows = telemetry.get("slots")
        if telemetry.get("sensor_mode") != "hx711" or not isinstance(rows, list):
            raise ValueError("hx711_mode_required")
        measurements = {row.get("code"): row for row in rows if isinstance(row, dict)}
        if set(measurements) != set(expected):
            raise ValueError("hx711_sensor_data_incomplete")
        self.slots: dict[str, SlotChange] = {}
        for code, present in expected.items():
            row = measurements[code]
            grams = row.get("grams")
            if (row.get("ready") is not True or row.get("calibrated") is not True
                    or row.get("tare_ready") is not True
                    or row.get("fault") not in (None, "")
                    or not self._valid_number(grams)):
                raise ValueError("hx711_sensor_not_ready")
            self.slots[code] = SlotChange(float(grams), present, present)

    @staticmethod
    def _valid_number(value: object) -> bool:
        return type(value) in (float, int) and math.isfinite(value)

    def observe(self, telemetry: dict, boot_id: str | None) -> None:
        if self.invalid:
            return
        if boot_id != self.boot_id or telemetry.get("sensor_mode") != "hx711":
            self.invalid = True
            return
        sequence = telemetry.get("seq")
        if type(sequence) is not int:
            self.invalid = True
            return
        if self.last_seq is not None and sequence <= self.last_seq:
            return
        self.last_seq = sequence
        rows = telemetry.get("slots")
        if not isinstance(rows, list):
            return
        measurements = {row.get("code"): row for row in rows if isinstance(row, dict)}
        for code, state in self.slots.items():
            row = measurements.get(code, {})
            grams = row.get("grams")
            if (row.get("ready") is not True or row.get("calibrated") is not True
                    or row.get("tare_ready") is not True
                    or row.get("fault") not in (None, "")
                    or not self._valid_number(grams)):
                state.candidate = None
                state.samples = 0
                continue
            state.delta = float(grams) - state.baseline
            # Positive change means placement, negative means removal.
            # A return near the original baseline explicitly restores state.
            if abs(state.delta) <= self.restore_g:
                desired = state.expected
            elif not state.expected and state.delta >= self.slot_thresholds_g.get(code, self.threshold_g):
                desired = True
            elif state.expected and state.delta <= -self.slot_thresholds_g.get(code, self.threshold_g):
                desired = False
            else:
                state.candidate = None
                state.samples = 0
                continue
            if desired == state.present:
                state.candidate = None
                state.samples = 0
            else:
                if state.candidate == desired:
                    state.samples += 1
                else:
                    state.candidate = desired
                    state.samples = 1
                if state.samples >= self.stable_samples:
                    state.present = desired
                    state.candidate = None
                    state.samples = 0

    def overlay(self, telemetry: dict) -> dict:
        """Decorate a copied telemetry frame; do not alter raw ESP data."""
        for row in telemetry.get("slots", []):
            state = self.slots.get(row.get("code"))
            if state is None:
                continue
            row["baseline_g"] = state.baseline
            if self.invalid:
                row.update(ready=False, present=None, fault="hx711_restarted")
                row["weight_change_g"] = None
                continue
            grams = row.get("grams")
            healthy = (row.get("ready") is True and row.get("calibrated") is True
                       and row.get("tare_ready") is True
                       and row.get("fault") in (None, "")
                       and self._valid_number(grams))
            row["weight_change_g"] = (round(float(grams) - state.baseline, 3)
                                      if healthy else None)
            row["present"] = state.present if healthy else None
        return telemetry
