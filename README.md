# SAULI

**Secure Automated Unit for Lost Item** is a thesis prototype for reporting, storing, finding, and retrieving lost property. It connects a finder-facing kiosk with a claimant web app and an administrator dashboard. The goal is to make the path from finding an item to returning it traceable, while reducing manual description and search work.

## How the prototype works

1. **Report a found item.** At the kiosk, a finder takes two photos and records where the item was found. A local Qwen model analyzes the images and suggests an item description and storage size. The finder can review and correct the description.
2. **Store the item.** The API saves the item in Supabase and reserves an available pocket-size or medium-size position. In the current prototype, placement and door actions are simulated in the web interface.
3. **Search for a missing item.** A claimant signs in with Facebook, describes the item, and searches eligible stored items. The app uses Qwen to rank possible matches. The claimant can also post a missing-item report to watch for items placed later.
4. **Notify and review.** When a newly placed item qualifies as a possible match, the backend queues an email alert through EmailJS. The claimant reviews the candidate in SAULI and decides whether it is theirs. An alert is a possible match, not proof of ownership.
5. **Retrieve the item.** Confirming a match creates a one-time QR pass. The kiosk validates it and shows the assigned position. Web controls simulate correct removal, wrong-item removal, and return; the claimant page follows retrieval status. A completed retrieval is recorded and the position becomes available again.

The administrator dashboard shows container positions and retrieval records. Its account is separate from claimant Facebook sign-in.

## Thesis focus and prototype scope

SAULI explores a connected lost-and-found workflow: image-assisted item description, ranked matching, controlled storage assignment, claimant notifications, and a recorded retrieval trail. This repository contains the software prototype used to demonstrate that workflow. **Physical door locks, cameras, and weight sensors are not controlled by the current web simulation.** The kiosk's placement and retrieval buttons represent hardware events for testing the application flow.

## System overview

| Part | Role | Technology |
| --- | --- | --- |
| Kiosk, claimant app, admin dashboard | Capture, search, review, retrieval, monitoring | Next.js, React, TypeScript |
| API and background matching | Validation, image analysis, ranking, storage and retrieval rules, notifications | FastAPI, Python |
| Data and authentication | Application records, private item images, Facebook sign-in | Supabase Postgres, Storage, Auth |
| Local AI | Found-item analysis and match ranking | Ollama with Qwen |
| Match email | Sends the dashboard-managed possible-match template | EmailJS |

The browser talks to FastAPI for application actions. FastAPI holds server-only credentials and writes to Supabase. The EmailJS template design lives in EmailJS, not in this repository.

## Repository layout

| Path | Contents |
| --- | --- |
| [`frontend/`](frontend/) | Next.js kiosk, claimant, and admin interfaces |
| [`services/api/`](services/api/) | FastAPI routes, application services, and tests |
| [`supabase/migrations/`](supabase/migrations/) | Database schema and transaction functions |
| [`supabase/reset_sauli_data.sql`](supabase/reset_sauli_data.sql) | Manual development-data reset script; never run as a migration |
| [`firmware/`](firmware/) | Hardware-related workspace |
| [`docs/`](docs/) | Local development guidance |

## Run locally

The application needs Node.js, Python, a configured Supabase project, and Ollama with the model specified in [`services/.env.example`](services/.env.example). EmailJS and Facebook sign-in require their own dashboard configuration. Review and apply the Supabase migrations to the intended project before using the database-backed flows; migrations are not applied automatically.

From the repository root in Windows PowerShell:

```powershell
Copy-Item frontend\.env.example frontend\.env
Copy-Item services\.env.example services\.env

cd frontend
npm.cmd install
cd ..

py -3 -m venv services\.venv
.\services\.venv\Scripts\python.exe -m pip install -r services\requirements.txt
```

Fill the local `.env` files with your own project values. Keep Supabase service-role credentials, the retrieval-token pepper, and EmailJS private credentials on the backend. Do not commit real secrets. In separate terminals, start the API and frontend:

```powershell
cd services\api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend
npm.cmd run dev
```

Open `http://localhost:3000/auth/login` for the claimant app or `http://localhost:3000/kiosk` for the kiosk. The API health route is `http://localhost:8000/health`, and its interactive documentation is at `http://localhost:8000/docs`.

For Supabase migrations, Facebook OAuth, administrator setup, Ollama, EmailJS, and troubleshooting, follow the detailed guides: [local development](docs/local-development.md), [backend and API](services/README.md), and [database setup](supabase/README.md).

## Checks

```powershell
cd frontend
npm.cmd test
npm.cmd run lint
npx.cmd tsc --noEmit

cd ..\services\api
..\.venv\Scripts\python.exe -m pytest
```

The automated tests mock external providers. They do not send real EmailJS messages or operate physical hardware.
