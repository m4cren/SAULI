-- MANUAL, DESTRUCTIVE, ALL-UNIT PRODUCTION OPERATIONAL RESET.
-- Run only after reviewing production_reset_preflight.sql, taking a database
-- backup, physically emptying every cabinet, and stopping kiosk writes and
-- matching/email workers. This script is deliberately NOT a migration.
-- Do not run if any item is still inside a cabinet: this marks slots available.
-- Preserve this script with the development reset whenever application tables
-- change. Auth users, units, devices, credentials, browser sessions, device
-- audit events, slot rows and Storage files are preserved. Remove test images
-- separately through the Storage API or dashboard, never storage.objects SQL.
--
-- Before running, replace the five values in the first DO block below with:
--   confirmation: RESET ALL SAULI PRODUCTION DATA
--   units, found_items, missing_reports, nonempty_slots: exact preflight counts
-- The default placeholders make accidental execution fail before any deletion.

begin;
set local lock_timeout = '10s';
lock table public.sauli_deployment_guard, public.sauli_units,
  public.sauli_hardware_snapshots, public.sauli_hardware_commands,
  public.found_items, public.storage_slots, public.storage_slot_events,
  public.match_candidates, public.retrieval_sessions, public.retrieval_events,
  public.retrieval_logs, public.matching_jobs, public.email_notifications,
  public.missing_reports, public.search_requests,
  public.sauli_email_dispatch_clock in access exclusive mode;

-- Prevent registration changes while preserving kiosk identities and sessions.
lock table public.kiosk_devices, public.kiosk_device_credentials,
  public.kiosk_browser_sessions in share mode;
create temporary table sauli_reset_devices on commit drop as
select id, unit_id, device_code, status, is_primary, revoked_at
from public.kiosk_devices;
create temporary table sauli_reset_credentials on commit drop as
select id, device_id, secret_hash, expires_at, revoked_at
from public.kiosk_device_credentials;
create temporary table sauli_reset_browser_sessions on commit drop as
select id, device_id, token_hash, expires_at, revoked_at
from public.kiosk_browser_sessions;

do $$
declare
  v_confirmation text := 'REPLACE_WITH_CONFIRMATION';
  v_expected_units bigint := -1;
  v_expected_found_items bigint := -1;
  v_expected_missing_reports bigint := -1;
  v_expected_nonempty_slots bigint := -1;
begin
  if (select environment from public.sauli_deployment_guard where id = 1)
      is distinct from 'production' then
    raise exception 'SAULI_PRODUCTION_RESET_WRONG_ENVIRONMENT';
  end if;
  if v_confirmation <> 'RESET ALL SAULI PRODUCTION DATA'
      or v_expected_units < 1 or v_expected_found_items < 0
      or v_expected_missing_reports < 0 or v_expected_nonempty_slots < 0 then
    raise exception 'SAULI_PRODUCTION_RESET_NOT_CONFIRMED';
  end if;
  if v_expected_units <> (select count(*) from public.sauli_units)
      or v_expected_found_items <> (select count(*) from public.found_items)
      or v_expected_missing_reports <> (select count(*) from public.missing_reports)
      or v_expected_nonempty_slots <> (select count(*) from public.storage_slots
        where current_found_item_id is not null or status in ('reserved','occupied')
          or reserved_at is not null or occupied_at is not null) then
    raise exception 'SAULI_PRODUCTION_RESET_COUNTS_CHANGED: rerun preflight';
  end if;
  if exists (select 1 from public.sauli_units u where
      (select count(*) from public.storage_slots s where s.unit_id = u.id and s.is_active) <> 12
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'pocket') <> 8
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'medium') <> 4) then
    raise exception 'SAULI_PRODUCTION_RESET_SLOT_CONFIGURATION_INVALID';
  end if;
end $$;

-- Delete dependents before their referenced items, reports and searches.
delete from public.sauli_hardware_commands;
delete from public.sauli_hardware_snapshots;
delete from public.email_notifications;
delete from public.retrieval_events;
delete from public.retrieval_logs;
delete from public.retrieval_sessions;
delete from public.match_candidates;
delete from public.matching_jobs;
delete from public.storage_slot_events;

-- The operator has physically emptied every cabinet. Preserve out-of-service
-- maintenance flags and inactive retired slots, but clear their item links.
update public.storage_slots
set status = case when status = 'out_of_service' then 'out_of_service' else 'available' end,
    current_found_item_id = null, reserved_at = null, occupied_at = null
where current_found_item_id is not null or status in ('reserved','occupied')
   or reserved_at is not null or occupied_at is not null;

delete from public.found_items;
delete from public.missing_reports;
delete from public.search_requests;

-- Keep device security counters and audit history. Reset only the email send
-- spacing clock so future notifications do not inherit an old delay.
update public.sauli_email_dispatch_clock set next_allowed_at = now() where id = 1;

do $$ begin
  if exists (select 1 from public.found_items)
    or exists (select 1 from public.sauli_hardware_commands)
    or exists (select 1 from public.sauli_hardware_snapshots)
    or exists (select 1 from public.missing_reports)
    or exists (select 1 from public.search_requests)
    or exists (select 1 from public.match_candidates)
    or exists (select 1 from public.matching_jobs)
    or exists (select 1 from public.storage_slot_events)
    or exists (select 1 from public.retrieval_sessions)
    or exists (select 1 from public.retrieval_events)
    or exists (select 1 from public.retrieval_logs)
    or exists (select 1 from public.email_notifications)
    or exists (select 1 from public.storage_slots where current_found_item_id is not null
      or status in ('reserved','occupied') or reserved_at is not null
      or occupied_at is not null) then
    raise exception 'SAULI_PRODUCTION_RESET_VERIFICATION_FAILED';
  end if;
  if exists (select * from sauli_reset_devices except
      select id, unit_id, device_code, status, is_primary, revoked_at
      from public.kiosk_devices)
    or exists (select id, unit_id, device_code, status, is_primary, revoked_at
      from public.kiosk_devices except select * from sauli_reset_devices)
    or exists (select * from sauli_reset_credentials except
      select id, device_id, secret_hash, expires_at, revoked_at
      from public.kiosk_device_credentials)
    or exists (select id, device_id, secret_hash, expires_at, revoked_at
      from public.kiosk_device_credentials except select * from sauli_reset_credentials)
    or exists (select * from sauli_reset_browser_sessions except
      select id, device_id, token_hash, expires_at, revoked_at
      from public.kiosk_browser_sessions)
    or exists (select id, device_id, token_hash, expires_at, revoked_at
      from public.kiosk_browser_sessions except select * from sauli_reset_browser_sessions) then
    raise exception 'SAULI_PRODUCTION_RESET_KIOSK_REGISTRATION_CHANGED';
  end if;
  if exists (select 1 from public.sauli_units u where
      (select count(*) from public.storage_slots s where s.unit_id = u.id and s.is_active) <> 12
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'pocket') <> 8
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'medium') <> 4) then
    raise exception 'SAULI_PRODUCTION_RESET_SLOT_CONFIGURATION_INVALID';
  end if;
end $$;
commit;
