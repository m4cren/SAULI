# Supabase for the initial foundation

Facebook sign-in uses Supabase Auth's managed user records. This phase needs no SQL migration, custom users table, or profiles trigger. Configure the Facebook provider and redirect URLs in the Supabase dashboard; do not modify `auth.users` or run remote migrations for this setup.
