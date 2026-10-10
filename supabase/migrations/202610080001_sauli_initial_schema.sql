-- Initial SAULI application schema. Review and apply in the Supabase SQL Editor.
-- Does not modify Supabase Auth or any existing rows.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.found_items (
  id uuid primary key default gen_random_uuid(),
  idempotency_key uuid not null unique,
  created_by uuid null references auth.users(id) on delete set null,
  status text not null default 'available' check (status in ('available','claimed','retrieved','archived')),
  found_location text not null check (char_length(found_location) between 1 and 200),
  finder_notes text null check (finder_notes is null or char_length(finder_notes) <= 1000),
  found_at timestamptz not null default now(),
  generic_name text not null,
  object_name text not null,
  alternative_names text[] not null default '{}',
  category text not null,
  subcategory text not null default '',
  document_kind text not null default 'none',
  document_owner_name text null,
  colors text[] not null default '{}',
  materials text[] not null default '{}',
  brand text null,
  model_or_variant text null,
  visible_markings text[] not null default '{}',
  functional_components text[] not null default '{}',
  condition text not null,
  condition_details text[] not null default '{}',
  patterns text[] not null default '{}',
  distinctive_features text[] not null default '{}',
  short_description text not null,
  extraction_summary text not null,
  confidence text not null check (confidence in ('high','medium','low')),
  needs_review boolean not null default false,
  uncertainty_notes text[] not null default '{}',
  analysis_json jsonb not null check (jsonb_typeof(analysis_json) = 'object'),
  search_document text not null,
  front_image_path text not null,
  back_image_path text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists found_items_status_idx on public.found_items(status);
create index if not exists found_items_found_at_idx on public.found_items(found_at);
create index if not exists found_items_status_found_at_idx on public.found_items(status,found_at);
create index if not exists found_items_category_idx on public.found_items(category);
create index if not exists found_items_created_by_idx on public.found_items(created_by);
create index if not exists found_items_idempotency_idx on public.found_items(idempotency_key);

create table if not exists public.search_requests (
  id uuid primary key default gen_random_uuid(),
  idempotency_key uuid not null unique,
  user_id uuid null references auth.users(id) on delete set null,
  description text not null,
  category text null,
  color text null,
  last_seen_location text null,
  last_seen_at timestamptz null,
  filters jsonb not null default '{}'::jsonb check (jsonb_typeof(filters) = 'object'),
  query_analysis jsonb not null check (jsonb_typeof(query_analysis) = 'object'),
  search_summary text not null,
  created_at timestamptz not null default now()
);
create index if not exists search_requests_idempotency_idx on public.search_requests(idempotency_key);
create index if not exists search_requests_user_idx on public.search_requests(user_id);
create index if not exists search_requests_created_idx on public.search_requests(created_at);
create index if not exists search_requests_last_seen_idx on public.search_requests(last_seen_at);

create table if not exists public.match_candidates (
  id uuid primary key default gen_random_uuid(),
  search_request_id uuid not null references public.search_requests(id) on delete cascade,
  found_item_id uuid not null references public.found_items(id) on delete cascade,
  rank integer not null check (rank > 0),
  rank_score numeric(5,2) not null check (rank_score between 0 and 100),
  score_breakdown jsonb not null check (jsonb_typeof(score_breakdown) = 'object'),
  matched_attributes text[] not null default '{}',
  differences text[] not null default '{}',
  explanation text not null,
  ai_comparison jsonb not null check (jsonb_typeof(ai_comparison) = 'object'),
  created_at timestamptz not null default now(),
  unique(search_request_id,found_item_id),
  unique(search_request_id,rank)
);
create index if not exists match_candidates_search_idx on public.match_candidates(search_request_id);
create index if not exists match_candidates_item_idx on public.match_candidates(found_item_id);
create index if not exists match_candidates_score_idx on public.match_candidates(rank_score);

create or replace function public.sauli_set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
drop trigger if exists found_items_updated_at on public.found_items;
create trigger found_items_updated_at before update on public.found_items
for each row execute function public.sauli_set_updated_at();

create or replace function public.get_eligible_found_items(
  p_last_seen_at timestamptz default null,
  p_limit integer default 50
) returns setof public.found_items
language sql stable security invoker set search_path = '' as $$
  select fi.* from public.found_items as fi
  where fi.status = 'available'
    and (p_last_seen_at is null or fi.found_at >= p_last_seen_at)
  order by fi.found_at desc, fi.id asc
  limit greatest(1,least(coalesce(p_limit,50),100));
$$;

-- Search request and candidate audit are one transaction through this RPC.
-- A candidate insert error rolls back the request insert automatically.
create or replace function public.record_sauli_search(
  p_search jsonb,
  p_candidates jsonb
) returns uuid
language plpgsql security invoker set search_path = '' as $$
declare
  v_id uuid;
begin
  insert into public.search_requests (
    id,idempotency_key,description,category,color,last_seen_location,last_seen_at,
    filters,query_analysis,search_summary
  ) values (
    (p_search->>'id')::uuid,(p_search->>'idempotency_key')::uuid,p_search->>'description',
    p_search->>'category',p_search->>'color',p_search->>'last_seen_location',
    (p_search->>'last_seen_at')::timestamptz,p_search->'filters',p_search->'query_analysis',
    p_search->>'search_summary'
  ) returning id into v_id;

  insert into public.match_candidates (
    search_request_id,found_item_id,rank,rank_score,score_breakdown,
    matched_attributes,differences,explanation,ai_comparison
  )
  select v_id,(item->>'found_item_id')::uuid,(item->>'rank')::integer,
    (item->>'rank_score')::numeric,item->'score_breakdown',
    array(select jsonb_array_elements_text(item->'matched_attributes')),
    array(select jsonb_array_elements_text(item->'differences')),
    item->>'explanation',item->'ai_comparison'
  from jsonb_array_elements(p_candidates) as e(item);
  return v_id;
end;
$$;

insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values ('sauli-item-images','sauli-item-images',false,10485760,array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

alter table public.found_items enable row level security;
alter table public.search_requests enable row level security;
alter table public.match_candidates enable row level security;
revoke all on public.found_items,public.search_requests,public.match_candidates from anon,authenticated;
revoke all on function public.get_eligible_found_items(timestamptz,integer) from public,anon,authenticated;
revoke all on function public.record_sauli_search(jsonb,jsonb) from public,anon,authenticated;
grant all on public.found_items,public.search_requests,public.match_candidates to service_role;
grant execute on function public.get_eligible_found_items(timestamptz,integer) to service_role;
grant execute on function public.record_sauli_search(jsonb,jsonb) to service_role;
