# SAULI hardware integration checkpoint - 2026-11-13

## Current working tree

The current uncommitted work addresses the kiosk unlock 404 and intermittent
Supabase read failures. No migration, reset, deployment, firmware flash, or
physical actuation was performed. Registered kiosk records, the production GPIO
map, the GPIO3 shutdown button, and ESP32 firmware are unchanged.

## Confirmed findings

- The kiosk submits `POST /api/kiosk/found-items/{id}/request-unlock` or
  `POST /api/kiosk/retrieval-sessions/{id}/request-unlock`. FastAPI has both
  authenticated endpoints, but the Next.js kiosk proxy rejected both paths with
  404 before forwarding them. The proxy now allows those exact actions.
- The supplied FastAPI traceback shows `httpx.ReadError` during a Supabase
  workflow read. Safe read-only repository calls now retry transient transport
  and PostgREST failures with bounded backoff, then return a controlled 503.
  RPCs and writes are not automatically retried because a timeout may follow a
  successful commit. The underlying network cause remains unconfirmed.
- The P-01 snapshot reports PRESENT while the deposit has not completed. The
  existing SQL unlock guard requires switch presence to agree with database
  slot state. This mismatch must be investigated physically and in the database;
  it must not be bypassed to make the solenoid pulse.
- The existing `202611110002_sauli_workflow_unlock_and_incident_corrections.sql`
  queue RPC is idempotent for an unexpired pending command and guards fresh
  Pi/ESP evidence, closed reeds, inactive outputs, active incidents, and slot
  consistency. No new SQL migration was needed for this change. Whether the
  deployed database has this migration must be checked before a physical test.

## Implementation

- The proxy allowlist includes the two authenticated unlock actions.
- The workflow response exposes the existing command status and returns a null
  phase when no transaction exists. The kiosk uses that read to recover after
  an ambiguous unlock POST without issuing an automatic second write.
- A failed or rejected command shows a staff-attention message; a response that
  could not be verified no longer claims that no command was queued.
- Read-only identity, location, unit, device, workflow, and public hardware
  status queries use the same bounded retry and sanitized 503 behavior.

## Modified files

- `frontend/app/api/kiosk/[...path]/route.ts`
- `frontend/libs/api/kiosk-actions.ts` (new)
- `frontend/app/kiosk/_hooks/useKioskFlow.tsx`
- `frontend/app/kiosk/_hooks/kioskUnlockStatus.ts` (new)
- `frontend/app/kiosk/_components/DoorUnlockNotice.tsx`
- `frontend/libs/api/sauli.ts`
- `frontend/tests/storage-flow.test.mjs`
- `services/api/app/repositories/supabase_kiosks.py`
- `services/api/tests/test_hardware.py`
- `SAULI_PROGRESS.md`

## Verification

- FastAPI: `python -m pytest -q` - 113 passed, 61 deprecation warnings.
- Pi controller: `PYTHONPATH=src python -m pytest -q` - 28 passed.
- Frontend: `npm test` - 41 passed; `npx tsc --noEmit` - passed;
  `npm run lint` - passed with one existing `ItemCaptureStep.tsx` hook warning.
- `git diff --check` - passed.
- No live database, Raspberry Pi, ESP32, or solenoid test was performed.

## Rollout and supervised test

1. Review and commit these changes. Confirm the production database has the
   required existing workflow migration before testing; do not reapply a
   migration merely because it appears in the repository.
2. Deploy FastAPI and the Vercel frontend from the same commit. Pi and firmware
   code did not change, so a Pi pull/restart is optional for version alignment.
3. With staff present and the cabinet secured, inspect P-01's physical switch,
   latest ESP snapshot, database slot state, active incidents, and transaction
   history. Resolve the cause of the PRESENT/RESERVED mismatch without editing
   evidence to force an unlock.
4. Only after readiness evidence agrees, perform one authorized P-01 deposit.
   Observe the queued command, one bounded GPIO27 pulse, command acknowledgment,
   BCM7 reed opening, placement detection, door close, and final saved state.
   Check that a second request does not create a second pulse. Do not infer
   physical unlock from an HTTP response alone.

The implementation is ready for supervised physical hardware testing only after
the deployed database definition and P-01 sensor discrepancy are checked. It has
not yet been physically verified.
