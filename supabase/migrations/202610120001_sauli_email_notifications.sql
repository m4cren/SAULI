-- Durable missing reports, placement matching, and server-only email outbox.
-- Legacy phone/SMS data is intentionally left untouched if it exists elsewhere.
create table public.missing_reports (
  id uuid primary key default gen_random_uuid(),
  idempotency_key uuid not null unique,
  search_request_id uuid not null unique references public.search_requests(id) on delete restrict,
  claimant_user_id uuid not null references auth.users(id) on delete restrict,
  claimant_name text not null default 'SAULI user',
  summary text not null,
  notification_email text not null check (char_length(notification_email) between 3 and 254),
  email_notifications_enabled boolean not null default false,
  status text not null default 'active' check (status in ('active','matched','resolved','cancelled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index missing_reports_active_idx on public.missing_reports(status,created_at);
create index missing_reports_claimant_idx on public.missing_reports(claimant_user_id,created_at desc);
create trigger missing_reports_updated_at before update on public.missing_reports
  for each row execute function public.sauli_set_updated_at();

create table public.matching_jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('report_posted','item_placed')),
  missing_report_id uuid references public.missing_reports(id) on delete restrict,
  found_item_id uuid references public.found_items(id) on delete restrict,
  status text not null default 'pending' check (status in ('pending','processing','retry_pending','completed','failed')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz not null default now(),
  lease_until timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((kind = 'report_posted' and missing_report_id is not null and found_item_id is null)
    or (kind = 'item_placed' and found_item_id is not null and missing_report_id is null))
);
create unique index matching_jobs_report_once on public.matching_jobs(missing_report_id) where kind = 'report_posted';
create unique index matching_jobs_item_once on public.matching_jobs(found_item_id) where kind = 'item_placed';
create index matching_jobs_due_idx on public.matching_jobs(status,next_attempt_at,created_at);
create trigger matching_jobs_updated_at before update on public.matching_jobs
  for each row execute function public.sauli_set_updated_at();

create table public.email_notifications (
  id uuid primary key default gen_random_uuid(),
  matching_job_id uuid not null references public.matching_jobs(id) on delete restrict,
  missing_report_id uuid not null references public.missing_reports(id) on delete restrict,
  found_item_id uuid not null references public.found_items(id) on delete restrict,
  match_candidate_id uuid not null references public.match_candidates(id) on delete restrict,
  recipient_email text not null,
  provider text not null default 'emailjs' check (provider = 'emailjs'),
  notification_type text not null default 'possible_match' check (notification_type = 'possible_match'),
  status text not null default 'pending' check (status in
    ('pending','sending','retry_pending','sent','failed','skipped_disabled','skipped_unconfigured','cancelled','delivery_unknown')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  last_attempt_at timestamptz,
  next_attempt_at timestamptz not null default now(),
  lease_until timestamptz,
  sent_at timestamptz,
  last_error text,
  provider_response text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(missing_report_id,match_candidate_id,provider,notification_type),
  unique(matching_job_id,missing_report_id)
);
create index email_notifications_due_idx on public.email_notifications(status,next_attempt_at,created_at);
create trigger email_notifications_updated_at before update on public.email_notifications
  for each row execute function public.sauli_set_updated_at();

-- A single database row enforces EmailJS's account-wide one-request-per-second limit.
create table public.sauli_email_dispatch_clock (
  id integer primary key check (id = 1),
  next_allowed_at timestamptz not null default now()
);
insert into public.sauli_email_dispatch_clock(id) values(1);

create function public.sauli_create_missing_report(
  p_search_id uuid,p_user_id uuid,p_email text,p_enabled boolean,p_name text,p_key uuid
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_search public.search_requests; v_report public.missing_reports;
begin
  select * into v_search from public.search_requests
    where id = p_search_id and user_id = p_user_id for update;
  if not found then return jsonb_build_object('error','SEARCH_NOT_FOUND'); end if;
  select * into v_report from public.missing_reports
    where search_request_id = p_search_id or idempotency_key = p_key limit 1;
  if found then
    if v_report.claimant_user_id <> p_user_id or v_report.search_request_id <> p_search_id
      then return jsonb_build_object('error','REPORT_CONFLICT'); end if;
    return to_jsonb(v_report);
  end if;
  insert into public.missing_reports(idempotency_key,search_request_id,claimant_user_id,
    claimant_name,summary,notification_email,email_notifications_enabled)
    values(p_key,p_search_id,p_user_id,coalesce(nullif(trim(p_name),''),'SAULI user'),
      v_search.search_summary,lower(trim(p_email)),p_enabled)
    returning * into v_report;
  insert into public.matching_jobs(kind,missing_report_id)
    values('report_posted',v_report.id) on conflict do nothing;
  return to_jsonb(v_report);
end;
$$;

-- Placement and job enqueue commit together. Matching and email run later.
create or replace function public.simulate_sauli_placement(p_item_id uuid,p_slot_code text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_item public.found_items; v_slot public.storage_slots;
begin
  select * into v_slot from public.storage_slots where code = p_slot_code for update;
  if not found or v_slot.current_found_item_id is distinct from p_item_id then
    raise exception using message = 'SLOT_RESERVATION_MISMATCH', errcode = 'P0001';
  end if;
  select * into v_item from public.found_items where id = p_item_id for update;
  if v_slot.status = 'occupied' and v_item.placement_status = 'placed' then
    insert into public.matching_jobs(kind,found_item_id) values('item_placed',p_item_id) on conflict do nothing;
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
  insert into public.matching_jobs(kind,found_item_id) values('item_placed',p_item_id) on conflict do nothing;
  return jsonb_build_object('item',to_jsonb(v_item),'slot',to_jsonb(v_slot));
end;
$$;

create function public.sauli_claim_matching_job() returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_job public.matching_jobs;
begin
  select * into v_job from public.matching_jobs
    where (status in ('pending','retry_pending') and next_attempt_at <= now())
       or (status = 'processing' and lease_until < now())
    order by created_at,id limit 1 for update skip locked;
  if not found then return null; end if;
  update public.matching_jobs set status = 'processing',attempt_count = attempt_count + 1,
    lease_until = now() + interval '30 minutes'
    where id = v_job.id returning * into v_job;
  return to_jsonb(v_job);
end;
$$;

create function public.sauli_finish_matching_job(p_id uuid,p_status text,p_error text default null)
returns void language plpgsql security invoker set search_path = '' as $$
begin
  if p_status not in ('completed','retry_pending','failed') then raise exception 'INVALID_JOB_STATUS'; end if;
  update public.matching_jobs set status = p_status,lease_until = null,
    next_attempt_at = case when p_status = 'retry_pending'
      then now() + make_interval(secs => least(3600,30 * power(2,least(attempt_count,7))::integer))
      else next_attempt_at end,
    last_error = left(p_error,200)
    where id = p_id and status = 'processing';
end;
$$;

-- Candidate insert and one best notification are atomic and idempotent.
create function public.sauli_store_report_matches(p_report_id uuid,p_job_id uuid,p_matches jsonb,p_min_score numeric)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_report public.missing_reports;
  v_match jsonb;
  v_candidate public.match_candidates;
  v_best_id uuid;
  v_best_item uuid;
  v_best_score numeric := -1;
  v_rank integer;
  v_item_id uuid;
  v_score numeric;
begin
  select * into v_report from public.missing_reports where id = p_report_id for update;
  if not found or v_report.status <> 'active' then return jsonb_build_object('queued',false); end if;
  if jsonb_typeof(p_matches) <> 'array' then raise exception 'INVALID_MATCH_LIST'; end if;
  for v_match in select value from jsonb_array_elements(p_matches) loop
    v_item_id := (v_match->>'found_item_id')::uuid;
    v_score := (v_match->>'rank_score')::numeric;
    if v_score < p_min_score or v_score > 100 or v_score < 0 then continue; end if;
    if not exists (
      select 1 from public.found_items fi join public.storage_slots ss
        on ss.current_found_item_id = fi.id and ss.status = 'occupied'
      where fi.id = v_item_id and fi.status = 'available' and fi.placement_status = 'placed'
    ) then continue; end if;
    select * into v_candidate from public.match_candidates
      where search_request_id = v_report.search_request_id and found_item_id = v_item_id;
    if not found then
      select coalesce(max(rank),0) + 1 into v_rank from public.match_candidates
        where search_request_id = v_report.search_request_id;
      insert into public.match_candidates(id,search_request_id,found_item_id,rank,rank_score,
        score_breakdown,matched_attributes,differences,explanation,ai_comparison)
      values((v_match->>'id')::uuid,v_report.search_request_id,v_item_id,v_rank,v_score,
        v_match->'score_breakdown',array(select jsonb_array_elements_text(v_match->'matched_attributes')),
        array(select jsonb_array_elements_text(v_match->'differences')),
        v_match->>'explanation',v_match->'ai_comparison') returning * into v_candidate;
    elsif v_candidate.decision = 'pending' and v_score > v_candidate.rank_score then
      update public.match_candidates set rank_score = v_score,
        score_breakdown = v_match->'score_breakdown',
        matched_attributes = array(select jsonb_array_elements_text(v_match->'matched_attributes')),
        differences = array(select jsonb_array_elements_text(v_match->'differences')),
        explanation = v_match->>'explanation',ai_comparison = v_match->'ai_comparison'
        where id = v_candidate.id returning * into v_candidate;
    end if;
    if v_candidate.decision <> 'pending' then continue; end if;
    if exists (select 1 from public.email_notifications
      where missing_report_id = p_report_id and match_candidate_id = v_candidate.id) then continue; end if;
    if v_score > v_best_score then
      v_best_score := v_score; v_best_id := v_candidate.id; v_best_item := v_item_id;
    end if;
  end loop;
  if v_best_id is not null and not exists (select 1 from public.email_notifications
    where matching_job_id = p_job_id and missing_report_id = p_report_id) then
    insert into public.email_notifications(matching_job_id,missing_report_id,found_item_id,match_candidate_id,
      recipient_email,status)
    values(p_job_id,v_report.id,v_best_item,v_best_id,v_report.notification_email,
      case when v_report.email_notifications_enabled then 'pending' else 'skipped_disabled' end)
    on conflict do nothing;
  end if;
  return jsonb_build_object('queued',v_best_id is not null,'candidate_id',v_best_id);
end;
$$;

create function public.sauli_claim_email_notification() returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_clock public.sauli_email_dispatch_clock; v_email public.email_notifications;
begin
  -- Ambiguous abandoned sends are held for manual investigation, never resent automatically.
  update public.email_notifications set status = 'delivery_unknown',lease_until = null,
    last_error = 'Sender stopped before delivery was confirmed'
    where status = 'sending' and lease_until < now();
  update public.email_notifications en set status = 'cancelled'
    from public.missing_reports mr
    where en.missing_report_id = mr.id and mr.status <> 'active'
      and en.status in ('pending','retry_pending');
  select * into v_clock from public.sauli_email_dispatch_clock where id = 1 for update;
  if v_clock.next_allowed_at > now() then return null; end if;
  select en.* into v_email from public.email_notifications en
    join public.missing_reports mr on mr.id = en.missing_report_id
    join public.match_candidates mc on mc.id = en.match_candidate_id
    where en.status in ('pending','retry_pending') and en.next_attempt_at <= now()
      and mr.status = 'active' and mr.email_notifications_enabled and mc.decision = 'pending'
    order by en.created_at,en.id limit 1 for update of en skip locked;
  if not found then return null; end if;
  update public.sauli_email_dispatch_clock set next_allowed_at = now() + interval '1 second' where id = 1;
  update public.email_notifications set status = 'sending',attempt_count = attempt_count + 1,
    last_attempt_at = now(),lease_until = now() + interval '2 minutes'
    where id = v_email.id returning * into v_email;
  return to_jsonb(v_email);
end;
$$;

create function public.sauli_finish_email_notification(
  p_id uuid,p_status text,p_error text default null,p_response text default null
) returns void language plpgsql security invoker set search_path = '' as $$
begin
  if p_status not in ('sent','retry_pending','failed','skipped_unconfigured','skipped_disabled','delivery_unknown','cancelled')
    then raise exception 'INVALID_EMAIL_STATUS'; end if;
  update public.email_notifications set status = p_status,lease_until = null,
    last_error = left(p_error,200),provider_response = left(p_response,100),
    sent_at = case when p_status = 'sent' then now() else sent_at end,
    next_attempt_at = case when p_status = 'retry_pending' then now() + interval '30 seconds'
      else next_attempt_at end
    where id = p_id and status in ('sending','pending','retry_pending');
end;
$$;

create function public.sauli_retry_unconfigured_email() returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
  update public.email_notifications en set status = 'pending',next_attempt_at = now(),last_error = null
    from public.missing_reports mr
    where en.missing_report_id = mr.id and en.status = 'skipped_unconfigured'
      and mr.status = 'active' and mr.email_notifications_enabled;
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

-- Keep the existing ownership/slot checks while updating report monitoring.
create or replace function public.decide_sauli_match(p_candidate_id uuid,p_user_id uuid,p_decision text)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_candidate public.match_candidates;
  v_item public.found_items;
  v_slot public.storage_slots;
  v_report public.missing_reports;
begin
  if p_decision not in ('accepted','rejected') then
    raise exception using message = 'INVALID_MATCH_DECISION', errcode = 'P0001';
  end if;
  -- Both matching and decisions lock the report before the candidate.
  select mr.* into v_report from public.missing_reports mr
    join public.match_candidates mc on mc.search_request_id = mr.search_request_id
    join public.search_requests sr on sr.id = mc.search_request_id
    where mc.id = p_candidate_id and sr.user_id = p_user_id for update of mr;
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
  if v_report.id is not null and v_report.status <> 'active' then
    raise exception using message = 'MATCH_DECISION_CONFLICT', errcode = 'P0001';
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
  if p_decision = 'accepted' then
    update public.missing_reports set status = 'matched'
      where search_request_id = v_candidate.search_request_id and status = 'active';
    update public.email_notifications set status = 'cancelled'
      where missing_report_id in (select id from public.missing_reports
        where search_request_id = v_candidate.search_request_id)
        and status in ('pending','retry_pending');
  else
    update public.email_notifications set status = 'cancelled'
      where match_candidate_id = p_candidate_id and status in ('pending','retry_pending');
  end if;
  return jsonb_build_object('candidate',to_jsonb(v_candidate),'slot',to_jsonb(v_slot));
end;
$$;

alter table public.missing_reports enable row level security;
alter table public.matching_jobs enable row level security;
alter table public.email_notifications enable row level security;
alter table public.sauli_email_dispatch_clock enable row level security;
revoke all on public.missing_reports,public.matching_jobs,public.email_notifications,
  public.sauli_email_dispatch_clock from anon,authenticated;
grant all on public.missing_reports,public.matching_jobs,public.email_notifications,
  public.sauli_email_dispatch_clock to service_role;
revoke all on function public.sauli_create_missing_report(uuid,uuid,text,boolean,text,uuid),
  public.sauli_claim_matching_job(),public.sauli_finish_matching_job(uuid,text,text),
  public.sauli_store_report_matches(uuid,uuid,jsonb,numeric),public.sauli_claim_email_notification(),
  public.sauli_finish_email_notification(uuid,text,text,text),public.sauli_retry_unconfigured_email()
  from public,anon,authenticated;
grant execute on function public.sauli_create_missing_report(uuid,uuid,text,boolean,text,uuid),
  public.sauli_claim_matching_job(),public.sauli_finish_matching_job(uuid,text,text),
  public.sauli_store_report_matches(uuid,uuid,jsonb,numeric),public.sauli_claim_email_notification(),
  public.sauli_finish_email_notification(uuid,text,text,text),public.sauli_retry_unconfigured_email()
  to service_role;
