-- READ ONLY. Run this single query in the production SQL Editor and keep its
-- result. The four counts used by the reset are units, found_items,
-- missing_reports, and nonempty_slots. The other counts show the full impact.
with unit_layout as (
  select u.unit_code,
    count(s.id) filter (where s.is_active) as active_slots,
    count(s.id) filter (where s.is_active and s.size_class = 'pocket') as pocket_slots,
    count(s.id) filter (where s.is_active and s.size_class = 'medium') as medium_slots
  from public.sauli_units u
  left join public.storage_slots s on s.unit_id = u.id
  group by u.id, u.unit_code
)
select
  (select environment from public.sauli_deployment_guard where id = 1) as deployment_guard,
  (select count(*) from public.sauli_units) as units,
  (select count(*) from public.found_items) as found_items,
  (select count(*) from public.missing_reports) as missing_reports,
  (select count(*) from public.storage_slots
    where current_found_item_id is not null or status in ('reserved','occupied')
      or reserved_at is not null or occupied_at is not null) as nonempty_slots,
  (select count(*) from public.search_requests) as search_requests,
  (select count(*) from public.match_candidates) as match_candidates,
  (select count(*) from public.matching_jobs) as matching_jobs,
  (select count(*) from public.storage_slot_events) as storage_slot_events,
  (select count(*) from public.retrieval_sessions) as retrieval_sessions,
  (select count(*) from public.retrieval_events) as retrieval_events,
  (select count(*) from public.retrieval_logs) as retrieval_logs,
  (select count(*) from public.email_notifications) as email_notifications,
  (select coalesce(jsonb_agg(jsonb_build_object(
      'unit',u.unit_code, 'position',s.code, 'status',s.status,
      'active',s.is_active, 'found_item_id',s.current_found_item_id)
      order by u.unit_code,s.size_class,s.ordinal), '[]'::jsonb)
    from public.storage_slots s join public.sauli_units u on u.id = s.unit_id
    where s.current_found_item_id is not null or s.status in ('reserved','occupied')
      or s.reserved_at is not null or s.occupied_at is not null) as nonempty_position_details,
  (select coalesce(jsonb_agg(jsonb_build_object(
      'unit',unit_code, 'active_slots',active_slots,
      'pocket_slots',pocket_slots, 'medium_slots',medium_slots)
      order by unit_code), '[]'::jsonb) from unit_layout) as active_slot_layout;
