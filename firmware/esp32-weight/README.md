# SAULI ESP32-S3 weight controller

One ESP32-S3 reads the 12 HX711 DOUT pins with a **single shared GPIO47 clock**. `src/main.cpp` lists every DOUT pin and slot. The Arduino/PlatformIO target is an ESP32-S3 N16R8 (16 MB flash, 8 MB octal PSRAM); confirm the board markings and USB port before flashing.

```bash
python3 -m pip install --user platformio
cd firmware/esp32-weight
python3 -m platformio run
python3 -m platformio device list
python3 -m platformio run -t upload --upload-port /dev/ttyACM0
python3 -m platformio device monitor --port /dev/ttyACM0 --baud 115200
```

Change the port to the one actually listed. Native USB CDC is for human debug. `Serial1` is the Pi protocol at 115200 8N1: ESP RX GPIO44 receives Pi BCM14 TX; ESP TX GPIO43 sends to Pi BCM15 RX. Share ground and use 3.3 V TTL.

UART frames are newline-delimited JSON, version `v:1`, max 4096 bytes. The ESP sends `hello` and 1-second `telemetry`; it answers `ping` with `pong` and `status` with telemetry. Pi-to-ESP `command` accepts `tare`, `calibrate`, lighting guidance, and `set_door_states`. The Pi refreshes both pocket and medium reed states every three seconds. Missing, unknown, or older-than-seven-second door state turns the affected compartment LEDs off. Calibration also needs `reference_grams` from a known test weight. A duplicate ID is acknowledged without reapplying it. All sensor channels publish signed 24-bit raw readings, readiness/fault, and grams/presence only after calibration. Missing sensors report `not_ready`; a fault does not count as a removal. The last eight command IDs are retained in RAM only, so **do not replay commands after reboot**. The Pi does not currently forward remote calibration commands.

Compartment LEDs are driven only through the SN74HC595 chain (DATA GPIO1, CLOCK GPIO2, LATCH GPIO21) and AO3400A low-side MOSFETs, with LED positive connected directly to 5 V. The fixed mapping is bits 0-7 for P-01..P-08 and bits 9-12 for M-01..M-04; bits 8 and 13-15 are always zero. A closed pocket reed masks bits 0-7, a closed medium reed masks bits 9-12, and each bank is independent. Closing or losing a reed state also discards that bank's cached modes, so reopening cannot resurrect an old command. The removed AO4407A + 2N2222 bank gates were Raspberry Pi BCM16/20 outputs, not ESP32 pins; the Pi service no longer claims them and leaves them high-impedance. No physical polarity or installed hardware behavior has been verified by repository tests.

The opt-in HX711 reader waits for **all enabled channels** to signal ready before one shared 25-pulse train (24 data bits plus channel A gain 128). It keeps clock LOW between reads. If any enabled module is absent or unready, the group pauses and eventually reports `not_ready`. Inspect all raw/ready values during bench bring-up; validate load cells and shared clock before enabling a live door workflow. Do not trust item-change thresholds until each load cell has been mechanically tested and calibrated with a known weight.

## HX711 transition (opt-in; switch build remains the default)

**Do not reflash the working switch controller simply to inspect this change.**
The existing `esp32-s3-n16r8` build stays in switch mode. The dedicated
`esp32-s3-n16r8-hx711` build reads the actual load cells; use the `-bench`
variant for calibration over the **ESP USB CDC port only**, not Pi UART.

Wiring is unchanged: all 12 HX711 `PD_SCK/CLK` share ESP GPIO47. Each HX711
`DOUT/DT` uses its former switch input GPIO in this exact order:

| Slot | ESP DT GPIO | Slot | ESP DT GPIO |
| --- | ---: | --- | ---: |
| P-01 | 40 | P-07 | 5 |
| P-02 | 18 | P-08 | 9 |
| P-03 | 17 | M-01 | 14 |
| P-04 | 15 | M-02 | 13 |
| P-05 | 7 | M-03 | 12 |
| P-06 | 6 | M-04 | 11 |

### Hardware acquisition and boot tare

