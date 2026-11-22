# SAULI direct hardware transport checkpoint - 2026-11-22

## Reed-controlled compartment lighting - 2026-11-22

Raspberry Pi BCM16 and BCM20 were confirmed as the obsolete pocket/medium
AO4407A + 2N2222 bank-gate outputs. They are not ESP32 pins. The GPIO adapter
keeps their compatibility status fields false but no longer creates output
devices for either pin, leaving them unclaimed/high-impedance. Main light,
buzzer, solenoids, reeds, and all existing mappings are unchanged.

The Pi now sends both debounced reed states in one authenticated existing-UART
`set_door_states` command on changes, ESP hello/reconnect, and every three
seconds. ESP32 firmware 0.3 times that state out after seven seconds. The
SN74HC595 renderer uses bits 0-7 for P-01..P-08 and bits 9-12 for M-01..M-04;
bit 8 and bits 13-15 are masked permanently off. Closed, unknown, startup, or
stale states fail off independently per bank. Closing a bank clears its cached
modes, so reopening cannot restore an old steady/normal/SOS command; fresh
guidance is required. Presence sensors and incident/security state are not
changed or cleared by LED masking.

Focused verification passed: 39 Pi hardware/direct tests and 6 firmware
lighting-policy tests. These cover all four door combinations, independent
bank masking, exact mapping and unused bits, normal/SOS timing, UART staleness,
safe startup, cached-command clearing, high-impedance legacy pins, and both
reed states in the UART payload. PlatformIO/compiler tooling is not installed
in this workspace, so an actual ESP32 firmware build was not run. The firmware
must be reviewed, built, and reflashed before this behavior exists on hardware.
No flashing or physical output activation was performed.

## Direct finalization correction - 2026-11-22

Final verification found and fixed one delayed-event edge: a frozen pre-open
snapshot delivered after the authenticated open could previously resemble an
unauthenticated close and force review. Reconciliation now compares the Pi
snapshot observation time with the recorded open event. A genuinely later
closed state without the authenticated close event still enters review;
missing timestamps request a fresh snapshot; older snapshots return
`STALE_EVENT_IGNORED` without changing transaction state. Completed
transactions return before any deposit/retrieval writes, making duplicate
finalization idempotent.

Focused verification now passes 38 API tests and 37 Pi tests, including frozen
FIFO event delivery, delayed/out-of-order handling, missing telemetry recovery,
duplicate finalization guards, boot-ID recovery, and the existing direct and
kiosk regressions. Both direct migrations pass the installed PostgreSQL
`pglast` parser. No local `psql`, `pg_isready`, or Docker runtime is available,
so actual isolated PostgreSQL function execution and transaction behavior
remain unverified until reviewed deployment testing. No production connection
or lengthy database setup was attempted.

Direct workflow events now call
`sauli_reconcile_direct_hardware_workflow`, introduced by migration
`202611220001_sauli_direct_workflow_finalization.sql`. The function never reads
or writes `sauli_hardware_presence` and never stores a routine hardware
snapshot. It validates the registered primary device, transaction and assigned
slot identity, authenticated command and reed cycle, fresh ESP telemetry, all
12 ready/fault-free sensor values, authoritative slot assignments, active
incidents, and a distinct sensor reading after door closure before committing
deposit or retrieval business records.

The Pi now freezes the close-event snapshot instead of retaining references to
mutable ESP telemetry. The following telemetry frame therefore has a provably
newer sequence. A new ESP boot ID is accepted only through a complete fresh
post-close snapshot, and direct mode emits one startup recovery snapshot so a
Pi/ESP restart after an already-recorded authenticated close can finish safely.
Missing/stale/incomplete data requests another ESP snapshot; unauthenticated
door transitions or an incorrect assigned-slot final state enter review.
Wrong changes in other slots create or resolve the existing durable incidents.

Focused verification after this correction: 36 API tests and 36 Pi tests
passed with mocked hardware. This includes deposit/retrieval SQL contracts,
post-close freshness, new boot-ID recovery, missing/stale sensor handling,
wrong-slot incidents, unresolved-incident blocking, review failure paths, and
the unchanged kiosk/direct-command regression suites. No migration was run and
no physical hardware was activated.

## Current implementation

The active command path is now `Next.js kiosk -> FastAPI -> private Tailscale
Pi endpoint -> GPIO/ESP32-S3`. FastAPI retains the Supabase workflow guard for
the registered primary kiosk, active unit, placement/retrieval transaction,
assigned slot, concurrent workflow, active security incidents, and the full
12-slot database expectation. The new
`sauli_authorize_workflow_unlock` RPC returns an expiring command envelope; it
does not insert into `sauli_hardware_commands`.

The Pi authenticates the private request and, immediately before a pulse,
checks the device UUID, expiry, real/actuator mode, output polarity, fresh ESP
boot and telemetry state, all 12 ready/fault-free readings against the
authorized expectation, the target reed, solenoid output, and local workflow.
GPIO27 remains the pocket solenoid and GPIO23 the medium solenoid. A fail-closed
replay reservation is persisted before GPIO activation, so duplicate delivery
or a process restart cannot automatically produce another pulse.

