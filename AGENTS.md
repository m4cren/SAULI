# SAULI repository instructions

When changing SAULI's Supabase application tables, foreign keys, storage slots,
or image bucket, update `supabase/reset_sauli_data.sql` in the same change so it
still clears all application records and releases every position. Keep the reset
script outside `supabase/migrations`; it must run only when explicitly requested.
Preserve Supabase Auth accounts and delete Storage files through the Storage API
or dashboard, never by deleting rows from `storage.objects` with SQL.
