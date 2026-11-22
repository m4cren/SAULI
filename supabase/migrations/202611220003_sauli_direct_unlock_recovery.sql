begin;

-- Re-arm only the legacy five-second timeout case after FastAPI has fetched a
-- fresh state directly from the authenticated Pi. This deliberately does not
-- make other review reasons recoverable and does not queue a hardware command.
create function public.sauli_recover_direct_unopened_workflow(
  p_device_id uuid,
  p_item_id uuid default null,
  p_session_id uuid default null,
  p_snapshot jsonb default '{}'::jsonb)
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
  if (p_item_id is null) = (p_session_id is null) then
    return jsonb_build_object('error','INVALID_WORKFLOW');
  end if;

  select d.* into v_device from public.kiosk_devices d
    join public.sauli_units u on u.id=d.unit_id
    where d.id=p_device_id and d.status='active' and d.revoked_at is null
      and d.is_primary and u.status='active';
  if v_device.id is null then
    return jsonb_build_object('error','DEVICE_ACCESS_DENIED');
  end if;

  perform 1 from public.sauli_units
    where id=v_device.unit_id and status='active' for update;
  select * into v_tx from public.sauli_hardware_transactions
    where unit_id=v_device.unit_id for update;
  if v_tx.unit_id is null
     or v_tx.phase not in ('requires_review','awaiting_door_open')
     or v_tx.found_item_id is distinct from p_item_id
     or v_tx.retrieval_session_id is distinct from p_session_id
     or v_tx.opened_at is not null or v_tx.closed_at is not null
     or v_tx.last_door is distinct from 'closed' or v_tx.command_id is null then
    return jsonb_build_object('error','RECOVERY_NOT_ELIGIBLE');
  end if;

  select * into v_slot from public.storage_slots
    where id=v_tx.assigned_slot_id and unit_id=v_device.unit_id and is_active
    for update;
  if v_slot.id is null then
    return jsonb_build_object('error','SLOT_UNAVAILABLE');
  end if;
  if p_item_id is not null then
    if v_slot.status <> 'reserved'
       or v_slot.current_found_item_id is distinct from p_item_id
       or not exists(select 1 from public.found_items
         where id=p_item_id and unit_id=v_device.unit_id
           and placement_status='reserved') then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  else
    if v_slot.status <> 'occupied'
       or not exists(select 1 from public.retrieval_sessions rs
         join public.found_items fi on fi.id=rs.found_item_id
         where rs.id=p_session_id and rs.status='validated'
           and fi.unit_id=v_device.unit_id
           and fi.id=v_slot.current_found_item_id) then
      return jsonb_build_object('error','WORKFLOW_CHANGED');
    end if;
  end if;
  if exists(select 1 from public.sauli_hardware_incidents
      where unit_id=v_device.unit_id and active) then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;

  begin
    v_recorded_at := (p_snapshot->>'recorded_at')::timestamptz;
    v_telemetry_at := (p_snapshot #>> '{esp,telemetry_at}')::timestamptz;
  exception when others then
    return jsonb_build_object('error','STALE_HARDWARE_STATE');
  end;
  if v_recorded_at not between clock_timestamp()-interval '10 seconds'
                               and clock_timestamp()+interval '5 seconds'
     or v_telemetry_at not between clock_timestamp()-interval '5 seconds'
                                  and clock_timestamp()+interval '5 seconds'
     or p_snapshot #>> '{pi,mode}' is distinct from 'real'
     or p_snapshot #>> '{esp,connection}' is distinct from 'online'
     or nullif(p_snapshot #>> '{esp,boot_id}','') is null
     or p_snapshot #>> '{pi,doors,pocket,door}' is distinct from 'closed'
     or p_snapshot #>> '{pi,doors,medium,door}' is distinct from 'closed'
     or p_snapshot #> '{pi,doors,pocket,raw_level}' is null
     or p_snapshot #> '{pi,doors,pocket,raw_level}' = 'null'::jsonb
     or p_snapshot #> '{pi,doors,medium,raw_level}' is null
     or p_snapshot #> '{pi,doors,medium,raw_level}' = 'null'::jsonb
     or p_snapshot #>> '{pi,outputs,pocket_solenoid}' is distinct from 'false'
     or p_snapshot #>> '{pi,outputs,medium_solenoid}' is distinct from 'false'
     or p_snapshot #>> '{door_workflow,phase}' is distinct from 'fault'
     or p_snapshot #>> '{door_workflow,fault}' is distinct from 'door_open_timeout'
     or p_snapshot #>> '{door_workflow,command_id}' is distinct from v_tx.command_id
     or p_snapshot #>> '{door_workflow,door}' is distinct from v_slot.size_class
     or p_snapshot #>> '{last_unlock,command_id}' is distinct from v_tx.command_id
     or p_snapshot #>> '{last_unlock,target_group}' is distinct from v_slot.size_class
     or p_snapshot #>> '{last_unlock,status}' is distinct from 'failed'
     or p_snapshot #>> '{last_unlock,deactivated_at}' is null
     or p_snapshot #>> '{local_warning,command_id}' is distinct from v_tx.command_id
     or p_snapshot #>> '{local_warning,active}' is distinct from 'false' then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if exists(select 1 from jsonb_array_elements(
      case when jsonb_typeof(p_snapshot->'events')='array'
           then p_snapshot->'events' else '[]'::jsonb end) event
      where event->>'kind'='workflow_door_opened'
        and event->>'command_id'=v_tx.command_id) then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if jsonb_typeof(p_snapshot #> '{local_warning,violations}') is distinct from 'array' then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;
  if jsonb_array_length(p_snapshot #> '{local_warning,violations}') <> 0 then
    return jsonb_build_object('error','HARDWARE_NOT_SAFE');
  end if;

  if jsonb_typeof(p_snapshot #> '{esp,telemetry,slots}') is distinct from 'array' then
    return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
  end if;
  if jsonb_array_length(p_snapshot #> '{esp,telemetry,slots}') <> 12
     or (select count(*) from public.storage_slots
         where unit_id=v_device.unit_id and is_active) <> 12 then
    return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
  end if;
  for v_slot in select * from public.storage_slots
      where unit_id=v_device.unit_id and is_active loop
    if (select count(*) from jsonb_array_elements(
          p_snapshot #> '{esp,telemetry,slots}') as reading(value)
        where reading.value->>'code'=v_slot.code) <> 1 then
      return jsonb_build_object('error','INCOMPLETE_TELEMETRY');
    end if;
    select reading.value into v_reading from jsonb_array_elements(
      p_snapshot #> '{esp,telemetry,slots}') as reading(value)
      where reading.value->>'code'=v_slot.code;
    if v_reading->>'ready' is distinct from 'true'
       or nullif(v_reading->>'fault','') is not null
       or v_reading->>'present' is distinct from (v_slot.status='occupied')::text then
      return jsonb_build_object('error','HARDWARE_NOT_SAFE');
    end if;
  end loop;

  insert into public.sauli_hardware_review_resolutions
    (unit_id,assigned_slot_id,actor_id,reason,previous_phase,previous_command_id)
    values(v_device.unit_id,v_tx.assigned_slot_id,v_device.id,
      'Authenticated direct unopened timeout recovery',v_tx.phase,v_tx.command_id)
    returning id into v_resolution_id;
  update public.sauli_hardware_transactions set
    phase='awaiting_door_open',command_id=null,opened_at=null,closed_at=null,
    close_telemetry_seq=null,close_boot_id=null,updated_at=now()
    where unit_id=v_device.unit_id;
  return jsonb_build_object('status','recovered','resolution_id',v_resolution_id);
end $$;

revoke all on function public.sauli_recover_direct_unopened_workflow(
  uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.sauli_recover_direct_unopened_workflow(
  uuid,uuid,uuid,jsonb) to service_role;

commit;
