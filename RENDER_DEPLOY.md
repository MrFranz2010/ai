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

Configuration, workflows, planner data, Telegram settings, Google Calendar
credentials and tokens, chat history and personal memory are saved in the
`app_state` table, so they survive Render
restarts, sleep cycles and redeployments. If `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is missing,
`render_start.py` falls back to local JSON files and prints a warning; those
files are not durable on Render's free plan.

## app_state save error

If the logs show `new row for relation "app_state" violates check constraint
"app_state_key_check"`, the Supabase table was created with an older constraint.
Run the migration for the row named in the error in the Supabase SQL Editor for
the project used by Render:

- [`supabase/migrations/2026-11-04_chats_key.sql`](supabase/migrations/2026-11-04_chats_key.sql)
  for `chats.json`;
- [`supabase/migrations/2026-11-06_memory_and_calendar_keys.sql`](supabase/migrations/2026-11-06_memory_and_calendar_keys.sql)
  for `memories.json` or `google_calendar.json`.

You can also re-run [`supabase/schema.sql`](supabase/schema.sql), which is
idempotent and now allows every persisted state file. No Render redeploy is
needed: the change is in the database.

## Web search

No paid key is required. `web_search` uses DuckDuckGo's public HTML endpoint by
default and falls back to Yahoo, then Bing, when DuckDuckGo answers with an
anti-bot challenge; Bing results that do not match the query are discarded.
Optionally set `EXA_API_KEY` or `TAVILY_API_KEY` for their free tiers; the old
`SERPER_API_KEY` is used only as a last fallback when present.

## Google Calendar

Add the redirect URI shown in **Settings → Google Calendar** to your Google
OAuth client; on Render it is the service URL plus
`/oauth/google/callback`. The client ID, client secret and refresh token are
stored in the private `app_state` row as `google_calendar.json` and never
returned to the browser. The callback route is the only page that skips
Basic Authentication, because Google redirects the browser there without
credentials; the single-use OAuth state keeps it tied to an authenticated
session. You can also provide `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and
`GOOGLE_OAUTH_REDIRECT_URI` as service environment variables.

## Troubleshooting web search

- The Render service must deploy the `copilot/supabase-config-storage` branch.
  `main` no longer contains `render_start.py` or `render.yaml`.
- Without any search key the app still searches through DuckDuckGo.
- DuckDuckGo can temporarily block automated requests; configure Exa or Tavily
  if that happens.
- `GET /api/config` with Basic Authentication includes
  `search_configured` and `search_providers`.
- HTTP 401 or 402 from an optional search provider means an invalid key or no
  credits; the app then tries the next provider.

## Run locally

`python app.py` still runs the app on `127.0.0.1:8000` with local JSON files and
does not use Supabase. Use `render_start.py` only for the hosted deployment.

## Tests

`python -m unittest discover -s tests` runs the local suite. The Supabase
round-trip test is skipped by default because it writes to `app_state`. To run
it, use a disposable test project and set `SUPABASE_TEST_URL`,
`SUPABASE_TEST_SERVICE_ROLE_KEY` and `SUPABASE_TEST_ALLOW_WRITES=1`. The test
restores the previous `memories.json` row when it finishes.
