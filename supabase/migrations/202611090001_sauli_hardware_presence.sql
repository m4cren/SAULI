begin;

alter table public.sauli_hardware_commands drop constraint sauli_hardware_commands_action_check;
alter table public.sauli_hardware_commands add constraint sauli_hardware_commands_action_check
  check (action in ('pulse_pocket','pulse_medium','capture_light_on','capture_light_off'));

-- Physical observations are separate from the authoritative slot assignment.
create table public.sauli_hardware_presence (
  unit_id uuid not null references public.sauli_units(id),
  slot_id uuid not null references public.storage_slots(id),
  device_id uuid not null references public.kiosk_devices(id),
  boot_id text not null,
  last_sequence bigint not null,
  present boolean not null,
  observed_at timestamptz not null default now(),
  primary key (unit_id,slot_id)
);
create table public.sauli_hardware_presence_events (
  device_id uuid not null references public.kiosk_devices(id),
  event_id text not null,
  unit_id uuid not null references public.sauli_units(id),
  slot_id uuid not null references public.storage_slots(id),
  kind text not null,
  outcome text not null,
  created_at timestamptz not null default now(),
  primary key (device_id,event_id)
);
create table public.sauli_hardware_incidents (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid not null references public.sauli_units(id),
  slot_id uuid not null references public.storage_slots(id),
  assigned_slot_id uuid not null references public.storage_slots(id),
  found_item_id uuid references public.found_items(id),
  retrieval_session_id uuid references public.retrieval_sessions(id),
  kind text not null check (kind in ('wrong_placement','wrong_removal')),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  check ((found_item_id is not null) <> (retrieval_session_id is not null))
);
create unique index sauli_hardware_incidents_active_slot
  on public.sauli_hardware_incidents(unit_id,slot_id) where active;

alter table public.storage_slot_events drop constraint storage_slot_events_event_type_check;
alter table public.storage_slot_events add constraint storage_slot_events_event_type_check
  check (event_type in ('slot_reserved','simulated_door_ready','simulated_item_placed',
    'reservation_released','slot_out_of_service','hardware_item_placed'));
alter table public.retrieval_events drop constraint retrieval_events_event_type_check;
alter table public.retrieval_events add constraint retrieval_events_event_type_check
  check (event_type in ('qr_issued','qr_replaced','qr_validated','qr_expired','qr_rejected',
    'simulated_door_ready','simulated_correct_item_lifted','simulated_wrong_item_lifted',
    'simulated_item_returned','retrieval_completed','retrieval_cancelled',
    'hardware_correct_item_lifted','hardware_wrong_item_lifted','hardware_item_returned'));

create function public.sauli_apply_hardware_presence(
  p_device_id uuid,p_event_id text,p_boot_id text,p_sequence bigint,
  p_slot_code text,p_kind text,p_present boolean)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_unit uuid; v_slot public.storage_slots; v_previous public.sauli_hardware_presence;
  v_item public.found_items; v_session public.retrieval_sessions;
  v_assigned public.storage_slots; v_incident public.sauli_hardware_incidents;
  v_outcome text := 'observed'; v_completed_at timestamptz;
