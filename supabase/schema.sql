-- Private JSON state for the Render deployment. Run this in the Supabase SQL Editor.
create table if not exists public.app_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

-- Keep the allowed state keys updated when applying this schema over an older table.
alter table public.app_state drop constraint if exists app_state_key_check;
alter table public.app_state add constraint app_state_key_check check (
  key in (
    'config.json', 'workflows.json', 'planner.json', 'telegram.json',
    'google_calendar.json', 'chats.json', 'memories.json', 'api.json'
  )
);

alter table public.app_state enable row level security;
-- Do not create public/anon policies. The Render server accesses the table using
-- SUPABASE_SERVICE_ROLE_KEY, kept only as a server-side secret.
