# Supabase for SAULI

Facebook sign-in continues to use Supabase Auth's managed user records. The found-item and search integration adds the separate, reviewable [initial application migration](migrations/202610080001_sauli_initial_schema.sql). It creates three public application tables, two service-role RPCs, and a private image bucket. It does not modify the Auth schema, its users, or its providers.

Review and run the migration manually in the Supabase SQL Editor when the backend service-role key is ready. It has not been applied automatically. Setup and verification queries are in [services/README.md](../services/README.md).
