-- =====================================================
-- SAULI PRODUCTION OPERATIONAL RESET
-- Includes door-gated hardware transactions migration.
-- Preserves kiosk registrations, credentials, browser sessions,
-- audit history, units, slot definitions, Auth users and Storage files.
--
-- DESTRUCTIVE: Back up database, physically empty cabinet,
-- and stop kiosk/hardware/backend/worker writes before execution.
-- One atomic DO statement: errors roll back all changes.
-- =====================================================
DO $sauli_reset$
DECLARE
    v_devices_before jsonb;
    v_credentials_before jsonb;
    v_sessions_before jsonb;
    v_devices_after jsonb;
    v_credentials_after jsonb;
    v_sessions_after jsonb;
BEGIN
    PERFORM set_config('lock_timeout', '10s', true);

    LOCK TABLE
        public.sauli_deployment_guard,
        public.sauli_units,
        public.sauli_hardware_snapshots,
        public.sauli_hardware_commands,
        public.sauli_hardware_presence,
        public.sauli_hardware_presence_events,
        public.sauli_hardware_incidents,
        public.sauli_hardware_transactions,
        public.found_items,
        public.storage_slots,
        public.storage_slot_events,
        public.match_candidates,
        public.retrieval_sessions,
        public.retrieval_events,
        public.retrieval_logs,
        public.matching_jobs,
        public.email_notifications,
        public.missing_reports,
        public.search_requests,
        public.sauli_email_dispatch_clock
    IN ACCESS EXCLUSIVE MODE;

    LOCK TABLE
        public.kiosk_devices,
        public.kiosk_device_credentials,
        public.kiosk_browser_sessions
    IN SHARE MODE;

    IF (
        SELECT environment
        FROM public.sauli_deployment_guard
        WHERE id = 1
    ) IS DISTINCT FROM 'production' THEN
        RAISE EXCEPTION 'SAULI_PRODUCTION_RESET_WRONG_ENVIRONMENT';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.sauli_units)
       OR EXISTS (
        SELECT 1 FROM public.sauli_units u
        WHERE (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active) <> 12
           OR (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active
                 AND s.size_class = 'pocket') <> 8
           OR (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active
                 AND s.size_class = 'medium') <> 4
    ) THEN
        RAISE EXCEPTION 'SAULI_RESET_SLOT_CONFIGURATION_INVALID';
    END IF;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_devices_before
    FROM (SELECT id, unit_id, device_code, status, is_primary, revoked_at
          FROM public.kiosk_devices) t;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_credentials_before
    FROM (SELECT id, device_id, secret_hash, expires_at, revoked_at
          FROM public.kiosk_device_credentials) t;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_sessions_before
    FROM (SELECT id, device_id, token_hash, expires_at, revoked_at
          FROM public.kiosk_browser_sessions) t;

    -- The door-gated transaction table references both found_items
    -- and retrieval_sessions. Clear it FIRST to avoid FK 23503.
    DELETE FROM public.sauli_hardware_transactions;

    DELETE FROM public.sauli_hardware_incidents;
    DELETE FROM public.sauli_hardware_presence_events;
    DELETE FROM public.sauli_hardware_presence;
    DELETE FROM public.sauli_hardware_commands;
    DELETE FROM public.sauli_hardware_snapshots;

    DELETE FROM public.email_notifications;
    DELETE FROM public.retrieval_events;
    DELETE FROM public.retrieval_logs;
    DELETE FROM public.retrieval_sessions;

    DELETE FROM public.match_candidates;
    DELETE FROM public.matching_jobs;
    DELETE FROM public.storage_slot_events;

    UPDATE public.storage_slots
    SET status = CASE WHEN status = 'out_of_service'
                      THEN 'out_of_service' ELSE 'available' END,
        current_found_item_id = NULL,
        reserved_at = NULL,
        occupied_at = NULL
    WHERE current_found_item_id IS NOT NULL
       OR status IN ('reserved', 'occupied')
       OR reserved_at IS NOT NULL
       OR occupied_at IS NOT NULL;

    DELETE FROM public.found_items;
    DELETE FROM public.missing_reports;
    DELETE FROM public.search_requests;

    UPDATE public.sauli_email_dispatch_clock
    SET next_allowed_at = now()
    WHERE id = 1;

    IF EXISTS (
        SELECT 1 FROM public.sauli_hardware_transactions
        UNION ALL SELECT 1 FROM public.found_items
        UNION ALL SELECT 1 FROM public.missing_reports
        UNION ALL SELECT 1 FROM public.search_requests
        UNION ALL SELECT 1 FROM public.match_candidates
        UNION ALL SELECT 1 FROM public.matching_jobs
        UNION ALL SELECT 1 FROM public.storage_slot_events
        UNION ALL SELECT 1 FROM public.retrieval_sessions
        UNION ALL SELECT 1 FROM public.retrieval_events
        UNION ALL SELECT 1 FROM public.retrieval_logs
        UNION ALL SELECT 1 FROM public.email_notifications
        UNION ALL SELECT 1 FROM public.sauli_hardware_commands
        UNION ALL SELECT 1 FROM public.sauli_hardware_snapshots
        UNION ALL SELECT 1 FROM public.sauli_hardware_presence
        UNION ALL SELECT 1 FROM public.sauli_hardware_presence_events
        UNION ALL SELECT 1 FROM public.sauli_hardware_incidents
    ) THEN
        RAISE EXCEPTION 'SAULI_PRODUCTION_RESET_VERIFICATION_FAILED';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.storage_slots
        WHERE current_found_item_id IS NOT NULL
           OR status IN ('reserved', 'occupied')
           OR reserved_at IS NOT NULL
           OR occupied_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'SAULI_RESET_SLOT_VERIFICATION_FAILED';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.sauli_units u
        WHERE (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active) <> 12
           OR (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active
                 AND s.size_class = 'pocket') <> 8
           OR (SELECT count(*) FROM public.storage_slots s
               WHERE s.unit_id = u.id AND s.is_active
                 AND s.size_class = 'medium') <> 4
    ) THEN
        RAISE EXCEPTION 'SAULI_RESET_SLOT_CONFIGURATION_INVALID_AFTER_RESET';
    END IF;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_devices_after
    FROM (SELECT id, unit_id, device_code, status, is_primary, revoked_at
          FROM public.kiosk_devices) t;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_credentials_after
    FROM (SELECT id, device_id, secret_hash, expires_at, revoked_at
          FROM public.kiosk_device_credentials) t;

    SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.id), '[]'::jsonb)
    INTO v_sessions_after
    FROM (SELECT id, device_id, token_hash, expires_at, revoked_at
          FROM public.kiosk_browser_sessions) t;

    IF v_devices_before IS DISTINCT FROM v_devices_after
       OR v_credentials_before IS DISTINCT FROM v_credentials_after
       OR v_sessions_before IS DISTINCT FROM v_sessions_after
    THEN
        RAISE EXCEPTION 'SAULI_PRODUCTION_RESET_KIOSK_REGISTRATION_CHANGED';
    END IF;

    RAISE NOTICE 'SAULI RESET SUCCESSFUL - KIOSK REGISTRATION PRESERVED';
END
$sauli_reset$;
