-- Fix "app_state_key_check" errors when saving memory or Google Calendar.
-- Run this in the Supabase SQL Editor on the project used by Render.
-- It is safe to run more than once.
alter table public.app_state drop constraint if exists app_state_key_check;
alter table public.app_state add constraint app_state_key_check check (
  key in (
    'config.json', 'workflows.json', 'planner.json', 'telegram.json',
    'google_calendar.json', 'chats.json', 'memories.json'
  )
);
