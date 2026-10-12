# SAULI initial backend integration

The kiosk analyzes two item photos with Ollama. After review and an explicit storage-size choice, FastAPI saves the item and atomically reserves a Supabase position. A web-only placement action marks that position occupied. Claimant search considers only placed items in occupied positions. Claimant confirmation issues a QR; kiosk validation reveals the database position and web simulation records retrieval. The admin container view polls the same slot table. Physical doors and sensors remain outside this phase.

## Structure

- `api/app/main.py`: application factory, CORS and safe error handlers.
- `api/app/routes`: health, found-item and search endpoints; existing auth routes remain.
- `api/app/integrations/ollama.py`: local structured model gateway.
- `api/app/services`: image validation, analysis, confirmation and matching.
- `api/app/repositories/supabase_found_items.py`: server-only database and private Storage calls.
- `../supabase/migrations/202610080001_sauli_initial_schema.sql`: initial schema.
- `../supabase/migrations/202610110001_sauli_storage_slots.sql`: additive slot and claim migration.

## Local setup (Windows PowerShell)

```powershell
cd services
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull qwen3.5:9b-q8_0
ollama serve
```

In `services/.env`, set `SUPABASE_URL` and the server-only `SUPABASE_SERVICE_ROLE_KEY`, and retain `OLLAMA_MODEL=qwen3.5:9b-q8_0`. `SUPABASE_PUBLISHABLE_KEY` remains for the existing authentication route. The other settings are `OLLAMA_HOST`, `OLLAMA_TIMEOUT_SECONDS`, `SUPABASE_STORAGE_BUCKET`, `SUPABASE_SIGNED_URL_TTL_SECONDS`, `FRONTEND_ORIGIN`, `MAX_IMAGE_BYTES` and `MAX_IMAGE_PIXELS`. Two-image analysis uses a minimum Ollama timeout of 180 seconds; older `.env` values such as 5 seconds are raised to that minimum. Keep `.env` private. Never set a `NEXT_PUBLIC_*` service role variable.

Review both migrations in `supabase/migrations`. The storage migration is additive and seeds exactly 10 pocket and 5 medium positions. It has not been applied automatically. With the Supabase CLI installed and the intended project linked, run from the repository root:

```powershell
supabase db push --dry-run
supabase db push
```

If the initial migration was applied manually outside CLI history, reconcile migration history before pushing or paste only `202610110001_sauli_storage_slots.sql` into the Supabase SQL Editor. Do not reset a remote database. Keep the service-role key only in `services/.env`. The original validated image bytes remain in the private bucket.

Verification SQL after applying:

```sql
select table_name from information_schema.tables where table_schema = 'public'
  and table_name in ('found_items','search_requests','match_candidates') order by table_name;
select id, name, public, file_size_limit, allowed_mime_types
  from storage.buckets where id = 'sauli-item-images';
select routine_name from information_schema.routines where routine_schema = 'public'
  and routine_name = 'get_eligible_found_items';
select schemaname, tablename, rowsecurity from pg_tables where schemaname = 'public'
  and tablename in ('found_items','search_requests','match_candidates','storage_slots','storage_slot_events',
    'retrieval_sessions','retrieval_events','retrieval_logs');
select size_class,status,count(*) from public.storage_slots group by size_class,status order by size_class,status;
select code,size_class,status from public.storage_slots order by case size_class when 'pocket' then 0 else 1 end,ordinal;
```

Start FastAPI from `services/api`:

```powershell
cd api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in the frontend environment. `GET /health` reports `degraded` until Ollama, the configured model, database and bucket are ready. The API is available at `http://localhost:8000/docs`.

## API flow

1. `POST /api/found-items/analyze` with multipart `front_image`, `back_image`, `found_location` and optional `notes`. Images are checked by MIME and decoded bytes, sent in front/back order, and held only in memory during analysis. Qwen also returns a required `storage_size` recommendation (`pocket` or `medium`) based on the whole item's likely physical size; the kiosk preselects it and lets the finder correct an uncertain fit before confirmation.
2. `POST /api/found-items/reconcile-review` with complete `analysis`, location, notes and `correction_notes` JSON. It returns a full revised analysis and does not save anything.
3. `GET /api/storage-slots/availability?size_class=pocket` gives advisory size-specific counts.
4. `POST /api/found-items/confirm-and-store` accepts the original images, location, notes, analysis JSON, reviewed `storage_size` (`pocket` or `medium`) and UUID idempotency key. It reserves the first available compatible slot in a database transaction. A full section returns `409 NO_AVAILABLE_STORAGE_SLOT` with `requested_size`.
5. `POST /api/found-items/{item_id}/simulate-placement` with `slot_code` changes the reserved slot to occupied. Repeating the same operation is safe. This endpoint is a web simulation, not a hardware command.
6. `POST /api/matches/search` keeps Qwen ranking and returns at most five placed, occupied candidates with candidate IDs. Authenticated searches record the claimant owner.
7. `POST /api/matches/{match_candidate_id}/confirm` and `/reject` require a Supabase user token. Confirmation keeps the slot occupied; the claimant response hides its position.
8. `GET /api/storage-slots` returns all slots and safe item summaries only to the dedicated account whose Supabase ID matches server-only `SAULI_ADMIN_USER_ID` and whose trusted `app_metadata.sauli_role` is `admin`. The admin page polls every four seconds. Other signed-in accounts receive `403 Forbidden`.
9. `GET /api/found-items/{item_id}` returns allowlisted details and a short-lived signed image URL where appropriate.

