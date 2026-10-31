-- Retire the three positions removed from the physical cabinet without deleting
-- their rows or breaking item, event, and retrieval foreign keys.
begin;
set local lock_timeout = '10s';

lock table public.storage_slots in access exclusive mode;

-- A pending placement at a removed position needs an operator decision first.
-- Occupied positions remain linked to their items for supervised retrieval.
do $$
begin
  if exists (
    select 1 from public.storage_slots
    where code in ('P-09','P-10','M-05') and status = 'reserved'
  ) then
    raise exception using message = 'RETIRED_SLOT_HAS_PENDING_RESERVATION',
      hint = 'Inspect P-09, P-10, and M-05. Complete or resolve their reservations before applying this migration.';
  end if;
end;
$$;

alter table public.storage_slots
  add column if not exists is_active boolean not null default true;

update public.storage_slots set is_active = false
where code in ('P-09','P-10','M-05') and is_active;

-- The original migration remains unchanged for projects that already applied it.
-- Ensure the finalized positions exist, without touching their assignments.
insert into public.storage_slots(code,size_class,ordinal,is_active)
select 'P-' || lpad(n::text,2,'0'),'pocket',n,true from generate_series(1,8) as n
union all
select 'M-' || lpad(n::text,2,'0'),'medium',n,true from generate_series(1,4) as n
on conflict (code) do update set is_active = true
  where storage_slots.is_active is false;

alter table public.storage_slots
  drop constraint if exists storage_slots_active_code_check;
alter table public.storage_slots
  add constraint storage_slots_active_code_check check (
    not is_active or
    (size_class = 'pocket' and ordinal between 1 and 8 and code = 'P-' || lpad(ordinal::text,2,'0')) or
    (size_class = 'medium' and ordinal between 1 and 4 and code = 'M-' || lpad(ordinal::text,2,'0'))
  );

-- Keep the existing idempotent reservation transaction and lock order, but
-- never reserve an inactive position even if its old row is available.
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
    where size_class = p_size and status = 'available' and is_active
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

commit;
