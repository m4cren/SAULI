-- Storage assignment and claimant decisions. Apply after the initial SAULI schema.
alter table public.found_items
  add column if not exists storage_size text,
  add column if not exists placement_status text not null default 'unassigned',
  add column if not exists placed_at timestamptz;
alter table public.found_items
  drop constraint if exists found_items_storage_size_check,
  drop constraint if exists found_items_placement_status_check;
alter table public.found_items
  add constraint found_items_storage_size_check check (storage_size is null or storage_size in ('pocket','medium')),
  add constraint found_items_placement_status_check check (placement_status in ('unassigned','reserved','placed'));

create table if not exists public.storage_slots (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  size_class text not null check (size_class in ('pocket','medium')),
  ordinal integer not null,
  status text not null default 'available' check (status in ('available','reserved','occupied','out_of_service')),
  current_found_item_id uuid unique references public.found_items(id) on delete restrict,
  reserved_at timestamptz,
  occupied_at timestamptz,
  updated_at timestamptz not null default now(),
  unique(size_class,ordinal),
  check ((size_class = 'pocket' and ordinal between 1 and 10 and code = 'P-' || lpad(ordinal::text,2,'0'))
      or (size_class = 'medium' and ordinal between 1 and 5 and code = 'M-' || lpad(ordinal::text,2,'0'))),
  check ((status in ('available','out_of_service') and current_found_item_id is null)
      or (status in ('reserved','occupied') and current_found_item_id is not null))
);
create index if not exists storage_slots_assignment_idx on public.storage_slots(size_class,status,ordinal);
drop trigger if exists storage_slots_updated_at on public.storage_slots;
create trigger storage_slots_updated_at before update on public.storage_slots
for each row execute function public.sauli_set_updated_at();

insert into public.storage_slots(code,size_class,ordinal)
select 'P-' || lpad(n::text,2,'0'),'pocket',n from generate_series(1,10) as n
union all
select 'M-' || lpad(n::text,2,'0'),'medium',n from generate_series(1,5) as n
on conflict (code) do nothing;

