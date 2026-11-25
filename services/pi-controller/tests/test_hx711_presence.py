"""HX711 migration regression tests: boot tare != empty, only workflow delta counts."""
import copy

import pytest

from sauli_pi.hx711_presence import HX711PresenceSession

CODES = [f"P-{x:02}" for x in range(1, 9)] + [f"M-{x:02}" for x in range(1, 5)]


def reading(initial=0.0, *, sequence=1):
    return {"type": "telemetry", "sensor_mode": "hx711", "seq": sequence,
            "slots": [{"code": code, "grams": initial, "ready": True,
                       "calibrated": True, "tare_ready": True,
                       "fault": "", "raw": 1000} for code in CODES]}


def update(telemetry, code, grams, seq):
    changed = copy.deepcopy(telemetry)
    changed["seq"] = seq
    next(s for s in changed["slots"] if s["code"] == code)["grams"] = grams
    return changed


def get(telemetry, code):
    return next(s for s in telemetry["slots"] if s["code"] == code)


def test_boot_tared_occupied_retrieval_is_negative_change():
    expected = {code: code == "P-01" for code in CODES}
    initial = reading()  # Already-occupied 120 g wallet is zero-tared after reboot
    session = HX711PresenceSession(expected, initial, boot_id="abc")
    assert session.overlay(copy.deepcopy(initial))["slots"][0]["present"] is True
    session.observe(update(initial, "P-01", -120, 2), "abc")
    assert session.slots["P-01"].present is True  # no single-frame false positive
    moved = update(initial, "P-01", -119, 3)
    session.observe(moved, "abc")
    assert get(session.overlay(moved), "P-01")["present"] is False
    assert get(session.overlay(moved), "P-01")["weight_change_g"] == -119


def test_placement_and_wrong_compartment_restoration():
    initial = reading()
    session = HX711PresenceSession({c: False for c in CODES}, initial, boot_id="boot")
    for seq in (2, 3):
        session.observe(update(initial, "P-03", 25, seq), "boot")
    assert session.slots["P-03"].present is True
    for seq in (4, 5):
        session.observe(update(initial, "P-03", 0.5, seq), "boot")
    assert session.slots["P-03"].present is False
    for seq in (6, 7):
        session.observe(update(initial, "P-02", 12, seq), "boot")
    assert session.slots["P-02"].present is True


def test_noise_and_stale_frames_do_not_generate_events():
    initial = reading()
    session = HX711PresenceSession({c: False for c in CODES}, initial, boot_id="boot")
    for seq, grams in ((2, 1), (3, 4), (4, 8), (5, 2), (6, 8), (7, 0)):
        session.observe(update(initial, "P-03", grams, seq), "boot")
    assert session.slots["P-03"].present is False
    moved = update(initial, "P-03", 10, 9)
    session.observe(moved, "boot")
    session.observe(moved, "boot")  # repeat same seq cannot count twice
    assert session.slots["P-03"].present is False
    session.observe(update(initial, "P-03", 11, 10), "boot")
    assert session.slots["P-03"].present is True


def test_reboot_during_workflow_fails_closed():
    initial = reading()
    session = HX711PresenceSession({c: False for c in CODES}, initial, boot_id="first")
    session.observe(update(initial, "P-01", 50, 2), "second")
    after = session.overlay(update(initial, "P-01", 51, 3))
    assert session.invalid
    assert all(s["present"] is None and s["ready"] is False for s in after["slots"])
    session.observe(update(initial, "P-01", 52, 4), "first")
    assert session.invalid


@pytest.mark.parametrize("change", ["uncalibrated", "unready", "no_tare", "missing_slot"])
def test_refuse_unsafe_baseline(change):
    t = reading()
    if change == "uncalibrated":
        t["slots"][0]["calibrated"] = False
    elif change == "unready":
        t["slots"][0]["ready"] = False
    elif change == "no_tare":
        t["slots"][0]["tare_ready"] = False
    else:
        t["slots"].pop()
    with pytest.raises(ValueError):
        HX711PresenceSession({c: False for c in CODES}, t, boot_id="abc")


