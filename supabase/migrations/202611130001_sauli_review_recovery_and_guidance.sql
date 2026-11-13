begin;

-- A transaction awaiting operator review is not itself a security incident.
-- Only a recorded, active incident may drive the buzzer or an SOS slot light.
create or replace function public.sauli_hardware_guidance(p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_slot record; v_assigned uuid; v_deposit uuid; v_retrieval uuid;
  v_modes jsonb := '{}'::jsonb; v_buzzer boolean := false;
  v_review_required boolean := false; v_mode text;
begin
  select rs.id,ss.id into v_retrieval,v_assigned from public.retrieval_sessions rs
    join public.found_items fi on fi.id = rs.found_item_id
    join public.storage_slots ss on ss.current_found_item_id = fi.id
    where fi.unit_id = p_unit_id and rs.status = 'validated'
    order by rs.validated_at desc limit 1;
  if v_assigned is null then
    select ss.current_found_item_id,ss.id into v_deposit,v_assigned
      from public.storage_slots ss where ss.unit_id = p_unit_id and ss.status = 'reserved'
      order by ss.reserved_at desc limit 1;
  end if;
  select exists(select 1 from public.sauli_hardware_incidents
    where unit_id = p_unit_id and active) into v_buzzer;
  select exists(select 1 from public.sauli_hardware_transactions
    where unit_id = p_unit_id and phase = 'requires_review') into v_review_required;
  for v_slot in select ss.id,ss.code,ss.status,coalesce(hp.present,false) as present
    from public.storage_slots ss left join public.sauli_hardware_presence hp
      on hp.slot_id = ss.id and hp.unit_id = ss.unit_id
    where ss.unit_id = p_unit_id and ss.is_active loop
    v_mode := case
      when exists(select 1 from public.sauli_hardware_incidents
        where unit_id = p_unit_id and slot_id = v_slot.id and active) then 'SOS_BLINK'
      when v_deposit is not null and v_slot.id = v_assigned and v_buzzer then 'SOS_BLINK'
      when v_assigned = v_slot.id and v_deposit is not null and v_slot.present then 'STEADY_ON'
      when v_assigned = v_slot.id then 'NORMAL_BLINK'
      when v_slot.present or v_slot.status = 'occupied' then 'STEADY_ON'
      else 'OFF' end;
    v_modes := v_modes || jsonb_build_object(v_slot.code,v_mode);
  end loop;
  return jsonb_build_object('modes',v_modes,'buzzer',v_buzzer,
    'review_required',v_review_required,
    'deposit_item_id',v_deposit,'retrieval_session_id',v_retrieval);
end $$;

-- Keep an independent audit trail for a manual rearm of a transaction whose
-- door has never opened. A later normal workflow still records the outcome.
create table public.sauli_hardware_review_resolutions (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references public.sauli_units(id),
  assigned_slot_id uuid not null references public.storage_slots(id),
  actor_id uuid not null,
  reason text not null check (char_length(btrim(reason)) between 20 and 500),
  previous_phase text not null,
  previous_command_id text,
  resolved_at timestamptz not null default now()
);
alter table public.sauli_hardware_review_resolutions enable row level security;
revoke all on public.sauli_hardware_review_resolutions from anon, authenticated;
grant all on public.sauli_hardware_review_resolutions to service_role;

create function public.sauli_rearm_unopened_hardware_review(
  p_unit_id uuid, p_actor_id uuid, p_reason text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_tx public.sauli_hardware_transactions;
  v_slot public.storage_slots;
  v_device public.kiosk_devices;
  v_snapshot public.sauli_hardware_snapshots;
  v_readings jsonb;
  v_reading jsonb;
  v_presence public.sauli_hardware_presence;
  v_resolution_id uuid;
begin
  if p_actor_id is null or p_reason is null
     or char_length(btrim(p_reason)) not between 20 and 500 then
    return jsonb_build_object('error','INVALID_REVIEW_REASON');
  end if;
  -- This lock matches the workflow/presence functions' unit-level lock.
  perform 1 from public.sauli_units where id = p_unit_id and status = 'active' for update;
  if not found then return jsonb_build_object('error','UNIT_UNAVAILABLE'); end if;
  select * into v_tx from public.sauli_hardware_transactions
    where unit_id = p_unit_id for update;
  if v_tx.unit_id is null or v_tx.phase is distinct from 'requires_review'
     or v_tx.last_door is distinct from 'closed' or v_tx.opened_at is not null
     or v_tx.closed_at is not null then
    return jsonb_build_object('error','REVIEW_NOT_ELIGIBLE');
  end if;
  select * into v_slot from public.storage_slots
    where id = v_tx.assigned_slot_id and unit_id = p_unit_id and is_active for update;
  if v_slot.id is null then return jsonb_build_object('error','SLOT_UNAVAILABLE'); end if;
  if v_tx.found_item_id is not null then
    if v_slot.status <> 'reserved' or
       v_slot.current_found_item_id is distinct from v_tx.found_item_id or
       not exists(select 1 from public.found_items
         where id = v_tx.found_item_id and unit_id = p_unit_id
           and placement_status = 'reserved') then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  elsif v_tx.retrieval_session_id is not null then
    if v_slot.status <> 'occupied' or
       not exists(select 1 from public.retrieval_sessions rs
         join public.found_items fi on fi.id = rs.found_item_id
         where rs.id = v_tx.retrieval_session_id and rs.status = 'validated'
           and fi.unit_id = p_unit_id and fi.id = v_slot.current_found_item_id) then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  else
    return jsonb_build_object('error','WORKFLOW_CHANGED');
  end if;
  if exists(select 1 from public.sauli_hardware_incidents
      where unit_id = p_unit_id and active)
     or exists(select 1 from public.sauli_hardware_commands
       where unit_id = p_unit_id and action in ('pulse_pocket','pulse_medium')
         and status in ('pending','claimed') and expires_at > now()) then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  select * into v_device from public.kiosk_devices
    where unit_id = p_unit_id and is_primary and status = 'active'
      and revoked_at is null limit 1;
  if v_device.id is null then return jsonb_build_object('error','DEVICE_UNAVAILABLE'); end if;
  select * into v_snapshot from public.sauli_hardware_snapshots
    where unit_id = p_unit_id and device_id = v_device.id
      and received_at between now()-interval '5 seconds' and now()+interval '5 seconds';
  if v_snapshot.device_id is null or
     v_snapshot.snapshot #>> '{pi,mode}' is distinct from 'real' or
     v_snapshot.snapshot #>> '{esp,connection}' is distinct from 'online' or
     nullif(v_snapshot.snapshot #>> '{esp,boot_id}','') is null or
     v_snapshot.snapshot #>> '{pi,doors,pocket,door}' is distinct from 'closed' or
     v_snapshot.snapshot #>> '{pi,doors,medium,door}' is distinct from 'closed' or
     v_snapshot.snapshot #>> '{pi,doors,pocket,raw_level}' is null or
     v_snapshot.snapshot #>> '{pi,doors,medium,raw_level}' is null or
     v_snapshot.snapshot #>> '{pi,outputs,pocket_solenoid}' is distinct from 'false' or
     v_snapshot.snapshot #>> '{pi,outputs,medium_solenoid}' is distinct from 'false' or
     v_snapshot.snapshot #>> '{door_workflow,phase}' not in ('idle','completed') or
     v_snapshot.snapshot #>> '{door_workflow,phase}' is null or
     v_snapshot.snapshot #>> '{last_unlock,last_output_error}' is not null or
     v_snapshot.snapshot->>'pending_presence_count' is distinct from '0' then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if (v_snapshot.snapshot #>> '{esp,telemetry_at}') is null or
     (v_snapshot.snapshot #>> '{esp,telemetry_at}')::timestamptz
       not between now()-interval '5 seconds' and now()+interval '5 seconds' then
    return jsonb_build_object('error','STALE_TELEMETRY');
  end if;
  v_readings := v_snapshot.snapshot #> '{esp,telemetry,slots}';
  if jsonb_typeof(v_readings) is distinct from 'array' or
     (select count(*) from public.storage_slots
       where unit_id = p_unit_id and is_active) <> 12 then
    return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
  end if;
  if jsonb_array_length(v_readings) <> 12 then
    return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
  end if;
  for v_slot in select * from public.storage_slots
      where unit_id = p_unit_id and is_active loop
    if (select count(*) from jsonb_array_elements(v_readings) as r(value)
        where r.value->>'code' = v_slot.code) <> 1 then
      return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
    end if;
    select r.value into v_reading from jsonb_array_elements(v_readings) as r(value)
      where r.value->>'code' = v_slot.code;
    select * into v_presence from public.sauli_hardware_presence
      where unit_id = p_unit_id and slot_id = v_slot.id;
    if v_presence.slot_id is null or
       v_presence.boot_id is distinct from (v_snapshot.snapshot #>> '{esp,boot_id}') or
       v_presence.present is distinct from (v_slot.status = 'occupied') or
       v_reading->>'ready' is distinct from 'true' or
       nullif(v_reading->>'fault','') is not null or
       v_reading->>'present' is distinct from v_presence.present::text then
      return jsonb_build_object('error','HARDWARE_NOT_SAFE');
    end if;
  end loop;
  insert into public.sauli_hardware_review_resolutions
    (unit_id,assigned_slot_id,actor_id,reason,previous_phase,previous_command_id)
    values(p_unit_id,v_tx.assigned_slot_id,p_actor_id,btrim(p_reason),
      v_tx.phase,v_tx.command_id) returning id into v_resolution_id;
  update public.sauli_hardware_transactions set
    phase = 'awaiting_door_open', command_id = null,
    close_telemetry_seq = null, close_boot_id = null, updated_at = now()
    where unit_id = p_unit_id;
  return jsonb_build_object('status','rearmed','resolution_id',v_resolution_id);
end $$;
revoke all on function public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)
  from public,anon,authenticated;
grant execute on function public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)
  to service_role;

commit;
