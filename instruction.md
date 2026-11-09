# SAULI hardware installation and verification

This guide uses the existing Raspberry Pi 4 checkout at `/home/sauli/sauli`, one ESP32-S3 N16R8, and the 12-position cabinet (P-01–P-08, M-01–M-04). Next.js stays on Vercel, FastAPI stays on its configured HTTPS host, and the Pi runs the kiosk browser and hardware controller. This guide does not reset a database.

## 1. Deploy the compatible application and schema

Commit and push the tested revision on the development PC. Apply pending migrations in order to the intended Supabase project, including `supabase/migrations/202611070001_sauli_hardware_diagnostics.sql`, then `supabase/migrations/202611090001_sauli_hardware_presence.sql`. The latter adds presence, event, incident, and lighting guidance records; it does not clear item records or registered kiosks. Restart FastAPI and deploy the corresponding frontend revision to Vercel. Keep `HARDWARE_TEST_ENABLED=false` for normal operation; it gates separate admin test pulses. The backend needs its existing Supabase service role configuration and kiosk/device authentication.

On the Pi, preserve any local edits shown by `git status` before pulling. Do not clone over the existing checkout.

```bash
ssh sauli@sauli-lspuspcc
cd /home/sauli/sauli
git status --short
git pull --ff-only origin main
ls firmware/esp32-weight services/pi-controller
```

## 2. Audit wiring before enabling outputs

These are **Pi BCM** assignments in the current controller. BCM24 main light and BCM17 buzzer are the requested targets. An older plan used BCM24 for the medium solenoid and BCM17 for the main light. The current map uses BCM23 for the medium solenoid and BCM27 for the pocket solenoid. Check the actual installed wires against this table; if a solenoid is still wired to BCM24, leave outputs disabled until the physical wiring or configuration is corrected. Never put two outputs on one GPIO.

| Pi function | BCM | Physical pin |
| --- | ---: | ---: |
| Main capture light MOSFET | 24 | 18 |
| Warning buzzer MOSFET | 17 | 11 |
| Medium solenoid MOSFET | 23 | 16 |
| Pocket solenoid MOSFET | 27 | 13 |
| Medium door reed input | 8 | 24 |
| Pocket door reed input | 7 | 26 |
| Pocket light bank gate | 16 | 36 |
| Medium light bank gate | 20 | 38 |
| UART TX / RX | 14 / 15 | 8 / 10 |
| OS power button | 3 | 5 |

Check BCM8/7 against SPI0 CE0/CE1 ownership. Reeds connect only to Pi GND and their respective inputs, never 5 V or 12 V. The power button connects BCM3 to GND and is active LOW. After checking its wiring and ensuring no other service owns BCM3, configure the Raspberry Pi OS `gpio-shutdown` overlay in that OS installation's boot config, for example `dtoverlay=gpio-shutdown,gpio_pin=3,active_low=1,gpio_pull=up`. Test graceful shutdown. Pi shutdown does not disconnect the external 12 V supply.

Wire each **ESP32** presence switch between 3.3 V and its GPIO. HIGH means an item is present only while the switch remains held; LOW means absent.

| Slot | ESP GPIO | Shift output | Bit |
| --- | ---: | --- | ---: |
| P-01 | 40 | IC1 B1 | 0 |
| P-02 | 18 | IC1 B2 | 1 |
| P-03 | 17 | IC1 B3 | 2 |
| P-04 | 15 | IC1 B4 | 3 |
| P-05 | 7 | IC1 B5 | 4 |
| P-06 | 6 | IC1 B6 | 5 |
| P-07 | 5 | IC1 B7 | 6 |
| P-08 | 9 | IC1 B8 | 7 |
| M-01 | 14 | IC2 B2 | 9 |
| M-02 | 13 | IC2 B3 | 10 |
| M-03 | 12 | IC2 B4 | 11 |
| M-04 | 11 | IC2 B5 | 12 |

Shift-register DATA=GPIO1, CLOCK=GPIO2, LATCH=GPIO21. IC1 QH' feeds IC2 SER; both share CLOCK and LATCH, run at 3.3 V, OE LOW, SRCLR HIGH. IC2 B1/bit 8 is unused. Check transistor polarity and output wiring with a meter before attaching lights. The main light, buzzer, solenoids, and fans require external power/driver circuits, not a direct GPIO load. The Pi/ESP UART is 3.3 V TTL, 115200 8N1: Pi TX BCM14 to ESP RX GPIO44, Pi RX BCM15 to ESP TX GPIO43, plus common GND.

## 3. Install and configure the Pi controller

