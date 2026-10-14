# SAULI frontend

Next.js app for SAULI. For environment variables, Supabase setup, and the FastAPI service, see [local development](../docs/local-development.md).

## Run locally

From this directory:

```powershell
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:3000/auth/login`.

For PC-webcam kiosk testing, open `/kiosk` on `http://localhost:3000` or an HTTPS deployment. Browsers normally block camera access on other insecure origins. Choose **Scan a found item**, allow camera access, capture front and back images, then review and analyze them. Image upload remains available if a camera is unavailable. The future Raspberry Pi camera can use this browser flow when Chromium exposes it as a video device.

## Project structure

- `app/**/page.tsx` and `app/**/layout.tsx`: route entry points and layouts.
- `app/**/_components/`: components used only by that route. The root page uses `app/_components/`.
- `app/components/`: components shared by multiple routes.
- `providers/`: shared React context providers.
- `hooks/`: shared React hooks.
- `libs/`: Supabase clients, API helpers, and types.

Keep a component beside its route until another route needs it. Move it to `app/components/` when it becomes shared.