All enabled HX711 chips are clocked together in one 25-pulse cycle. The
firmware **waits until every enabled DOUT is LOW** before clocking, to avoid
corrupting an unready chip on the shared CLK net. If one chip is absent or
stuck unready, the group stops acquiring and reports `not_ready` (fail-closed).
**Do not enable single-channel acquisition against the connected 12-module
cabinet without isolating other modules on that shared CLK net.** To test just
one HX711 on a *separate bench setup*, temporarily override
`SAULI_HX711_ENABLED_MASK=0x0001` in an additional local build configuration;
this must not be used for a complete live cabinet.

On every HX711 boot, the ESP collects six readings with a sufficiently small
raw spread as the startup tare, including any item already present. It does
not save this tare in flash. Saved per-slot **counts per gram** calibration
factors survive reboot. The ESP then reports raw counts and **signed relative
grams**, not boolean occupancy. Zero after boot does **not** mean empty.

### Bench calibration (do not use during an authorized workflow)

Run `pio run -e esp32-s3-n16r8-hx711-bench -t upload --upload-port COM6`
(or your actual port) to flash the bench firmware. Later, use
`pio run -e esp32-s3-n16r8-hx711 -t upload --upload-port COM6` only after
bench calibration and complete testing. An ordinary `pio run` or upload with
no environment selection continues to use the original switch firmware.

All enabled sensors must be connected and ready (the default bench mask enables
all 12). For one-sensor bench bring-up, explicitly configure a one-channel
mask on an isolated breadboard, not on the complete shared-clock PCB. Open USB CDC
Serial Monitor at 115200 baud. After stable boot tare, send a line (newline
termination) containing one of the following:

```
STATUS
TARE P-01
CALIBRATE P-01 100
STATUS
```

Run `TARE P-01` with the unloaded platform stationary; then place a known
**100 g test mass** on that compartment and run `CALIBRATE P-01 100`.
The factor is stored in ESP Preferences `sauli-hx711` as `s0`..`s11`.
Repeat for every slot with a known mass; test lightweight items at the front,
center, and back **after** calibration. An unstable signal is a mechanical,
wiring or shared-clock problem—not something to fix by silently reducing the
threshold. To leave bench mode, flash the `-hx711` build (without `-bench`).

### Authorized-workflow change detection on the Pi

The Pi uses the 12 expected boolean occupancies from its existing authenticated
unlock grant; these are *not* derived from zero grams. Before unlocking the
door, it takes a new baseline for every calibrated, ready HX711 channel.
Only during that workflow, positive changes in an initially empty slot
indicate placement; negative changes in an initially occupied slot indicate
removal. Consecutive fresh, stable telemetry readings are required. A return
to the baseline restores the initial state. Existing warning, SOS lighting,
buzzer, reed and completion checks remain on the Pi. If the ESP reboots during
the workflow, the session invalidates instead of automatically retaring and
calling the transaction successful. An idle reboot is supported.

Hardware config keys (Pi's `/etc/sauli/hardware.json`):

```json
"hx711_change_threshold_g": 5.0,
"hx711_restore_threshold_g": 2.0,
"hx711_stable_telemetry_samples": 2,
"hx711_slot_thresholds_g": {}
```

These are **initial testing defaults**, not proven thresholds for the actual
platform. Measure the worst-case light-item signal and idle noise and tune
per installation before real use. They do not change the existing switch mode.
Disable `sensor_simulation_enabled` for real sensor testing.

`/hardware-debug` shows signed grams relative to startup tare, raw counts,
DT GPIO, calibration/boot-tare state, and workflow weight change relative to
the Pi's pre-opening baseline. This public page remains **read only**. It
cannot tare sensors or command doors.

**Known constraints:** A failed/missing sensor blocks real HX711 door unlock.
One HX711 supporting one leg only may produce unreliable readings for objects
far from that leg. Sensor differences across positions and cross-compartment
mechanical forces need physical tests. Warning response time depends on UART
telemetry rate and required stable samples. Database records currently use the
legacy `esp32_switch` event-source label, even with HX711 evidence; migrate
that provenance only after verifying the physical flow and database schema.

When mechanical tests establish different sensitivities, use
`hx711_slot_thresholds_g` for individual overrides, for example
`{"P-01": 3.0}`. Each threshold must be greater than the restore threshold.
Do not lower thresholds until stationary noise and worst-case placement are
measured with the installed platform and fans running.
