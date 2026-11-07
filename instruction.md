# SAULI hardware bring-up instructions

These steps deploy the repository to a Raspberry Pi 4 running Raspberry Pi OS Lite 64-bit, flash the single ESP32-S3 N16R8 board, and check the new diagnostics path. The Next.js app stays on Vercel and the central FastAPI app stays at its configured HTTPS origin. The Pi opens the deployed kiosk page through the existing browser service. No database reset is part of this procedure.

## 1. Update code and backend schema

Commit and push the tested changes from the development PC. On the Pi, use the existing clone if it already exists. Check for local edits before pulling:

```bash
cd /opt/sauli/SAULI
git status --short
git pull --ff-only origin main
```

For a fresh Pi, create a service user and clone once (skip these commands if SAULI is already installed):

```bash
id sauli || sudo useradd --create-home --shell /bin/bash sauli
sudo install -d -o sauli -g sauli /opt/sauli
sudo -u sauli git clone https://github.com/m4cren/SAULI.git /opt/sauli/SAULI
```

Apply `supabase/migrations/202611070001_sauli_hardware_diagnostics.sql` to the intended Supabase project, after prior migrations, using the SQL Editor or the established Supabase migration workflow. It adds device-scoped snapshots and one-time command claims. It does **not** wipe data. Verify `sauli_hardware_snapshots` and `sauli_hardware_commands` exist. Leave `HARDWARE_TEST_ENABLED=false` in the central FastAPI environment and restart that API so `/api/hardware/public` is available. Deploy the frontend revision to Vercel; the browser route is `/hardware-debug`. Keep the backend origin and device credential server-side.

## 2. Prepare Pi Python and test the reed contacts first

