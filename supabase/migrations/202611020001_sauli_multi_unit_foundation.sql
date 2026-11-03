-- Multi-unit foundation. Apply in a maintenance window after reviewing the
-- preflight queries in docs/multi-unit-rollout.md. This never deletes legacy data.
begin;
set local lock_timeout = '10s';
lock table public.found_items, public.storage_slots in access exclusive mode;

create table public.sauli_units (
  id uuid primary key default gen_random_uuid(),
  unit_code text not null unique check (unit_code ~ '^SAULI-[A-Z0-9-]+$'),
  display_name text not null,
  campus_code text not null,
  campus_name text not null,
  building_name text not null,
  floor text,
  location_description text,
  status text not null default 'provisioning'
    check (status in ('provisioning','active','maintenance','inactive','retired')),
  installed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- Default-deny reset marker. Development operators must explicitly mark a
-- disposable project as development before the separate reset script can run.
create table public.sauli_deployment_guard (
  id integer primary key check (id = 1),
  environment text not null default 'production' check (environment in ('development','staging','production'))
);
insert into public.sauli_deployment_guard(id,environment) values (1,'production');
create trigger sauli_units_updated_at before update on public.sauli_units
  for each row execute function public.sauli_set_updated_at();
create function public.sauli_keep_unit_identity() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.id is distinct from old.id or new.unit_code is distinct from old.unit_code then
    raise exception 'UNIT_IDENTITY_IMMUTABLE';
  end if;
  return new;
end; $$;
create trigger sauli_units_keep_identity before update of id,unit_code on public.sauli_units
  for each row execute function public.sauli_keep_unit_identity();

create table public.kiosk_devices (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references public.sauli_units(id) on delete restrict,
  device_code text not null unique,
  hostname text,
  hardware_type text,
  status text not null default 'pending'
    check (status in ('pending','active','revoked')),
  is_primary boolean not null default true,
  last_seen_at timestamptz,
  controller_version text,
  firmware_version text,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status = 'revoked') = (revoked_at is not null))
);
create unique index kiosk_devices_one_active_primary_per_unit
  on public.kiosk_devices(unit_id) where is_primary and status = 'active';
create trigger kiosk_devices_updated_at before update on public.kiosk_devices
  for each row execute function public.sauli_set_updated_at();

