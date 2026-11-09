import os
from datetime import datetime, timezone


STATE_FILES = frozenset({
    "config.json",
    "workflows.json",
    "planner.json",
    "telegram.json",
    "google_calendar.json",
    "chats.json",
    "memories.json",
    "api.json",
})
MISSING = object()


class SupabaseJSONStore:
    """Store the app's JSON state files in a private Supabase table."""

    def __init__(self, client):
        self.client = client

    @classmethod
    def from_environment(cls):
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if bool(url) != bool(key):
            raise RuntimeError(
                "Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or neither."
            )
        if not url:
            return None
        try:
            from supabase import create_client
        except ImportError as error:
            raise RuntimeError(
                "Supabase storage is enabled but the supabase package is unavailable."
            ) from error
        return cls(create_client(url, key))

    @staticmethod
    def _validate_name(name):
        if name not in STATE_FILES:
            raise ValueError(f"Unsupported persistent state file: {name}")

    def load(self, name):
        self._validate_name(name)
        response = (
            self.client.table("app_state")
            .select("value")
            .eq("key", name)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return MISSING
        return rows[0]["value"]

    def save(self, name, value):
        self._validate_name(name)
        self.client.table("app_state").upsert({
            "key": name,
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="key").execute()
