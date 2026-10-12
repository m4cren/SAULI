-- Development-only reset for the SAULI application data.
-- Run manually in the Supabase SQL Editor against the intended project.
-- Empty the sauli-item-images bucket through Supabase Storage first if you
-- also want to delete the uploaded image files. Never DELETE from storage.objects.
-- This file is not a migration and must not be included in db push.
-- It preserves auth.users, auth.identities, the bucket, schema, and all 15
-- seeded storage_slots rows, including their stable IDs and codes.
-- Retrieval sessions, events, and completed logs are also cleared.

begin;
set local lock_timeout = '10s';

-- Block concurrent kiosk/search writes until the reset commits.
lock table public.found_items, public.storage_slots,
  public.storage_slot_events, public.search_requests,
  public.match_candidates, public.retrieval_sessions,
  public.retrieval_events, public.retrieval_logs,
  public.missing_reports, public.matching_jobs,
  public.email_notifications, public.sauli_email_dispatch_clock in access exclusive mode;

-- Clear dependent records first. RESTART IDENTITY resets event IDs.
truncate table public.retrieval_events,
  public.retrieval_logs,
  public.retrieval_sessions,
  public.email_notifications,
  public.matching_jobs,
  public.missing_reports,
  public.storage_slot_events,
  public.match_candidates,
  public.search_requests restart identity;

-- Release every position before deleting its referenced found item.
update public.storage_slots
set status = 'available',
    current_found_item_id = null,
    reserved_at = null,
    occupied_at = null
where status <> 'available'
   or current_found_item_id is not null
   or reserved_at is not null
   or occupied_at is not null;

delete from public.found_items;
update public.sauli_email_dispatch_clock set next_allowed_at = now() where id = 1;

-- Abort the transaction if any listed table still contains records.
do $$
begin
  if exists (select 1 from public.found_items)
    or exists (select 1 from public.search_requests)
    or exists (select 1 from public.match_candidates)
    or exists (select 1 from public.storage_slot_events)
    or exists (select 1 from public.retrieval_events)
    or exists (select 1 from public.retrieval_logs)
    or exists (select 1 from public.retrieval_sessions)
    or exists (select 1 from public.missing_reports)
    or exists (select 1 from public.matching_jobs)
    or exists (select 1 from public.email_notifications)
    or exists (
      select 1 from public.storage_slots
      where status <> 'available'
         or current_found_item_id is not null
         or reserved_at is not null
         or occupied_at is not null
    ) then
    raise exception 'SAULI data reset verification failed';
  end if;
end;
$$;

commit;

-- Optional read-only verification after commit:
-- select 'found_items' as name, count(*) from public.found_items
-- union all select 'search_requests', count(*) from public.search_requests
-- union all select 'match_candidates', count(*) from public.match_candidates
-- union all select 'storage_slot_events', count(*) from public.storage_slot_events
-- union all select 'retrieval_sessions', count(*) from public.retrieval_sessions
-- union all select 'retrieval_events', count(*) from public.retrieval_events
-- union all select 'retrieval_logs', count(*) from public.retrieval_logs
-- union all select 'missing_reports', count(*) from public.missing_reports
-- union all select 'matching_jobs', count(*) from public.matching_jobs
-- union all select 'email_notifications', count(*) from public.email_notifications
-- union all select 'available_storage_slots', count(*) from public.storage_slots
--   where status = 'available' and current_found_item_id is null;
-- Expected counts: zero application records and 15 available slots.