create table if not exists public.storage_slot_events (
  id bigint generated always as identity primary key,
  slot_id uuid not null references public.storage_slots(id) on delete restrict,
  found_item_id uuid references public.found_items(id) on delete restrict,
  event_type text not null check (event_type in ('slot_reserved','simulated_door_ready','simulated_item_placed','reservation_released','slot_out_of_service')),
  event_source text not null,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index if not exists storage_slot_events_slot_idx on public.storage_slot_events(slot_id,created_at desc);

alter table public.match_candidates
  add column if not exists decision text not null default 'pending',
  add column if not exists decided_at timestamptz;
alter table public.match_candidates drop constraint if exists match_candidates_decision_check;
alter table public.match_candidates
  add constraint match_candidates_decision_check check (decision in ('pending','accepted','rejected'));

-- A single row lock determines the first free position. All inserts roll back
-- if assignment cannot complete; no found-item orphan is left behind.
create or replace function public.reserve_sauli_storage_slot(p_item jsonb,p_size text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_item public.found_items;
  v_slot public.storage_slots;
begin
  if p_size not in ('pocket','medium') or p_size is null then
    raise exception using message = 'INVALID_STORAGE_SIZE', errcode = 'P0001';
  end if;
  select * into v_item from public.found_items
    where idempotency_key = (p_item->>'idempotency_key')::uuid for update;
  if found then
    select * into v_slot from public.storage_slots where current_found_item_id = v_item.id;
    if not found then raise exception using message = 'STORAGE_STATE_CONFLICT', errcode = 'P0001'; end if;
    return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
  end if;
  select * into v_slot from public.storage_slots
    where size_class = p_size and status = 'available'
    order by ordinal limit 1 for update skip locked;
  if not found then
    raise exception using message = 'NO_AVAILABLE_STORAGE_SLOT', errcode = 'P0001';
  end if;
  v_item := jsonb_populate_record(null::public.found_items,p_item);
  v_item.storage_size := p_size;
  v_item.placement_status := 'reserved';
  v_item.placed_at := null;
  v_item.created_at := now();
  v_item.updated_at := now();
  insert into public.found_items select (v_item).* returning * into v_item;
  update public.storage_slots set status = 'reserved',current_found_item_id = v_item.id,
    reserved_at = now(),occupied_at = null where id = v_slot.id returning * into v_slot;
  insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
    values(v_slot.id,v_item.id,'slot_reserved','kiosk_web'),
          (v_slot.id,v_item.id,'simulated_door_ready','web_simulation');
  return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
end;
$$;

create or replace function public.simulate_sauli_placement(p_item_id uuid,p_slot_code text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_item public.found_items;
  v_slot public.storage_slots;
begin
  select * into v_slot from public.storage_slots where code = p_slot_code for update;
  if not found or v_slot.current_found_item_id is distinct from p_item_id then
    raise exception using message = 'SLOT_RESERVATION_MISMATCH', errcode = 'P0001';
  end if;
  select * into v_item from public.found_items where id = p_item_id for update;
  if v_slot.status = 'occupied' and v_item.placement_status = 'placed' then
    return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
  end if;
  if v_slot.status <> 'reserved' or v_item.placement_status <> 'reserved' then
    raise exception using message = 'SLOT_RESERVATION_MISMATCH', errcode = 'P0001';
  end if;
  update public.storage_slots set status = 'occupied',occupied_at = now()
    where id = v_slot.id returning * into v_slot;
  update public.found_items set placement_status = 'placed',placed_at = v_slot.occupied_at
    where id = p_item_id returning * into v_item;
  insert into public.storage_slot_events(slot_id,found_item_id,event_type,event_source)
    values(v_slot.id,p_item_id,'simulated_item_placed','web_simulation');
  return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
end;
$$;

-- Keep the search audit atomic while recording the verified claimant owner.
create or replace function public.record_sauli_search(p_search jsonb,p_candidates jsonb)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare v_id uuid;
begin
  insert into public.search_requests (
    id,idempotency_key,user_id,description,category,color,last_seen_location,last_seen_at,
    filters,query_analysis,search_summary
  ) values (
    (p_search->>'id')::uuid,(p_search->>'idempotency_key')::uuid,
    (p_search->>'user_id')::uuid,p_search->>'description',p_search->>'category',
    p_search->>'color',p_search->>'last_seen_location',
    (p_search->>'last_seen_at')::timestamptz,p_search->'filters',p_search->'query_analysis',
    p_search->>'search_summary'
  ) returning id into v_id;
  insert into public.match_candidates (
    id,search_request_id,found_item_id,rank,rank_score,score_breakdown,
    matched_attributes,differences,explanation,ai_comparison
  ) select (item->>'id')::uuid,v_id,(item->>'found_item_id')::uuid,(item->>'rank')::integer,
    (item->>'rank_score')::numeric,item->'score_breakdown',
    array(select jsonb_array_elements_text(item->'matched_attributes')),
    array(select jsonb_array_elements_text(item->'differences')),
    item->>'explanation',item->'ai_comparison'
  from jsonb_array_elements(p_candidates) as e(item);
  return v_id;
end;
$$;

create or replace function public.decide_sauli_match(p_candidate_id uuid,p_user_id uuid,p_decision text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_candidate public.match_candidates;
  v_item public.found_items;
  v_slot public.storage_slots;
begin
  if p_decision not in ('accepted','rejected') then
    raise exception using message = 'INVALID_MATCH_DECISION', errcode = 'P0001';
  end if;
  select mc.* into v_candidate from public.match_candidates mc
    join public.search_requests sr on sr.id = mc.search_request_id
    where mc.id = p_candidate_id and sr.user_id = p_user_id for update of mc;
  if not found then raise exception using message = 'MATCH_NOT_FOUND', errcode = 'P0001'; end if;
  if v_candidate.decision = p_decision then
    if p_decision = 'accepted' then
      select * into v_slot from public.storage_slots where current_found_item_id = v_candidate.found_item_id;
      return jsonb_build_object('candidate',to_jsonb(v_candidate),'slot',to_jsonb(v_slot));
    end if;
    return jsonb_build_object('candidate',to_jsonb(v_candidate));
  end if;
  if v_candidate.decision <> 'pending' then
    raise exception using message = 'MATCH_DECISION_CONFLICT', errcode = 'P0001';
  end if;
  if p_decision = 'accepted' then
    select * into v_slot from public.storage_slots
      where current_found_item_id = v_candidate.found_item_id and status = 'occupied' for update;
    if not found then raise exception using message = 'MATCH_NO_LONGER_AVAILABLE', errcode = 'P0001'; end if;
    select * into v_item from public.found_items where id = v_candidate.found_item_id for update;
    if not found or v_item.status <> 'available' or v_item.placement_status <> 'placed' then
      raise exception using message = 'MATCH_NO_LONGER_AVAILABLE', errcode = 'P0001';
    end if;
    update public.found_items set status = 'claimed' where id = v_item.id;
  end if;
  update public.match_candidates set decision = p_decision,decided_at = now()
    where id = p_candidate_id returning * into v_candidate;
  return jsonb_build_object('candidate',to_jsonb(v_candidate),'slot',to_jsonb(v_slot));
end;
$$;

alter table public.storage_slots enable row level security;
alter table public.storage_slot_events enable row level security;
revoke all on public.storage_slots,public.storage_slot_events from anon,authenticated;
revoke all on function public.reserve_sauli_storage_slot(jsonb,text) from public,anon,authenticated;
revoke all on function public.simulate_sauli_placement(uuid,text) from public,anon,authenticated;
revoke all on function public.decide_sauli_match(uuid,uuid,text) from public,anon,authenticated;
grant all on public.storage_slots,public.storage_slot_events to service_role;
grant usage,select on sequence public.storage_slot_events_id_seq to service_role;
grant execute on function public.reserve_sauli_storage_slot(jsonb,text) to service_role;
grant execute on function public.simulate_sauli_placement(uuid,text) to service_role;
grant execute on function public.decide_sauli_match(uuid,uuid,text) to service_role;
