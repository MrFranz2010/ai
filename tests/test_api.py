import json
import tempfile
import time
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import api_access
import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        base = Path(cls.directory.name)
        app.CONFIG_FILE = base / "config.json"
        app.WORKFLOWS_FILE = base / "workflows.json"
        app.PLANNER_FILE = base / "planner.json"
        app.TELEGRAM_FILE = base / "telegram.json"
        app.GOOGLE_CALENDAR_FILE = base / "google_calendar.json"
        app.API_FILE = base / "api.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def setUp(self):
        for path in (
            app.CONFIG_FILE,
            app.WORKFLOWS_FILE,
            app.PLANNER_FILE,
            app.TELEGRAM_FILE,
            app.GOOGLE_CALENDAR_FILE,
            app.API_FILE,
        ):
            path.unlink(missing_ok=True)
        with app.config_lock:
            app.config.update(app.default_config())
            app.workflows.clear()
            app.planner.clear()
            app.planner.update(app.default_planner())
        with app.api_lock:
            app.api_config.clear()
            app.api_config.update(app.default_api_config())
        app.api_rate_limiter.reset()
        with app.chat_jobs_lock:
            app.chat_jobs.clear()

    def send(self, path, payload=None, key=None, method="POST", headers=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if key is not None:
            request_headers["X-API-Key"] = key
        request_headers.update(headers or {})
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request) as response:
                raw = response.read()
                return (
                    response.status,
                    json.loads(raw) if raw else None,
                    dict(response.headers),
                )
        except HTTPError as error:
            raw = error.read()
            return (
                error.code,
                json.loads(raw) if raw else None,
                dict(error.headers),
            )

    def enable(self):
        status, _, _ = self.send(
            "/api/api-keys", {"action": "set_enabled", "enabled": True}
        )
        self.assertEqual(status, 200)

    def create_key(self, name="Test"):
        self.enable()
        status, data, _ = self.send(
            "/api/api-keys", {"action": "create", "name": name}
        )
        self.assertEqual(status, 200)
        return data["key"]

    # -- gestione chiavi -------------------------------------------------

    def test_creating_a_key_returns_the_secret_only_once(self):
        key = self.create_key("Webhook")
        self.assertTrue(key.startswith("nokk_"))
        status, listing, _ = self.send("/api/api-keys", method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(listing["enabled"])
        self.assertEqual(len(listing["keys"]), 1)
        self.assertEqual(listing["keys"][0]["name"], "Webhook")
        self.assertEqual(listing["keys"][0]["hint"], key[-4:])
        self.assertNotIn("key", listing["keys"][0])

        stored = json.loads(app.API_FILE.read_text(encoding="utf-8"))
        self.assertNotIn(key, json.dumps(stored))
        self.assertEqual(stored["keys"][0]["hash"], api_access.hash_api_key(key))

    def test_revoking_a_key_invalidates_it(self):
        key = self.create_key()
        _, listing, _ = self.send("/api/api-keys", method="GET")
        key_id = listing["keys"][0]["id"]
        status, _, _ = self.send(
            "/api/api-keys", {"action": "revoke", "id": key_id}
        )
        self.assertEqual(status, 200)
        status, data, _ = self.send("/api/v1/planner", method="GET", key=key)
        self.assertEqual(status, 401)
        self.assertIn("Chiave API", data["error"])

    def test_a_revoked_key_cannot_be_created_twice(self):
        self.create_key()
        status, _, _ = self.send(
            "/api/api-keys", {"action": "revoke", "id": "0" * 16}
        )
        self.assertEqual(status, 404)

    def test_more_than_the_key_limit_is_refused(self):
        self.enable()
        for index in range(api_access.MAX_API_KEYS):
            status, _, _ = self.send(
                "/api/api-keys", {"action": "create", "name": f"Key {index}"}
            )
            self.assertEqual(status, 200)
        status, data, _ = self.send(
            "/api/api-keys", {"action": "create", "name": "Extra"}
        )
        self.assertEqual(status, 400)
        self.assertIn("massimo", data["error"])

    # -- accesso all'API -------------------------------------------------

    def test_the_api_refuses_requests_while_it_is_disabled(self):
        status, data, _ = self.send(
            "/api/v1/planner", method="GET", key="nokk_" + "a" * 32
        )
        self.assertEqual(status, 403)
        self.assertIn("disattivata", data["error"])

    def test_a_missing_or_wrong_key_is_rejected(self):
        key = self.create_key()
        status, _, _ = self.send("/api/v1/planner", method="GET")
        self.assertEqual(status, 401)
        status, _, _ = self.send(
            "/api/v1/planner", method="GET", key="nokk_" + "b" * 32
        )
        self.assertEqual(status, 401)
        status, _, _ = self.send("/api/v1/planner", method="GET", key=key)
        self.assertEqual(status, 200)

    def test_a_bearer_token_is_accepted_too(self):
        key = self.create_key()
        status, _, _ = self.send(
            "/api/v1/planner",
            method="GET",
            headers={"Authorization": f"Bearer {key}"},
        )
        self.assertEqual(status, 200)

    def test_health_needs_no_key_and_allows_the_extension_origin(self):
        status, data, headers = self.send("/api/v1/health", method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_options_answers_the_preflight_without_a_key(self):
        status, _, headers = self.send("/api/v1/chat", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertIn("X-API-Key", headers.get("Access-Control-Allow-Headers"))

    def test_the_rate_limit_stops_a_flood(self):
        key = self.create_key()
        original = app.api_rate_limiter
        app.api_rate_limiter = api_access.RateLimiter(limit=2, window=60)
        try:
            for _ in range(2):
                status, _, _ = self.send("/api/v1/planner", method="GET", key=key)
                self.assertEqual(status, 200)
            status, data, _ = self.send("/api/v1/planner", method="GET", key=key)
            self.assertEqual(status, 429)
            self.assertIn("Troppe richieste", data["error"])
        finally:
            app.api_rate_limiter = original

    # -- uso dell'API ----------------------------------------------------

    def test_a_reminder_can_be_created_through_the_api(self):
        key = self.create_key()
        status, data, _ = self.send(
            "/api/v1/reminders",
            {"text": "Riunione con cliente domani alle 10"},
            key=key,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["item"]["title"], "Riunione con cliente")
        self.assertEqual(data["item"]["starts_at"], _tomorrow_at(10))

        status, planner, _ = self.send("/api/v1/planner", method="GET", key=key)
        self.assertEqual(status, 200)
        self.assertEqual(len(planner["tasks"]), 1)

    def test_chat_needs_a_configured_provider_even_with_a_valid_key(self):
        key = self.create_key()
        status, data, _ = self.send(
            "/api/v1/chat",
            {"messages": [{"role": "user", "content": "Ciao"}]},
            key=key,
        )
        self.assertEqual(status, 409)
        self.assertIn("provider", data["error"])

    def test_an_unknown_mode_is_refused(self):
        key = self.create_key()
        status, data, _ = self.send(
            "/api/v1/chat",
            {"messages": [{"role": "user", "content": "Ciao"}], "mode": "poeta"},
            key=key,
        )
        self.assertEqual(status, 400)
        self.assertIn("Modalità", data["error"])

    def test_a_gateway_without_system_role_still_gets_the_instructions(self):
        received = []

        class Gateway(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received.append(json.loads(self.rfile.read(length)))
                if len(received) == 1:
                    payload = {
                        "error": {
                            "message": (
                                "role 'system' is not supported by this model"
                            ),
                        },
                    }
                    status = 400
                else:
                    payload = {
                        "choices": [
                            {"message": {"role": "assistant", "content": "Ciao"}},
                        ],
                    }
                    status = 200
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            with app.config_lock:
                app.config.update(app.validate_config(
                    "custom",
                    "my-model",
                    "secret",
                    workspace=str(app.APP_DIR),
                    system_prompt="Chiamami Franz.",
                    base_url=f"http://127.0.0.1:{gateway.server_port}/v1",
                ))
            key = self.create_key()
            status, started, _ = self.send(
                "/api/v1/chat",
                {"messages": [{"role": "user", "content": "Ciao"}]},
                key=key,
            )
            self.assertEqual(status, 202)
            job = None
            for _ in range(60):
                time.sleep(0.2)
                _, job, _ = self.send(
                    f"/api/v1/jobs/{started['job_id']}", method="GET", key=key
                )
                if job["status"] in {"complete", "failed"}:
                    break
            self.assertEqual(job["status"], "complete", job)
            self.assertEqual(len(received), 2)
            retried = received[1]["messages"]
            self.assertNotIn("system", [message["role"] for message in retried])
            self.assertIn("Chiamami Franz.", retried[0]["content"])
            self.assertIn("Ciao", retried[0]["content"])
        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_an_unknown_job_is_reported(self):
        key = self.create_key()
        status, data, _ = self.send(
            f"/api/v1/jobs/{'a' * 32}", method="GET", key=key
        )
        self.assertEqual(status, 404)
        self.assertIn("non trovata", data["error"])

    def test_an_unknown_api_route_is_reported(self):
        key = self.create_key()
        status, _, _ = self.send("/api/v1/nope", method="GET", key=key)
        self.assertEqual(status, 404)


def _tomorrow_at(hour):
    import datetime

    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    return f"{tomorrow.isoformat()}T{hour:02d}:00"


if __name__ == "__main__":
    unittest.main()
