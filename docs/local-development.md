# SAULI local development

This foundation uses Next.js 16 in `frontend/`, FastAPI in `services/api/`, Supabase Auth for Facebook sign-in, and an optional Ollama server. The signed-in landing page is `/`; `/auth/login` is public. Administrator sign-in uses `/auth/admin`; see [admin account setup](../services/README.md#dedicated-administrator-account).

## Environment

Keep real values in the existing ignored `frontend/.env` and `services/.env` files. If a file is absent, copy its `.env.example` first. Do not put Meta's app secret, a Supabase secret/service-role key, or an Ollama credential in a `NEXT_PUBLIC_` variable.

`frontend/.env`:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Project URL from Supabase Connect, such as `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Project publishable key from Supabase Connect |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` for local FastAPI; optional because this is the default |

An existing `NEXT_PUBLIC_SUPABASE_ANON_KEY` is accepted as a legacy fallback when no publishable key is set. Use only a public key in browser code.

`services/.env`:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | Same project URL, using HTTPS |
| `SUPABASE_PUBLISHABLE_KEY` | Same public project key; `SUPABASE_ANON_KEY` is accepted as a legacy fallback |
| `OLLAMA_BASE_URL` | `http://localhost:11434` by default, or a private remote URL such as `http://100.x.y.z:11434` |
| `OLLAMA_TIMEOUT_SECONDS` | Positive number of seconds, default `5` |
| `CORS_ORIGINS` | Comma-separated exact web origins, default `http://localhost:3000`; add production origins explicitly |

The backend starts without the Supabase variables so `/health` remains available. Protected requests return a service error until they are configured. Restart Next.js after changing `NEXT_PUBLIC_` variables.

## Install and start on Windows PowerShell

From the `sauli` directory, install dependencies if needed:

```powershell
cd frontend
npm.cmd install
cd ..
py -3 -m venv services\.venv  # only if the virtual environment does not exist
.\services\.venv\Scripts\python.exe -m pip install -r services\requirements-dev.txt
```

Start FastAPI in one terminal:

```powershell
cd services\api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Start Next.js in another terminal from `sauli`:

```powershell
cd frontend
npm.cmd run dev
```

Open `http://localhost:3000/auth/login`. `http://localhost:8000/health` should return `{"status":"ok"}` even if Ollama is offline. API documentation is at `http://localhost:8000/docs`.

## Configure Facebook OAuth

1. In Supabase, open **Authentication → Providers → Facebook**. Enable it and enter the Meta app ID and app secret there. Keep the Meta app secret in the Supabase dashboard only.
2. In Meta's **Facebook Login → Settings**, register this **Supabase Auth callback** as a Valid OAuth Redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`. Copy the exact callback shown by Supabase for your project.
3. In Supabase **Authentication → URL Configuration**, set the Site URL to `http://localhost:3000` and add this **application callback** to the redirect allowlist: `http://localhost:3000/auth/callback`.
4. For production, add the deployed application's callback URL to Supabase's redirect allowlist and set an appropriate production Site URL. Keep Meta's redirect URI pointed at the Supabase Auth callback for the corresponding Supabase project.
5. In Meta's Authentication and Account Creation use case, check that `public_profile` and `email` are **Ready for testing**. Facebook may still omit an email for a particular user, so the app treats it as optional.
6. While the Meta app is in Development mode, use an administrator, developer, or tester account assigned to the app. Testers must accept the invitation. Public sign-in requires moving the app to Live mode and satisfying Meta's current review and permission requirements for the permissions you request.

The callback in **Meta** is the Supabase URL ending in `/auth/v1/callback`. The callback in **Supabase's redirect allowlist** is the Next.js URL ending in `/auth/callback`. Swapping them causes sign-in failures. See [Supabase's Facebook guide](https://supabase.com/docs/guides/auth/social-login/auth-facebook) and [redirect URL guide](https://supabase.com/docs/guides/auth/redirect-urls) for current dashboard steps and Meta development-mode guidance.

## Ollama and protected API checks

Install and start Ollama separately using the [official quickstart](https://docs.ollama.com/quickstart). The app does not launch Ollama or download models. Check its model-list API without loading a model:

```powershell
curl.exe http://localhost:11434/api/tags
```

For a private remote Ollama server, set `OLLAMA_BASE_URL` in `services/.env` to the server's reachable private address, such as its Tailscale IP and port. Ensure the server listens on that interface and that the API host can reach it. Keep it private and restart FastAPI after changing the variable. The status route uses Ollama's [model-list API](https://docs.ollama.com/api/tags); an empty `models` array is a successful connection when no models are installed.

After a real Facebook sign-in, use the **Supabase application access token** from `supabase.auth.getSession().data.session.access_token` in the signed-in browser app. Do not use `provider_token`, which belongs to Facebook. Place the access token in a local shell variable and call:

```powershell
$env:SAULI_ACCESS_TOKEN = '<Supabase application access token>'
curl.exe -H "Authorization: Bearer $env:SAULI_ACCESS_TOKEN" http://localhost:8000/api/v1/me
curl.exe -H "Authorization: Bearer $env:SAULI_ACCESS_TOKEN" http://localhost:8000/api/v1/ollama/status
Remove-Item Env:SAULI_ACCESS_TOKEN
```

The frontend's typed `getMe()` and `getOllamaStatus()` helpers in `frontend/libs/api/client.ts` add this access token automatically for browser calls. The API verifies each bearer token with Supabase Auth over HTTPS before returning protected data. `/health` needs no token. The Ollama status route returns `503` if Ollama cannot be reached and `504` on timeout.

## Troubleshooting

- **Missing URL/key:** Fill both environment files with values from the same Supabase project, then restart both servers. Never put a service-role key in the frontend.
- **Redirect mismatch:** Check the exact Supabase callback in Meta and the exact Next.js callback in Supabase's allowlist, including scheme, host, port, and path.
- **App not set up / permission error:** Check Meta app mode, assigned test roles, accepted invitations, and `public_profile`/`email` readiness.
- **Sign-in returns to login:** Check browser cookies, project URL/key consistency, and the callback exchange. The callback shows a friendly message if consent was denied or exchange failed.
- **API `401`:** Use a current Supabase application access token. A Facebook provider token is not accepted.
- **Admin API `403`:** Sign-in worked, but this is not the dedicated admin account. Sign in at `/auth/admin` with the admin credentials. If that account still receives 403, check that both servers have the same `SAULI_ADMIN_USER_ID` and restart them. See [admin account setup](../services/README.md#dedicated-administrator-account).
- **API `503`:** Check backend Supabase configuration or Auth availability. For Ollama status, check `OLLAMA_BASE_URL` and connectivity from the API host.
- **API `504`:** Increase `OLLAMA_TIMEOUT_SECONDS` or fix a slow/unreachable Ollama host.
- **CORS error:** Add the exact frontend origin to `CORS_ORIGINS` and restart FastAPI.

## Local checks

From `frontend/`, run `npm.cmd run lint`, `npx.cmd tsc --noEmit`, `npm.cmd run test`, and `npm.cmd run build`. From `services/api/`, run `..\.venv\Scripts\python.exe -m pytest`. These checks mock external services; live Facebook OAuth and live Ollama connectivity still require your dashboard credentials and running services.