### QR retrieval on a PC

Configure `RETRIEVAL_QR_TTL_MINUTES=180` and a long random `RETRIEVAL_TOKEN_PEPPER` in `services/.env`. Generate the pepper with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set `ENVIRONMENT=production` in production; startup then rejects a missing, short, or placeholder pepper. Development without a pepper uses a temporary process secret, so its existing QR codes stop working after an API restart.

After confirming a match, the claimant app calls `POST /api/retrieval-sessions` with the accepted `match_candidate_id`. Only the current authenticated claimant can issue, inspect, or replace their session. `GET /api/retrieval-sessions/{id}` returns status without the token; `POST /api/retrieval-sessions/{id}/replace` invalidates a lost or expired QR. The raw QR token is returned only at issue or replacement and kept in same-tab `sessionStorage`, never in a URL or database row.

Apply `supabase/migrations/202610110003_sauli_retrieval_live_status.sql` after the retrieval migration. The claimant status route then reveals the assigned position only after kiosk validation, along with wrong-item, return, and completion state. The open claimant page checks this status every second and refreshes immediately when the phone returns to the foreground. `GET /api/retrieval-sessions/history` returns only that claimant's completed retrieval logs.

The kiosk accepts a PC webcam scan or a downloaded PNG/JPEG/WebP QR image. `POST /api/retrieval-sessions/validate` consumes the QR once and returns the database position and a session-scoped kiosk action capability. The kiosk sends that capability in `X-Retrieval-Action` to `simulate-wrong-item`, `simulate-item-returned`, and `simulate-completion`. These endpoints call atomic Supabase functions. Correct removal marks the item retrieved, releases its exact slot, adds a retrieval log, and updates the admin view on its next poll. No physical door or sensor code is involved.

To test on one PC: store and place a found item, sign in as a claimant, search and confirm it, download the QR, open `/kiosk`, choose **Station retrieval**, upload the PNG or use a webcam, simulate a wrong lift and return, then simulate the correct lift. Verify that the slot is available in `/admin` and the completed event is in `/admin/retrieval-logs`. Scanning the same QR again returns `RETRIEVAL_QR_ALREADY_USED`.

### Dedicated administrator account

Use `/auth/admin` to sign in with the administrator username and password. The password is held by Supabase Auth and is not saved in either `.env` file or the repository. The Auth email is an internal account identifier; the login form accepts the username. The admin route and the API both pin access to the same Supabase user ID through server-only `SAULI_ADMIN_USER_ID` in `frontend/.env` and `services/.env`. After changing either environment file, restart that server.

To re-provision the account or rotate its password, run `python -m scripts.provision_admin` from `services/api` with the virtual environment active. It prompts for the password without terminal echo, creates or updates the dedicated account, revokes older SAULI admin grants, verifies sign-in, and writes the admin ID to both local environment files. Keep Supabase's built-in JWT role as `authenticated` because it controls database access. Do not put the service-role key in the browser.

Example search:

```powershell
$key = [guid]::NewGuid().ToString()
$body = @{ description = 'Blue metal bottle lost at the library'; last_seen_location = 'Library' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/matches/search -Method Post -Headers @{ 'X-Idempotency-Key' = $key } -ContentType 'application/json' -Body $body
```

## Tests and limits

### Missing-item reports and email alerts

Apply `supabase/migrations/202610120001_sauli_email_notifications.sql` after the three `20261011` migrations. It creates `missing_reports`, `matching_jobs`, `email_notifications`, and a dispatch clock. It also updates the placement and match-decision transactions. The migration has not been applied by this repository change. Do not run `supabase/reset_sauli_data.sql` as a migration; that separate script is for an intentional manual data wipe.

