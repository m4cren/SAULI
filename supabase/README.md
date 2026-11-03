# Supabase for SAULI

Facebook sign-in continues to use Supabase Auth's managed user records. The [initial application migration](migrations/202610080001_sauli_initial_schema.sql) creates found-item and search tables. The original [storage-slot migration](migrations/202610110001_sauli_storage_slots.sql) seeded 15 positions and atomic placement; its applied history is unchanged. The [12-position migration](migrations/202610310001_sauli_twelve_active_storage_slots.sql) keeps those rows for historical references, retires P-09, P-10, and M-05, and permits new reservations only in P-01 through P-08 and M-01 through M-04. The [retrieval migration](migrations/202610110002_sauli_retrieval_sessions.sql) adds hashed one-time QR sessions, retrieval events and logs, and atomic issue, validation, replacement, and completion functions. The [live-status migration](migrations/202610110003_sauli_retrieval_live_status.sql) lets the claimant see the validated position and wrong-item state after kiosk scanning.

The [email-notification migration](migrations/202610120001_sauli_email_notifications.sql) adds missing reports, durable matching jobs, an EmailJS outbox, and a database dispatch clock. It updates the placement function to enqueue matching only when a slot becomes occupied, and updates match decisions so accepting marks the report matched while rejecting leaves it active. No EmailJS credentials are stored in Supabase.

The [retrieved-report migration](migrations/202610140001_sauli_resolve_retrieved_reports.sql) marks an accepted missing report `resolved` in the same transaction that completes its retrieval. It also repairs reports for already completed retrievals. After applying it, refresh the claimant's report page to see the updated status.

Migrations are not applied automatically. After linking the correct project and reviewing its migration history, run `supabase db push --dry-run` and then `supabase db push` from the repository root. If earlier migrations were applied manually outside CLI history, reconcile that history before pushing; alternatively apply only the unapplied SQL files in order through the Supabase SQL Editor. Never run `supabase db reset --linked` against this project. Setup and verification queries are in [services/README.md](../services/README.md).

Before applying the 12-position migration, inspect the three retired codes:

```sql
select ss.code, ss.status, ss.current_found_item_id, fi.placement_status
from public.storage_slots ss
left join public.found_items fi on fi.id = ss.current_found_item_id
where ss.code in ('P-09','P-10','M-05')
order by ss.code;
```

The migration aborts if one is `reserved`; complete or resolve that placement manually before retrying. An `occupied` row stays linked to its item and appears as a retired assignment in the admin dashboard. Do not remove its physical position until that item is retrieved or handled by an operator. After the migration, verify `select size_class, is_active, count(*) from public.storage_slots group by size_class, is_active order by size_class, is_active;` returns 8 active pocket and 4 active medium positions. No remote database was changed by editing this file.

For an intentional development data wipe, first empty the `sauli-item-images` bucket through the Supabase Storage dashboard or API, then run [reset_sauli_data.sql](reset_sauli_data.sql) manually in the SQL Editor. The script requires a `development` deployment guard and removes found items, searches, match candidates, missing reports, matching jobs, email notifications, slot events, retrieval sessions, retrieval events, and retrieval logs, and releases every position. It preserves slot rows, Auth users (including the admin account), the bucket, and the schema. It is **not** a migration and must never be applied with `db push`.

For a live **all-unit** operational reset, follow the [production reset procedure](../docs/multi-unit-rollout.md#intentional-all-unit-production-reset). Its separate [preflight](production_reset_preflight.sql) is read-only; [production_reset_sauli_data.sql](production_reset_sauli_data.sql) requires matching counts and an explicit confirmation phrase. Do not relabel a live project as development to run the development reset. Keep both reset scripts updated whenever the application schema or storage layout changes.
