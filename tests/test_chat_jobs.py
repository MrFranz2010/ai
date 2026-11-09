import json
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import app


def sample_config():
    config = app.default_config()
    config.update({
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-chiave-di-prova",
        "base_url": "",
        "terminal_enabled": False,
        "app_tools_enabled": False,
    })
    return config


class ChatJobFailureTests(unittest.TestCase):
    def setUp(self):
        self.job_id = uuid.uuid4().hex
        with app.chat_jobs_lock:
            app.chat_jobs.clear()
            app.chat_jobs[self.job_id] = {
                "status": "running",
                "created_at": time.time(),
                "updated_at": time.time(),
                "tool_events": [],
                "workspace": str(Path.cwd()),
                "approved": None,
            }
        self.config = sample_config()

    def tearDown(self):
        with app.chat_jobs_lock:
            app.chat_jobs.clear()

    def run_job(self, error):
        with patch("app.urlopen", side_effect=error):
            app.run_chat_job(
                self.job_id, [{"role": "user", "content": "ciao"}], self.config
            )
        with app.chat_jobs_lock:
            return dict(app.chat_jobs[self.job_id])

    def test_a_timed_out_provider_fails_the_job(self):
        job = self.run_job(TimeoutError("timed out"))
        self.assertEqual(job["status"], "failed")
        self.assertIn("non ha risposto in tempo", job["error"])

    def test_a_dropped_connection_fails_the_job(self):
        job = self.run_job(ConnectionResetError("remote closed"))
        self.assertEqual(job["status"], "failed")
        self.assertIn("Connessione al provider interrotta", job["error"])

    def test_an_unexpected_error_still_fails_the_job(self):
        job = self.run_job(RuntimeError("boom"))
        self.assertEqual(job["status"], "failed")
        self.assertIn("Errore inatteso", job["error"])

    def test_a_worker_that_dies_never_leaves_the_job_running(self):
        with patch("app.run_chat_job", side_effect=SystemExit("stop")):
            with self.assertRaises(SystemExit):
                app._run_chat_job_safely(self.job_id, [], self.config)
        with app.chat_jobs_lock:
            job = dict(app.chat_jobs[self.job_id])
        self.assertEqual(job["status"], "failed")
        self.assertIn("interrotta senza risposta", job["error"])


class StaleJobEndpointTests(unittest.TestCase):
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

    def tearDown(self):
        with app.chat_jobs_lock:
            app.chat_jobs.clear()

    def make_job(self, age):
        job_id = uuid.uuid4().hex
        with app.chat_jobs_lock:
            app.chat_jobs[job_id] = {
                "status": "running",
                "created_at": time.time() - age,
                "updated_at": time.time() - age,
                "tool_events": [],
                "workspace": str(Path.cwd()),
                "approved": None,
            }
        return job_id

    def test_a_job_that_never_answers_is_reported_as_failed(self):
        job_id = self.make_job(app.CHAT_JOB_STALE_SECONDS + 10)
        with urlopen(f"{self.base_url}/api/jobs/{job_id}") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["status"], "failed")
        self.assertIn("minuti", payload["error"])

    def test_a_fresh_job_stays_running(self):
        job_id = self.make_job(1)
        with urlopen(f"{self.base_url}/api/jobs/{job_id}") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["status"], "running")


if __name__ == "__main__":
    unittest.main()