create table public.kiosk_device_credentials (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.kiosk_devices(id) on delete restrict,
  secret_hash text not null unique check (secret_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  revoked_at timestamptz
);
create unique index kiosk_device_one_valid_credential
  on public.kiosk_device_credentials(device_id) where revoked_at is null;

create table public.kiosk_pairing_requests (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.kiosk_devices(id) on delete restrict,
  request_hash text not null unique check (request_hash ~ '^[0-9a-f]{64}$'),
  status text not null default 'pending'
    check (status in ('pending','approved','redeemed','expired','rejected')),
  expires_at timestamptz not null,
  approved_by uuid references auth.users(id) on delete restrict,
  approved_at timestamptz,
  redeemed_at timestamptz,
  created_at timestamptz not null default now()
);
create index kiosk_pairing_pending_idx on public.kiosk_pairing_requests(device_id,status,expires_at);

create table public.kiosk_browser_bootstraps (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.kiosk_devices(id) on delete restrict,
  code_hash text not null unique check (code_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  redeemed_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.kiosk_browser_sessions (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.kiosk_devices(id) on delete restrict,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz,
  revoked_at timestamptz
);
create index kiosk_browser_sessions_device_idx on public.kiosk_browser_sessions(device_id,expires_at);

create table public.kiosk_device_events (
  id bigint generated always as identity primary key,
  device_id uuid not null references public.kiosk_devices(id) on delete restrict,
  event_type text not null check (event_type in
    ('registered','pairing_requested','pairing_approved','pairing_rejected',
     'credential_issued','credential_rotated','session_issued','heartbeat','revoked')),
  actor_user_id uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- Shared rate counters keep enrollment limits effective across API workers.
create table public.kiosk_rate_limits (
  action text not null check (action in ('enroll_ip','enroll_device','redeem_ip')),
  subject_hash text not null check (subject_hash ~ '^[0-9a-f]{64}$'),
  window_started_at timestamptz not null default now(),
  attempts integer not null default 1 check (attempts > 0),
  primary key (action,subject_hash)
);

create function public.sauli_check_kiosk_rate_limit(
  p_action text,p_subject_hash text,p_max_attempts integer,p_window_seconds integer)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare v_attempts integer;
begin
  if p_action not in ('enroll_ip','enroll_device','redeem_ip') or
     p_subject_hash !~ '^[0-9a-f]{64}$' or
     p_max_attempts < 1 or p_window_seconds < 1 then
    raise exception 'INVALID_RATE_LIMIT';
  end if;
  insert into public.kiosk_rate_limits(action,subject_hash,window_started_at,attempts)
    values(p_action,p_subject_hash,now(),1)
  on conflict (action,subject_hash) do update set
    attempts = case when public.kiosk_rate_limits.window_started_at <=
      now() - make_interval(secs => p_window_seconds) then 1
      else public.kiosk_rate_limits.attempts + 1 end,
    window_started_at = case when public.kiosk_rate_limits.window_started_at <=
      now() - make_interval(secs => p_window_seconds) then now()
      else public.kiosk_rate_limits.window_started_at end
  returning attempts into v_attempts;
  return v_attempts <= p_max_attempts;
end; $$;

insert into public.sauli_units(unit_code,display_name,campus_code,campus_name,
  building_name,location_description,status)
values ('SAULI-LSPUSPCC-001','SAULI Engineering Building','LSPU-SPCC',
  'Laguna State Polytechnic University - San Pablo City Campus',
  'Engineering Building','Engineering Building','active');

alter table public.found_items add column unit_id uuid;
alter table public.storage_slots add column unit_id uuid;
update public.found_items set unit_id = (select id from public.sauli_units
  where unit_code = 'SAULI-LSPUSPCC-001');
update public.storage_slots set unit_id = (select id from public.sauli_units
  where unit_code = 'SAULI-LSPUSPCC-001');
alter table public.found_items alter column unit_id set not null;
alter table public.storage_slots alter column unit_id set not null;
alter table public.found_items add constraint found_items_unit_id_fkey
  foreign key (unit_id) references public.sauli_units(id) on delete restrict;
alter table public.storage_slots add constraint storage_slots_unit_id_fkey
  foreign key (unit_id) references public.sauli_units(id) on delete restrict;
create index found_items_unit_status_idx on public.found_items(unit_id,status);
create index storage_slots_unit_status_idx on public.storage_slots(unit_id,status,size_class,ordinal);

-- Keep all 15 legacy UUIDs and history; the obsolete three remain inactive.
update public.storage_slots set is_active = false
  where code in ('P-09','P-10','M-05') and is_active;
alter table public.storage_slots drop constraint if exists storage_slots_code_key;
alter table public.storage_slots drop constraint if exists storage_slots_size_class_ordinal_key;
alter table public.storage_slots add constraint storage_slots_unit_code_key unique(unit_id,code);
alter table public.storage_slots add constraint storage_slots_unit_size_ordinal_key
  unique(unit_id,size_class,ordinal);

-- A slot may only contain an item belonging to the same unit.
create function public.sauli_check_slot_item_unit() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.current_found_item_id is not null and not exists (
    select 1 from public.found_items fi where fi.id = new.current_found_item_id
      and fi.unit_id = new.unit_id
  ) then raise exception 'CROSS_UNIT_SLOT_ITEM'; end if;
  return new;
end; $$;
create trigger storage_slots_item_unit before insert or update of unit_id,current_found_item_id
  on public.storage_slots for each row execute function public.sauli_check_slot_item_unit();
create function public.sauli_keep_slot_unit() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.unit_id is distinct from old.unit_id then
    raise exception 'SLOT_UNIT_IMMUTABLE';
  end if;
  return new;
end; $$;
create trigger storage_slots_keep_unit before update of unit_id on public.storage_slots
  for each row execute function public.sauli_keep_slot_unit();

-- Historical slot events must also reference an item from that slot's unit.
create function public.sauli_check_slot_event_unit() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.found_item_id is not null and not exists (
    select 1 from public.storage_slots ss
    join public.found_items fi on fi.id = new.found_item_id
    where ss.id = new.slot_id and ss.unit_id = fi.unit_id
  ) then raise exception 'CROSS_UNIT_SLOT_EVENT'; end if;
  return new;
end; $$;
create trigger storage_slot_events_item_unit before insert or update of slot_id,found_item_id
  on public.storage_slot_events for each row execute function public.sauli_check_slot_event_unit();

-- Once an item is assigned, changing its unit would invalidate its audit trail.
create function public.sauli_keep_item_unit() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.unit_id is distinct from old.unit_id then
    raise exception 'ITEM_UNIT_IMMUTABLE';
  end if;
  return new;
end; $$;
create trigger found_items_keep_unit before update of unit_id on public.found_items
  for each row execute function public.sauli_keep_item_unit();

create function public.sauli_provision_unit_slots(p_unit_id uuid) returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
  perform 1 from public.sauli_units where id = p_unit_id for update;
  if not found then raise exception 'UNIT_NOT_FOUND'; end if;
  insert into public.storage_slots(unit_id,code,size_class,ordinal,is_active)
  select p_unit_id,'P-' || lpad(n::text,2,'0'),'pocket',n,true
    from generate_series(1,8) n
  union all
  select p_unit_id,'M-' || lpad(n::text,2,'0'),'medium',n,true
    from generate_series(1,4) n
  on conflict (unit_id,code) do nothing;
  select count(*) into v_count from public.storage_slots where unit_id = p_unit_id
    and is_active and ((size_class = 'pocket' and ordinal between 1 and 8)
      or (size_class = 'medium' and ordinal between 1 and 4));
  if v_count <> 12 or (select count(*) from public.storage_slots
      where unit_id = p_unit_id and is_active) <> 12 then
    raise exception 'UNIT_SLOT_CONFIGURATION_INVALID';
  end if;
  return v_count;
end; $$;

create function public.sauli_register_unit(p_unit jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_unit public.sauli_units;
begin
  insert into public.sauli_units(unit_code,display_name,campus_code,campus_name,
    building_name,floor,location_description,status)
  values(p_unit->>'unit_code',p_unit->>'display_name',p_unit->>'campus_code',
    p_unit->>'campus_name',p_unit->>'building_name',p_unit->>'floor',
    p_unit->>'location_description','provisioning') returning * into v_unit;
  perform public.sauli_provision_unit_slots(v_unit.id);
  return to_jsonb(v_unit);
end; $$;

-- Registration and pairing approval include their audit events in the same
-- transaction. Re-approval invalidates any earlier unredeemed pairing code.
create function public.sauli_register_kiosk_device(
  p_unit_id uuid,p_device_code text,p_hostname text,p_hardware_type text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_device public.kiosk_devices;
begin
  perform 1 from public.sauli_units where id = p_unit_id
    and status in ('provisioning','active') for update;
  if not found then return jsonb_build_object('error','UNIT_NOT_FOUND'); end if;
  insert into public.kiosk_devices(unit_id,device_code,hostname,hardware_type)
    values(p_unit_id,p_device_code,p_hostname,p_hardware_type)
    on conflict (device_code) do nothing returning * into v_device;
  if not found then return jsonb_build_object('error','DEVICE_EXISTS'); end if;
  insert into public.kiosk_device_events(device_id,event_type)
    values(v_device.id,'registered');
  return to_jsonb(v_device);
end; $$;

create function public.sauli_approve_kiosk_pairing(
  p_device_id uuid,p_request_hash text,p_actor uuid,p_expires_at timestamptz)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_device public.kiosk_devices; v_pair public.kiosk_pairing_requests;
begin
  select * into v_device from public.kiosk_devices where id = p_device_id for update;
  if not found or v_device.status <> 'pending' or
     not exists (select 1 from public.sauli_units where id = v_device.unit_id
       and status = 'active') or p_expires_at <= now() or
     p_expires_at > now() + interval '11 minutes' then
    return jsonb_build_object('error','PAIRING_DENIED');
  end if;
  update public.kiosk_pairing_requests set status = 'expired'
    where device_id = p_device_id and status = 'approved';
  insert into public.kiosk_pairing_requests(device_id,request_hash,status,
    expires_at,approved_by,approved_at)
    values(p_device_id,p_request_hash,'approved',p_expires_at,p_actor,now())
    returning * into v_pair;
  insert into public.kiosk_device_events(device_id,event_type,actor_user_id)
    values(p_device_id,'pairing_approved',p_actor);
  return jsonb_build_object('request_id',v_pair.id);
end; $$;

-- The existing singleton RPC is denied after the coordinated API rollout.
-- Its new form requires the authenticated device's server-derived unit UUID.
create function public.reserve_sauli_storage_slot(p_item jsonb,p_size text,p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_item public.found_items; v_slot public.storage_slots;
begin
  if p_size not in ('pocket','medium') or p_unit_id is null then
    raise exception 'INVALID_STORAGE_SIZE'; end if;
  if not exists (select 1 from public.sauli_units where id = p_unit_id and status = 'active') then
    raise exception 'UNIT_NOT_ACTIVE'; end if;
  select * into v_item from public.found_items
    where idempotency_key = (p_item->>'idempotency_key')::uuid for update;
  if found then
    if v_item.unit_id <> p_unit_id then raise exception 'CROSS_UNIT_ITEM'; end if;
    select * into v_slot from public.storage_slots where current_found_item_id = v_item.id;
    if not found then raise exception 'STORAGE_STATE_CONFLICT'; end if;
    return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
  end if;
  select * into v_slot from public.storage_slots
    where unit_id = p_unit_id and size_class = p_size and status = 'available' and is_active
    order by ordinal limit 1 for update skip locked;
  if not found then raise exception 'NO_AVAILABLE_STORAGE_SLOT'; end if;
  v_item := jsonb_populate_record(null::public.found_items,p_item);
  if v_item.unit_id is not null and v_item.unit_id <> p_unit_id then
    raise exception 'CROSS_UNIT_ITEM'; end if;
  v_item.unit_id := p_unit_id;
  v_item.storage_size := p_size;
  v_item.placement_status := 'reserved';
  v_item.placed_at := null;
  v_item.created_at := now(); v_item.updated_at := now();
  insert into public.found_items select (v_item).* returning * into v_item;
  update public.storage_slots set status = 'reserved',current_found_item_id = v_item.id,
    reserved_at = now(),occupied_at = null where id = v_slot.id returning * into v_slot;
  insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
    values(v_slot.id,v_item.id,'slot_reserved','kiosk_web'),
          (v_slot.id,v_item.id,'simulated_door_ready','web_simulation');
  return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
end; $$;

create function public.simulate_sauli_placement(p_item_id uuid,p_slot_code text,p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_item public.found_items; v_slot public.storage_slots;
begin
  select * into v_slot from public.storage_slots
    where unit_id = p_unit_id and code = p_slot_code for update;
  if not found or v_slot.current_found_item_id is distinct from p_item_id then
    raise exception 'SLOT_RESERVATION_MISMATCH'; end if;
  select * into v_item from public.found_items where id = p_item_id for update;
  if v_item.unit_id <> p_unit_id then raise exception 'CROSS_UNIT_ITEM'; end if;
  if v_slot.status = 'occupied' and v_item.placement_status = 'placed' then
    insert into public.matching_jobs(kind,found_item_id)
      values('item_placed',p_item_id) on conflict do nothing;
    return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot)); end if;
  if v_slot.status <> 'reserved' or v_item.placement_status <> 'reserved' then
    raise exception 'SLOT_RESERVATION_MISMATCH'; end if;
  update public.storage_slots set status = 'occupied',occupied_at = now()
    where id = v_slot.id returning * into v_slot;
  update public.found_items set placement_status = 'placed',placed_at = v_slot.occupied_at
    where id = p_item_id returning * into v_item;
  insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
    values(v_slot.id,p_item_id,'simulated_item_placed','web_simulation');
  insert into public.matching_jobs(kind,found_item_id)
    values('item_placed',p_item_id) on conflict do nothing;
  return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
end; $$;

-- Check the item's immutable unit before invoking the existing transactional
-- retrieval functions. An otherwise valid QR cannot open another cabinet.
create function public.sauli_validate_unit_retrieval(
  p_token_hash text,p_action_hash text,p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
begin
  if not exists (select 1 from public.retrieval_sessions rs
      join public.found_items fi on fi.id = rs.found_item_id
      join public.storage_slots ss on ss.current_found_item_id = fi.id
      where rs.token_hash = p_token_hash and fi.unit_id = p_unit_id
        and ss.unit_id = p_unit_id and ss.is_active and ss.status = 'occupied') then
    return jsonb_build_object('error','INVALID_RETRIEVAL_TOKEN');
  end if;
  return public.sauli_validate_retrieval(p_token_hash,p_action_hash);
end; $$;

create function public.sauli_simulate_unit_retrieval(
  p_session_id uuid,p_action_hash text,p_event text,p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
begin
  if not exists (select 1 from public.retrieval_sessions rs
      join public.found_items fi on fi.id = rs.found_item_id
      where rs.id = p_session_id and fi.unit_id = p_unit_id
        and ((rs.status = 'completed' and p_event = 'correct_item_lifted')
          or exists (select 1 from public.storage_slots ss
            where ss.current_found_item_id = fi.id and ss.unit_id = p_unit_id
              and ss.is_active and ss.status = 'occupied'))) then
    return jsonb_build_object('error','RETRIEVAL_NOT_FOUND');
  end if;
  return public.sauli_simulate_retrieval(p_session_id,p_action_hash,p_event);
end; $$;

-- Atomic single-use enrollment and browser handoff. Only the API service role
-- can invoke these; FastAPI checks the caller before calling them.
create function public.sauli_redeem_pairing(
  p_device_code text,p_request_hash text,p_secret_hash text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_device public.kiosk_devices; v_pair public.kiosk_pairing_requests;
begin
  select * into v_device from public.kiosk_devices where device_code = p_device_code for update;
  if not found or v_device.status <> 'pending' or
    not exists (select 1 from public.sauli_units where id = v_device.unit_id and status = 'active') then
    return jsonb_build_object('error','PAIRING_DENIED'); end if;
  select * into v_pair from public.kiosk_pairing_requests
    where device_id = v_device.id and request_hash = p_request_hash for update;
  if not found or v_pair.status <> 'approved' or v_pair.expires_at <= now() then
    return jsonb_build_object('error','PAIRING_DENIED'); end if;
  update public.kiosk_pairing_requests set status = 'redeemed',redeemed_at = now()
    where id = v_pair.id;
  insert into public.kiosk_device_credentials(device_id,secret_hash)
    values(v_device.id,p_secret_hash);
  update public.kiosk_devices set status = 'active' where id = v_device.id;
  insert into public.kiosk_device_events(device_id,event_type,actor_user_id)
    values(v_device.id,'credential_issued',v_pair.approved_by);
  return jsonb_build_object('device_id',v_device.id,'unit_id',v_device.unit_id,
    'unit_code',(select unit_code from public.sauli_units where id = v_device.unit_id));
end; $$;

create function public.sauli_redeem_browser_bootstrap(
  p_code_hash text,p_session_hash text,p_expires_at timestamptz)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_code public.kiosk_browser_bootstraps; v_device public.kiosk_devices;
begin
  select * into v_code from public.kiosk_browser_bootstraps
    where code_hash = p_code_hash for update;
  if not found or v_code.redeemed_at is not null or v_code.expires_at <= now()
    or p_expires_at <= now() or p_expires_at > now() + interval '12 hours' then
    return jsonb_build_object('error','BOOTSTRAP_DENIED'); end if;
  select * into v_device from public.kiosk_devices where id = v_code.device_id for update;
  if v_device.status <> 'active' or v_device.revoked_at is not null or
    not exists (select 1 from public.sauli_units where id = v_device.unit_id and status = 'active') then
    return jsonb_build_object('error','BOOTSTRAP_DENIED'); end if;
  update public.kiosk_browser_bootstraps set redeemed_at = now() where id = v_code.id;
  insert into public.kiosk_browser_sessions(device_id,token_hash,expires_at)
    values(v_device.id,p_session_hash,p_expires_at);
  insert into public.kiosk_device_events(device_id,event_type)
    values(v_device.id,'session_issued');
  return jsonb_build_object('device_id',v_device.id,'unit_id',v_device.unit_id,
    'unit_code',(select unit_code from public.sauli_units where id = v_device.unit_id));
end; $$;

create function public.sauli_rotate_device_credential(
  p_device_id uuid,p_old_hash text,p_new_hash text)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare v_old uuid;
begin
  perform 1 from public.kiosk_devices where id = p_device_id and status = 'active'
    and revoked_at is null for update;
  if not found then return false; end if;
  select id into v_old from public.kiosk_device_credentials
    where device_id = p_device_id and secret_hash = p_old_hash
      and revoked_at is null and (expires_at is null or expires_at > now()) for update;
  if not found then return false; end if;
  update public.kiosk_device_credentials set revoked_at = now() where id = v_old;
  insert into public.kiosk_device_credentials(device_id,secret_hash)
    values(p_device_id,p_new_hash);
  insert into public.kiosk_device_events(device_id,event_type)
    values(p_device_id,'credential_rotated');
  return true;
end; $$;

create function public.sauli_revoke_device(p_device_id uuid,p_actor uuid)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
  perform 1 from public.kiosk_devices where id = p_device_id for update;
  if not found then return false; end if;
  update public.kiosk_devices set status = 'revoked',revoked_at = now()
    where id = p_device_id and status <> 'revoked';
  update public.kiosk_device_credentials set revoked_at = now()
    where device_id = p_device_id and revoked_at is null;
  update public.kiosk_browser_sessions set revoked_at = now()
    where device_id = p_device_id and revoked_at is null;
  update public.kiosk_pairing_requests set status = 'rejected'
    where device_id = p_device_id and status in ('pending','approved');
  insert into public.kiosk_device_events(device_id,event_type,actor_user_id)
    values(p_device_id,'revoked',p_actor);
  return true;
end; $$;

insert into public.kiosk_devices(unit_id,device_code,hostname,hardware_type)
select id,'KIOSK-LSPUSPCC-ENGINEERING-01','sauli-lspuspcc','Raspberry Pi 4 Model B, 4GB'
  from public.sauli_units where unit_code = 'SAULI-LSPUSPCC-001';
insert into public.kiosk_device_events(device_id,event_type)
  select id,'registered' from public.kiosk_devices
  where device_code = 'KIOSK-LSPUSPCC-ENGINEERING-01';

-- All privileged tables remain service-role only; no browser table access.
alter table public.sauli_units enable row level security;
alter table public.sauli_deployment_guard enable row level security;
alter table public.kiosk_devices enable row level security;
alter table public.kiosk_device_credentials enable row level security;
alter table public.kiosk_pairing_requests enable row level security;
alter table public.kiosk_browser_bootstraps enable row level security;
alter table public.kiosk_browser_sessions enable row level security;
alter table public.kiosk_device_events enable row level security;
alter table public.kiosk_rate_limits enable row level security;
revoke all on public.sauli_deployment_guard,public.sauli_units,public.kiosk_devices,public.kiosk_device_credentials,
  public.kiosk_pairing_requests,public.kiosk_browser_bootstraps,
  public.kiosk_browser_sessions,public.kiosk_device_events,public.kiosk_rate_limits
  from anon,authenticated;
grant all on public.sauli_deployment_guard,public.sauli_units,public.kiosk_devices,public.kiosk_device_credentials,
  public.kiosk_pairing_requests,public.kiosk_browser_bootstraps,
  public.kiosk_browser_sessions,public.kiosk_device_events,public.kiosk_rate_limits
  to service_role;
grant usage,select on sequence public.kiosk_device_events_id_seq to service_role;
revoke all on function public.sauli_provision_unit_slots(uuid),
  public.sauli_register_unit(jsonb),
  public.sauli_register_kiosk_device(uuid,text,text,text),
  public.sauli_approve_kiosk_pairing(uuid,text,uuid,timestamptz),
  public.reserve_sauli_storage_slot(jsonb,text,uuid),
  public.simulate_sauli_placement(uuid,text,uuid),
  public.sauli_validate_unit_retrieval(text,text,uuid),
  public.sauli_simulate_unit_retrieval(uuid,text,text,uuid),
  public.sauli_redeem_pairing(text,text,text),
  public.sauli_redeem_browser_bootstrap(text,text,timestamptz),
  public.sauli_rotate_device_credential(uuid,text,text),
  public.sauli_revoke_device(uuid,uuid),
  public.sauli_check_kiosk_rate_limit(text,text,integer,integer)
  from public,anon,authenticated;
grant execute on function public.sauli_provision_unit_slots(uuid),
  public.sauli_register_unit(jsonb),
  public.sauli_register_kiosk_device(uuid,text,text,text),
  public.sauli_approve_kiosk_pairing(uuid,text,uuid,timestamptz),
  public.reserve_sauli_storage_slot(jsonb,text,uuid),
  public.simulate_sauli_placement(uuid,text,uuid),
  public.sauli_validate_unit_retrieval(text,text,uuid),
  public.sauli_simulate_unit_retrieval(uuid,text,text,uuid),
  public.sauli_redeem_pairing(text,text,text),
  public.sauli_redeem_browser_bootstrap(text,text,timestamptz),
  public.sauli_rotate_device_credential(uuid,text,text),
  public.sauli_revoke_device(uuid,uuid),
  public.sauli_check_kiosk_rate_limit(text,text,integer,integer) to service_role;
revoke all on function public.reserve_sauli_storage_slot(jsonb,text),
  public.simulate_sauli_placement(uuid,text) from public,anon,authenticated,service_role;

-- Abort if existing occupancy is inconsistent or the first cabinet is not 8+4.
do $$ begin
  if exists (select 1 from public.storage_slots ss join public.found_items fi
      on fi.id = ss.current_found_item_id where ss.unit_id <> fi.unit_id)
    or (select count(*) from public.storage_slots where is_active) <> 12
    or exists (select 1 from public.storage_slots
      where code in ('P-09','P-10','M-05') and status = 'reserved') then
    raise exception 'LEGACY_STORAGE_REQUIRES_OPERATOR_REVIEW';
  end if;
end $$;
commit;
