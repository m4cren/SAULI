begin;

-- The presence edge is provisional. The group reed and a later, complete ESP
-- snapshot are required before either operational record can be committed.
create table public.sauli_hardware_transactions (
  unit_id uuid primary key references public.sauli_units(id),
  assigned_slot_id uuid not null references public.storage_slots(id),
  found_item_id uuid references public.found_items(id),
  retrieval_session_id uuid references public.retrieval_sessions(id),
  phase text not null default 'awaiting_door_open' check (phase in
    ('awaiting_door_open','door_open','provisional_success','warning_active',
     'awaiting_door_close','requires_review','completed')),
  last_door text not null default 'unknown' check (last_door in ('unknown','open','closed')),
  opened_at timestamptz,
  closed_at timestamptz,
  close_telemetry_seq bigint,
  close_boot_id text,
  command_id text,
  updated_at timestamptz not null default now(),
  check ((found_item_id is not null) <> (retrieval_session_id is not null))
);
alter table public.sauli_hardware_transactions enable row level security;
revoke all on public.sauli_hardware_transactions from anon,authenticated;
grant all on public.sauli_hardware_transactions to service_role;

create or replace function public.sauli_apply_hardware_presence(
  p_device_id uuid,p_event_id text,p_boot_id text,p_sequence bigint,
  p_slot_code text,p_kind text,p_present boolean)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_unit uuid; v_slot public.storage_slots; v_previous public.sauli_hardware_presence;
  v_item public.found_items; v_session public.retrieval_sessions;
  v_assigned public.storage_slots; v_outcome text := 'observed';
  v_incident public.sauli_hardware_incidents;
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
    insert into public.sauli_hardware_presence(unit_id,slot_id,device_id,boot_id,last_sequence,present)
      values(v_unit,v_slot.id,p_device_id,p_boot_id,p_sequence,p_present)
      on conflict (unit_id,slot_id) do update set device_id = excluded.device_id,
        boot_id = excluded.boot_id,last_sequence = excluded.last_sequence,
        present = excluded.present,observed_at = now();
    v_outcome := 'baseline';
  elsif p_sequence <= v_previous.last_sequence then
    v_outcome := 'stale';
  else
    update public.sauli_hardware_presence set last_sequence = p_sequence,
      present = p_present,observed_at = now() where unit_id = v_unit and slot_id = v_slot.id;
    if p_kind = 'SENSOR_SNAPSHOT' then
      v_outcome := 'snapshot';
    elsif v_previous.present = p_present then
      v_outcome := 'unchanged';
    else
      select rs.* into v_session from public.retrieval_sessions rs
        join public.found_items fi on fi.id = rs.found_item_id
        where fi.unit_id = v_unit and rs.status = 'validated'
        order by rs.validated_at desc limit 1 for update of rs;
      if v_session.id is not null then
        select * into v_item from public.found_items where id = v_session.found_item_id for update;
        select * into v_assigned from public.storage_slots
          where unit_id = v_unit and current_found_item_id = v_item.id for update;
      else
        select * into v_assigned from public.storage_slots
          where unit_id = v_unit and status = 'reserved'
          order by reserved_at desc limit 1 for update;
        if v_assigned.id is not null then
          select * into v_item from public.found_items where id = v_assigned.current_found_item_id for update;
        end if;
      end if;
      if v_assigned.id is not null then
        -- Every slot stays under surveillance, including after a correct edge.
        if v_slot.id <> v_assigned.id then
          if not p_present and v_slot.status = 'occupied' then
            insert into public.sauli_hardware_incidents(unit_id,slot_id,assigned_slot_id,
              found_item_id,retrieval_session_id,kind)
              values(v_unit,v_slot.id,v_assigned.id,
                case when v_session.id is null then v_item.id else null end,
                v_session.id,'wrong_removal') on conflict do nothing;
            v_outcome := 'wrong_removal';
          elsif p_present and v_slot.status = 'available' then
            insert into public.sauli_hardware_incidents(unit_id,slot_id,assigned_slot_id,
              found_item_id,retrieval_session_id,kind)
              values(v_unit,v_slot.id,v_assigned.id,
                case when v_session.id is null then v_item.id else null end,
                v_session.id,'wrong_placement') on conflict do nothing;
            v_outcome := 'wrong_placement';
          else
            update public.sauli_hardware_incidents set active = false,resolved_at = now()
              where unit_id = v_unit and slot_id = v_slot.id and active
                and ((v_session.id is not null and retrieval_session_id = v_session.id)
                  or (v_session.id is null and found_item_id = v_item.id))
                and ((kind = 'wrong_removal' and p_present)
                  or (kind = 'wrong_placement' and not p_present));
            if found then v_outcome := 'wrong_item_restored'; end if;
          end if;
        elsif v_session.id is null then
          if p_present then
            update public.sauli_hardware_incidents set active = false,resolved_at = now()
              where unit_id = v_unit and slot_id = v_slot.id and found_item_id = v_item.id
                and kind = 'wrong_removal' and active;
            v_outcome := 'provisional_placement';
          elsif v_previous.present then
            insert into public.sauli_hardware_incidents(unit_id,slot_id,assigned_slot_id,
              found_item_id,kind)
              values(v_unit,v_slot.id,v_assigned.id,v_item.id,'wrong_removal')
              on conflict do nothing;
            v_outcome := 'placement_reversed';
          end if;
        else
          v_outcome := case when p_present then 'retrieval_reversed' else 'provisional_retrieval' end;
        end if;
      end if;
    end if;
  end if;
  insert into public.sauli_hardware_presence_events(device_id,event_id,unit_id,slot_id,kind,outcome)
    values(p_device_id,p_event_id,v_unit,v_slot.id,p_kind,v_outcome);
  if v_session.id is not null then
    update public.retrieval_sessions set wrong_item_out = exists (
      select 1 from public.sauli_hardware_incidents
      where retrieval_session_id = v_session.id and active)
      where id = v_session.id;
  end if;
  return jsonb_build_object('outcome',v_outcome,'slot',p_slot_code);