Direct mode rejects legacy `/api/hardware/heartbeat`, `/presence`, and `/ack`
transport requests and never calls `sauli_claim_hardware_commands`. The Pi no
longer sends routine hardware heartbeats, GPIO/sensor snapshots, or command
acknowledgments to Supabase. Actual placement/retrieval changes, door workflow
transitions, and genuine security mismatches still use the authenticated
workflow-event route so transaction and incident correction state reconcile.
Light/buzzer guidance is returned only for those events and refreshed locally
without a database poll.

`sauli_hardware_commands` and `sauli_claim_hardware_commands` remain for
rollback/removal after live verification, but direct mode has no active path to
them. No application table, foreign key, storage-slot schema, bucket, Auth
account, kiosk credential, GPIO mapping, or ESP32 firmware changed, so
`supabase/reset_sauli_data.sql` requires no update.

## Current changed files

- `services/api/app/integrations/direct_hardware.py`
- `services/api/app/config.py`
- `services/api/app/main.py`
- `services/api/app/repositories/supabase_kiosks.py`
- `services/api/app/routes/hardware.py`
- `services/pi-controller/src/sauli_pi/hardware_service.py`
- `supabase/migrations/202611210001_sauli_direct_hardware_transport.sql`
- direct API/Pi tests and configuration/documentation examples

## Current verification

- Focused FastAPI direct/finalization, legacy hardware, and kiosk recovery tests: 38 passed.
- Focused Pi direct-command/restart and existing mocked hardware tests: 37 passed.
- Pocket: one mocked GPIO27 pulse; medium: one mocked GPIO23 pulse.
- Duplicate UUID: cached result with no second pulse.
- Unauthenticated or sensor-unsafe command: rejected with no pulse.
- Direct legacy heartbeat: HTTP 410 before any repository/claim call.
- Existing registered-kiosk credential heartbeat tests remain unchanged and
  pass, including revoked/expired credential and database-outage behavior.
- Python compilation and `git diff --check` passed; Git emitted only Windows
  line-ending notices.

All verification used mocked GPIO/ESP state. No deployment, production data,
live migration, or physical activation was performed. Rollout requires applying
`202611210001` followed by `202611220001`, configuring matching per-device direct tokens and private
Tailscale URLs, restarting FastAPI and the Pi together in direct mode, and only
then conducting supervised physical pocket/medium workflow tests. Do not run a
legacy controller concurrently.

## Prior checkpoint (superseded)

The 2026-11-15 heartbeat/claim implementation below is retained as historical
context. Its deployment instructions are superseded by the direct-mode section
above.

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

## 2026-11-22 — Continuous local security warnings

- The Pi now retains the authorized operation's 12-slot baseline and monitors
  all compartments locally until FastAPI confirms finalization. Correct
  deposit/retrieval evidence is provisional while the door remains open;
  reversing the assigned-slot change or changing any unrelated slot creates a
  local violation immediately. Independent violations remain active until each
  corresponding sensor state is corrected, and door closure does not clear
  them.
- Active local violations drive GPIO17 and overlay `SOS_BLINK` guidance for
  their exact slots. The existing ESP32 reed masks remain authoritative, so a
  closed compartment's LEDs stay off. Backend guidance loss cannot clear the
  Pi's local warning state.
- Direct mode acknowledges routine ESP32 presence events locally and no longer
  forwards them as routine backend workflow events. Only genuine incident and
  correction transitions enter a bounded, disk-backed Pi queue. FastAPI applies
  those authenticated transitions idempotently to the existing
  `sauli_hardware_incidents` rows; no hardware-event table or routine snapshot
  logging was added.
- The authenticated workflow read overlays the live Pi warning state on the
  existing `wrong_slots` and `phase` response. The existing kiosk popup therefore
  shows `warning_active` without waiting for Supabase incident reconciliation.
- `202611220001_sauli_direct_workflow_finalization.sql` now includes the
  backward-compatible `sauli_apply_direct_security_updates` RPC. It validates
  the primary device, active unit, transaction command, assigned slot, and all
  incident updates; corrections resolve the same incident identity. It must be
  reviewed and applied before deploying the matching API and Pi code. No
  production migration or data change was executed here, and
  `reset_sauli_data.sql` is unchanged because no application table, foreign key,
  storage-slot definition, or bucket changed.

Focused mocked verification:

- Pi hardware/direct suites: 43 passed.
- FastAPI hardware/direct suites: 34 passed.
- Kiosk storage-flow suite: 9 passed.
- `git diff --check`: passed (Windows line-ending notices only).

The tests cover assigned-item reversal for deposit and retrieval, simultaneous
wrong placement/removal, independent correction, warning persistence across
door closure and backend outage, durable queue retention, backend-confirmed
monitor completion, authenticated live popup state, and incident-update
idempotency. Physical GPIO, buzzer, sensors, doors, ESP32 firmware, and live
PostgreSQL execution remain unverified and were not activated.
