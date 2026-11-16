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


class ChatJobAccountingTests(unittest.TestCase):
    def setUp(self):
        with app.chat_jobs_lock:
            app.chat_jobs.clear()

    def tearDown(self):
        with app.chat_jobs_lock:
            app.chat_jobs.clear()

    def add_job(self, status, age=0):
        with app.chat_jobs_lock:
            app.chat_jobs[uuid.uuid4().hex] = {
                "status": status,
                "updated_at": time.time() - age,
            }

    def test_completed_jobs_do_not_block_new_requests(self):
        for _ in range(30):
            self.add_job("complete")
        with app.chat_jobs_lock:
            app._prune_chat_jobs_locked()
            self.assertEqual(app._active_chat_job_count_locked(), 0)

    def test_only_fresh_running_jobs_are_counted(self):
        for _ in range(4):
            self.add_job("running", age=1)
        self.add_job("awaiting_approval", age=1)
        with app.chat_jobs_lock:
            self.assertEqual(app._active_chat_job_count_locked(), 5)

    def test_stale_running_jobs_are_closed_and_ignored(self):
        self.add_job("running", age=app.CHAT_JOB_STALE_SECONDS + 10)
        with app.chat_jobs_lock:
            app._prune_chat_jobs_locked()
            job = next(iter(app.chat_jobs.values()))
            self.assertEqual(job["status"], "failed")
            self.assertEqual(app._active_chat_job_count_locked(), 0)

    def test_finished_jobs_are_capped(self):
        for _ in range(app.MAX_STORED_CHAT_JOBS + 10):
            self.add_job("failed")
        with app.chat_jobs_lock:
            app._prune_chat_jobs_locked()
            self.assertEqual(len(app.chat_jobs), app.MAX_STORED_CHAT_JOBS)


if __name__ == "__main__":
    unittest.main()