def test_sensor_dropout_cannot_be_counted_as_removal():
    expected = {c: c == "P-04" for c in CODES}
    initial = reading()
    session = HX711PresenceSession(expected, initial, boot_id="first")
    invalid = update(initial, "P-04", -80, 2)
    get(invalid, "P-04")["ready"] = False
    get(invalid, "P-04")["fault"] = "not_ready"
    session.observe(invalid, "first")
    assert session.slots["P-04"].present is True
    assert get(session.overlay(invalid), "P-04")["present"] is None


def test_pi_direct_workflow_hx711_wrong_compartment_buzzer_and_completion(tmp_path):
    """Exercise the existing Pi buzzer/warning/completion, not only the detector."""
    import asyncio
    from uuid import uuid4

    from test_direct_commands import make_service, command, set_door

    async def run():
        device_id = str(uuid4())
        service, _settings = make_service(tmp_path, device_id)
        async def noop(_message):
            return None
        service.esp.send = noop
        payload = command(device_id, "pocket", "retrieval")
        t = reading()
        service.esp.boot_id = "hx-test"
        service.esp.last_telemetry = t
        # HX711 never advertises absolute occupancy after tare.
        for row in t["slots"]:
            row["present"] = None
        service._validate_direct_unlock(payload, "pocket")
        service._start_local_operation(payload, {"workflow_id": str(uuid4())})
        service.door_workflow.start(payload["id"], "pocket", "closed")
        service.door_workflow.pulsing()
        service.door_workflow.unlock_activated()
        set_door(service, "pocket", "open")
        # P-03 is occupied too, so lifting it is an unauthorized decrease.
        # Expected slots must be reflected before the operation starts.
        assert service._local_operation["assigned_slot"] == "P-01"
        assert service._hx_session is not None
        assert service._local_present["P-01"] is True
        for seq in (2, 3):
            t = update(t, "P-01", -120, seq)
            await service._observe_local_telemetry(t)
        assert service._local_provisional
        assert service._local_present["P-01"] is False
        # Simulate unauthorized placement in an EMPTY alternative slot.
        for seq in (4, 5):
            t = update(t, "P-03", 40, seq)
            await service._observe_local_telemetry(t)
        assert service._local_violations["P-03"] == "wrong_placement"
        assert service.gpio.outputs["buzzer"] is True
        # Return the unauthorized item; warning must clear.
        for seq in (6, 7):
            t = update(t, "P-03", 0, seq)
            await service._observe_local_telemetry(t)
        assert "P-03" not in service._local_violations
        assert service.gpio.outputs["buzzer"] is False
        set_door(service, "pocket", "closed")
        final = update(t, "P-01", -120, 8)
        await service._observe_local_telemetry(final)
        evidence, error = service._local_completion_evidence(final)
        assert error is None
        assert evidence["verified"] is True
        assert evidence["sensor_source"] == "esp32_hx711"
        assert evidence["observed_slots"]["P-01"] is False
    asyncio.run(run())


def test_per_slot_detection_threshold_without_changing_switch_state():
    initial = reading()
    session = HX711PresenceSession(
        {c: False for c in CODES}, initial, boot_id="test",
        threshold_g=5, restore_g=1, slot_thresholds_g={"P-02": 2.0})
    for seq in (2, 3):
        sample = update(initial, "P-02", 3.0, seq)
        session.observe(sample, "test")
    assert session.slots["P-02"].present
    assert not session.slots["P-03"].present
    for seq in (4, 5):
        sample = update(initial, "P-02", 0.2, seq)
        session.observe(sample, "test")
    assert not session.slots["P-02"].present


def test_wrong_item_lift_and_return_is_detectable_after_boot_tare():
    expected = {code: code in ("P-01", "P-02") for code in CODES}
    initial = reading()  # Both stored items were zero-tared at boot
    session = HX711PresenceSession(expected, initial, boot_id="rebooted")
    for seq in (2, 3):
        session.observe(update(initial, "P-02", -38, seq), "rebooted")
    assert session.slots["P-02"].present is False
    assert session.slots["P-01"].present is True
    for seq in (4, 5):
        session.observe(update(initial, "P-02", 0.3, seq), "rebooted")
    assert session.slots["P-02"].present is True