end $$;

create or replace function public.sauli_hardware_guidance(p_unit_id uuid)
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
    where unit_id = p_unit_id and active)
    or exists(select 1 from public.sauli_hardware_transactions
      where unit_id = p_unit_id and phase = 'requires_review') into v_buzzer;
  for v_slot in select ss.id,ss.code,ss.status,coalesce(hp.present,false) as present
    from public.storage_slots ss left join public.sauli_hardware_presence hp
      on hp.slot_id = ss.id and hp.unit_id = ss.unit_id
    where ss.unit_id = p_unit_id and ss.is_active loop
    v_mode := case
      when exists(select 1 from public.sauli_hardware_incidents
        where unit_id = p_unit_id and slot_id = v_slot.id and active) then 'SOS_BLINK'
      when v_deposit is not null and v_slot.id = v_assigned and v_buzzer then 'SOS_BLINK'
      when v_assigned = v_slot.id then 'NORMAL_BLINK'
      when v_slot.present or v_slot.status = 'occupied' then 'STEADY_ON'
      else 'OFF' end;
    v_modes := v_modes || jsonb_build_object(v_slot.code,v_mode);
  end loop;
  return jsonb_build_object('modes',v_modes,'buzzer',v_buzzer,
    'deposit_item_id',v_deposit,'retrieval_session_id',v_retrieval);
end $$;

