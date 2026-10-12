-- Expose the claimant's retrieval progress without revealing the position
-- until the one-time QR has been validated at the kiosk.
create or replace function public.sauli_retrieval_status(p_session_id uuid,p_user_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_session public.retrieval_sessions;
  v_name text;
  v_slot_id uuid;
  v_slot_code text;
  v_section text;
begin
  select * into v_session from public.retrieval_sessions
    where id = p_session_id and claimant_user_id = p_user_id for update;
  if not found then return jsonb_build_object('error','RETRIEVAL_NOT_FOUND'); end if;
  if v_session.status = 'issued' and v_session.expires_at <= now() then
    update public.retrieval_sessions set status = 'expired'
      where id = v_session.id returning * into v_session;
    select id into v_slot_id from public.storage_slots
      where current_found_item_id = v_session.found_item_id;
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_session.found_item_id,v_slot_id,'qr_expired','web_simulation');
  end if;
  select object_name into v_name from public.found_items where id = v_session.found_item_id;
  if v_session.status in ('validated','completed') then
    -- The validation event keeps the actual assigned position available even
    -- after completion has released the slot's current item reference.
    select ss.code,ss.size_class into v_slot_code,v_section
      from public.retrieval_events re
      join public.storage_slots ss on ss.id = re.storage_slot_id
      where re.retrieval_session_id = v_session.id and re.event_type = 'qr_validated'
      order by re.id desc limit 1;
  end if;
  return jsonb_build_object('id',v_session.id,'status',v_session.status,
    'issued_at',v_session.issued_at,'expires_at',v_session.expires_at,
    'validated_at',v_session.validated_at,'completed_at',v_session.completed_at,
    'item_summary',v_name,'slot_code',v_slot_code,'section',v_section,
    'wrong_item_out',v_session.status = 'validated' and v_session.wrong_item_out,
    'retriever',v_session.claimant_display_name,
    'can_replace',v_session.status in ('issued','expired'),
    'completed',v_session.status = 'completed');
end;
$$;

revoke all on function public.sauli_retrieval_status(uuid,uuid) from public,anon,authenticated;
grant execute on function public.sauli_retrieval_status(uuid,uuid) to service_role;
