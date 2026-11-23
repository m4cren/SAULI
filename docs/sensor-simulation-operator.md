# SAULI operator sensor simulation (temporary physical-cabinet demo)

This is **not** the old browser-only `simulate-placement` / `simulate-completion` flow.
The optional controls send authenticated instructions using the registered Next.js
kiosk session, through Windows FastAPI and its private Tailscale gateway,
to the Raspberry Pi hardware service. The Pi substitutes *logical slot
presence* into the existing security monitor and post-door-close verification.
It does **not** rewrite or flash ESP32 firmware, drive Pi GPIO, or directly call
a Supabase placement/retrieval RPC. The physical door reed, authorized unlock,
ESP connection, 12 ready sensor channels, actual door closure, fresh ESP
telemetry, warning resolution, solenoid deactivation, and backend reconciliation
are still required. Sensor *presence* is simulated, not physically measured.

This is a **temporary supervised demo**, with no separate operator password.
Anyone with access to the registered kiosk while all simulation flags are enabled
can use the controls. Do not use it for unattended public
storage, genuine ownership decisions, or claims of physical inventory accuracy.
The current SQL completion function still labels simulated completions
`esp32_switch` in database event provenance; the Pi journal and the durable
completion proof include `operator_simulation`. Do not treat database provenance
as evidence of real switch verification in this mode.

## Activation (three opt-in switches, all disabled by default)

1. **Pi** `/etc/sauli/hardware.json`: keep `"mode": "real"`,
   `"command_transport": "direct"`, and existing output configuration. Add
   `"sensor_simulation_enabled": true`. Do **not** set `mode` to `simulation`:
   that mode disables real actuator commands. Install/update the editable
   `services/pi-controller` package if needed and restart
   `sauli-pi-hardware.service`. This changes only *presence decisions* while an
   authorized workflow is active. Pi settings are never deployed to Vercel.
2. **Windows FastAPI backend** `.env`: set
   `HARDWARE_SENSOR_SIMULATION_ENABLED=true`. Remove any old
   `HARDWARE_SENSOR_SIMULATION_TOKEN` entry; it is no longer used. Keep the
   existing `HARDWARE_DIRECT_DEVICES` and private Tailscale endpoint.
   Restart the FastAPI backend.
3. **Vercel frontend**: set `NEXT_PUBLIC_SENSOR_SIMULATION_ENABLED=true`,
   redeploy the frontend, then refresh the kiosk browser. The API still requires
   the registered kiosk session; the Pi still verifies an authorized workflow,
   open door and safe compartment bank. There is no separate operator password.

The panel appears in the deposit placement and retrieval QR/item-location
screens. Open **Operator sensor simulation — TEST ONLY** and keep the real
authorized door open. The same panel is available
inside the wrong-compartment warning and correct-item provisional modal so
that you can test restoration or disturbances after a provisional success.

## Buttons

- **Simulate item placed / retrieved**: Toggle only the assigned virtual slot to
  the transaction's expected target state (present for deposit, absent for
  retrieval). The Pi will show provisional success; then **physically close
  the correct door**. Its reed and the following ESP telemetry must be valid
  before the normal finalization completes.
- **Undo assigned change**: Restore the assigned slot to its pre-operation
  logical presence while the door is still open.
- **Wrong placement / Wrong item lifted**: Choose another slot **in the same
  open compartment bank** and toggle its logical presence to simulate an
  incident. Deposit wrong placement requires an empty alternative slot;
  retrieval wrong lift requires a *previously occupied* alternative slot.
- **Restore**: Set the other slot back to its pre-operation state. The existing
  Pi warning, SOS lighting and buzzer policy should clear after the backend
  receives the resolved incident.

The panel refuses operations with a closed door, no active signed workflow,
wrong assigned slot, different workflow ID, different door bank, or a synced /
faulted workflow. No simulation buttons issue door-unlock commands or bypass the
existing signed unlock grant. All simulated actions are logged to `journalctl`.

## Disable after the demo

1. Set `sensor_simulation_enabled` to `false` on the Pi, restart the service.
2. Set `HARDWARE_SENSOR_SIMULATION_ENABLED=false` on Windows, restart FastAPI.
3. Remove or set `NEXT_PUBLIC_SENSOR_SIMULATION_ENABLED=false` on Vercel,
   redeploy and reload the kiosk.
4. Once the actual HX711/load-cell sensing is ready and independently verified,
   migrate only through a separate explicitly approved firmware change.

## Tests

From the repository root after installing Python project requirements:

```
PYTHONPATH=services/pi-controller/src pytest -q \
  services/pi-controller/tests/test_direct_commands.py \
  services/pi-controller/tests/test_hardware.py
```

On Windows PowerShell, use `$env:PYTHONPATH="services/pi-controller/src"` then
run `pytest -q services/pi-controller/tests`.

**Compatibility**: This patch is built against `SAULI-source(6).zip` (Nov 22,
2026). It does not include or revert earlier kiosk reducer or success-text
patches. Check with `git apply --check` before applying; do not reverse any
already deployed retrieval fix.