Install OS GPIO and serial support. Keep the existing Chromium/labwc kiosk setup and enrolled `/etc/sauli/controller.json` and credential file.

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-gpiozero python3-lgpio python3-serial
sudo install -d -o sauli -g sauli /opt/sauli/pi-controller
sudo -u sauli python3 -m venv --system-site-packages /opt/sauli/pi-controller/.venv
sudo -u sauli /opt/sauli/pi-controller/.venv/bin/python -m pip install -e /opt/sauli/SAULI/services/pi-controller
sudo usermod -aG dialout,gpio sauli
```

Log out and back in after adding groups. If `python3-lgpio` is unavailable on this OS image, install the package compatible with that Raspberry Pi OS release and confirm `python3 -c 'import lgpio, gpiozero'` works before starting the service. Do not assume a Python wheel tested on a PC can access Pi GPIO.

**First physical milestone, input only:** with 12 V disconnected and the hardware service stopped, check that BCM8 (physical pin 24) and BCM7 (physical pin 26) are not owned by SPI0 CE0/CE1 or another process. Check SPI configuration with `sudo raspi-config` and `lsmod | grep spi`; resolve an actual owner before claiming pins. Do not silently disable an SPI device. The medium reed contact uses BCM8, pocket uses BCM7. Connect each contact COM to a Pi GND such as physical pin 6; identify the correct other terminal by a continuity test. Never connect 5 V or 12 V to either GPIO.

```bash
sudo systemctl stop sauli-pi-hardware.service  # only if this service is already installed
cd /opt/sauli/SAULI/services/pi-controller
/opt/sauli/pi-controller/.venv/bin/python scripts/check_reeds.py
```

With the input unconnected, observe HIGH. Temporarily connect each input to GND and observe LOW, one at a time. Then test each magnet/contact. The script reports raw level and debounced changes and releases both pins on Ctrl+C. A busy-pin error means stop the owning service or resolve the SPI configuration; do not force GPIO ownership. Record whether the chosen contact reads LOW or HIGH when the door is actually closed. A closed reed contact does not prove a solenoid is locked.

## 3. Configure and start the Pi hardware service

In the existing `/etc/sauli/controller.json`, verify the backend and frontend HTTPS origins, unit/device codes, and absolute credential path. Do not re-enroll or overwrite that credential. Find the registered device UUID using the admin fleet page or a read-only `kiosk_devices` lookup, and put it in `/etc/sauli/hardware.json`.

```bash
sudo install -d -m 755 /etc/sauli
sudo cp /opt/sauli/SAULI/services/pi-controller/hardware.example.json /etc/sauli/hardware.json
sudo nano /etc/sauli/hardware.json
```

Set `mode` to `real`, set the exact enrolled `device_id`, and set `reed_closed_level` from the input test. Leave `output_polarity_verified=false` and `enable_actuators=false`. In this state the service claims only the reed GPIO inputs; it does not claim or drive outputs. Verify the credential file is owned by the service user and has mode `0600`. Set the ESP port to `/dev/serial0` after UART is configured.

Use `sudo raspi-config`: Interface Options → Serial Port → disable the login shell on serial, enable the serial hardware, then reboot. Cross Pi BCM14 TX/physical 8 to ESP RX GPIO44, Pi BCM15 RX/physical 10 to ESP TX GPIO43, and GND to GND. Both sides use 3.3 V TTL at 115200 8N1, not RS-232 levels. Confirm the actual ESP board's pin labels and any USB-to-UART bridge connection before wiring. Do not connect the Pi UART to a 5 V signal.

```bash
sudo cp /opt/sauli/SAULI/services/pi-controller/sauli-pi-hardware.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sauli-pi-hardware.service
systemctl status sauli-pi-hardware.service
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/state
journalctl -u sauli-pi-hardware.service -n 100 --no-pager
```

The hardware service runs one worker on Pi loopback. Keep the existing browser service separately; do not run a second copy of the hardware service or use `uvicorn --reload` on the Pi. A health response with `ok:false` means inspect the journal and fix GPIO access before proceeding. The public Vercel page never connects to this loopback URL; the Pi sends telemetry outbound to FastAPI using its existing device credential.

## 4. Build and flash the ESP32-S3

On the development PC, install PlatformIO (CLI or VS Code extension) and plug the ESP32-S3 into its native USB port. Verify the board really is N16R8. From the repository:

```bash
cd firmware/esp32-weight
python3 -m platformio run
python3 -m platformio device list
python3 -m platformio run -t upload --upload-port /dev/ttyACM0
python3 -m platformio device monitor --port /dev/ttyACM0 --baud 115200
```

Replace `/dev/ttyACM0` with the port shown on that computer (`COMx` on Windows). The firmware uses native USB CDC for human debug and UART1 on GPIO44/GPIO43 for the Pi JSON protocol. Boot chatter is ignored by the Pi decoder. Check `/state` for ESP `hello`, live telemetry, and a fresh `pong` after crossing the UART wires.

On the Windows development PC, the equivalent flash commands are:

```powershell
cd firmware/esp32-weight
python -m platformio run
python -m platformio device list
python -m platformio run -t upload --upload-port COM5
python -m platformio device monitor --port COM5 --baud 115200
```

Replace `COM5` with the actual port shown by `device list`. Disconnect the Pi UART while using a USB-to-UART bridge on the same ESP pins, if the board's wiring would make the two drivers contend.

The 12 HX711 DOUT pin assignments are in `firmware/esp32-weight/src/main.cpp`; all modules share SCK GPIO47. Start with one powered 3.3 V module and a known test weight, then connect the remaining channels. `raw` may be available before calibration; grams and presence stay unknown until tare/calibration. The lights remain disabled because the raster schematic does not establish the 74HC595 Q-bit order or output polarity. Trace the source netlist or the actual board before changing `LIGHT_BITS`. Do not treat a simulated slot as a real load-cell reading.

## 5. Verify end to end, then decide on actuator tests

Check the Pi `/state` and public `/hardware-debug` live view. A real unit should show a recent backend snapshot, raw/interpreted reed states, ESP readiness, and all 12 slot codes P-01–P-08 and M-01–M-04. Pull the ESP UART briefly to confirm offline/stale status, then reconnect and confirm it recovers. The public page's Simulation tab is browser-local and never changes production occupancy or hardware.

Only after checking the MOSFET circuit, coil rating, output active levels, bank-gate polarity, emergency buttons, and mechanical door behavior should an attended test set `output_polarity_verified=true` and then `enable_actuators=true` in `/etc/sauli/hardware.json`. The pulse is bounded to at most 1 second. `HARDWARE_TEST_ENABLED` on the central backend is a separate admin-only gate and should stay false during normal use. The manual emergency buttons and continuously powered fans are hardware paths, not software-controlled GPIOs. Output command state is **not** proof of a physical lock or placement.

An authorized test pulse requires the selected door's debounced reed state to be **closed**. The Pi records the command, pulse activation and deactivation, then waits up to `door_open_timeout_seconds` for the selected reed to show **open** and up to `door_close_timeout_seconds` for it to show **closed** again. The public diagnostics page shows this workflow and any timeout fault. The API command acknowledgment `pulse_completed` means only that the electrical pulse ended; inspect the later door workflow for observed movement. Neither observation proves the lock latched or an item was placed or removed.

This milestone adds hardware telemetry and guarded test commands. The existing kiosk placement/retrieval screens still use their established database simulation actions; they do not automatically infer successful storage or retrieval from a load-cell reading. Do not claim live sensor-controlled retrieval until that workflow has been validated on the assembled cabinet.

## Pin reference

| Pi function | BCM | Physical pin |
| --- | ---: | ---: |
| Medium reed input | 8 | 24 |
| Pocket reed input | 7 | 26 |
| Main light MOSFET | 24 | 18 |
| Buzzer MOSFET | 17 | 11 |
| Medium solenoid MOSFET | 23 | 16 |
| Pocket solenoid MOSFET | 27 | 13 |
| Pocket light bank gate | 16 | 36 |
| Medium light bank gate | 20 | 38 |
| UART TX / RX | 14 / 15 | 8 / 10 |

ESP32-S3 DOUT: P-01=40, P-02=18, P-03=17, P-04=15, P-05=7, P-06=6, P-07=5, P-08=9, M-01=14, M-02=13, M-03=12, M-04=11. Shared HX711 SCK=47. Shift register DATA=1, CLOCK=2, LATCH=21. These are ESP GPIO numbers, not Pi BCM numbers.
