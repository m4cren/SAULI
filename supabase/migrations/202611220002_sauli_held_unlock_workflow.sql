begin;

-- Hold the authorized GPIO gate active through door closure. The authenticated
-- close snapshot must show the target output HIGH; the Pi releases it only after
-- this function commits final success. A later post-close snapshot may show LOW
-- only when a Pi restart has already failed the physical output safely.
create or replace function public.sauli_reconcile_direct_hardware_workflow(
  p_device_id uuid, p_snapshot jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_unit uuid;
  v_tx public.sauli_hardware_transactions;
  v_slot public.storage_slots;
  v_observed_slot public.storage_slots;
  v_item public.found_items;
  v_session public.retrieval_sessions;
  v_reading jsonb;
  v_telemetry jsonb := p_snapshot #> '{esp,telemetry}';
  v_boot text := p_snapshot #>> '{esp,boot_id}';
  v_group text;
  v_door text;
  v_workflow_phase text := p_snapshot #>> '{door_workflow,phase}';
  v_telemetry_at timestamptz;
  v_snapshot_at timestamptz;
  v_seq bigint;
  v_open_event_at timestamptz;
  v_close_event_at timestamptz;
  v_activated_at timestamptz;
  v_snapshot_ready boolean := false;
  v_command_ok boolean := false;
  v_expected boolean;
  v_present boolean;
  v_mismatch boolean := false;
  v_assigned_mismatch boolean := false;
  v_active_incident boolean := false;
  v_completed_at timestamptz;
  v_phase text;
begin
  select d.unit_id into v_unit from public.kiosk_devices d
    join public.sauli_units u on u.id=d.unit_id
    where d.id=p_device_id and d.status='active' and d.revoked_at is null
      and d.is_primary and u.status='active'
    for share of d;
  if v_unit is null then
    return jsonb_build_object('error','DEVICE_ACCESS_DENIED');
  end if;

  perform 1 from public.sauli_units where id=v_unit for update;
  select * into v_tx from public.sauli_hardware_transactions
    where unit_id=v_unit for update;
  if v_tx.unit_id is null then
    return jsonb_build_object('phase','idle','finalized',false);
  end if;
  if v_tx.phase='completed' then
    return jsonb_build_object('phase','completed','finalized',true);
  end if;
  if v_tx.phase='requires_review' then
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','REVIEW_REQUIRED');
  end if;

  select * into v_slot from public.storage_slots
    where id=v_tx.assigned_slot_id and unit_id=v_unit and is_active for update;
  if v_slot.id is null or v_tx.command_id is null then
    update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','TRANSACTION_IDENTITY_INVALID');
  end if;

  if v_tx.found_item_id is not null and v_tx.retrieval_session_id is null then
    select * into v_item from public.found_items
      where id=v_tx.found_item_id and unit_id=v_unit for update;
    if v_item.id is null or v_item.placement_status <> 'reserved'
       or v_slot.status <> 'reserved'
       or v_slot.current_found_item_id is distinct from v_item.id then
      update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
        where unit_id=v_unit;
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','DEPOSIT_TRANSACTION_INVALID');
    end if;
  elsif v_tx.retrieval_session_id is not null and v_tx.found_item_id is null then
    select * into v_session from public.retrieval_sessions
      where id=v_tx.retrieval_session_id for update;
    if v_session.id is not null then
      select * into v_item from public.found_items
        where id=v_session.found_item_id and unit_id=v_unit for update;
    end if;
    if v_session.id is null or v_session.status <> 'validated'
       or v_item.id is null or v_item.status <> 'claimed'
       or v_item.placement_status <> 'placed'
       or v_slot.status <> 'occupied'
       or v_slot.current_found_item_id is distinct from v_item.id then
      update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
        where unit_id=v_unit;
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','RETRIEVAL_TRANSACTION_INVALID');
    end if;
  else
    update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','TRANSACTION_IDENTITY_INVALID');
  end if;

  v_group := v_slot.size_class;
  v_door := p_snapshot #>> array['pi','doors',v_group,'door'];
  if v_door not in ('open','closed')
     or p_snapshot #> array['pi','doors',v_group,'raw_level'] is null
     or p_snapshot #> array['pi','doors',v_group,'raw_level'] = 'null'::jsonb then
    v_door := 'unknown';
  end if;

  begin
    v_telemetry_at := nullif(p_snapshot #>> '{esp,telemetry_at}','')::timestamptz;
    v_snapshot_at := coalesce(
      nullif(p_snapshot->>'observed_at','')::timestamptz,
      nullif(p_snapshot->>'recorded_at','')::timestamptz);
    v_seq := nullif(v_telemetry->>'seq','')::bigint;
    v_activated_at := nullif(p_snapshot #>> '{last_unlock,activated_at}','')::timestamptz;
    select max((event->>'at')::timestamptz) into v_open_event_at
      from jsonb_array_elements(coalesce(p_snapshot->'events','[]'::jsonb)) event
      where event->>'kind'='workflow_door_opened'
        and event->>'command_id'=v_tx.command_id::text;
    select max((event->>'at')::timestamptz) into v_close_event_at
      from jsonb_array_elements(coalesce(p_snapshot->'events','[]'::jsonb)) event
      where event->>'kind'='workflow_door_closed'
        and event->>'command_id'=v_tx.command_id::text;
  exception when invalid_text_representation or datetime_field_overflow then
    return jsonb_build_object('phase',v_tx.phase,'finalized',false,
      'reason','INVALID_SNAPSHOT','needs_fresh_snapshot',true);
  end;

  v_command_ok :=
    p_snapshot #>> '{last_unlock,command_id}' = v_tx.command_id::text
    and p_snapshot #>> '{last_unlock,target_group}' = v_group
    and p_snapshot #>> '{last_unlock,status}' = 'completed'
    and v_activated_at is not null
    and p_snapshot #>> '{last_unlock,last_output_error}' is null
    and p_snapshot #>> '{door_workflow,command_id}' = v_tx.command_id::text
    and p_snapshot #>> '{door_workflow,door}' = v_group
    and v_workflow_phase in ('awaiting_open','awaiting_close','completed')
    and p_snapshot #>> array['pi','outputs',v_group || '_solenoid'] = 'true';

  -- Door edges are accepted only while accompanied by this transaction's
  -- completed direct command evidence. Once recorded, they survive a later Pi
  -- restart so a post-close ESP snapshot can still finalize safely.
  if v_tx.opened_at is null and v_open_event_at is not null then
    if v_command_ok is distinct from true or v_open_event_at < v_tx.updated_at
       or v_door not in ('open','closed')
       or v_workflow_phase not in ('awaiting_close','completed') then
      update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
        where unit_id=v_unit;
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','UNAUTHENTICATED_DOOR_OPEN');
    end if;
    update public.sauli_hardware_transactions
      set opened_at=v_open_event_at,last_door=v_door,phase='door_open',updated_at=now()
      where unit_id=v_unit;
    select * into v_tx from public.sauli_hardware_transactions
      where unit_id=v_unit for update;
  elsif v_tx.opened_at is null and v_door='open' then
    update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','UNAUTHENTICATED_DOOR_OPEN');
  end if;

  if v_tx.opened_at is not null and v_tx.closed_at is null
     and v_close_event_at is not null and v_close_event_at >= v_tx.opened_at then
    if v_command_ok is distinct from true or v_door <> 'closed'
       or v_workflow_phase <> 'completed' then
      update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
        where unit_id=v_unit;
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','UNAUTHENTICATED_DOOR_CLOSE');
    end if;
    update public.sauli_hardware_transactions
      set closed_at=v_close_event_at,last_door='closed',phase='awaiting_door_close',
        close_telemetry_seq=v_seq,close_boot_id=v_boot,updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','FRESH_POST_CLOSE_SENSOR_REQUIRED','needs_fresh_snapshot',true);
  elsif v_tx.opened_at is not null and v_tx.closed_at is null
        and v_tx.last_door='open' and v_door='closed' then
    if v_snapshot_at is null then
      return jsonb_build_object('phase',v_tx.phase,'finalized',false,
        'reason','SNAPSHOT_TIME_REQUIRED','needs_fresh_snapshot',true);
    elsif v_snapshot_at >= v_tx.opened_at then
      update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
        where unit_id=v_unit;
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','UNAUTHENTICATED_DOOR_CLOSE');
    else
      return jsonb_build_object('phase',v_tx.phase,'finalized',false,
        'reason','STALE_EVENT_IGNORED');
    end if;
  end if;

  -- While the door is open, compare unrelated slots from a fresh full view so
  -- a wrong placement/removal becomes a durable incident without persisting
  -- routine presence rows. The assigned slot is allowed to be in transition.
  v_snapshot_ready :=
    p_snapshot #>> '{pi,mode}' = 'real'
    and p_snapshot #>> '{esp,connection}' = 'online'
    and v_boot ~ '^[a-zA-Z0-9_-]{1,40}$'
    and v_telemetry_at between now()-interval '5 seconds' and now()+interval '5 seconds'
    and v_seq is not null and v_seq >= 0
    and jsonb_typeof(v_telemetry->'slots')='array'
    and jsonb_array_length(v_telemetry->'slots')=12
    and (select count(*) from public.storage_slots
         where unit_id=v_unit and is_active)=12;
  if v_tx.closed_at is null and v_snapshot_ready is true then
    for v_observed_slot in select * from public.storage_slots
        where unit_id=v_unit and is_active and id<>v_slot.id order by code for update loop
      select reading.value into v_reading
        from jsonb_array_elements(v_telemetry->'slots') reading(value)
        where reading.value->>'code'=v_observed_slot.code limit 1;
      if v_reading is null or v_reading->>'ready' is distinct from 'true'
         or nullif(v_reading->>'fault','') is not null
         or coalesce(v_reading->>'present','') not in ('true','false') then
        continue;
      end if;
      v_present := (v_reading->>'present')::boolean;
      v_expected := v_observed_slot.status='occupied';
      if v_present is distinct from v_expected then
        insert into public.sauli_hardware_incidents(
          unit_id,slot_id,assigned_slot_id,found_item_id,retrieval_session_id,kind)
        values(v_unit,v_observed_slot.id,v_slot.id,v_tx.found_item_id,
          v_tx.retrieval_session_id,
          case when v_present then 'wrong_placement' else 'wrong_removal' end)
        on conflict do nothing;
      else
        update public.sauli_hardware_incidents set active=false,resolved_at=now()
          where unit_id=v_unit and slot_id=v_observed_slot.id and active
            and ((kind='wrong_removal' and v_present)
              or (kind='wrong_placement' and not v_present));
      end if;
    end loop;
    select exists(select 1 from public.sauli_hardware_incidents
      where unit_id=v_unit and active) into v_active_incident;
    if v_session.id is not null then
      update public.retrieval_sessions set wrong_item_out=v_active_incident
        where id=v_session.id;
    end if;
  end if;
  select exists(select 1 from public.sauli_hardware_incidents
    where unit_id=v_unit and active) into v_active_incident;

  if v_tx.closed_at is null then
    v_phase := case when v_tx.opened_at is null then 'awaiting_door_open'
                    when v_active_incident then 'warning_active'
                    else 'door_open' end;
    update public.sauli_hardware_transactions set phase=v_phase,last_door=v_door,
      updated_at=now() where unit_id=v_unit;
    return jsonb_build_object('phase',v_phase,'finalized',false);
  end if;

  -- Finalization requires a complete, fresh authenticated controller view.
  v_snapshot_ready :=
    p_snapshot #>> '{pi,mode}' = 'real'
    and p_snapshot #>> '{esp,connection}' = 'online'
    and v_boot ~ '^[a-zA-Z0-9_-]{1,40}$'
    and v_telemetry_at between now()-interval '5 seconds' and now()+interval '5 seconds'
    and v_telemetry_at > v_tx.closed_at
    and v_seq is not null and v_seq >= 0
    and jsonb_typeof(v_telemetry->'slots')='array'
    and jsonb_array_length(v_telemetry->'slots')=12
    and (select count(*) from public.storage_slots
         where unit_id=v_unit and is_active)=12
    and v_door='closed'
    and p_snapshot #>> array['pi','outputs',v_group || '_solenoid'] in ('true','false');

  if v_snapshot_ready is distinct from true then
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','FRESH_SNAPSHOT_REQUIRED','needs_fresh_snapshot',true);
  end if;
  if v_boot = v_tx.close_boot_id and v_tx.close_telemetry_seq is not null
     and v_seq <= v_tx.close_telemetry_seq then
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','POST_CLOSE_SEQUENCE_REQUIRED','needs_fresh_snapshot',true);
  end if;

  -- A new ESP boot is accepted only through this fresh full snapshot after the
  -- authenticated close. No historical presence baseline is consulted.
  for v_observed_slot in select * from public.storage_slots
      where unit_id=v_unit and is_active order by code for update loop
    select reading.value into v_reading
      from jsonb_array_elements(v_telemetry->'slots') reading(value)
      where reading.value->>'code'=v_observed_slot.code limit 1;
    if v_reading is null or v_reading->>'ready' is distinct from 'true'
       or nullif(v_reading->>'fault','') is not null
       or coalesce(v_reading->>'present','') not in ('true','false') then
      return jsonb_build_object('phase','awaiting_door_close','finalized',false,
        'reason','SENSOR_DATA_INCOMPLETE','needs_fresh_snapshot',true);
    end if;

    v_present := (v_reading->>'present')::boolean;
    v_expected := case
      when v_observed_slot.id=v_slot.id and v_tx.found_item_id is not null then true
      when v_observed_slot.id=v_slot.id and v_tx.retrieval_session_id is not null then false
      else v_observed_slot.status='occupied' end;

    if v_present is distinct from v_expected then
      v_mismatch := true;
      if v_observed_slot.id=v_slot.id then
        v_assigned_mismatch := true;
      else
        insert into public.sauli_hardware_incidents(
          unit_id,slot_id,assigned_slot_id,found_item_id,retrieval_session_id,kind)
        values(v_unit,v_observed_slot.id,v_slot.id,v_tx.found_item_id,
          v_tx.retrieval_session_id,
          case when v_present then 'wrong_placement' else 'wrong_removal' end)
        on conflict do nothing;
      end if;
    else
      update public.sauli_hardware_incidents set active=false,resolved_at=now()
        where unit_id=v_unit and slot_id=v_observed_slot.id and active
          and ((kind='wrong_removal' and v_present)
            or (kind='wrong_placement' and not v_present));
    end if;
  end loop;

  select exists(select 1 from public.sauli_hardware_incidents
    where unit_id=v_unit and active) into v_active_incident;
  if v_session.id is not null then
    update public.retrieval_sessions set wrong_item_out=v_active_incident
      where id=v_session.id;
  end if;

  if v_assigned_mismatch then
    update public.sauli_hardware_transactions set phase='requires_review',updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','ASSIGNED_SLOT_FINAL_STATE_MISMATCH');
  end if;
  if v_mismatch or v_active_incident then
    update public.sauli_hardware_transactions set phase='warning_active',updated_at=now()
      where unit_id=v_unit;
    return jsonb_build_object('phase','warning_active','finalized',false,
      'reason','UNRESOLVED_HARDWARE_INCIDENT');
  end if;

  v_completed_at := now();
  if v_tx.found_item_id is not null then
    update public.storage_slots set status='occupied',occupied_at=v_completed_at
      where id=v_slot.id and status='reserved';
    update public.found_items set placement_status='placed',placed_at=v_completed_at
      where id=v_item.id and placement_status='reserved';
    insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
      values(v_slot.id,v_item.id,'hardware_item_placed','esp32_switch');
    insert into public.matching_jobs(kind,found_item_id)
      values('item_placed',v_item.id) on conflict do nothing;
  else
    update public.found_items set status='retrieved'
      where id=v_item.id and status='claimed';
    update public.storage_slots set status='available',current_found_item_id=null,
      reserved_at=null,occupied_at=null where id=v_slot.id and status='occupied';
    update public.retrieval_sessions set status='completed',completed_at=v_completed_at,
      wrong_item_out=false where id=v_session.id and status='validated';
    insert into public.retrieval_logs(retrieval_session_id,found_item_id,claimant_user_id,
      storage_slot_id,slot_code,item_summary,retriever,retrieved_at,completion_source)
      values(v_session.id,v_item.id,v_session.claimant_user_id,v_slot.id,v_slot.code,
        v_item.object_name,v_session.claimant_display_name,v_completed_at,'esp32_switch')
      on conflict (retrieval_session_id) do nothing;
    insert into public.retrieval_events(
      retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_item.id,v_slot.id,'retrieval_completed','esp32_switch');
  end if;

  update public.sauli_hardware_transactions
    set phase='completed',last_door='closed',updated_at=now()
    where unit_id=v_unit;
  return jsonb_build_object('phase','completed','finalized',true,
    'assigned_slot',v_slot.code,
    'esp_boot_id',v_boot,'telemetry_sequence',v_seq);
end $$;

revoke all on function public.sauli_reconcile_direct_hardware_workflow(uuid,jsonb)
  from public,anon,authenticated;
grant execute on function public.sauli_reconcile_direct_hardware_workflow(uuid,jsonb)
  to service_role;

commit;