Keep the existing `/etc/sauli/controller.json`, registered device, `/var/lib/sauli/credential`, and Chromium kiosk user service. Do not re-enroll a working kiosk. Use its registered device UUID in `/etc/sauli/hardware.json`.

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-gpiozero python3-lgpio python3-serial
mkdir -p /home/sauli/.venvs
python3 -m venv --system-site-packages /home/sauli/.venvs/sauli-pi-hardware
/home/sauli/.venvs/sauli-pi-hardware/bin/python -m pip install -e /home/sauli/sauli/services/pi-controller
sudo usermod -aG dialout,gpio sauli
sudo install -d -m 755 /etc/sauli
sudo cp /home/sauli/sauli/services/pi-controller/hardware.example.json /etc/sauli/hardware.json
sudo nano /etc/sauli/hardware.json
```

Log out and back in after changing groups. If the OS needs a different GPIO package, install its compatible package and verify `python3 -c 'import gpiozero, lgpio'`. Run `services/pi-controller/scripts/check_reeds.py` with the hardware service stopped to find each reed's actual closed level. Set `mode` to `real`, the registered `device_id`, both `reed_closed_level` values, and the ESP serial port. Keep `enable_actuators=false` and `output_polarity_verified=false` until every output pin, polarity, coil driver, emergency button, and door has been tested. Those defaults prevent GPIO output actuation. `controller.json` must reference the deployed frontend and backend HTTPS origins and the existing credential file.

In `sudo raspi-config`, disable the serial login shell and enable serial hardware, then reboot. Avoid another UART owner. Install and start one hardware controller:

```bash
sudo cp /home/sauli/sauli/services/pi-controller/sauli-pi-hardware.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sauli-pi-hardware.service
sudo systemctl status sauli-pi-hardware.service --no-pager
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/state
journalctl -u sauli-pi-hardware.service -n 100 --no-pager
```

The public frontend cannot connect to Pi loopback. The controller sends authenticated device telemetry and switch events to FastAPI. `/hardware-debug` live view is read-only; browser-local simulation does not actuate hardware. Do not run a second controller or use `uvicorn --reload` on the Pi.

## 4. Build and flash the ESP32-S3

Use PlatformIO on the development PC. Replace `COM5` with the detected port and confirm the board is N16R8 before flashing.

```powershell
cd firmware/esp32-weight
python -m platformio run
python -m platformio device list
python -m platformio run -t upload --upload-port COM5
python -m platformio device monitor --port COM5 --baud 115200
```

Firmware defaults to maintained switch mode. HX711 code remains available behind `SAULI_SENSOR_MODE_HX711`; do not initialize both sensor modes on shared pins. After boot the ESP sends 12 initial snapshots. Allow all 12 to reach the backend before testing transitions. It debounces HIGH/LOW changes, retains events until Pi ACK, and accepts `OFF`, `STEADY_ON`, `NORMAL_BLINK`, and `SOS_BLINK` LED guidance. A 15-second Pi guidance timeout clears all LEDs. A restart snapshot reconciles physical presence but is deliberately **not** proof of a new placement or removal; an interrupted transaction needs operator review.

The USB Serial Monitor prints boot, switch, debounced presence, UART acknowledgment, lighting mode, and output-mask diagnostics. `SAULI_VERBOSE_DIAGNOSTICS` defaults to `1`; add `-DSAULI_VERBOSE_DIAGNOSTICS=0` to the PlatformIO `build_flags` to turn verbose logging off without changing sensor or lighting behavior. The Pi UART remains separate from USB Serial Monitor.

## 5. Verify the workflow

First check Pi `/state` and `/hardware-debug` for a fresh heartbeat, ESP `hello`, all 12 switch states, and no GPIO faults. With outputs disabled, hold and release switches one at a time. Confirm the correct slot changes between present and absent. Test multiple switches and a Pi/ESP disconnect; stale/offline status must appear with no false placement or retrieval. Reconnect and wait for all snapshots.

For attended actuator testing, verify each output pin and polarity with a meter, emergency buttons, driver circuitry, and actual cabinet wiring. Only then set `output_polarity_verified=true` and `enable_actuators=true`, restart the controller, and test bounded door pulses and reed open/close feedback. Keep the separate `HARDWARE_TEST_ENABLED` admin gate false except during authorized manual pulse tests. The command ending does not prove a door opened or locked.

With a test item and empty assigned slot, capture and confirm two photos in `/kiosk`: main light should be on only during item photography and off during QR scanning or idle. The assigned slot should blink normally. Place the item in that slot; verify backend placement, occupied status, and steady light. On another run, put an item in a wrong available slot: the **assigned** slot should show SOS and the Pi buzzer should sound. Remove that item, confirm both warnings clear, then place it correctly. Test two wrong slots to ensure clearing one does not clear the other.

For retrieval, use an authorized one-time QR pass and check that the correct slot blinks normally. Remove an item from a different occupied slot: the **wrong** slot should show SOS, the correct slot should keep blinking, and the Pi buzzer should sound. Return it; verify the wrong slot resumes steady light and the buzzer stops. Then lift the authorized item and confirm one retrieval log, released slot, and light off. Switches indicate presence only; they cannot identify objects. Supervise these tests and reconcile contradictory switch/database states.

After a tested software update on the Pi:

```bash
cd /home/sauli/sauli
git status --short
git pull --ff-only origin main
/home/sauli/.venvs/sauli-pi-hardware/bin/python -m pip install -e /home/sauli/sauli/services/pi-controller
sudo systemctl restart sauli-pi-hardware.service
curl -fsS http://127.0.0.1:8765/state
journalctl -u sauli-pi-hardware.service -n 100 --no-pager
```

## Current hardware limits

Physical door-closed power cutoff for 5 V compartment lights is not implemented. An occupied slot remains steadily lit while powered. The power button is handled by the OS shutdown overlay, not a competing GPIO3 listener. A switch transition while both ESP and Pi are offline cannot be reconstructed from a baseline snapshot. HX711 calibration and weight-based confirmation remain future work. Verify the full flow on the assembled cabinet before relying on it unattended.
