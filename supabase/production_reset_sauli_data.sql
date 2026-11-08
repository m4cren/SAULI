-- MANUAL, DESTRUCTIVE, ALL-UNIT PRODUCTION OPERATIONAL RESET.
-- Run only after taking a database backup, physically emptying every cabinet,
-- and stopping kiosk writes and matching/email workers. This script is
-- deliberately NOT a migration.
-- Do not run if any item is still inside a cabinet: this marks slots available.
-- Preserve this script with the development reset whenever application tables
-- change. Auth users, units, devices, credentials, browser sessions, device
-- audit events, slot rows and Storage files are preserved. Remove test images
-- separately through the Storage API or dashboard, never storage.objects SQL.
--
-- Paste and run the entire single DO statement in the Supabase SQL Editor.
-- No confirmation values or counts are needed. An error rolls everything back.

do $sauli_reset$
declare
  v_devices_before jsonb;
  v_credentials_before jsonb;
  v_browser_sessions_before jsonb;
  v_devices_after jsonb;
  v_credentials_after jsonb;
  v_browser_sessions_after jsonb;
begin
  perform set_config('lock_timeout', '10s', true);
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

  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_devices_before
  from (select id, unit_id, device_code, status, is_primary, revoked_at
        from public.kiosk_devices) t;
  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_credentials_before
  from (select id, device_id, secret_hash, expires_at, revoked_at
        from public.kiosk_device_credentials) t;
  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_browser_sessions_before
  from (select id, device_id, token_hash, expires_at, revoked_at
        from public.kiosk_browser_sessions) t;
  if (select environment from public.sauli_deployment_guard where id = 1)
      is distinct from 'production' then
    raise exception 'SAULI_PRODUCTION_RESET_WRONG_ENVIRONMENT';
  end if;
  if exists (select 1 from public.sauli_units u where
      (select count(*) from public.storage_slots s where s.unit_id = u.id and s.is_active) <> 12
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'pocket') <> 8
      or (select count(*) from public.storage_slots s where s.unit_id = u.id
        and s.is_active and s.size_class = 'medium') <> 4) then
    raise exception 'SAULI_PRODUCTION_RESET_SLOT_CONFIGURATION_INVALID';
  end if;

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

  -- Preserve out-of-service maintenance flags and inactive retired slots.
  update public.storage_slots
  set status = case when status = 'out_of_service' then 'out_of_service' else 'available' end,
      current_found_item_id = null, reserved_at = null, occupied_at = null
  where current_found_item_id is not null or status in ('reserved','occupied')
     or reserved_at is not null or occupied_at is not null;

  delete from public.found_items;
  delete from public.missing_reports;
  delete from public.search_requests;

  -- Keep device security counters and audit history.
  update public.sauli_email_dispatch_clock set next_allowed_at = now() where id = 1;

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
  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_devices_after
  from (select id, unit_id, device_code, status, is_primary, revoked_at
        from public.kiosk_devices) t;
  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_credentials_after
  from (select id, device_id, secret_hash, expires_at, revoked_at
        from public.kiosk_device_credentials) t;
  select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb)
    into v_browser_sessions_after
  from (select id, device_id, token_hash, expires_at, revoked_at
        from public.kiosk_browser_sessions) t;
  if v_devices_before is distinct from v_devices_after
    or v_credentials_before is distinct from v_credentials_after
    or v_browser_sessions_before is distinct from v_browser_sessions_after then
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
end
$sauli_reset$;
