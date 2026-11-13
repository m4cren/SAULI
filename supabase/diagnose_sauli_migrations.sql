-- SAULI catalog diagnostic. Read-only: one WITH ... SELECT statement.
-- Run the complete file in the Supabase SQL Editor. It does not call SAULI RPCs.
-- "present" means compatible catalog evidence, not proof of migration history.
with
expected_tables(migration, name) as (values
  ('202610080001','found_items'), ('202610080001','search_requests'),
  ('202610080001','match_candidates'),
  ('202610110001','storage_slots'), ('202610110001','storage_slot_events'),
  ('202610110002','retrieval_sessions'), ('202610110002','retrieval_events'),
  ('202610110002','retrieval_logs'),
  ('202610120001','missing_reports'), ('202610120001','matching_jobs'),
  ('202610120001','email_notifications'), ('202610120001','sauli_email_dispatch_clock'),
  ('202611020001','sauli_units'), ('202611020001','sauli_deployment_guard'),
  ('202611020001','kiosk_devices'), ('202611020001','kiosk_device_credentials'),
  ('202611020001','kiosk_pairing_requests'), ('202611020001','kiosk_browser_bootstraps'),
  ('202611020001','kiosk_browser_sessions'), ('202611020001','kiosk_device_events'),
  ('202611020001','kiosk_rate_limits'),
  ('202611070001','sauli_hardware_snapshots'),
  ('202611070001','sauli_hardware_commands'),
  ('202611090001','sauli_hardware_presence'),
  ('202611090001','sauli_hardware_presence_events'),
  ('202611090001','sauli_hardware_incidents'),
  ('202611090002','sauli_hardware_transactions'),
  ('202611130001','sauli_hardware_review_resolutions')
),
expected_columns(migration, relation, column_name, data_type, must_be_not_null) as (values
  ('202610110001','found_items','storage_size','text',false),
  ('202610110001','found_items','placement_status','text',true),
  ('202610110001','found_items','placed_at','timestamp with time zone',false),
  ('202610310001','storage_slots','is_active','boolean',true),
  ('202611020001','found_items','unit_id','uuid',true),
  ('202611020001','storage_slots','unit_id','uuid',true),
  ('202611070001','sauli_hardware_snapshots','snapshot','jsonb',true),
  ('202611070001','sauli_hardware_snapshots','received_at','timestamp with time zone',true),
  ('202611070001','sauli_hardware_commands','action','text',true),
  ('202611090001','sauli_hardware_presence','boot_id','text',true),
  ('202611090001','sauli_hardware_presence','last_sequence','bigint',true),
  ('202611090001','sauli_hardware_presence','present','boolean',true),
  ('202611090001','sauli_hardware_incidents','active','boolean',true),
  ('202611090001','sauli_hardware_incidents','found_item_id','uuid',false),
  ('202611090001','sauli_hardware_incidents','retrieval_session_id','uuid',false),
  ('202611090002','sauli_hardware_transactions','unit_id','uuid',true),
  ('202611090002','sauli_hardware_transactions','assigned_slot_id','uuid',true),
  ('202611090002','sauli_hardware_transactions','phase','text',true),
  ('202611090002','sauli_hardware_transactions','last_door','text',true),
  ('202611090002','sauli_hardware_transactions','close_telemetry_seq','bigint',false),
  ('202611090002','sauli_hardware_transactions','close_boot_id','text',false),
  ('202611090002','sauli_hardware_transactions','command_id','text',false),
  ('202611130001','sauli_hardware_review_resolutions','id','uuid',true),
  ('202611130001','sauli_hardware_review_resolutions','unit_id','uuid',true),
  ('202611130001','sauli_hardware_review_resolutions','assigned_slot_id','uuid',true),
  ('202611130001','sauli_hardware_review_resolutions','actor_id','uuid',true),
  ('202611130001','sauli_hardware_review_resolutions','reason','text',true),
  ('202611130001','sauli_hardware_review_resolutions','previous_phase','text',true),
  ('202611130001','sauli_hardware_review_resolutions','previous_command_id','text',false),
  ('202611130001','sauli_hardware_review_resolutions','resolved_at','timestamp with time zone',true)
),
expected_rpcs(migration, signature) as (values
  ('202610080001','public.sauli_set_updated_at()'),
  ('202610080001','public.get_eligible_found_items(timestamp with time zone,integer)'),
  ('202610080001','public.record_sauli_search(jsonb,jsonb)'),
  ('202610110001','public.reserve_sauli_storage_slot(jsonb,text)'),
  ('202610110001','public.simulate_sauli_placement(uuid,text)'),
  ('202610110001','public.decide_sauli_match(uuid,uuid,text)'),
  ('202610110002','public.sauli_issue_retrieval(uuid,uuid,text,integer,text)'),
  ('202610110002','public.sauli_retrieval_status(uuid,uuid)'),
  ('202610110002','public.sauli_replace_retrieval(uuid,uuid,text,integer)'),
  ('202610110002','public.sauli_validate_retrieval(text,text)'),
  ('202610110002','public.sauli_simulate_retrieval(uuid,text,text)'),
  ('202610120001','public.sauli_create_missing_report(uuid,uuid,text,boolean,text,uuid)'),
  ('202610120001','public.sauli_claim_matching_job()'),
  ('202610120001','public.sauli_finish_matching_job(uuid,text,text)'),
  ('202610120001','public.sauli_store_report_matches(uuid,uuid,jsonb,numeric)'),
  ('202610120001','public.sauli_claim_email_notification()'),
  ('202610120001','public.sauli_finish_email_notification(uuid,text,text,text)'),
  ('202610120001','public.sauli_retry_unconfigured_email()'),
  ('202610140001','public.sauli_resolve_report_after_retrieval()'),
  ('202611020001','public.sauli_keep_unit_identity()'),
  ('202611020001','public.sauli_check_kiosk_rate_limit(text,text,integer,integer)'),
  ('202611020001','public.sauli_check_slot_item_unit()'),
  ('202611020001','public.sauli_keep_slot_unit()'),
  ('202611020001','public.sauli_check_slot_event_unit()'),
  ('202611020001','public.sauli_keep_item_unit()'),
  ('202611020001','public.sauli_provision_unit_slots(uuid)'),
  ('202611020001','public.sauli_register_unit(jsonb)'),
  ('202611020001','public.sauli_register_kiosk_device(uuid,text,text,text)'),
  ('202611020001','public.sauli_approve_kiosk_pairing(uuid,text,uuid,timestamp with time zone)'),
  ('202611020001','public.reserve_sauli_storage_slot(jsonb,text,uuid)'),
  ('202611020001','public.simulate_sauli_placement(uuid,text,uuid)'),
  ('202611020001','public.sauli_validate_unit_retrieval(text,text,uuid)'),
  ('202611020001','public.sauli_simulate_unit_retrieval(uuid,text,text,uuid)'),
  ('202611020001','public.sauli_redeem_pairing(text,text,text)'),
  ('202611020001','public.sauli_redeem_browser_bootstrap(text,text,timestamp with time zone)'),
  ('202611020001','public.sauli_rotate_device_credential(uuid,text,text)'),
  ('202611020001','public.sauli_revoke_device(uuid,uuid)'),
  ('202611070001','public.sauli_claim_hardware_commands(uuid,uuid)'),
  ('202611090001','public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean)'),
  ('202611090001','public.sauli_hardware_guidance(uuid)'),
  ('202611090002','public.sauli_reconcile_hardware_workflow(uuid,jsonb)'),
  ('202611110002','public.sauli_queue_workflow_unlock(uuid,uuid,uuid)'),
  ('202611130001','public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)')
),
critical_rpc_attributes(migration, signature) as (values
  ('202611110002','public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean)'),
  ('202611110002','public.sauli_reconcile_hardware_workflow(uuid,jsonb)'),
  ('202611110002','public.sauli_queue_workflow_unlock(uuid,uuid,uuid)'),
  ('202611130001','public.sauli_hardware_guidance(uuid)'),
  ('202611130001','public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)')
),
expected_constraints(migration, relation, constraint_name, fragment) as (values
  ('202610110001','found_items','found_items_storage_size_check','storage_size'),
  ('202610110001','found_items','found_items_placement_status_check','placement_status'),
  ('202610110001','match_candidates','match_candidates_decision_check','decision'),
  ('202610310001','storage_slots','storage_slots_active_code_check','is_active'),
  ('202611020001','found_items','found_items_unit_id_fkey','sauli_units'),
  ('202611020001','storage_slots','storage_slots_unit_id_fkey','sauli_units'),
  ('202611020001','storage_slots','storage_slots_unit_code_key','unit_id'),
  ('202611020001','storage_slots','storage_slots_unit_size_ordinal_key','unit_id'),
  ('202611090001','sauli_hardware_commands','sauli_hardware_commands_action_check','capture_light_off'),
  ('202611090001','storage_slot_events','storage_slot_events_event_type_check','hardware_item_placed'),
  ('202611090001','retrieval_events','retrieval_events_event_type_check','hardware_item_returned'),
  ('202611110002','sauli_hardware_incidents','sauli_hardware_incidents_workflow_check','num_nonnulls'),
  ('202611130001','sauli_hardware_review_resolutions','sauli_hardware_review_resolutions_reason_check','500'),
  ('202611130001','sauli_hardware_review_resolutions','sauli_hardware_review_resolutions_unit_id_fkey','sauli_units'),
  ('202611130001','sauli_hardware_review_resolutions','sauli_hardware_review_resolutions_assigned_slot_id_fkey','storage_slots')
),
expected_indexes(migration, name, fragment) as (values
  ('202610120001','matching_jobs_report_once','missing_report_id'),
  ('202610120001','matching_jobs_item_once','found_item_id'),
  ('202611020001','kiosk_devices_one_active_primary_per_unit','is_primary'),
  ('202611020001','kiosk_device_one_valid_credential','revoked_at'),
  ('202611090001','sauli_hardware_incidents_active_slot','active'),
  ('202611070001','sauli_hardware_commands_claim_idx','expires_at')
),
expected_triggers(migration, relation, name) as (values
  ('202610080001','found_items','found_items_updated_at'),
  ('202610140001','retrieval_sessions','retrieval_sessions_resolve_report'),
  ('202611020001','sauli_units','sauli_units_keep_identity'),
  ('202611020001','storage_slots','storage_slots_item_unit'),
  ('202611020001','storage_slots','storage_slots_keep_unit'),
  ('202611020001','storage_slot_events','storage_slot_events_item_unit'),
  ('202611020001','found_items','found_items_keep_unit')
),
body_markers(migration, signature, marker, fragment) as (values
  ('202610110003','public.sauli_retrieval_status(uuid,uuid)','validated slot history','re.event_type = ''qr_validated'''),
  ('202611110001','public.sauli_reconcile_hardware_workflow(uuid,jsonb)','fail closed pending count (historically ambiguous)','v_pending = 0'),
  ('202611110002','public.sauli_reconcile_hardware_workflow(uuid,jsonb)','idle snapshot slot audit','v_observed_slot'),
  ('202611110002','public.sauli_reconcile_hardware_workflow(uuid,jsonb)','sticky review phase','v_tx.phase = ''requires_review'''),
  ('202611110002','public.sauli_apply_hardware_presence(uuid,text,text,bigint,text,text,boolean)','idle incident resolution','and found_item_id is null and retrieval_session_id is null'),
  ('202611110002','public.sauli_queue_workflow_unlock(uuid,uuid,uuid)','safe unlock guard','HARDWARE_NOT_READY'),
  ('202611130001','public.sauli_hardware_guidance(uuid)','separate review flag','''review_required'',v_review_required'),
  ('202611130001','public.sauli_hardware_guidance(uuid)','incident-driven buzzer','where unit_id = p_unit_id and active) into v_buzzer'),
  ('202611130001','public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)','resolution audit insert','insert into public.sauli_hardware_review_resolutions'),
  ('202611130001','public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)','unopened review guard','REVIEW_NOT_ELIGIBLE'),
  ('202611130001','public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)','complete telemetry guard','INCOMPLETE_TELEMETRY')
),
checks as (
  select t.migration, 'table'::text as object_type, 'public.'||t.name as target,
    case when c.oid is null then 'missing' else 'ok' end as status,
    case when c.oid is null then 'relation absent' else 'relation present' end as detail
  from expected_tables t left join pg_catalog.pg_class c
    on c.oid = to_regclass('public.'||t.name) and c.relkind in ('r','p')
  union all
  select t.migration, 'rls', 'public.'||t.name,
    case when c.oid is null then 'missing'
      when c.relrowsecurity then 'ok' else 'mismatch' end,
    case when c.oid is null then 'relation absent'
      else 'row level security='||c.relrowsecurity::text end
  from expected_tables t left join pg_catalog.pg_class c
    on c.oid = to_regclass('public.'||t.name) and c.relkind in ('r','p')
  union all
  select x.migration, 'column', 'public.'||x.relation||'.'||x.column_name,
    case when a.attnum is null then 'missing'
      when pg_catalog.format_type(a.atttypid,a.atttypmod) <> x.data_type
        or (x.must_be_not_null and not a.attnotnull) then 'mismatch'
      else 'ok' end,
    coalesce(pg_catalog.format_type(a.atttypid,a.atttypmod),'absent')||
      case when a.attnotnull then ' NOT NULL' else ' nullable' end
  from expected_columns x left join pg_catalog.pg_attribute a
    on a.attrelid = to_regclass('public.'||x.relation)
      and a.attname = x.column_name and a.attnum > 0 and not a.attisdropped
  union all
  select f.migration, 'rpc', f.signature,
    case when p.oid is null then 'missing'
      when p.prokind <> 'f' then 'mismatch' else 'ok' end,
    case when p.oid is null then 'signature absent'
      else 'kind='||p.prokind::text||'; returns '||pg_catalog.pg_get_function_result(p.oid)||
        '; security '||case when p.prosecdef then 'definer' else 'invoker' end end
  from expected_rpcs f left join pg_catalog.pg_proc p
    on p.oid = to_regprocedure(f.signature)
  union all
  select f.migration, 'rpc attributes', f.signature,
    case when p.oid is null then 'missing'
      when pg_catalog.pg_get_function_result(p.oid) <> 'jsonb'
        or p.prosecdef or not coalesce(p.proconfig && array['search_path=','search_path=""']::text[],false)
        then 'mismatch' else 'ok' end,
    case when p.oid is null then 'function absent'
      else 'returns='||pg_catalog.pg_get_function_result(p.oid)||
        ', security_invoker='||(not p.prosecdef)::text||
        ', empty_search_path='||coalesce((p.proconfig && array['search_path=','search_path=""']::text[])::text,'false') end
  from critical_rpc_attributes f left join pg_catalog.pg_proc p
    on p.oid = to_regprocedure(f.signature)
  union all
  select k.migration, 'constraint', 'public.'||k.relation||'.'||k.constraint_name,
    case when c.oid is null then 'missing'
      when strpos(lower(pg_catalog.pg_get_constraintdef(c.oid)),lower(k.fragment)) = 0
        then 'mismatch' else 'ok' end,
    coalesce(pg_catalog.pg_get_constraintdef(c.oid),'absent')
  from expected_constraints k left join pg_catalog.pg_constraint c
    on c.conrelid = to_regclass('public.'||k.relation)
      and c.conname = k.constraint_name
  union all
  select i.migration, 'index', 'public.'||i.name,
    case when c.oid is null then 'missing'
      when strpos(lower(pg_catalog.pg_get_indexdef(c.oid)),lower(i.fragment)) = 0
        then 'mismatch' else 'ok' end,
    coalesce(pg_catalog.pg_get_indexdef(c.oid),'absent')
  from expected_indexes i left join pg_catalog.pg_class c
    on c.oid = to_regclass('public.'||i.name) and c.relkind in ('i','I')
  union all
  select t.migration, 'trigger', 'public.'||t.relation||'.'||t.name,
    case when g.oid is null then 'missing'
      when g.tgenabled not in ('O','A') then 'disabled' else 'ok' end,
    case when g.oid is null then 'absent' else 'enabled='||g.tgenabled::text end
  from expected_triggers t left join pg_catalog.pg_trigger g
    on g.tgrelid = to_regclass('public.'||t.relation)
      and g.tgname = t.name and not g.tgisinternal
  union all
  select b.migration, 'body marker', b.signature||' / '||b.marker,
    case when p.oid is null then 'missing'
      when strpos(lower(p.prosrc),lower(b.fragment)) = 0 then 'mismatch'
      else 'ok' end,
    case when p.oid is null then 'function absent'
      else 'source contains required marker='||
        (strpos(lower(p.prosrc),lower(b.fragment)) > 0)::text end
  from body_markers b left join pg_catalog.pg_proc p
    on p.oid = to_regprocedure(b.signature)
  union all
  select '202611130001', 'rpc access',
    'public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)',
    case when p.oid is null then 'missing'
      when p.prosecdef or not coalesce(p.proconfig && array['search_path=','search_path=""']::text[],false)
        or pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated',p.oid,'EXECUTE')
        or not pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE')
        then 'mismatch' else 'ok' end,
    case when p.oid is null then 'function absent'
      else 'security_invoker='|| (not p.prosecdef)::text ||
        ', empty_search_path='||coalesce((p.proconfig && array['search_path=','search_path=""']::text[])::text,'false')||
        ', anon_execute='||pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE')::text||
        ', authenticated_execute='||pg_catalog.has_function_privilege('authenticated',p.oid,'EXECUTE')::text||
        ', service_role_execute='||pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE')::text end
  from (select to_regprocedure('public.sauli_rearm_unopened_hardware_review(uuid,uuid,text)') as oid) r
  left join pg_catalog.pg_proc p on p.oid = r.oid
  union all
  select '202611130001', 'table access', 'public.sauli_hardware_review_resolutions',
    case when c.oid is null then 'missing'
      when pg_catalog.has_table_privilege('anon',c.oid,'SELECT')
        or pg_catalog.has_table_privilege('authenticated',c.oid,'SELECT')
        or not pg_catalog.has_table_privilege('service_role',c.oid,'SELECT')
        then 'mismatch' else 'ok' end,
    case when c.oid is null then 'table absent'
      else 'anon_select='||pg_catalog.has_table_privilege('anon',c.oid,'SELECT')::text||
        ', authenticated_select='||pg_catalog.has_table_privilege('authenticated',c.oid,'SELECT')::text||
        ', service_role_select='||pg_catalog.has_table_privilege('service_role',c.oid,'SELECT')::text end
  from (select to_regclass('public.sauli_hardware_review_resolutions') as oid) r
  left join pg_catalog.pg_class c on c.oid = r.oid
),
summary as (
  select migration, count(*) as total,
    count(*) filter (where status='ok') as ok_count,
    count(*) filter (where status <> 'ok') as issue_count
  from checks group by migration
),
report as (
  select 'summary'::text as section, s.migration, 'migration evidence'::text as object_type,
    s.migration as target,
    case when s.migration = '202611110001' then 'superseded_history_unknown'
      when s.issue_count = 0 then 'present'
      when s.ok_count = 0 then 'missing'
      else 'partial_or_conflicting' end as status,
    s.ok_count::text||'/'||s.total::text||' checks ok; catalog evidence only' as detail
  from summary s
  union all
  select 'detail', migration, object_type, target, status, detail from checks
  union all
  select 'legacy', '202611020001', 'obsolete constraint',
    'public.storage_slots.'||v.name,
    case when c.oid is null then 'ok' else 'obsolete_present' end,
    coalesce(pg_catalog.pg_get_constraintdef(c.oid),'absent as expected')
  from (values ('storage_slots_code_key'),('storage_slots_size_class_ordinal_key')) v(name)
  left join pg_catalog.pg_constraint c
    on c.conrelid = to_regclass('public.storage_slots') and c.conname = v.name
  union all
  select 'legacy', '202611110002', 'obsolete constraint',
    'public.sauli_hardware_incidents.sauli_hardware_incidents_check',
    case when c.oid is null then 'ok' else 'obsolete_present' end,
    coalesce(pg_catalog.pg_get_constraintdef(c.oid),'absent as expected')
  from (select 1) v left join pg_catalog.pg_constraint c
    on c.conrelid = to_regclass('public.sauli_hardware_incidents')
      and c.conname = 'sauli_hardware_incidents_check'
  union all
  select 'legacy', '202611020001', 'obsolete executable rpc', v.signature,
    case when p.oid is null then 'ok'
      when pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE')
        then 'obsolete_executable' else 'ok' end,
    case when p.oid is null then 'absent' else 'present; service_role execute='||
      pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE')::text end
  from (values ('public.reserve_sauli_storage_slot(jsonb,text)'),
               ('public.simulate_sauli_placement(uuid,text)')) v(signature)
  left join pg_catalog.pg_proc p on p.oid = to_regprocedure(v.signature)
  union all
  select 'overload', 'latest', 'unexpected critical rpc signature',
    'public.'||p.proname::text||'('||pg_catalog.pg_get_function_identity_arguments(p.oid)||')',
    'unexpected_overload', 'check for an older migration or manual definition'
  from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public'
    and p.proname in ('sauli_hardware_guidance','sauli_apply_hardware_presence',
      'sauli_reconcile_hardware_workflow','sauli_queue_workflow_unlock',
      'sauli_rearm_unopened_hardware_review')
    and not exists (select 1 from expected_rpcs e where to_regprocedure(e.signature)=p.oid)
  union all
  select 'history', 'all', 'migration ledger', 'supabase_migrations.schema_migrations',
    case when to_regclass('supabase_migrations.schema_migrations') is null
      then 'not_visible' else 'exists_untrusted' end,
    'Catalog checks above determine object state; a ledger row alone does not prove application'
  union all
  select 'interpretation', '202611110001', 'superseded body',
    'public.sauli_reconcile_hardware_workflow(uuid,jsonb)', 'history_indeterminate',
    '202611110002 replaces this body; the pending-count marker cannot prove 202611110001 ran'
  union all
  select 'order', '202611130001', 'dependency',
    '202611090002 -> 202611110001 -> 202611110002 -> 202611130001',
    'inspect_before_apply',
    '202611110002 requires 202611110001; 202611130001 requires the review-phase workflow and snapshot/presence tables'
)
select section,migration,object_type,target,status,detail from report
order by case section when 'summary' then 0 when 'detail' then 1
  when 'legacy' then 2 when 'overload' then 3 when 'history' then 4 else 5 end,
  migration,object_type,target;
