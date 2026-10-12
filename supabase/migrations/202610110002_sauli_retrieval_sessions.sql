-- One-time retrieval QR sessions. Only the trusted API service role may call
-- these functions or read their token hashes. Apply after storage slots.
create table public.retrieval_sessions (
  id uuid primary key default gen_random_uuid(),
  found_item_id uuid not null references public.found_items(id) on delete restrict,
  match_candidate_id uuid not null references public.match_candidates(id) on delete restrict,
  claimant_user_id uuid not null references auth.users(id) on delete restrict,
  claimant_display_name text not null default 'Claimant',
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  action_token_hash text unique check (action_token_hash is null or action_token_hash ~ '^[0-9a-f]{64}$'),
  status text not null default 'issued' check (status in ('issued','validated','completed','expired','cancelled')),
  wrong_item_out boolean not null default false,
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null,
  validated_at timestamptz,
  completed_at timestamptz,
  cancelled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (expires_at > issued_at)
);
create unique index retrieval_sessions_one_active_item_idx on public.retrieval_sessions(found_item_id)
  where status in ('issued','validated');
create index retrieval_sessions_item_idx on public.retrieval_sessions(found_item_id,created_at desc);
create index retrieval_sessions_claimant_idx on public.retrieval_sessions(claimant_user_id,created_at desc);
create index retrieval_sessions_expiry_idx on public.retrieval_sessions(expires_at)
  where status = 'issued';
create trigger retrieval_sessions_updated_at before update on public.retrieval_sessions
  for each row execute function public.sauli_set_updated_at();

