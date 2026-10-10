# SAULI initial backend integration

This phase connects the kiosk's two-image found-item flow and the claimant's existing search form to FastAPI. Found items are analyzed with a local Ollama model and saved to a private Supabase bucket and database only after review and confirmation. Search queries are analyzed, filtered by availability and time in both SQL and Python, ranked, and audited. Container assignment, doors, sensors, station retrieval and QR authorization are not implemented. The QR screen is a static, non-scannable prototype.

## Structure

- `api/app/main.py`: application factory, CORS and safe error handlers.
- `api/app/routes`: health, found-item and search endpoints; existing auth routes remain.
- `api/app/integrations/ollama.py`: local structured model gateway.
- `api/app/services`: image validation, analysis, confirmation and matching.
- `api/app/repositories/supabase_found_items.py`: server-only database and private Storage calls.
- `../supabase/migrations/202610080001_sauli_initial_schema.sql`: reviewable initial schema.

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

Review the migration in `supabase/migrations/202610080001_sauli_initial_schema.sql`, then open the Supabase project **SQL Editor**, paste the complete migration, and execute it. This repository does not apply it automatically. It creates `public.found_items`, `public.search_requests`, `public.match_candidates`, an eligible-item RPC, an atomic search-audit RPC, RLS and restricted grants, plus the private `sauli-item-images` bucket. The bucket accepts JPEG, PNG and WebP up to 10 MiB. The original validated image bytes are stored without permanent privacy redaction; use appropriate data retention and access controls before production use.

Verification SQL after applying:

```sql
select table_name from information_schema.tables where table_schema = 'public'
  and table_name in ('found_items','search_requests','match_candidates') order by table_name;
select id, name, public, file_size_limit, allowed_mime_types
  from storage.buckets where id = 'sauli-item-images';
select routine_name from information_schema.routines where routine_schema = 'public'
  and routine_name = 'get_eligible_found_items';
select schemaname, tablename, rowsecurity from pg_tables where schemaname = 'public'
  and tablename in ('found_items','search_requests','match_candidates');
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

1. `POST /api/found-items/analyze` with multipart `front_image`, `back_image`, `found_location` and optional `notes`. Images are checked by MIME and decoded bytes, sent in front/back order, and held only in memory during analysis.
2. `POST /api/found-items/reconcile-review` with complete `analysis`, location, notes and `correction_notes` JSON. It returns a full revised analysis and does not save anything.
3. `POST /api/found-items/confirm-and-store` with the original multipart images, `found_location`, optional `notes`, `analysis_json`, and UUID `X-Idempotency-Key`. A retry reuses that key. Images are uploaded to `found-items/{uuid}/front.ext` and `back.ext`; the API removes uploaded objects if a later step fails.
4. `POST /api/matches/search` with a JSON description and optional filters, plus a UUID `X-Idempotency-Key`. It returns at most five ranked candidates with a **Match rank score**, which is not an ownership probability.
5. `GET /api/found-items/{item_id}` returns allowlisted details and a short-lived signed image URL where appropriate. If a URL expires or cannot be signed, the frontend shows a placeholder. The browser never constructs a public bucket URL.

Example search:

```powershell
$key = [guid]::NewGuid().ToString()
$body = @{ description = 'Blue metal bottle lost at the library'; last_seen_location = 'Library' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/matches/search -Method Post -Headers @{ 'X-Idempotency-Key' = $key } -ContentType 'application/json' -Body $body
```

## Tests and limits

```powershell
cd services/api
..\.venv\Scripts\python.exe -m pytest -q
cd ../../frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

Backend tests use fake model and repository dependencies; they do not require live services. A complete live smoke test additionally requires a running local Ollama model, the reviewed migration applied remotely, and `SUPABASE_SERVICE_ROLE_KEY` set on the backend. Confirm two private objects and one `found_items` row after a successful save, then check `search_requests` and `match_candidates` after a search. The application does not generate retrieval tokens or operate hardware in this phase.