begin
  if p_event_id !~ '^[a-zA-Z0-9_-]{1,80}$' or p_boot_id !~ '^[a-zA-Z0-9_-]{1,40}$'
     or p_sequence < 1 or p_kind not in ('SENSOR_SNAPSHOT','ITEM_PRESENT','ITEM_REMOVED')
     or (p_kind = 'ITEM_PRESENT' and not p_present)
     or (p_kind = 'ITEM_REMOVED' and p_present) then
    return jsonb_build_object('error','INVALID_SENSOR_EVENT');
  end if;
  select d.unit_id into v_unit from public.kiosk_devices d
    join public.sauli_units u on u.id = d.unit_id
    where d.id = p_device_id and d.status = 'active' and d.revoked_at is null
      and u.status = 'active' for share of d;
  if v_unit is null then return jsonb_build_object('error','DEVICE_ACCESS_DENIED'); end if;
  -- Serialise observations for this cabinet before reading mutable slot state.
  perform 1 from public.sauli_units where id = v_unit for update;
  select * into v_slot from public.storage_slots
    where unit_id = v_unit and code = p_slot_code and is_active for update;
  if not found then return jsonb_build_object('error','UNKNOWN_SLOT'); end if;
  if exists (select 1 from public.sauli_hardware_presence_events
      where device_id = p_device_id and event_id = p_event_id) then
    return jsonb_build_object('outcome','duplicate');
  end if;
  select * into v_previous from public.sauli_hardware_presence
    where unit_id = v_unit and slot_id = v_slot.id for update;
  if v_previous.slot_id is null or v_previous.boot_id <> p_boot_id then
    -- A boot snapshot is a baseline, never evidence of a fresh placement/removal.
    insert into public.sauli_hardware_presence(unit_id,slot_id,device_id,boot_id,last_sequence,present)
      values(v_unit,v_slot.id,p_device_id,p_boot_id,p_sequence,p_present)
      on conflict (unit_id,slot_id) do update set device_id = excluded.device_id,
        boot_id = excluded.boot_id,last_sequence = excluded.last_sequence,
        present = excluded.present,observed_at = now();
    v_outcome := 'baseline';
  elsif p_sequence <= v_previous.last_sequence then
    v_outcome := 'stale';
  elsif p_kind = 'SENSOR_SNAPSHOT' then
    -- Reconciliation is visible to operators but cannot finalize a transaction.
    update public.sauli_hardware_presence set last_sequence = p_sequence,
      present = p_present,observed_at = now() where unit_id = v_unit and slot_id = v_slot.id;
    v_outcome := 'snapshot';
  elsif v_previous.present = p_present then
    update public.sauli_hardware_presence set last_sequence = p_sequence,
      observed_at = now() where unit_id = v_unit and slot_id = v_slot.id;
    v_outcome := 'unchanged';
  else
    update public.sauli_hardware_presence set last_sequence = p_sequence,
      present = p_present,observed_at = now() where unit_id = v_unit and slot_id = v_slot.id;
    -- One active retrieval per unit is required to infer the authorized slot.
    select rs.* into v_session from public.retrieval_sessions rs
      join public.found_items fi on fi.id = rs.found_item_id
      where fi.unit_id = v_unit and rs.status = 'validated'
      order by rs.validated_at desc limit 1 for update of rs;
    if v_session.id is not null then
      select * into v_item from public.found_items where id = v_session.found_item_id for update;
      select * into v_assigned from public.storage_slots
        where unit_id = v_unit and current_found_item_id = v_item.id for update;
      if v_assigned.id is not null and v_slot.id <> v_assigned.id and not p_present
         and v_slot.status = 'occupied' then
        insert into public.sauli_hardware_incidents(unit_id,slot_id,assigned_slot_id,
          retrieval_session_id,kind) values(v_unit,v_slot.id,v_assigned.id,v_session.id,'wrong_removal')
          on conflict do nothing;
        insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
          values(v_session.id,v_item.id,v_slot.id,'hardware_wrong_item_lifted','esp32_switch');
        v_outcome := 'wrong_removal';
      elsif p_present and v_slot.id <> v_assigned.id then
        update public.sauli_hardware_incidents set active = false,resolved_at = now()
          where unit_id = v_unit and slot_id = v_slot.id and retrieval_session_id = v_session.id
            and kind = 'wrong_removal' and active;
        if found then
          insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
            values(v_session.id,v_item.id,v_slot.id,'hardware_item_returned','esp32_switch');
          v_outcome := 'wrong_item_returned';
        end if;
      elsif not p_present and v_slot.id = v_assigned.id and v_slot.status = 'occupied'
          and v_item.status = 'claimed' and v_item.placement_status = 'placed'
          and not exists (select 1 from public.sauli_hardware_incidents
            where unit_id = v_unit and retrieval_session_id = v_session.id and active) then
        v_completed_at := now();
        update public.found_items set status = 'retrieved' where id = v_item.id;
        update public.storage_slots set status = 'available',current_found_item_id = null,
          reserved_at = null,occupied_at = null where id = v_slot.id;
        update public.retrieval_sessions set status = 'completed',completed_at = v_completed_at
          where id = v_session.id;
        insert into public.retrieval_logs(retrieval_session_id,found_item_id,claimant_user_id,
          storage_slot_id,slot_code,item_summary,retriever,retrieved_at,completion_source)
          values(v_session.id,v_item.id,v_session.claimant_user_id,v_slot.id,v_slot.code,
            v_item.object_name,v_session.claimant_display_name,v_completed_at,'esp32_switch');
        insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
          values(v_session.id,v_item.id,v_slot.id,'hardware_correct_item_lifted','esp32_switch'),
            (v_session.id,v_item.id,v_slot.id,'retrieval_completed','esp32_switch');
        v_outcome := 'retrieved';
      end if;
    else
      select * into v_assigned from public.storage_slots
        where unit_id = v_unit and status = 'reserved'
        order by reserved_at desc limit 1 for update;
      if v_assigned.id is not null then
        select * into v_item from public.found_items
          where id = v_assigned.current_found_item_id for update;
        if p_present and v_slot.id <> v_assigned.id and v_slot.status = 'available' then
          insert into public.sauli_hardware_incidents(unit_id,slot_id,assigned_slot_id,
            found_item_id,kind) values(v_unit,v_slot.id,v_assigned.id,v_item.id,'wrong_placement')
            on conflict do nothing;
          v_outcome := 'wrong_placement';
        elsif not p_present and v_slot.id <> v_assigned.id then
          update public.sauli_hardware_incidents set active = false,resolved_at = now()
            where unit_id = v_unit and slot_id = v_slot.id and found_item_id = v_item.id
              and kind = 'wrong_placement' and active;
          if found then v_outcome := 'wrong_placement_cleared'; end if;
        elsif p_present and v_slot.id = v_assigned.id and v_item.placement_status = 'reserved'
            and not exists (select 1 from public.sauli_hardware_incidents
              where unit_id = v_unit and found_item_id = v_item.id and active) then
          update public.storage_slots set status = 'occupied',occupied_at = now()
            where id = v_slot.id returning * into v_slot;
          update public.found_items set placement_status = 'placed',placed_at = v_slot.occupied_at
            where id = v_item.id;
          insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
            values(v_slot.id,v_item.id,'hardware_item_placed','esp32_switch');
          insert into public.matching_jobs(kind,found_item_id)
            values('item_placed',v_item.id) on conflict do nothing;
          v_outcome := 'placed';
        end if;
      end if;
    end if;
  end if;
  insert into public.sauli_hardware_presence_events(device_id,event_id,unit_id,slot_id,kind,outcome)
    values(p_device_id,p_event_id,v_unit,v_slot.id,p_kind,v_outcome);
  return jsonb_build_object('outcome',v_outcome,'slot',p_slot_code);
