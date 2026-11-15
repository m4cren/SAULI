# SAULI hardware integration checkpoint - 2026-11-15

## What the evidence shows

The supplied Raspberry Pi log shows ESP32 sensor and reed events, intermittent
backend 503 responses, and later backend recovery. During the reported failed
unlock, the Pi reported `last_unlock: null` and an idle door workflow. No
authenticated unlock command or GPIO27 pulse appeared in that interval. A
manual GPIO27 pin test checks the output signal only; it does not prove a
command was queued or that a physical solenoid and door will operate.

One reproducible command-delivery gap was found: a failed presence upload
stopped that Pi publishing cycle before the heartbeat that receives commands.
The exact cause of the reported live failure is still unproven without the
matching backend queue result and database state. The existing SQL unlock
guard also rejects a slot whose sensor presence disagrees with the database,
among other readiness conditions. Do not bypass that guard.

## Changes in this working tree

- The Pi retains a failed presence event and continues sending heartbeats.
  The snapshot reports its pending event count. A later successful upload
  acknowledges the event to the ESP32 and clears the pending count. Repeated
  failures do not produce a log line on every heartbeat.
- FastAPI reconciles each heartbeat and obtains guidance before claiming
  commands. It does not claim an unlock command while that heartbeat reports
  pending presence events. This prevents command delivery against unresolved
  sensor state and avoids claiming a command that a failed guidance response
  would discard.
- The kiosk waits for final placement or retrieval status before showing
  success. A warning remains visible until the backend reports the wrong
  slots cleared and the workflow leaves its warning or review phase.
- Regression tests simulate a failed presence upload followed by recovery,
  command delivery, and a single bounded pulse on GPIO27 and GPIO23. API and
  kiosk tests cover the command claim gate and final-state display.

## Files changed

- `frontend/app/kiosk/_hooks/kioskUnlockStatus.ts`
- `frontend/app/kiosk/_hooks/useKioskFlow.tsx`
- `frontend/tests/storage-flow.test.mjs`
- `services/api/app/routes/hardware.py`
- `services/api/tests/test_hardware.py`
- `services/pi-controller/src/sauli_pi/hardware_service.py`
- `services/pi-controller/tests/test_hardware.py`
- `SAULI_PROGRESS.md`

No schema, storage slot, image bucket, ESP32 firmware, GPIO mapping, GPIO3
shutdown button, kiosk registration, service ownership, or safety interlock
was changed. No migration or reset script is part of this change.

## Verification

- FastAPI: `python -m pytest -q` from `services/api`: 117 passed, 61 warnings.
- Pi controller: `PYTHONPATH=src python -m pytest -q` from
  `services/pi-controller`: 34 passed.
- Frontend: `npm test` from `frontend`: 43 passed.
- Frontend: `npx tsc --noEmit`: passed.
- Frontend: `npm run lint`: passed with one existing React hook dependency
  warning in `ItemCaptureStep.tsx`.
- `git diff --check`: passed. Git reported Windows line-ending notices only.

These are mocked/simulated tests. No live database, Pi, ESP32, reed switch,
presence sensor, solenoid, door, migration, reset, deployment, or physical
actuation was exercised in this work.

## Deployment order

1. Review and commit the tested changes. Inspect the live database objects
   for the existing `202611110002` workflow and `202611130001` guidance
   definitions before deployment. Do not infer application from migration
   history alone or reapply an existing migration automatically. This change
   adds no migration.
2. Deploy FastAPI, then the matching frontend build using the established
   deployment process. Verify API health and authenticated kiosk status.
3. On the Pi, pull the same commit and restart only the Pi hardware service:

   ```bash
   ssh sauli@sauli-lspuspcc
   cd /home/sauli/sauli
   git status --short
   git pull --ff-only origin main
   /home/sauli/.venvs/sauli-pi-hardware/bin/python -m pip install -e /home/sauli/sauli/services/pi-controller
   sudo systemctl restart sauli-pi-hardware.service
   sudo journalctl -u sauli-pi-hardware.service -n 100 --no-pager
   curl -fsS http://127.0.0.1:8765/state
   ```

4. Leave ESP32 firmware as deployed. Confirm all 12 fresh sensor readings,
   both reed levels, Pi and backend connectivity, and no unresolved incident.
   Resolve any physically observed sensor/database mismatch before testing.

## Supervised physical test

With trained staff present, verify output polarity, driver wiring, emergency
buttons, and door mechanics before enabling actuators. Start with an empty
P-01 slot: confirm it is absent in ESP telemetry and available in the database.
Perform one authorized pocket deposit. Record one command ID, one GPIO27
pulse, acknowledgment, BCM7 reed opening and closing, P-01 presence, and
final `placed`/`completed` state. Confirm no second pulse and no early success
screen. Repeat for an empty M-01 slot using GPIO23 and BCM8. Check that a wrong
slot triggers warning and that returning the item clears it only after the
backend confirms recovery. A brief backend failure must retain the presence
event while heartbeat continues; recovery must upload it before a command is
claimed. Do not continue if the physical state and database disagree.

**Readiness:** the implementation is ready for supervised physical hardware
testing after the existing SQL definitions, actual sensor states, output
polarity, and safety wiring are checked. Live unlock and full placement remain
unverified.
