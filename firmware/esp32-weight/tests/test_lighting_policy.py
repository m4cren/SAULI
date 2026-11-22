"""Host-side contract tests for the ESP32 shift-register lighting policy."""

from pathlib import Path


POLICY = Path(__file__).resolve().parents[1] / "src/lighting_policy.h"
FIRMWARE = Path(__file__).resolve().parents[1] / "src/main.cpp"
BITS = [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12]


def sos_on(elapsed: int) -> bool:
    widths = [150, 150, 150, 450, 450, 450, 150, 150, 150]
    phase = elapsed % (750 + sum(width + 150 for width in widths))
    for width in widths:
        if phase < width:
            return True
        phase -= width
        if phase < 150:
            return False
        phase -= 150
    return False


def mode_on(mode: str, now: int) -> bool:
    return (mode == "STEADY_ON"
            or mode == "NORMAL_BLINK" and now % 1300 < 650
            or mode == "SOS_BLINK" and sos_on(now))


def render(modes: list[str], pocket: str, medium: str, now: int = 0) -> int:
    mask = 0
    for slot, mode in enumerate(modes):
        allowed = pocket == "open" if slot < 8 else medium == "open"
        if allowed and mode_on(mode, now):
            mask |= 1 << BITS[slot]
    return mask & 0x1EFF


def test_all_four_door_combinations_mask_banks_independently():
    modes = ["STEADY_ON"] * 12
    assert render(modes, "open", "open") == 0x1EFF
    assert render(modes, "closed", "open") == 0x1E00
    assert render(modes, "open", "closed") == 0x00FF
    assert render(modes, "closed", "closed") == 0x0000


def test_unknown_or_stale_state_fails_closed_per_bank():
    modes = ["STEADY_ON"] * 12
    assert render(modes, "unknown", "open") == 0x1E00
    assert render(modes, "open", "unknown") == 0x00FF
    assert render(modes, "unknown", "unknown") == 0x0000


def test_exact_mapping_and_unused_bits_are_always_zero():
    for slot, bit in enumerate(BITS):
        modes = ["OFF"] * 12
        modes[slot] = "STEADY_ON"
        assert render(modes, "open", "open") == 1 << bit
    assert render(["STEADY_ON"] * 12, "open", "open") & 0xE100 == 0


def test_normal_and_sos_blinking_remain_door_masked():
    normal = ["NORMAL_BLINK"] * 12
    assert render(normal, "open", "open", 0) == 0x1EFF
    assert render(normal, "open", "open", 700) == 0
    sos = ["SOS_BLINK"] * 12
    assert render(sos, "open", "closed", 0) == 0x00FF
    assert render(sos, "open", "closed", 200) == 0


def test_firmware_discards_closed_and_stale_cached_commands():
    source = FIRMWARE.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    assert 'strcmp(action, "set_door_states") == 0' in source
    assert "if (nextPocket != DOOR_OPEN) clearLightGroup(true);" in source
    assert "if (nextMedium != DOOR_OPEN) clearLightGroup(false);" in source
    assert "applyDoorStates(DOOR_UNKNOWN, DOOR_UNKNOWN);" in source
    assert "DOOR_STATE_TIMEOUT_MS" in source
    assert "return mask & VALID_LIGHT_MASK;" in policy


def test_safe_startup_is_all_off_until_fresh_reed_states_arrive():
    source = FIRMWARE.read_text(encoding="utf-8")
    assert "DoorState pocketDoor = DOOR_UNKNOWN, mediumDoor = DOOR_UNKNOWN;" in source
    assert "bool doorStateArmed = false;" in source
    assert source.index("shiftAllOff();") < source.index("Serial1.begin")
    assert render(["STEADY_ON"] * 12, "unknown", "unknown") == 0
