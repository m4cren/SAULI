# Multi-unit rollout (review before applying)

The versioned migration `supabase/migrations/202611020001_sauli_multi_unit_foundation.sql` is a coordinated application/database deployment. It has **not** been run by this repository change. Back up Postgres and the private image bucket, schedule a maintenance window, and stop kiosk writes before applying it. The migration uses a transaction and preserves legacy item and slot UUIDs. A failed preflight or SQL statement rolls the transaction back.

## Preflight on the target Supabase project

Run these read-only queries in the SQL Editor and review every result:

```sql
select code, size_class, status, is_active, current_found_item_id
from public.storage_slots order by size_class, ordinal;
select code, status, current_found_item_id from public.storage_slots
where code in ('P-09','P-10','M-05');
select s.code, s.status, s.current_found_item_id, f.status as item_status,
       f.placement_status
from public.storage_slots s left join public.found_items f
  on f.id = s.current_found_item_id
where s.current_found_item_id is not null;
select count(*) filter (where is_active) as active_slots,
       count(*) filter (where is_active and size_class = 'pocket') as pocket_slots,
       count(*) filter (where is_active and size_class = 'medium') as medium_slots
from public.storage_slots;
```

The expected active configuration is 8 pocket and 4 medium slots. Resolve any reservation in P-09, P-10, or M-05 before migrating. An occupied retired slot is retained for its item and history, but it cannot receive new deposits or QR redemption through the new kiosk workflow. Arrange supervised handling for that item; do not delete it. Review the existing slot/item links and unresolved reservations manually. The migration's final assertion rejects active-layout or cross-unit inconsistencies.

Apply migrations in filename order through the normal Supabase SQL workflow. Apply the backend and frontend in the same maintenance window: the old singleton storage RPC loses service-role access once this migration commits. Do not apply `reset_sauli_data.sql` as a migration.

After applying, verify:

```sql
select u.unit_code, count(*) filter (where s.is_active) as active,
       count(*) filter (where s.is_active and s.size_class = 'pocket') as pocket,
       count(*) filter (where s.is_active and s.size_class = 'medium') as medium
from public.sauli_units u join public.storage_slots s on s.unit_id = u.id
group by u.unit_code;
select u.unit_code, d.device_code, d.status, d.last_seen_at
from public.sauli_units u left join public.kiosk_devices d on d.unit_id = u.id;
```

For rollback **before** commit, let the SQL transaction roll back. After commit, restore the database backup in a controlled recovery window. Do not drop the new unit columns or copy multi-unit records back into a singleton database; that would collide on slot codes and lose unit ownership. Preserve a snapshot of the original database until deposit and QR flows are verified.

## Backend and Vercel

FastAPI needs the existing Supabase service-role key, admin UUID, and retrieval pepper in `services/.env`; keep them server-side. `FRONTEND_ORIGIN` must be the actual Vercel origin. The public API must be reachable from phones and from Vercel over HTTPS; Tailscale alone does not make a private API reachable from Vercel. On Vercel, set `NEXT_PUBLIC_API_BASE_URL` to the browser-reachable HTTPS API and `SAULI_API_INTERNAL_URL` to a server-reachable HTTPS API. Do not put service-role keys or Pi credentials in `NEXT_PUBLIC_` variables. Restrict backend exposure with authentication; CORS only controls browser reads.

The first unit is `SAULI-LSPUSPCC-001` at LSPU San Pablo City Campus, Engineering Building. Its device registration is `KIOSK-LSPUSPCC-ENGINEERING-01`, hostname `sauli-lspuspcc`. The migration seeds the unit, its 12 active slots, and its **pending** device record. The hostname and device code are labels, not credentials.

## Enroll the first Pi

1. In `/admin/units`, confirm the seeded unit and pending device. A verified admin approves pairing. The page displays a single-use code valid for ten minutes. Transfer it to the Pi through a trusted local operator; do not put it in a public issue or log.
2. Install `services/pi-controller` in `/opt/sauli/pi-controller/.venv` as the `sauli` user. Copy `controller.example.json` to `/etc/sauli/controller.json`, set the HTTPS backend and frontend origins and correct device/unit codes, and make the file readable only by the operator. Create `/var/lib/sauli` owned by `sauli`, mode 0700. Do not put the long-term credential in this JSON file.
3. Run `python -m sauli_pi.main enroll --config /etc/sauli/controller.json` interactively as `sauli`, then enter the approved code. The credential is stored in `/var/lib/sauli/credential` with mode 0600. Run `python -m sauli_pi.main heartbeat --config /etc/sauli/controller.json` to confirm it is active.
4. Preserve the OS Lite auto-login and labwc setup. Install `sauli-pi-kiosk.service` as a **user** service for `sauli`. Start it from the existing labwc autostart after importing `DISPLAY` and `WAYLAND_DISPLAY` into the user systemd environment. Remove only the old direct Chromium launch line so there is one kiosk browser, while retaining camera permissions, Squeekboard, and other autostart settings. A normal reboot obtains a fresh one-time browser handoff and an expiring HttpOnly session. The browser must use the deployed HTTPS frontend URL.

Do not start two controller processes. The Python process terminates the kiosk browser on device heartbeat failure and does not issue physical unlock commands. The browser session expires after eight hours; the controller restarts Chromium after seven hours to obtain a fresh one-time handoff. This interrupts an in-progress kiosk flow, so schedule device use and monitor the kiosk during rollout.

## Register a second unit

From `/admin/units`, create a distinct unit code, campus/building/location, and device code. Unit creation transactionally provisions P-01 through P-08 and M-01 through M-04 under its own UUID. Confirm the 12-slot count, then activate the unit. Register the second Pi device, approve its pairing, and configure a separate Pi with that unit and device code. Never copy the first Pi's credential. Each Pi receives its own credential and browser session. A second unit can use the same compartment labels because uniqueness is per unit.

Revoke a compromised or replaced device in `/admin/units`. Revocation invalidates its credential and browser sessions without deleting its unit, items, slots, or logs. Enroll the replacement as a new pending device after revoking the old primary device.

## Operational reset and current hardware limit

`supabase/reset_sauli_data.sql` runs only when a disposable project's `sauli_deployment_guard` is explicitly set to `development` and both confirmation settings are supplied as documented in that file. A unit-specific reset removes that unit's operational item and dependent records while retaining shared claimant reports/searches and other units. `ALL` also clears shared operational records. Both preserve units, device enrollment, Auth accounts, and slot rows. The reset never deletes Storage objects; remove test images separately through the Storage API or dashboard. Never run it on production.

The existing `services/pi-controller/src/sauli_pi/hardware/` and ESP32 communication modules contain no implemented GPIO, lock, reed-switch, or weight-sensor mapping. The current kiosk placement and retrieval controls remain simulations. Before any physical lock can be driven, define and verify the real per-unit pin/channel map, safe output defaults, sensor protocol, command acknowledgement, and fault behavior on the installed cabinet. Do not treat a simulated door-ready screen as proof that a solenoid opened. Live Supabase, Vercel, Pi, camera, and lock integration still require on-device verification.
