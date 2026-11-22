begin;

-- Direct mode keeps the database as the workflow authorization boundary but
-- returns an expiring command envelope instead of inserting a queue row. The
-- Pi performs the final, local reed/ESP/output readiness check immediately
-- before the pulse.
create or replace function public.sauli_authorize_workflow_unlock(
  p_device_id uuid, p_item_id uuid default null, p_session_id uuid default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_device public.kiosk_devices;
  v_slot public.storage_slots;
  v_tx public.sauli_hardware_transactions;
  v_command_id uuid;
  v_expected jsonb;
  v_slot_count integer;
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

  perform 1 from public.sauli_units where id=v_device.unit_id for update;
  if p_item_id is not null then
    select ss.* into v_slot from public.storage_slots ss
      join public.found_items fi on fi.id=ss.current_found_item_id
      where fi.id=p_item_id and fi.unit_id=v_device.unit_id
        and fi.placement_status='reserved' and ss.status='reserved'
      for update of ss;
  else
    select ss.* into v_slot from public.storage_slots ss
      join public.found_items fi on fi.id=ss.current_found_item_id
      join public.retrieval_sessions rs on rs.found_item_id=fi.id
      where rs.id=p_session_id and rs.status='validated'
        and fi.unit_id=v_device.unit_id and ss.status='occupied'
      for update of ss;
  end if;
  if v_slot.id is null then
    return jsonb_build_object('error','WORKFLOW_NOT_READY');
  end if;

  select * into v_tx from public.sauli_hardware_transactions
    where unit_id=v_device.unit_id for update;
  if v_tx.unit_id is not null and v_tx.phase is distinct from 'completed'
     and (v_tx.found_item_id is distinct from p_item_id
       or v_tx.retrieval_session_id is distinct from p_session_id) then
    return jsonb_build_object('error','WORKFLOW_BUSY');
  end if;
  if v_tx.unit_id is not null and v_tx.phase in ('requires_review','warning_active') then
    return jsonb_build_object('error','WORKFLOW_REQUIRES_REVIEW');
  end if;
  if exists(select 1 from public.sauli_hardware_incidents
      where unit_id=v_device.unit_id and active) then
    return jsonb_build_object('error','HARDWARE_NOT_READY');
  end if;

  select count(*), jsonb_agg(
      jsonb_build_object('code',code,'present',(status='occupied')) order by code)
    into v_slot_count,v_expected
    from public.storage_slots where unit_id=v_device.unit_id and is_active;
  if v_slot_count <> 12 then
    return jsonb_build_object('error','HARDWARE_NOT_READY');
  end if;

  -- An ambiguous API-to-Pi timeout reuses this UUID. The Pi persists the
  -- result and returns it without pulsing a second time.
  if v_tx.unit_id is not null
     and v_tx.found_item_id is not distinct from p_item_id
     and v_tx.retrieval_session_id is not distinct from p_session_id
     and v_tx.phase='awaiting_door_open' and v_tx.command_id is not null then
    begin
      v_command_id := v_tx.command_id::uuid;
    exception when invalid_text_representation then
      return jsonb_build_object('error','WORKFLOW_REQUIRES_REVIEW');
    end;
  else
    v_command_id := gen_random_uuid();
  end if;

  insert into public.sauli_hardware_transactions(unit_id,assigned_slot_id,
    found_item_id,retrieval_session_id,phase,last_door,command_id)
    values(v_device.unit_id,v_slot.id,p_item_id,p_session_id,
      'awaiting_door_open','closed',v_command_id::text)
    on conflict (unit_id) do update set
      assigned_slot_id=excluded.assigned_slot_id,
      found_item_id=excluded.found_item_id,
      retrieval_session_id=excluded.retrieval_session_id,
      phase='awaiting_door_open',last_door='closed',
      opened_at=null,closed_at=null,close_telemetry_seq=null,
      close_boot_id=null,command_id=excluded.command_id,updated_at=now();

  return jsonb_build_object(
    'command_id',v_command_id,
    'status','authorized',
    'action','pulse_'||v_slot.size_class,
    'assigned_slot',v_slot.code,
    'expected_slots',v_expected,
    'expires_at',clock_timestamp()+interval '10 seconds');
end $$;

-- Only definitive Pi rejections clear an authorization for a new UUID. An
-- ambiguous network error never calls this function and therefore remains
-- replay-safe. A possible output failure requires manual review.
create or replace function public.sauli_record_direct_unlock_result(
  p_device_id uuid, p_command_id uuid, p_status text, p_code text)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare
  v_unit uuid;
begin
  select d.unit_id into v_unit from public.kiosk_devices d
    join public.sauli_units u on u.id=d.unit_id
    where d.id=p_device_id and d.status='active' and d.revoked_at is null
      and d.is_primary and u.status='active';
  if v_unit is null or p_status <> 'failed' then return false; end if;

  if p_code in ('expired','device_mismatch','actuators_disabled','outputs_unverified',
      'unsupported_action','test_channel_not_allowed','door_workflow_busy',
      'door_not_closed','hardware_not_ready','sensor_state_mismatch','invalid_command',
      'replay_storage_unavailable') then
    update public.sauli_hardware_transactions
      set command_id=null,updated_at=now()
      where unit_id=v_unit and command_id=p_command_id::text
        and phase='awaiting_door_open';
  else
    update public.sauli_hardware_transactions
      set phase='requires_review',updated_at=now()
      where unit_id=v_unit and command_id=p_command_id::text;
  end if;
  return found;
end $$;

revoke all on function public.sauli_authorize_workflow_unlock(uuid,uuid,uuid)
  from public,anon,authenticated;
revoke all on function public.sauli_record_direct_unlock_result(uuid,uuid,text,text)
  from public,anon,authenticated;
grant execute on function public.sauli_authorize_workflow_unlock(uuid,uuid,uuid)
  to service_role;
grant execute on function public.sauli_record_direct_unlock_result(uuid,uuid,text,text)
  to service_role;

-- sauli_hardware_commands and sauli_claim_hardware_commands intentionally
-- remain present for rollback, but direct mode has no call path to either.

commit;
