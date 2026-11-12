-- Apply after 202611090002 on databases where that migration already ran.
-- Preserve a missing pending-presence count as NULL, so older Pi heartbeats
-- cannot finalize a hardware transaction before event-queue reconciliation.
begin;

create or replace function public.sauli_reconcile_hardware_workflow(p_device_id uuid,p_snapshot jsonb)
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

commit;
