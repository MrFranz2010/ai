# Deploy NOKK on Render with Supabase storage

This branch (`copilot/supabase-config-storage`) is the online-hosting variant.
It starts through `render_start.py`, keeps HTTP Basic Authentication, and stores
configuration, planner, workflows, Telegram settings and chat history in a
private Supabase table instead of relying on the Render filesystem.

## Deploy

1. Create a Supabase project, open the SQL Editor and run
   [`supabase/schema.sql`](supabase/schema.sql). The table has RLS enabled and no
   public policies: only the server-side service role key can read or write it.
2. In Render, choose **New → Blueprint**, connect this GitHub repository and
   select the `copilot/supabase-config-storage` branch, not `main`.
3. When prompted, set `APP_PASSWORD` (at least 16 characters),
   `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Keep the password and the
   service role key private; never commit them or expose them to the browser.
4. Wait for the deployment to finish, then open the `onrender.com` URL. The
   browser asks for the username (`nokk`) and the password you configured.
   Render provides HTTPS.

The startup wrapper binds to `0.0.0.0` and to the `PORT` supplied by Render. It
requires HTTP Basic Authentication for both the website and its API; do not
remove the password or expose the service without another authentication layer.

## Persistence

Configuration, workflows, planner data, Telegram settings and chat history are
saved in the `app_state` table, so they survive Render restarts, sleep cycles
and redeployments. If `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is missing,
`render_start.py` falls back to local JSON files and prints a warning; those
files are not durable on Render's free plan.

## Google search

Set `SERPER_API_KEY` as a secret environment variable to enable the
`google_search` tool. Without it the assistant still works and the tool reports
that search is not configured. Search queries are sent to Serper.

## Troubleshooting Google search

- The Render service must deploy the `copilot/supabase-config-storage` branch.
  `main` no longer contains `render_start.py` or `render.yaml`.
- `sync: false` in `render.yaml` only asks for a value when the Blueprint is
  applied. For an existing service add `SERPER_API_KEY` under **Environment**
  and redeploy.
- Startup logs show `Google search: configured` or
  `not configured (set SERPER_API_KEY)`.
- `GET /api/config` with Basic Authentication includes
  `search_configured`; `false` means the running instance does not see the
  variable.
- HTTP 401 or 402 from the search service means an invalid key or no credits.

## Run locally

`python app.py` still runs the app on `127.0.0.1:8000` with local JSON files and
does not use Supabase. Use `render_start.py` only for the hosted deployment.
