begin;

-- Consume a completion proof created only after the Pi has verified a fresh
-- post-close 12-slot snapshot and returned the selected gate GPIO LOW.
create function public.sauli_reconcile_local_hardware_completion(
  p_device_id uuid, p_snapshot jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_device public.kiosk_devices;
  v_tx public.sauli_hardware_transactions;
  v_slot public.storage_slots;
  v_observed public.storage_slots;
  v_item public.found_items;
  v_session public.retrieval_sessions;
  v_completion jsonb := p_snapshot->'local_completion';
  v_telemetry jsonb := p_snapshot #> '{esp,telemetry}';
  v_reading jsonb;
  v_present boolean;
  v_expected boolean;
  v_activated_at timestamptz;
  v_opened_at timestamptz;
  v_closed_at timestamptz;
  v_verified_at timestamptz;
  v_deactivated_at timestamptz;
  v_completed_at timestamptz;
  v_telemetry_at timestamptz;
  v_completed_business_at timestamptz;
begin
  select d.* into v_device from public.kiosk_devices d
    join public.sauli_units u on u.id=d.unit_id
    where d.id=p_device_id and d.status='active' and d.revoked_at is null
      and d.is_primary and u.status='active';
  if v_device.id is null then
    return jsonb_build_object('error','DEVICE_ACCESS_DENIED');
  end if;
  perform 1 from public.sauli_units where id=v_device.unit_id for update;
  select * into v_tx from public.sauli_hardware_transactions
    where unit_id=v_device.unit_id for update;
  if v_tx.unit_id is null then
    return jsonb_build_object('phase','idle','finalized',false,
      'reason','TRANSACTION_NOT_FOUND');
  end if;
  if v_tx.phase='completed' then
    return jsonb_build_object('phase','completed','finalized',true);
  end if;
  if v_tx.phase='requires_review' then
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','REVIEW_REQUIRED');
  end if;

  select * into v_slot from public.storage_slots
    where id=v_tx.assigned_slot_id and unit_id=v_device.unit_id and is_active for update;
  if v_slot.id is null or v_tx.command_id is null
     or jsonb_typeof(v_completion) is distinct from 'object'
     or v_completion->>'verified' is distinct from 'true'
     or v_completion->>'command_id' is distinct from v_tx.command_id
     or v_completion->>'assigned_slot' is distinct from v_slot.code
     or v_completion->>'door' is distinct from v_slot.size_class
     or p_snapshot #>> '{last_unlock,command_id}' is distinct from v_tx.command_id
     or p_snapshot #>> '{last_unlock,target_group}' is distinct from v_slot.size_class
     or p_snapshot #>> '{last_unlock,status}' is distinct from 'completed'
     or p_snapshot #>> '{door_workflow,command_id}' is distinct from v_tx.command_id
     or p_snapshot #>> '{door_workflow,door}' is distinct from v_slot.size_class
     or p_snapshot #>> '{door_workflow,phase}' is distinct from 'completed'
     or p_snapshot #>> array['pi','doors',v_slot.size_class,'door'] is distinct from 'closed'
     or p_snapshot #> array['pi','doors',v_slot.size_class,'raw_level'] is null
     or p_snapshot #> array['pi','doors',v_slot.size_class,'raw_level'] = 'null'::jsonb
     or p_snapshot #>> '{pi,outputs,pocket_solenoid}' is distinct from 'false'
     or p_snapshot #>> '{pi,outputs,medium_solenoid}' is distinct from 'false'
     or p_snapshot #>> '{local_warning,locally_completed}' is distinct from 'true'
     or p_snapshot #>> '{local_warning,sync_pending}' is distinct from 'true'
     or p_snapshot #>> '{local_warning,command_id}' is distinct from v_tx.command_id then
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','LOCAL_COMPLETION_IDENTITY_INVALID');
  end if;
  if jsonb_typeof(p_snapshot #> '{local_warning,violations}') is distinct from 'array' then
    return jsonb_build_object('phase','warning_active','finalized',false,
      'reason','LOCAL_VIOLATIONS_UNRESOLVED');
  end if;
  if jsonb_array_length(p_snapshot #> '{local_warning,violations}') <> 0 then
    return jsonb_build_object('phase','warning_active','finalized',false,
      'reason','LOCAL_VIOLATIONS_UNRESOLVED');
  end if;

  if v_tx.found_item_id is not null and v_tx.retrieval_session_id is null then
    select * into v_item from public.found_items
      where id=v_tx.found_item_id and unit_id=v_device.unit_id for update;
    if v_item.id is null or v_item.placement_status <> 'reserved'
       or v_slot.status <> 'reserved'
       or v_slot.current_found_item_id is distinct from v_item.id
       or v_completion->>'operation' is distinct from 'deposit'
       or v_completion->>'workflow_id' is distinct from v_item.id::text then
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','DEPOSIT_TRANSACTION_INVALID');
    end if;
  elsif v_tx.retrieval_session_id is not null and v_tx.found_item_id is null then
    select * into v_session from public.retrieval_sessions
      where id=v_tx.retrieval_session_id for update;
    if v_session.id is not null then
      select * into v_item from public.found_items
        where id=v_session.found_item_id and unit_id=v_device.unit_id for update;
    end if;
    if v_session.id is null or v_session.status <> 'validated'
       or v_item.id is null or v_item.status <> 'claimed'
       or v_item.placement_status <> 'placed'
       or v_slot.status <> 'occupied'
       or v_slot.current_found_item_id is distinct from v_item.id
       or v_completion->>'operation' is distinct from 'retrieval'
       or v_completion->>'workflow_id' is distinct from v_session.id::text then
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','RETRIEVAL_TRANSACTION_INVALID');
    end if;
  else
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','TRANSACTION_IDENTITY_INVALID');
  end if;

  begin
    v_activated_at := (p_snapshot #>> '{last_unlock,activated_at}')::timestamptz;
    v_deactivated_at := (p_snapshot #>> '{last_unlock,deactivated_at}')::timestamptz;
    v_opened_at := (v_completion->>'opened_at')::timestamptz;
    v_closed_at := (v_completion->>'closed_at')::timestamptz;
    v_verified_at := (v_completion->>'verified_at')::timestamptz;
    v_completed_at := (v_completion->>'completed_at')::timestamptz;
    v_telemetry_at := (p_snapshot #>> '{esp,telemetry_at}')::timestamptz;
  exception when others then
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','LOCAL_COMPLETION_TIME_INVALID');
  end;
  if v_activated_at > v_opened_at or v_opened_at >= v_closed_at
     or v_closed_at > v_verified_at or v_verified_at > v_deactivated_at
     or v_deactivated_at > v_completed_at or v_telemetry_at < v_closed_at
     or v_completed_at > now()+interval '5 minutes' then
    return jsonb_build_object('phase','requires_review','finalized',false,
      'reason','LOCAL_COMPLETION_ORDER_INVALID');
  end if;
  if p_snapshot #>> '{esp,connection}' is distinct from 'online'
     or nullif(p_snapshot #>> '{esp,boot_id}','') is null
     or p_snapshot #>> '{esp,boot_id}' is distinct from v_completion->>'esp_boot_id'
     or p_snapshot #>> '{esp,telemetry,seq}' is distinct from
          v_completion->>'telemetry_sequence' then
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','LOCAL_COMPLETION_TELEMETRY_INVALID');
  end if;
  if jsonb_typeof(v_telemetry->'slots') is distinct from 'array' then
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','LOCAL_COMPLETION_TELEMETRY_INVALID');
  end if;
  if jsonb_array_length(v_telemetry->'slots') <> 12
     or (select count(*) from public.storage_slots
          where unit_id=v_device.unit_id and is_active) <> 12 then
    return jsonb_build_object('phase','awaiting_door_close','finalized',false,
      'reason','LOCAL_COMPLETION_TELEMETRY_INVALID');
  end if;

  for v_observed in select * from public.storage_slots
      where unit_id=v_device.unit_id and is_active order by code for update loop
    select reading.value into v_reading from jsonb_array_elements(v_telemetry->'slots')
      reading(value) where reading.value->>'code'=v_observed.code limit 1;
    if v_reading is null or v_reading->>'ready' is distinct from 'true'
       or nullif(v_reading->>'fault','') is not null
       or coalesce(v_reading->>'present','') not in ('true','false') then
      return jsonb_build_object('phase','awaiting_door_close','finalized',false,
        'reason','SENSOR_DATA_INCOMPLETE');
    end if;
    v_present := (v_reading->>'present')::boolean;
    v_expected := case
      when v_observed.id=v_slot.id and v_tx.found_item_id is not null then true
      when v_observed.id=v_slot.id and v_tx.retrieval_session_id is not null then false
      else v_observed.status='occupied' end;
    if v_present is distinct from v_expected then
      return jsonb_build_object('phase','requires_review','finalized',false,
        'reason','LOCAL_COMPLETION_SENSOR_MISMATCH','slot',v_observed.code);
    end if;
  end loop;
  if exists(select 1 from public.sauli_hardware_incidents
      where unit_id=v_device.unit_id and active) then
    return jsonb_build_object('phase','warning_active','finalized',false,
      'reason','UNRESOLVED_HARDWARE_INCIDENT');
  end if;

  v_completed_business_at := now();
  if v_tx.found_item_id is not null then
    update public.storage_slots set status='occupied',occupied_at=v_completed_business_at
      where id=v_slot.id and status='reserved';
    update public.found_items set placement_status='placed',placed_at=v_completed_business_at
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
    update public.retrieval_sessions set status='completed',completed_at=v_completed_business_at,
      wrong_item_out=false where id=v_session.id and status='validated';
    insert into public.retrieval_logs(retrieval_session_id,found_item_id,claimant_user_id,
      storage_slot_id,slot_code,item_summary,retriever,retrieved_at,completion_source)
      values(v_session.id,v_item.id,v_session.claimant_user_id,v_slot.id,v_slot.code,
        v_item.object_name,v_session.claimant_display_name,v_completed_business_at,'esp32_switch')
      on conflict (retrieval_session_id) do nothing;
    insert into public.retrieval_events(
      retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_item.id,v_slot.id,'retrieval_completed','esp32_switch');
  end if;
  update public.sauli_hardware_transactions set phase='completed',last_door='closed',
    opened_at=v_opened_at,closed_at=v_closed_at,
    close_telemetry_seq=(v_completion->>'telemetry_sequence')::bigint,
    close_boot_id=v_completion->>'esp_boot_id',updated_at=now()
    where unit_id=v_device.unit_id;
  return jsonb_build_object('phase','completed','finalized',true,
    'assigned_slot',v_slot.code,'local_completion',true);
end $$;

-- An operator may rearm an interrupted/reviewed workflow only after a fresh
-- authenticated Pi view exactly matches the unchanged database baseline.
create function public.sauli_rearm_direct_hardware_review(
  p_unit_id uuid, p_device_id uuid, p_actor_id uuid, p_reason text, p_snapshot jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_device public.kiosk_devices;
  v_tx public.sauli_hardware_transactions;
  v_slot public.storage_slots;
  v_reading jsonb;
  v_recorded_at timestamptz;
  v_telemetry_at timestamptz;
  v_resolution_id uuid;
begin
  if p_actor_id is null or p_reason is null
     or char_length(btrim(p_reason)) not between 20 and 500 then
    return jsonb_build_object('error','INVALID_REVIEW_REASON');
  end if;
  select d.* into v_device from public.kiosk_devices d
    where d.id=p_device_id and d.unit_id=p_unit_id and d.status='active'
      and d.revoked_at is null and d.is_primary;
  if v_device.id is null then return jsonb_build_object('error','DEVICE_ACCESS_DENIED'); end if;
  perform 1 from public.sauli_units where id=p_unit_id and status='active' for update;
  if not found then return jsonb_build_object('error','UNIT_UNAVAILABLE'); end if;
  select * into v_tx from public.sauli_hardware_transactions
    where unit_id=p_unit_id for update;
  if v_tx.unit_id is null or v_tx.phase <> 'requires_review' then
    return jsonb_build_object('error','REVIEW_NOT_ELIGIBLE');
  end if;
  select * into v_slot from public.storage_slots
    where id=v_tx.assigned_slot_id and unit_id=p_unit_id and is_active for update;
  if v_slot.id is null then return jsonb_build_object('error','SLOT_UNAVAILABLE'); end if;
  if v_tx.found_item_id is not null and v_tx.retrieval_session_id is null then
    if v_slot.status <> 'reserved'
       or v_slot.current_found_item_id is distinct from v_tx.found_item_id
       or not exists(select 1 from public.found_items where id=v_tx.found_item_id
         and unit_id=p_unit_id and placement_status='reserved') then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  elsif v_tx.retrieval_session_id is not null and v_tx.found_item_id is null then
    if v_slot.status <> 'occupied'
       or not exists(select 1 from public.retrieval_sessions rs
         join public.found_items fi on fi.id=rs.found_item_id
         where rs.id=v_tx.retrieval_session_id and rs.status='validated'
           and fi.id=v_slot.current_found_item_id and fi.unit_id=p_unit_id) then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  else
    return jsonb_build_object('error','WORKFLOW_CHANGED');
  end if;
  if exists(select 1 from public.sauli_hardware_incidents where unit_id=p_unit_id and active) then
    return jsonb_build_object('error','UNRESOLVED_HARDWARE_INCIDENT');
  end if;
  begin
    v_recorded_at := (p_snapshot->>'recorded_at')::timestamptz;
    v_telemetry_at := (p_snapshot #>> '{esp,telemetry_at}')::timestamptz;
  exception when others then
    return jsonb_build_object('error','STALE_HARDWARE_STATE');
  end;
  if v_recorded_at not between now()-interval '10 seconds' and now()+interval '5 seconds'
     or v_telemetry_at not between now()-interval '5 seconds' and now()+interval '5 seconds'
     or p_snapshot #>> '{pi,mode}' is distinct from 'real'
     or p_snapshot #>> '{esp,connection}' is distinct from 'online'
     or nullif(p_snapshot #>> '{esp,boot_id}','') is null
     or p_snapshot #>> '{pi,doors,pocket,door}' is distinct from 'closed'
     or p_snapshot #>> '{pi,doors,medium,door}' is distinct from 'closed'
     or p_snapshot #>> '{pi,outputs,pocket_solenoid}' is distinct from 'false'
     or p_snapshot #>> '{pi,outputs,medium_solenoid}' is distinct from 'false' then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if jsonb_typeof(p_snapshot #> '{esp,telemetry,slots}') is distinct from 'array' then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if jsonb_array_length(p_snapshot #> '{esp,telemetry,slots}') <> 12 then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  for v_slot in select * from public.storage_slots
      where unit_id=p_unit_id and is_active order by code for update loop
    select reading.value into v_reading from jsonb_array_elements(
      p_snapshot #> '{esp,telemetry,slots}') reading(value)
      where reading.value->>'code'=v_slot.code limit 1;
    if v_reading is null or v_reading->>'ready' is distinct from 'true'
       or nullif(v_reading->>'fault','') is not null
       or v_reading->>'present' is distinct from (v_slot.status='occupied')::text then
      return jsonb_build_object('error','PHYSICAL_DATABASE_MISMATCH','slot',v_slot.code);
    end if;
  end loop;
  insert into public.sauli_hardware_review_resolutions
    (unit_id,assigned_slot_id,actor_id,reason,previous_phase,previous_command_id)
    values(p_unit_id,v_tx.assigned_slot_id,p_actor_id,btrim(p_reason),
      v_tx.phase,v_tx.command_id) returning id into v_resolution_id;
  update public.sauli_hardware_transactions set phase='awaiting_door_open',
    command_id=null,opened_at=null,closed_at=null,close_telemetry_seq=null,
    close_boot_id=null,last_door='closed',updated_at=now() where unit_id=p_unit_id;
  return jsonb_build_object('status','rearmed','resolution_id',v_resolution_id);
end $$;

revoke all on function public.sauli_reconcile_local_hardware_completion(uuid,jsonb)
  from public,anon,authenticated;
grant execute on function public.sauli_reconcile_local_hardware_completion(uuid,jsonb)
  to service_role;
revoke all on function public.sauli_rearm_direct_hardware_review(uuid,uuid,uuid,text,jsonb)
  from public,anon,authenticated;
grant execute on function public.sauli_rearm_direct_hardware_review(uuid,uuid,uuid,text,jsonb)
  to service_role;

commit;