create table public.retrieval_events (
  id bigint generated always as identity primary key,
  retrieval_session_id uuid not null references public.retrieval_sessions(id) on delete restrict,
  found_item_id uuid not null references public.found_items(id) on delete restrict,
  storage_slot_id uuid references public.storage_slots(id) on delete restrict,
  event_type text not null check (event_type in (
    'qr_issued','qr_replaced','qr_validated','qr_expired','qr_rejected',
    'simulated_door_ready','simulated_correct_item_lifted',
    'simulated_wrong_item_lifted','simulated_item_returned',
    'retrieval_completed','retrieval_cancelled')),
  event_source text not null,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index retrieval_events_session_idx on public.retrieval_events(retrieval_session_id,created_at desc);
create index retrieval_events_item_idx on public.retrieval_events(found_item_id,created_at desc);

create table public.retrieval_logs (
  id uuid primary key default gen_random_uuid(),
  retrieval_session_id uuid not null unique references public.retrieval_sessions(id) on delete restrict,
  found_item_id uuid not null references public.found_items(id) on delete restrict,
  claimant_user_id uuid not null references auth.users(id) on delete restrict,
  storage_slot_id uuid not null references public.storage_slots(id) on delete restrict,
  slot_code text not null,
  item_summary text not null,
  retriever text not null,
  retrieved_at timestamptz not null,
  completion_source text not null
);
create index retrieval_logs_time_idx on public.retrieval_logs(retrieved_at desc);
create index retrieval_logs_claimant_idx on public.retrieval_logs(claimant_user_id,retrieved_at desc);

-- All transition functions lock the found item before the session and slot.
-- That order serializes concurrent issuance, validation, and completion.
create function public.sauli_issue_retrieval(
  p_candidate_id uuid,p_user_id uuid,p_token_hash text,p_ttl_minutes integer,p_display_name text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_candidate public.match_candidates;
  v_item public.found_items;
  v_slot public.storage_slots;
  v_old public.retrieval_sessions;
  v_new public.retrieval_sessions;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_ttl_minutes is null or p_ttl_minutes not between 1 and 1440 then
    return jsonb_build_object('error','INVALID_REQUEST');
  end if;
  select mc.* into v_candidate from public.match_candidates mc
    join public.search_requests sr on sr.id = mc.search_request_id
    where mc.id = p_candidate_id and sr.user_id = p_user_id;
  if not found then return jsonb_build_object('error','MATCH_NOT_FOUND'); end if;
  select * into v_item from public.found_items where id = v_candidate.found_item_id for update;
  if not found then return jsonb_build_object('error','ITEM_NOT_AVAILABLE'); end if;
  select * into v_candidate from public.match_candidates where id = p_candidate_id for update;
  select * into v_slot from public.storage_slots where current_found_item_id = v_item.id for update;
  if not found then return jsonb_build_object('error','STORAGE_POSITION_MISMATCH'); end if;
  if v_candidate.decision <> 'accepted' or v_item.status <> 'claimed'
     or v_item.placement_status <> 'placed' or v_slot.status <> 'occupied' then
    return jsonb_build_object('error','ITEM_NOT_AVAILABLE');
  end if;
  for v_old in select * from public.retrieval_sessions
    where found_item_id = v_item.id and status in ('issued','validated') for update loop
    if v_old.claimant_user_id <> p_user_id or v_old.status = 'validated' then
      return jsonb_build_object('error','RETRIEVAL_SESSION_EXISTS');
    end if;
    update public.retrieval_sessions set status = 'cancelled',cancelled_at = now()
      where id = v_old.id;
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_old.id,v_item.id,v_slot.id,'retrieval_cancelled','web_simulation');
  end loop;
  insert into public.retrieval_sessions(found_item_id,match_candidate_id,claimant_user_id,
    claimant_display_name,token_hash,issued_at,expires_at)
    values(v_item.id,p_candidate_id,p_user_id,left(coalesce(nullif(trim(p_display_name),''),'Claimant'),120),
      p_token_hash,now(),now() + make_interval(mins => p_ttl_minutes)) returning * into v_new;
  insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
    values(v_new.id,v_item.id,v_slot.id,'qr_issued','web_simulation');
  return jsonb_build_object('id',v_new.id,'issued_at',v_new.issued_at,'expires_at',v_new.expires_at,
    'status',v_new.status,'item_summary',v_item.object_name);
end;
$$;

create function public.sauli_retrieval_status(p_session_id uuid,p_user_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_session public.retrieval_sessions;
  v_name text;
  v_slot_id uuid;
begin
  select * into v_session from public.retrieval_sessions
    where id = p_session_id and claimant_user_id = p_user_id for update;
  if not found then return jsonb_build_object('error','RETRIEVAL_NOT_FOUND'); end if;
  if v_session.status = 'issued' and v_session.expires_at <= now() then
    update public.retrieval_sessions set status = 'expired' where id = v_session.id returning * into v_session;
    select id into v_slot_id from public.storage_slots where current_found_item_id = v_session.found_item_id;
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_session.found_item_id,v_slot_id,'qr_expired','web_simulation');
  end if;
  select object_name into v_name from public.found_items where id = v_session.found_item_id;
  return jsonb_build_object('id',v_session.id,'status',v_session.status,'issued_at',v_session.issued_at,
    'expires_at',v_session.expires_at,'item_summary',v_name,
    'can_replace',v_session.status in ('issued','expired'),'completed',v_session.status = 'completed');
end;
$$;

create function public.sauli_replace_retrieval(
  p_session_id uuid,p_user_id uuid,p_token_hash text,p_ttl_minutes integer
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_session public.retrieval_sessions;
  v_item public.found_items;
  v_slot public.storage_slots;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_ttl_minutes is null or p_ttl_minutes not between 1 and 1440 then
    return jsonb_build_object('error','INVALID_REQUEST');
  end if;
  select * into v_session from public.retrieval_sessions
    where id = p_session_id and claimant_user_id = p_user_id;
  if not found then return jsonb_build_object('error','RETRIEVAL_NOT_FOUND'); end if;
  select * into v_item from public.found_items where id = v_session.found_item_id for update;
  if not found then return jsonb_build_object('error','ITEM_NOT_AVAILABLE'); end if;
  select * into v_session from public.retrieval_sessions where id = p_session_id for update;
  select * into v_slot from public.storage_slots where current_found_item_id = v_item.id for update;
  if not found then return jsonb_build_object('error','STORAGE_POSITION_MISMATCH'); end if;
  if v_session.status not in ('issued','expired') then
    return jsonb_build_object('error','RETRIEVAL_QR_ALREADY_USED');
  end if;
  if v_item.status <> 'claimed' or v_item.placement_status <> 'placed' or v_slot.status <> 'occupied' then
    return jsonb_build_object('error','ITEM_NOT_AVAILABLE');
  end if;
  update public.retrieval_sessions set token_hash = p_token_hash,status = 'issued',
    issued_at = now(),expires_at = now() + make_interval(mins => p_ttl_minutes),
    validated_at = null,action_token_hash = null
    where id = p_session_id returning * into v_session;
  insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
    values(v_session.id,v_item.id,v_slot.id,'qr_replaced','web_simulation');
  return jsonb_build_object('id',v_session.id,'issued_at',v_session.issued_at,
    'expires_at',v_session.expires_at,'status',v_session.status,'item_summary',v_item.object_name);
end;
$$;

create function public.sauli_validate_retrieval(p_token_hash text,p_action_hash text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_session public.retrieval_sessions;
  v_item public.found_items;
  v_slot public.storage_slots;
begin
  select * into v_session from public.retrieval_sessions where token_hash = p_token_hash;
  if not found then return jsonb_build_object('error','INVALID_RETRIEVAL_TOKEN'); end if;
  select * into v_item from public.found_items where id = v_session.found_item_id for update;
  if not found then return jsonb_build_object('error','ITEM_NOT_AVAILABLE'); end if;
  select * into v_session from public.retrieval_sessions where id = v_session.id for update;
  if v_session.token_hash <> p_token_hash then
    return jsonb_build_object('error','INVALID_RETRIEVAL_TOKEN');
  end if;
  if v_session.status = 'cancelled' then
    insert into public.retrieval_events(retrieval_session_id,found_item_id,event_type,event_source,metadata)
      values(v_session.id,v_item.id,'qr_rejected','web_simulation','{"reason":"cancelled"}'::jsonb);
    return jsonb_build_object('error','RETRIEVAL_CANCELLED');
  end if;
  if v_session.status = 'expired' then
    insert into public.retrieval_events(retrieval_session_id,found_item_id,event_type,event_source,metadata)
      values(v_session.id,v_item.id,'qr_rejected','web_simulation','{"reason":"expired"}'::jsonb);
    return jsonb_build_object('error','RETRIEVAL_QR_EXPIRED');
  end if;
  if v_session.status <> 'issued' then
    insert into public.retrieval_events(retrieval_session_id,found_item_id,event_type,event_source,metadata)
      values(v_session.id,v_item.id,'qr_rejected','web_simulation','{"reason":"already_used"}'::jsonb);
    return jsonb_build_object('error','RETRIEVAL_QR_ALREADY_USED');
  end if;
  if v_session.expires_at <= now() then
    update public.retrieval_sessions set status = 'expired' where id = v_session.id;
    select * into v_slot from public.storage_slots where current_found_item_id = v_item.id;
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_item.id,v_slot.id,'qr_expired','web_simulation');
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source,metadata)
      values(v_session.id,v_item.id,v_slot.id,'qr_rejected','web_simulation','{"reason":"expired"}'::jsonb);
    return jsonb_build_object('error','RETRIEVAL_QR_EXPIRED');
  end if;
  select * into v_slot from public.storage_slots where current_found_item_id = v_item.id for update;
  if not found then return jsonb_build_object('error','STORAGE_POSITION_MISMATCH'); end if;
  if v_item.status <> 'claimed' or v_item.placement_status <> 'placed' then
    return jsonb_build_object('error','ITEM_NOT_AVAILABLE');
  end if;
  if v_slot.status <> 'occupied' or v_slot.current_found_item_id <> v_item.id then
    return jsonb_build_object('error','STORAGE_POSITION_MISMATCH');
  end if;
  update public.retrieval_sessions set status = 'validated',validated_at = now(),action_token_hash = p_action_hash
    where id = v_session.id;
  insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
    values(v_session.id,v_item.id,v_slot.id,'qr_validated','web_simulation'),
          (v_session.id,v_item.id,v_slot.id,'simulated_door_ready','web_simulation');
  return jsonb_build_object('id',v_session.id,'item_summary',v_item.object_name,'slot_code',v_slot.code,
    'section',v_slot.size_class,'slot_status',v_slot.status,'status','validated');
end;
$$;

create function public.sauli_simulate_retrieval(
  p_session_id uuid,p_action_hash text,p_event text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_session public.retrieval_sessions;
  v_item public.found_items;
  v_slot public.storage_slots;
  v_completed_at timestamptz;
begin
  select * into v_session from public.retrieval_sessions where id = p_session_id;
  if not found then return jsonb_build_object('error','RETRIEVAL_NOT_FOUND'); end if;
  select * into v_item from public.found_items where id = v_session.found_item_id for update;
  if not found then return jsonb_build_object('error','ITEM_NOT_AVAILABLE'); end if;
  select * into v_session from public.retrieval_sessions where id = p_session_id for update;
  if v_session.action_token_hash is null or v_session.action_token_hash <> p_action_hash then
    return jsonb_build_object('error','INVALID_RETRIEVAL_ACTION');
  end if;
  if v_session.status = 'completed' and p_event = 'correct_item_lifted' then
    return jsonb_build_object('id',v_session.id,'status','completed','completed_at',v_session.completed_at);
  end if;
  if v_session.status <> 'validated' then return jsonb_build_object('error','RETRIEVAL_QR_ALREADY_USED'); end if;
  select * into v_slot from public.storage_slots where current_found_item_id = v_item.id for update;
  if not found then return jsonb_build_object('error','STORAGE_POSITION_MISMATCH'); end if;
  if v_slot.status <> 'occupied' or v_slot.current_found_item_id <> v_item.id then
    return jsonb_build_object('error','STORAGE_POSITION_MISMATCH');
  end if;
  if p_event = 'wrong_item_lifted' then
    if not v_session.wrong_item_out then
      update public.retrieval_sessions set wrong_item_out = true where id = v_session.id;
      insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
        values(v_session.id,v_item.id,v_slot.id,'simulated_wrong_item_lifted','web_simulation');
    end if;
    return jsonb_build_object('id',v_session.id,'status','validated','wrong_item_out',true);
  elsif p_event = 'item_returned' then
    if v_session.wrong_item_out then
      update public.retrieval_sessions set wrong_item_out = false where id = v_session.id;
      insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
        values(v_session.id,v_item.id,v_slot.id,'simulated_item_returned','web_simulation');
    end if;
    return jsonb_build_object('id',v_session.id,'status','validated','wrong_item_out',false);
  elsif p_event = 'correct_item_lifted' then
    if v_session.wrong_item_out then return jsonb_build_object('error','WRONG_ITEM_NOT_RETURNED'); end if;
    if v_item.status <> 'claimed' or v_item.placement_status <> 'placed' then
      return jsonb_build_object('error','ITEM_NOT_AVAILABLE');
    end if;
    v_completed_at := now();
    update public.found_items set status = 'retrieved' where id = v_item.id;
    update public.storage_slots set status = 'available',current_found_item_id = null,
      reserved_at = null,occupied_at = null where id = v_slot.id;
    update public.retrieval_sessions set status = 'completed',completed_at = v_completed_at
      where id = v_session.id;
    insert into public.retrieval_logs(retrieval_session_id,found_item_id,claimant_user_id,
      storage_slot_id,slot_code,item_summary,retriever,retrieved_at,completion_source)
      values(v_session.id,v_item.id,v_session.claimant_user_id,v_slot.id,v_slot.code,
        v_item.object_name,v_session.claimant_display_name,v_completed_at,'web_simulation');
    insert into public.retrieval_events(retrieval_session_id,found_item_id,storage_slot_id,event_type,event_source)
      values(v_session.id,v_item.id,v_slot.id,'simulated_correct_item_lifted','web_simulation'),
            (v_session.id,v_item.id,v_slot.id,'retrieval_completed','web_simulation');
    return jsonb_build_object('id',v_session.id,'status','completed','completed_at',v_completed_at);
  end if;
  return jsonb_build_object('error','INVALID_REQUEST');
end;
$$;

alter table public.retrieval_sessions enable row level security;
alter table public.retrieval_events enable row level security;
alter table public.retrieval_logs enable row level security;
-- Claimants use authenticated FastAPI routes, which enforce ownership without
-- exposing token hashes in browser-side table selects.
revoke all on public.retrieval_sessions,public.retrieval_events,public.retrieval_logs from anon,authenticated;
grant all on public.retrieval_sessions,public.retrieval_events,public.retrieval_logs to service_role;
grant usage,select on sequence public.retrieval_events_id_seq to service_role;
revoke all on function public.sauli_issue_retrieval(uuid,uuid,text,integer,text),
  public.sauli_retrieval_status(uuid,uuid),public.sauli_replace_retrieval(uuid,uuid,text,integer),
  public.sauli_validate_retrieval(text,text),public.sauli_simulate_retrieval(uuid,text,text)
  from public,anon,authenticated;
grant execute on function public.sauli_issue_retrieval(uuid,uuid,text,integer,text),
  public.sauli_retrieval_status(uuid,uuid),public.sauli_replace_retrieval(uuid,uuid,text,integer),
  public.sauli_validate_retrieval(text,text),public.sauli_simulate_retrieval(uuid,text,text)
  to service_role;