end $$;

create function public.sauli_hardware_guidance(p_unit_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_slot record; v_assigned uuid; v_deposit uuid; v_retrieval uuid;
  v_modes jsonb := '{}'::jsonb; v_buzzer boolean := false; v_mode text;
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
    where unit_id = p_unit_id and active and
      (found_item_id = v_deposit or retrieval_session_id = v_retrieval)) into v_buzzer;
  for v_slot in select ss.id,ss.code,ss.status,coalesce(hp.present,false) as present
    from public.storage_slots ss left join public.sauli_hardware_presence hp
      on hp.slot_id = ss.id and hp.unit_id = ss.unit_id
    where ss.unit_id = p_unit_id and ss.is_active loop
    v_mode := case
      when v_retrieval is not null and exists(select 1 from public.sauli_hardware_incidents
        where unit_id = p_unit_id and retrieval_session_id = v_retrieval
          and slot_id = v_slot.id and active) then 'SOS_BLINK'
      when v_deposit is not null and v_slot.id = v_assigned and v_buzzer then 'SOS_BLINK'
      when v_assigned = v_slot.id then 'NORMAL_BLINK'
      when v_slot.present or v_slot.status = 'occupied' then 'STEADY_ON'
      else 'OFF' end;
    v_modes := v_modes || jsonb_build_object(v_slot.code,v_mode);
  end loop;
  return jsonb_build_object('modes',v_modes,'buzzer',v_buzzer,
    'deposit_item_id',v_deposit,'retrieval_session_id',v_retrieval);
end $$;

alter table public.sauli_hardware_presence enable row level security;
alter table public.sauli_hardware_presence_events enable row level security;
alter table public.sauli_hardware_incidents enable row level security;
revoke all on public.sauli_hardware_presence,public.sauli_hardware_presence_events,
  public.sauli_hardware_incidents from anon,authenticated;
grant all on public.sauli_hardware_presence,public.sauli_hardware_presence_events,
  public.sauli_hardware_incidents to service_role;
revoke all on function public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean),
  public.sauli_hardware_guidance(uuid) from public,anon,authenticated;
grant execute on function public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean),
  public.sauli_hardware_guidance(uuid) to service_role;
commit;
