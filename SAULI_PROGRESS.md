# SAULI hardware integration checkpoint — 2026-11-13

## Current state

The working tree contains targeted, uncommitted recovery work. No migration, reset,
deployment, firmware flash, or physical output test was run in this session.
The registered kiosk, credential, unit records, production GPIO mapping, and GPIO3
shutdown setup are unchanged.

## Completed implementation

- FastAPI kiosk identity lookup retries transient PostgREST/transport failures and
  returns a controlled 503 when Supabase is unavailable. Kiosk RPC, heartbeat, and
  bootstrap writes also return a sanitized 503 for those failures. A credential
  with NULL `expires_at` remains valid when active and not revoked.
- The Pi kiosk controller retries transient startup heartbeat failures before
  opening Chromium and tolerates two consecutive transient runtime failures.
  HTTP 401/403 still stops it immediately. The HTTP client retains the status
  code without exposing response bodies.
- `202611130001_sauli_review_recovery_and_guidance.sql` makes audible buzzer and
  SOS guidance depend on active incidents, while separately exposing
  `review_required`. Active deposit incidents still highlight the assigned slot.
  It adds an audit table and a service-role-only rearm RPC
  for an unopened `requires_review` transaction. The RPC requires fresh,
  complete, consistent Pi/ESP evidence, closed reeds, inactive outputs, no
  active incident or pending command, and an administrator's review reason.
  The RPC does not unlock a door. The admin-only FastAPI route invokes it.
- Both manual reset scripts include the new audit table and continue to
  preserve registered kiosks. Neither reset script was run.
- The previously committed `202611110002_sauli_workflow_unlock_and_incident_corrections.sql`
  compares every ready slot in a fresh ESP restart snapshot with database state.
  It raises an incident for a mismatch and clears it when readings agree.
  The existing regression tests cover this reboot path.

## Evidence and remaining limits

- Confirmed cause of the false alarm request: earlier `sauli_hardware_guidance`
  treated `requires_review` as buzzer/SOS even with zero active incidents.
  The new migration corrects the request; GPIO17 polarity and early boot
  electrical behavior still require measurement. A hardware pull-down may be
  needed to guarantee inactive level before software owns GPIO17.
- The exact exception behind the observed production heartbeat HTTP 500 was
  not supplied. The software now handles known PostgREST/transport failures,
  but production logs and deployed SQL definitions must be checked if a 500
  remains after rollout. No fake successful heartbeat was introduced.
- The historical M-01 `requires_review` record cannot be attributed to a
  specific missed command, reed edge, or reboot without its event/command
  history. It remains blocked until an operator reviews and rearms it; no
  production record was edited.
- Frontend review messaging was already implemented in the current baseline;
  frontend and ESP32 firmware have no uncommitted changes in this task.
  Switches establish presence, not item identity. Physical lock and power
  safety cannot be certified from mocked tests.

## Files in this working tree

- `services/api/app/repositories/supabase_kiosks.py`
- `services/api/app/routes/units.py`
- `services/api/tests/test_kiosk_recovery.py`
- `services/pi-controller/src/sauli_pi/communication/backend_client.py`
- `services/pi-controller/src/sauli_pi/main.py`
- `services/pi-controller/tests/test_kiosk_runtime.py`
- `supabase/migrations/202611130001_sauli_review_recovery_and_guidance.sql`
- `supabase/reset_sauli_data.sql`
- `supabase/production_reset_sauli_data.sql`
- `instruction.md`
- `SAULI_PROGRESS.md`

## Verification completed

- FastAPI: `python -m pytest -q` — 108 passed (61 deprecation warnings).
- Pi controller: `PYTHONPATH=src python -m pytest -q` — 28 passed.
- Frontend: `npm run lint` — passed with one pre-existing `ItemCaptureStep.tsx`
  React hook dependency warning; `npx tsc --noEmit` — passed; `npm test` — 39 passed.
- `git diff --check` — passed.
- `pglast.parse_sql` parsed `202611110002`, new `202611130001`, and both
  reset scripts. Parsing is not a live migration or schema integration test.
- PlatformIO was unavailable, so firmware build was not run. Firmware is unchanged.

## Deployment dependencies and next step

1. Review and commit the eleven files above. Confirm which migrations are already
   applied in the target Supabase project. Apply only pending migrations in
   filename order, with `202611110002` before `202611130001` if both are pending.
   Do not run either reset script. The new migration must precede the matching
   FastAPI and Pi code. Preserve the kiosk device and credential records.
2. Deploy the tested FastAPI revision. Pull the same commit on the Pi at
   `/home/sauli/sauli`, reinstall `services/pi-controller` in its existing venv,
   and restart `sauli-pi-hardware.service`; follow `instruction.md`. No frontend
   deployment or ESP32 flash is required for this working-tree change.
3. In a supervised session with actuators disabled, check a normal authenticated
   heartbeat, boot buzzer level, idle/review guidance, fresh ESP snapshot
   mismatch incident and clearing, and the M-01 command/reed/event history.
   Only if M-01 has never opened and all rearm guards pass, have an authorized
   admin invoke the new rearm route with an audit reason; then verify normal
   unlock handoff and provisional/final sensor behavior.

The next implementation action, if validation finds a remaining fault, is to
capture the exact FastAPI traceback and M-01 command/reed/event timeline and
patch that specific failure without resetting or re-enrolling the kiosk.