The claimant posts `POST /api/missing-reports` with the authenticated search request ID, a validated notification email, an email preference, and `X-Idempotency-Key`. The database copies the saved search summary and creates a durable matching job. `GET /api/missing-reports/{id}` is owner-only and returns the best unreviewed qualified result. The email links to `/missing/reports/{id}`; unauthenticated visitors sign in and return to that route. The existing match-decision and QR endpoints handle confirmation and retrieval. Rejection keeps the report active.

Placement commits its occupied slot and enqueues a matching job in one transaction. The API worker processes pending and retryable jobs after startup, compares eligible occupied items with active reports using the existing Qwen model and score formula, stores qualified candidates, and queues one alert for the highest-ranked new candidate per report and matching run. Candidate and job uniqueness prevent duplicate notifications after retries or restarts. The threshold is `MATCH_NOTIFICATION_MIN_SCORE=65` by default and uses the existing 0–100 rank score. The email outbox is claimed atomically and globally limited by the database clock to one EmailJS request per second. If the API is offline, queued work resumes when it starts again.

Use the existing **SAULI Possible Match** template in the EmailJS dashboard. Its complete HTML design stays in EmailJS; FastAPI sends only its six variables. In `services/.env`, set `EMAILJS_ENABLED=true`, `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID` (the ID of **SAULI Possible Match**), and `EMAILJS_PUBLIC_KEY`. `EMAILJS_PRIVATE_KEY` is optional and omitted from the REST request when empty; keep it in the backend if used. These existing settings serve the same purpose as `EMAILJS_MATCH_TEMPLATE_ID` and `FRONTEND_APP_URL`, so no duplicate environment variables are needed. `EMAILJS_API_URL` defaults to the [EmailJS REST send endpoint](https://www.emailjs.com/docs/rest-api/send/). Set `FRONTEND_BASE_URL` to the public frontend origin; localhost links are rejected for delivery in staging and production. Optional controls are `EMAILJS_TIMEOUT_SECONDS`, `EMAILJS_MAX_RETRIES`, and `MATCH_NOTIFICATION_MIN_SCORE`. With EmailJS disabled or required keys missing, report creation, placement, and matching still work; the outbox records `skipped_disabled` or `skipped_unconfigured` and no request is sent. After completing configuration and restarting the API, an authenticated SAULI admin can call `POST /api/missing-reports/admin/retry-unconfigured-email` to requeue configuration-skipped alerts. Disabled alerts remain disabled by the claimant's choice.

The saved EmailJS template uses these exact variables:

| Variable | Value |
| --- | --- |
| `to_email` | Report notification address; use as the template recipient |
| `recipient_name` | Claimant display name |
| `item_summary` | Generic possible match name; omits distinctive markings |
| `found_location` | General found location |
| `found_date` | Found date and time in Asia/Manila, such as `October 12, 2026 at 5:00 PM` |
| `match_url` | Authenticated report review URL, without a token |

The saved dashboard template supplies the subject and HTML; neither is stored in this repository. Verify its recipient field uses `{{to_email}}` and its other placeholders use the names above. Do not add storage position, QR code, private image path, serial number, or sensitive markings to the template. The backend treats HTTP 200 as sent, retries 429 and connection failures within the configured attempt limit, and holds timeouts or ambiguous server failures as `delivery_unknown` for manual investigation to avoid duplicate mail. The database unique constraint prevents a second notification for the same report and match candidate.

To verify safely without sending real mail, leave `EMAILJS_ENABLED=false`: post a report, place an eligible item, and check `missing_reports`, `matching_jobs`, `match_candidates`, and `email_notifications` in Supabase. A `skipped_disabled` email row is expected. The automated tests use HTTP mocks and never contact EmailJS.

For a manual delivery check, first configure the connected Gmail service, the saved template ID, and a real `FRONTEND_BASE_URL`. Then enable EmailJS, restart FastAPI, post a report, and simulate successful placement of a qualified item. Confirm that exactly one row for that report and candidate moves to `sent`, the email points to `/missing/reports/{id}`, and the claimant can sign in to review it. Repeating the placement or matching job must not send another email. A provider error leaves the match intact and records a safe failure state.

```powershell
cd services/api
..\.venv\Scripts\python.exe -m pytest -q
cd ../../frontend
npm.cmd test
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
```

Backend tests use fake model and repository dependencies, plus static migration checks. They do not execute PostgreSQL transactions. A live concurrency smoke test requires the migrations to be applied, configured Supabase credentials and a running Ollama model. Check retrieval transitions in `retrieval_sessions`, `retrieval_events`, `retrieval_logs`, `found_items`, and `storage_slots`. All kiosk removal actions in this phase are web simulations.