-- Heartbeats and presence events share the unit lock. Completion cannot race an
-- already delivered observation, and a fresh post-close telemetry frame is
-- required before the database accepts the final physical configuration.
create function public.sauli_reconcile_hardware_workflow(p_device_id uuid,p_snapshot jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_unit uuid; v_item public.found_items; v_session public.retrieval_sessions;
  v_slot public.storage_slots; v_tx public.sauli_hardware_transactions;
  v_door text; v_group text; v_start timestamptz; v_telemetry jsonb;
  v_boot text; v_seq bigint; v_telemetry_at timestamptz;
  v_pending integer; v_present boolean; v_warning boolean; v_mismatch boolean;
  v_phase text; v_completed_at timestamptz; v_authorized_open boolean;
  v_authorized_close boolean;
begin
  select d.unit_id into v_unit from public.kiosk_devices d
    join public.sauli_units u on u.id = d.unit_id
    where d.id = p_device_id and d.status = 'active' and d.revoked_at is null
      and u.status = 'active' for share of d;
  if v_unit is null then return jsonb_build_object('error','DEVICE_ACCESS_DENIED'); end if;
  perform 1 from public.sauli_units where id = v_unit for update;
  insert into public.sauli_hardware_snapshots(device_id,unit_id,snapshot,received_at)
    values(p_device_id,v_unit,p_snapshot,now())
    on conflict (device_id) do update set snapshot=excluded.snapshot,received_at=excluded.received_at;

  select rs.* into v_session from public.retrieval_sessions rs
    join public.found_items fi on fi.id = rs.found_item_id
    where fi.unit_id = v_unit and rs.status = 'validated'
    order by rs.validated_at desc limit 1 for update of rs;
  if v_session.id is not null then
    select * into v_item from public.found_items where id = v_session.found_item_id for update;
    select * into v_slot from public.storage_slots
      where unit_id = v_unit and current_found_item_id = v_item.id for update;
    v_start := v_session.validated_at;
  else
    select * into v_slot from public.storage_slots
      where unit_id = v_unit and status = 'reserved'
      order by reserved_at desc limit 1 for update;
    if v_slot.id is not null then
      select * into v_item from public.found_items where id = v_slot.current_found_item_id for update;
      v_start := v_slot.reserved_at;
    end if;
  end if;
  if v_slot.id is null or v_item.id is null then
    return jsonb_build_object('phase','idle');
  end if;
  v_group := v_slot.size_class;
  v_door := coalesce(p_snapshot #>> array['pi','doors',v_group,'door'],'unknown');
  if v_door not in ('open','closed') or
     p_snapshot #> array['pi','doors',v_group,'raw_level'] is null or
     p_snapshot #> array['pi','doors',v_group,'raw_level'] = 'null'::jsonb then
    v_door := 'unknown';
  end if;
  v_telemetry := p_snapshot #> '{esp,telemetry}';
  v_boot := p_snapshot #>> '{esp,boot_id}';
  v_seq := nullif(v_telemetry->>'seq','')::bigint;
  v_telemetry_at := nullif(p_snapshot #>> '{esp,telemetry_at}','')::timestamptz;
  -- An older controller does not report its in-flight event queue. Its missing
  -- count must never be interpreted as an empty queue during finalization.
  v_pending := (p_snapshot->>'pending_presence_count')::integer;

  insert into public.sauli_hardware_transactions(unit_id,assigned_slot_id,
    found_item_id,retrieval_session_id)
    values(v_unit,v_slot.id,case when v_session.id is null then v_item.id else null end,v_session.id)
    on conflict (unit_id) do update set
      assigned_slot_id = excluded.assigned_slot_id,
      found_item_id = excluded.found_item_id,
      retrieval_session_id = excluded.retrieval_session_id,
      phase = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then 'awaiting_door_open' else public.sauli_hardware_transactions.phase end,
      last_door = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then 'unknown' else public.sauli_hardware_transactions.last_door end,
      opened_at = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then null else public.sauli_hardware_transactions.opened_at end,
      closed_at = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then null else public.sauli_hardware_transactions.closed_at end,
      close_telemetry_seq = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then null else public.sauli_hardware_transactions.close_telemetry_seq end,
      close_boot_id = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then null else public.sauli_hardware_transactions.close_boot_id end,
      command_id = case when public.sauli_hardware_transactions.found_item_id is distinct from excluded.found_item_id
                    or public.sauli_hardware_transactions.retrieval_session_id is distinct from excluded.retrieval_session_id
        then null else public.sauli_hardware_transactions.command_id end;
  select * into v_tx from public.sauli_hardware_transactions where unit_id = v_unit for update;

  -- Only the reed transition following this transaction's authenticated unlock
  -- can start (or restart) its monitoring window. A stale event cannot authorize
  -- a later reopen of the same door group.
  select v_door = 'open' and
    p_snapshot #>> '{door_workflow,door}' = v_group and
    p_snapshot #>> '{door_workflow,phase}' = 'awaiting_close' and
    exists (
      select 1 from jsonb_array_elements(coalesce(p_snapshot->'events','[]'::jsonb)) e
      where e->>'kind' = 'workflow_door_opened'
        and e->>'command_id' = p_snapshot #>> '{door_workflow,command_id}'
        and (e->>'at')::timestamptz >= v_start
        and (v_tx.opened_at is null or (e->>'at')::timestamptz > v_tx.opened_at)
    ) into v_authorized_open;
  select v_door = 'closed' and
    p_snapshot #>> '{door_workflow,door}' = v_group and
    p_snapshot #>> '{door_workflow,phase}' = 'completed' and
    p_snapshot #>> '{door_workflow,command_id}' = v_tx.command_id and
    exists (
      select 1 from jsonb_array_elements(coalesce(p_snapshot->'events','[]'::jsonb)) e
      where e->>'kind' = 'workflow_door_closed'
        and e->>'command_id' = v_tx.command_id
        and (e->>'at')::timestamptz >= v_tx.opened_at
    ) into v_authorized_close;

  if v_door = 'open' and v_tx.last_door <> 'open' and v_authorized_open then
    update public.sauli_hardware_transactions set opened_at=now(),closed_at=null,
      close_telemetry_seq=null,close_boot_id=null,
      command_id=p_snapshot #>> '{door_workflow,command_id}' where unit_id=v_unit;
  elsif v_door = 'open' and v_tx.closed_at is not null then
    update public.sauli_hardware_transactions set opened_at=now(),closed_at=null,
      close_telemetry_seq=null,close_boot_id=null,phase='requires_review'
      where unit_id=v_unit;
  elsif v_door = 'open' and v_tx.opened_at is null then
    update public.sauli_hardware_transactions set phase='requires_review'
      where unit_id=v_unit;
  elsif v_door = 'closed' and v_tx.last_door = 'open' and
        v_tx.opened_at is not null and v_authorized_close then
    update public.sauli_hardware_transactions set closed_at=now(),
      close_telemetry_seq=v_seq,close_boot_id=v_boot where unit_id=v_unit;
  elsif v_door = 'closed' and v_tx.last_door = 'open' and v_tx.opened_at is not null then
    update public.sauli_hardware_transactions set phase='requires_review'
      where unit_id=v_unit;
  elsif v_door = 'unknown' then
    update public.sauli_hardware_transactions set closed_at=null,
      close_telemetry_seq=null,close_boot_id=null where unit_id=v_unit;
  end if;
  update public.sauli_hardware_transactions set last_door=v_door,updated_at=now()
    where unit_id=v_unit;
  select * into v_tx from public.sauli_hardware_transactions where unit_id=v_unit;
  select coalesce(hp.present,false) into v_present from public.sauli_hardware_presence hp
    where hp.unit_id=v_unit and hp.slot_id=v_slot.id;
  v_present := coalesce(v_present,false);
  select exists(select 1 from public.sauli_hardware_incidents
    where unit_id=v_unit and active) into v_warning;

  -- All 12 active slots, including unrelated occupied items, must agree with
  -- both the authoritative slot records and the latest ESP observation.
  select (select count(*) from public.storage_slots where unit_id=v_unit and is_active) <> 12
    or jsonb_typeof(v_telemetry->'slots') is distinct from 'array'
    or jsonb_array_length(case when jsonb_typeof(v_telemetry->'slots') = 'array'
      then v_telemetry->'slots' else '[]'::jsonb end) <> 12
    or exists (
      select 1 from public.storage_slots ss
      left join public.sauli_hardware_presence hp on hp.unit_id=v_unit and hp.slot_id=ss.id
      left join lateral (
        select r.value from jsonb_array_elements(case when jsonb_typeof(v_telemetry->'slots') = 'array'
          then v_telemetry->'slots' else '[]'::jsonb end) r(value)
        where r.value->>'code'=ss.code
      ) reading on true
      where ss.unit_id=v_unit and ss.is_active and (
        hp.slot_id is null or hp.boot_id is distinct from v_boot
        or reading.value is null or reading.value->>'ready' is distinct from 'true'
        -- Switch inputs have no weight calibration. The firmware sends a
        -- usable presence boolean only when that sensor is ready.
        or nullif(reading.value->>'fault','') is not null
        or reading.value->>'present' not in ('true','false')
        or reading.value->>'present' is distinct from hp.present::text
        or hp.present is distinct from case
          when ss.id=v_slot.id and v_session.id is null then true
          when ss.id=v_slot.id and v_session.id is not null then false
          when ss.status='occupied' then true
          when ss.status='available' then false
          else null end
      )) into v_mismatch;

  if v_tx.phase = 'requires_review' and not v_authorized_open then
    v_phase := 'requires_review';
  elsif v_warning then
    v_phase := 'warning_active';
  elsif v_door = 'closed' and v_tx.closed_at is not null and
        v_pending = 0 and v_boot is not null and v_boot = v_tx.close_boot_id
        and v_seq > coalesce(v_tx.close_telemetry_seq,-1)
        and v_telemetry_at > v_tx.closed_at
        and v_telemetry_at >= now() - interval '5 seconds'
        and v_mismatch then
    v_phase := 'requires_review';
  elsif v_tx.opened_at is null then
    v_phase := 'awaiting_door_open';
  elsif v_door = 'open' then
    v_phase := case when (v_session.id is null and v_present) or
                          (v_session.id is not null and not v_present)
      then 'provisional_success' else 'door_open' end;
  elsif v_door = 'closed' and v_tx.closed_at is not null then
    v_phase := 'awaiting_door_close';
  else
    v_phase := 'awaiting_door_open';
  end if;

  if v_phase = 'awaiting_door_close' and not v_mismatch and v_pending=0
     and p_snapshot #>> '{esp,connection}' = 'online'
     and v_boot is not null and v_boot = v_tx.close_boot_id
     and v_seq > coalesce(v_tx.close_telemetry_seq,-1)
     and v_telemetry_at > v_tx.closed_at
     and v_telemetry_at <= now() + interval '5 seconds'
     and v_telemetry_at >= now() - interval '5 seconds' then
    v_completed_at := now();
    if v_session.id is null then
      update public.storage_slots set status='occupied',occupied_at=v_completed_at
        where id=v_slot.id and status='reserved';
      update public.found_items set placement_status='placed',placed_at=v_completed_at
        where id=v_item.id and placement_status='reserved';
      insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
        values(v_slot.id,v_item.id,'hardware_item_placed','esp32_switch');
      insert into public.matching_jobs(kind,found_item_id)
        values('item_placed',v_item.id) on conflict do nothing;
    else
      update public.found_items set status='retrieved' where id=v_item.id and status='claimed';
      update public.storage_slots set status='available',current_found_item_id=null,
        reserved_at=null,occupied_at=null where id=v_slot.id and status='occupied';
      update public.retrieval_sessions set status='completed',completed_at=v_completed_at
        where id=v_session.id and status='validated';
      insert into public.retrieval_logs(retrieval_session_id,found_item_id,claimant_user_id,
        storage_slot_id,slot_code,item_summary,retriever,retrieved_at,completion_source)
        values(v_session.id,v_item.id,v_session.claimant_user_id,v_slot.id,v_slot.code,
          v_item.object_name,v_session.claimant_display_name,v_completed_at,'esp32_switch')
        on conflict (retrieval_session_id) do nothing;
      insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
        values(v_session.id,v_item.id,v_slot.id,'retrieval_completed','esp32_switch');
    end if;
    v_phase := 'completed';
  end if;
  update public.sauli_hardware_transactions set phase=v_phase,updated_at=now()
    where unit_id=v_unit;
  return jsonb_build_object('phase',v_phase,'door',v_door,'assigned_slot',v_slot.code,
    'provisional',(v_phase='provisional_success'),'warning',v_warning);
end $$;

revoke all on function public.sauli_reconcile_hardware_workflow(uuid,jsonb)
  from public,anon,authenticated;
grant execute on function public.sauli_reconcile_hardware_workflow(uuid,jsonb) to service_role;

revoke all on function public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean),
  public.sauli_hardware_guidance(uuid) from public,anon,authenticated;
grant execute on function public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean),
  public.sauli_hardware_guidance(uuid) to service_role;
commit;
