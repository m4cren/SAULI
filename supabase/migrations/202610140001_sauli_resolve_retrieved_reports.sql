-- Completing a retrieval also closes the claimant's accepted missing report.
-- The report table was added after the retrieval function, so earlier
-- completions left their reports in the matched state.
begin;

create function public.sauli_resolve_report_after_retrieval()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  update public.missing_reports as report
  set status = 'resolved'
  from public.match_candidates as candidate
  where candidate.id = new.match_candidate_id
    and candidate.found_item_id = new.found_item_id
    and candidate.decision = 'accepted'
    and report.search_request_id = candidate.search_request_id
    and report.claimant_user_id = new.claimant_user_id
    and report.status = 'matched';
  return new;
end;
$$;

revoke all on function public.sauli_resolve_report_after_retrieval()
  from public, anon, authenticated;

create trigger retrieval_sessions_resolve_report
after update of status on public.retrieval_sessions
for each row
when (new.status = 'completed' and old.status is distinct from new.status)
execute function public.sauli_resolve_report_after_retrieval();

-- Repair reports for sessions completed before this migration was applied.
update public.missing_reports as report
set status = 'resolved'
from public.match_candidates as candidate
join public.retrieval_sessions as session
  on session.match_candidate_id = candidate.id
 and session.found_item_id = candidate.found_item_id
join public.found_items as item on item.id = session.found_item_id
where report.search_request_id = candidate.search_request_id
  and report.claimant_user_id = session.claimant_user_id
  and report.status = 'matched'
  and candidate.decision = 'accepted'
  and session.status = 'completed'
  and item.status = 'retrieved';

commit;
