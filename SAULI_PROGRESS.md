# SAULI hardware integration checkpoint - 2026-11-14

## Scope and evidence

This working tree improves deposit verification and recovery from intermittent
Supabase reads. It does not change the Raspberry Pi controller, ESP32 firmware,
production GPIO map, GPIO3 shutdown button, kiosk registration, or database
schema. No migration, reset, deployment, flash, or physical actuation was run.

The supplied Pi log confirms ESP32 connectivity, brief backend 503 responses
followed by recovery, a P-08 presence transition, and P-02 presence. The
provided interval does **not** show a P-01 presence or reed transition, an
unlock command receipt, or a GPIO27 pulse. It cannot establish why P-01 did
not physically unlock. Earlier database evidence showed P-01 PRESENT while
its deposit had not completed. The existing SQL queue guard requires sensor
presence to agree with the slot record; that discrepancy must be checked, not
bypassed.

The previously committed kiosk proxy fix forwards the authenticated unlock
routes. This checkpoint does not change that proxy or its route allowlist.

## Changes in this working tree

- Read-only found-item and slot lookups retry transient transport/PostgREST
  failures with bounded backoff and return a controlled 503 after exhaustion.
  State-changing writes and RPCs are not retried automatically.
- Hardware guidance, which is a read-only RPC, uses the same bounded retry.
  Heartbeat reconciliation runs before guidance, and command claiming runs
  last. A guidance failure therefore cannot claim a command and then discard
  it in a failed heartbeat response.
- The kiosk shows a distinct verification state after a provisional sensor
  detection and door closure. It shows final placement success only when the
  backend reports `placement_status=placed`, transaction `phase=completed`,
  and no wrong slots.
- Regression tests cover guidance failure before claim, guidance and item-read
  retries, and the kiosk's final-placement condition.

## Files changed

- `frontend/app/kiosk/_components/PlacementScreen.tsx`
- `frontend/app/kiosk/_hooks/kioskUnlockStatus.ts`
- `frontend/app/kiosk/_hooks/useKioskFlow.tsx`
- `frontend/tests/storage-flow.test.mjs`
- `services/api/app/repositories/supabase_found_items.py`
- `services/api/app/repositories/supabase_kiosks.py`
- `services/api/app/routes/hardware.py`
- `services/api/tests/test_hardware.py`
- `services/api/tests/test_storage_slots.py`
- `SAULI_PROGRESS.md`

## Verification

- FastAPI: `python -m pytest -q` - 116 passed, 61 warnings.
- Pi controller: `PYTHONPATH=src python -m pytest -q` - 32 passed.
- Frontend: `npm test` - 42 passed; `npx tsc --noEmit` - passed;
  `npm run lint` - passed with one pre-existing `ItemCaptureStep.tsx` hook warning.
- `git diff --check` - passed.
- No live database, Raspberry Pi, ESP32, reed switch, presence sensor, or
  solenoid was exercised. A test of actual door movement remains necessary.

## Deployment order and supervised physical test

1. Review and commit the working tree. Confirm the deployed database has the
   existing `202611110002` workflow definition and `202611130001` guidance
   definition by inspecting the objects. Do not reapply a migration solely
   because its history entry is absent. This change adds no migration.
2. Deploy the FastAPI backend, then the frontend from the same commit. The Pi
   and ESP32 code are unchanged. A Pi pull and service restart is optional for
   version alignment; do it before the physical test if its checkout is behind.
3. With staff present and the cabinet safe, inspect P-01's physical switch,
   fresh ESP snapshot, database slot state, active incident, and transaction.
   Resolve any PRESENT/reserved mismatch using observed physical state.
4. Test one authorized pocket-size deposit. Observe one command ID and one
   GPIO27 pulse, command acknowledgment, BCM7 reed opening, P-01 detection,
   closure, and final `placed`/`completed` state. Confirm the kiosk stays in
   verification before the final state and does not issue a second pulse.
5. Test an unauthorized/wrong-position event and its safe clearance, then
   repeat the authorized path for a medium-size slot and GPIO23/BCM8. Check
   the behavior during a brief backend outage and ESP disconnect.

The implementation is ready for **supervised physical hardware testing after**
the deployed SQL definitions and P-01 sensor discrepancy are checked. A physical
unlock, sensor transition, and end-to-end placement have not been verified.
