import base64
import binascii
import hmac
import json
import os
import re
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

import app


USERNAME = os.environ.get("APP_USERNAME", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
STATE_FILES = frozenset({
    "config.json", "workflows.json", "planner.json", "telegram.json",
})
MISSING = object()

if not USERNAME or ":" in USERNAME:
    raise SystemExit("Set APP_USERNAME to a non-empty name without ':'.")
if len(PASSWORD) < 16:
    raise SystemExit("Set APP_PASSWORD to a password of at least 16 characters.")


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


def _configure_supabase_storage():
    storage = SupabaseJSONStore.from_environment()
    if storage is None:
        print("Supabase storage is not configured; using local JSON files.")
        return

    def load_json(path):
        value = storage.load(path.name)
        if value is not MISSING:
            return value
        # Import existing local state once, without overwriting an existing row.
        try:
            with path.open("r", encoding="utf-8") as state_file:
                value = json.load(state_file)
        except FileNotFoundError:
            return MISSING
        storage.save(path.name, value)
        print(f"Imported existing {path.name} into Supabase.")
        return value

    def save_json(path, data):
        storage.save(path.name, data)

    def load_config():
        saved = load_json(app.CONFIG_FILE)
        if saved is MISSING:
            return app.default_config()
        if not isinstance(saved, dict):
            raise RuntimeError("Supabase config.json must contain a JSON object.")
        workspace = saved.get("workspace", str(app.APP_DIR))
        if not isinstance(workspace, str) or not os.path.isdir(os.path.expanduser(workspace)):
            workspace = str(app.APP_DIR)
        try:
            return app.validate_config(
                saved.get("provider"), saved.get("model"), saved.get("api_key"),
                saved.get("terminal_enabled", False),
                saved.get("approval_mode", "manual"), workspace,
                saved.get("system_prompt", ""), saved.get("wake_phrase", "Nok"),
                saved.get("tts_auto_play", False),
            )
        except ValueError as error:
            raise RuntimeError(f"Supabase configuration is invalid: {error}") from error

    def load_workflows():
        saved = load_json(app.WORKFLOWS_FILE)
        if saved is MISSING:
            return []
        try:
            return app.validate_workflows(saved)
        except ValueError as error:
            raise RuntimeError(f"Supabase workflows are invalid: {error}") from error

    def load_planner():
        saved = load_json(app.PLANNER_FILE)
        if saved is MISSING:
            return app.default_planner()
        try:
            return app.validate_planner(saved)
        except ValueError as error:
            raise RuntimeError(f"Supabase planner data is invalid: {error}") from error

    def load_telegram():
        saved = load_json(app.TELEGRAM_FILE)
        if saved is MISSING:
            return {
                "token": None, "bot_username": None,
                "authorized_chats": [], "offset": 0,
            }
        if not isinstance(saved, dict):
            raise RuntimeError("Supabase telegram.json must contain a JSON object.")
        if saved.get("token") is None:
            if (
                saved.get("bot_username") is not None
                or saved.get("authorized_chats") != []
                or saved.get("offset", 0) != 0
            ):
                raise RuntimeError("Supabase Telegram configuration is invalid.")
            return {
                "token": None, "bot_username": None,
                "authorized_chats": [], "offset": 0,
            }
        if (
            not isinstance(saved.get("token"), str)
            or not app.TELEGRAM_TOKEN_PATTERN.fullmatch(saved["token"])
            or not isinstance(saved.get("bot_username"), str)
            or not isinstance(saved.get("authorized_chats"), list)
            or any(
                not isinstance(chat_id, str)
                or not re.fullmatch(r"-?[0-9]+", chat_id)
                for chat_id in saved["authorized_chats"]
            )
            or not isinstance(saved.get("offset", 0), int)
            or isinstance(saved.get("offset", 0), bool)
            or saved.get("offset", 0) < 0
        ):
            raise RuntimeError("Supabase Telegram configuration is invalid.")
        return {
            "token": saved["token"],
            "bot_username": saved["bot_username"],
            "authorized_chats": list(dict.fromkeys(saved["authorized_chats"])),
            "offset": saved.get("offset", 0),
        }

    # Replace import-time local state before serving requests.
    app.config = load_config()
    app.workflows[:] = load_workflows()
    app.planner.clear()
    app.planner.update(load_planner())
    app.telegram_config.clear()
    app.telegram_config.update(load_telegram())

    # All state mutations pass through these save functions.
    app.save_json_file = save_json
    app.save_config_file = lambda data: save_json(app.CONFIG_FILE, data)
    app.save_telegram_file = lambda data: save_json(app.TELEGRAM_FILE, data)


_configure_supabase_storage()


class AuthenticatedAppHandler(app.AppHandler):
    def _is_authenticated(self):
        authorization = self.headers.get("Authorization", "")
        scheme, separator, encoded = authorization.partition(" ")
        if not separator or scheme.lower() != "basic":
            return False
        try:
            credentials = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
        username, separator, password = credentials.partition(":")
        if not separator:
            return False
        return hmac.compare_digest(
            username.encode("utf-8"), USERNAME.encode("utf-8")
        ) and hmac.compare_digest(
            password.encode("utf-8"), PASSWORD.encode("utf-8")
        )

    def _require_authentication(self):
        if self._is_authenticated():
            return True
        body = b"Authentication required.\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="NOKK", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self):
        if self._require_authentication():
            super().do_GET()

    def do_POST(self):
        if self._require_authentication():
            super().do_POST()


if __name__ == "__main__":
    app.HOST = "0.0.0.0"
    app.PORT = int(os.environ.get("PORT", "10000"))
    app.start_telegram_polling()
    print(f"NOKK listening on {app.HOST}:{app.PORT}")
    ThreadingHTTPServer((app.HOST, app.PORT), AuthenticatedAppHandler).serve_forever()
