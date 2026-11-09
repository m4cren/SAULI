-- Manual DEVELOPMENT-ONLY operational reset. Never include this file in db push.
-- Before running, mark a disposable project in sauli_deployment_guard as
-- development, then execute in one SQL Editor session with:
--   select set_config('app.sauli_reset_confirmation', 'RESET DEVELOPMENT DATA', false);
--   select set_config('app.sauli_reset_unit_code', 'SAULI-LSPUSPCC-001', false);
-- Use ALL as the unit code only to intentionally clear every unit.
-- The default database guard is production and rejects this script.
-- This preserves Auth users, units, all slot rows, device registrations,
-- credentials, browser sessions, pairing audit, and Storage bucket/files.
-- Kiosk enrollment rate counters are also preserved.
-- Remove Storage files separately through the Storage API or dashboard.

begin;
set local lock_timeout = '10s';

do $$
declare v_scope text := current_setting('app.sauli_reset_unit_code', true);
begin
  if (select environment from public.sauli_deployment_guard where id = 1) is distinct from 'development' then
    raise exception 'SAULI_RESET_DEVELOPMENT_ONLY: use the reviewed production procedure for live data';
  end if;
  if current_setting('app.sauli_reset_confirmation', true) <> 'RESET DEVELOPMENT DATA'
    or v_scope is null or v_scope = '' then
    raise exception 'SAULI_RESET_CONFIRMATION_REQUIRED';
  end if;
  if v_scope <> 'ALL' and not exists
    (select 1 from public.sauli_units where unit_code = v_scope) then
    raise exception 'SAULI_RESET_UNKNOWN_UNIT';
  end if;
end $$;

lock table public.found_items, public.storage_slots, public.storage_slot_events,
  public.sauli_hardware_snapshots, public.sauli_hardware_commands,
  public.sauli_hardware_presence, public.sauli_hardware_presence_events,
  public.sauli_hardware_incidents,
  public.match_candidates, public.retrieval_sessions, public.retrieval_events,
  public.retrieval_logs, public.matching_jobs, public.email_notifications,
  public.missing_reports, public.search_requests, public.sauli_email_dispatch_clock
  in access exclusive mode;

-- Keep kiosk identity and active login material stable throughout the reset.
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

create temporary table sauli_reset_items on commit drop as
select fi.id from public.found_items fi
join public.sauli_units u on u.id = fi.unit_id
where current_setting('app.sauli_reset_unit_code') = 'ALL'
  or u.unit_code = current_setting('app.sauli_reset_unit_code');

create temporary table sauli_reset_slots on commit drop as
select s.id from public.storage_slots s
join public.sauli_units u on u.id = s.unit_id
where current_setting('app.sauli_reset_unit_code') = 'ALL'
  or u.unit_code = current_setting('app.sauli_reset_unit_code');

delete from public.sauli_hardware_commands where unit_id in
  (select id from public.sauli_units where current_setting('app.sauli_reset_unit_code') = 'ALL'
   or unit_code = current_setting('app.sauli_reset_unit_code'));
delete from public.sauli_hardware_snapshots where unit_id in
  (select id from public.sauli_units where current_setting('app.sauli_reset_unit_code') = 'ALL'
   or unit_code = current_setting('app.sauli_reset_unit_code'));
delete from public.sauli_hardware_incidents where slot_id in (select id from sauli_reset_slots);
delete from public.sauli_hardware_presence_events where slot_id in (select id from sauli_reset_slots);
delete from public.sauli_hardware_presence where slot_id in (select id from sauli_reset_slots);

create temporary table sauli_reset_candidates on commit drop as
select id, search_request_id from public.match_candidates
where found_item_id in (select id from sauli_reset_items);

create temporary table sauli_reset_reports on commit drop as
select distinct mr.id as missing_report_id from public.missing_reports mr
join sauli_reset_candidates c on c.search_request_id = mr.search_request_id;

delete from public.email_notifications
where found_item_id in (select id from sauli_reset_items)
  or match_candidate_id in (select id from sauli_reset_candidates);
delete from public.retrieval_events
where found_item_id in (select id from sauli_reset_items);
delete from public.retrieval_logs
where found_item_id in (select id from sauli_reset_items);
delete from public.retrieval_sessions
where found_item_id in (select id from sauli_reset_items);
delete from public.match_candidates
where id in (select id from sauli_reset_candidates);
delete from public.matching_jobs
where found_item_id in (select id from sauli_reset_items);
delete from public.storage_slot_events
where slot_id in (select id from sauli_reset_slots);

update public.storage_slots set status = case when status = 'out_of_service'
    then 'out_of_service' else 'available' end, current_found_item_id = null,
  reserved_at = null, occupied_at = null
where id in (select id from sauli_reset_slots)
  and (current_found_item_id is not null or status in ('reserved','occupied')
    or reserved_at is not null or occupied_at is not null);
-- Preserve out-of-service maintenance flags and inactive legacy positions.
delete from public.found_items where id in (select id from sauli_reset_items);

-- Unit-specific resets retain shared claimant reports and search history.
-- Any report whose accepted candidate was removed becomes active again.
update public.missing_reports mr set status = 'active'
where mr.id in (select missing_report_id from sauli_reset_reports)
  and mr.status in ('matched','resolved')
  and not exists (
    select 1 from public.match_candidates mc
    where mc.search_request_id = mr.search_request_id and mc.decision = 'accepted'
  );

do $$ begin
  if current_setting('app.sauli_reset_unit_code') = 'ALL' then
    -- These shared records are cleared only by an explicit all-unit reset.
    delete from public.email_notifications;
    delete from public.matching_jobs;
    delete from public.match_candidates;
    delete from public.missing_reports;
    delete from public.search_requests;
    delete from public.sauli_email_dispatch_clock;
    insert into public.sauli_email_dispatch_clock(id,next_allowed_at) values(1,now());
  end if;
  if exists (select 1 from sauli_reset_items i
    join public.found_items fi on fi.id = i.id) then
    raise exception 'SAULI_RESET_VERIFICATION_FAILED';
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
    raise exception 'SAULI_RESET_KIOSK_REGISTRATION_CHANGED';
  end if;
  if exists (select 1 from public.sauli_units u where
    (select count(*) from public.storage_slots s where s.unit_id = u.id and s.is_active) <> 12
    or (select count(*) from public.storage_slots s where s.unit_id = u.id
      and s.is_active and s.size_class = 'pocket') <> 8
    or (select count(*) from public.storage_slots s where s.unit_id = u.id
      and s.is_active and s.size_class = 'medium') <> 4) then
    raise exception 'SAULI_RESET_SLOT_CONFIGURATION_INVALID';
  end if;
end $$;
commit;
