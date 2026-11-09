import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import app
from search import excerpt, make_document, rank_documents, tokens


class SearchRankingTests(unittest.TestCase):
    def documents(self):
        return [
            make_document("task", "1", "Compiti di storia", "Ripassare il capitolo 4"),
            make_document("event", "2", "Riunione con il cliente", "Portare il preventivo"),
            make_document("nota", "3", "Nota personale", "Preferisco studiare la mattina"),
            make_document("workflow", "4", "Riassunto lezioni", "Riassumi gli appunti del giorno"),
        ]

    def test_a_prefix_finds_the_plural(self):
        results = rank_documents("compito", self.documents())
        self.assertTrue(results)
        self.assertEqual(results[0]["title"], "Compiti di storia")

    def test_accents_and_case_do_not_matter(self):
        results = rank_documents("PERCHÉ STUDIARE", self.documents())
        self.assertEqual(results[0]["title"], "Nota personale")
        self.assertIn("studiare", results[0]["snippet"])

    def test_the_most_specific_document_comes_first(self):
        results = rank_documents("preventivo cliente", self.documents())
        self.assertEqual(results[0]["title"], "Riunione con il cliente")
        self.assertEqual(len(results), 1)

    def test_stopwords_alone_match_nothing(self):
        self.assertEqual(tokens("il di e che"), [])
        self.assertEqual(rank_documents("il di e", self.documents()), [])

    def test_a_short_query_is_refused_by_the_endpoint(self):
        status, payload = self.get("/api/search?q=a")
        self.assertEqual(status, 400)
        self.assertIn("2 a 120", payload["error"])

    # -- helper usato dai test dell'endpoint -----------------------------

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
        for path in (app.CONFIG_FILE, app.WORKFLOWS_FILE, app.PLANNER_FILE, app.API_FILE):
            path.unlink(missing_ok=True)
        with app.config_lock:
            app.config.update(app.default_config())
            app.workflows.clear()
            app.planner.clear()
            app.planner.update(app.default_planner())
        app.search_extra_provider = None
        app.user_memory_loader = None

    def tearDown(self):
        app.search_extra_provider = None
        app.user_memory_loader = None

    def get(self, path):
        try:
            with urlopen(f"{self.base_url}{path}") as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_planner_workflow_and_memory_are_searchable(self):
        with app.config_lock:
            app.planner["tasks"].append({
                "id": "a" * 32,
                "title": "Verifica di matematica",
                "due_date": "2026-11-20",
                "completed": False,
                "starts_at": "2026-11-20T09:00",
            })
            app.workflows.append({
                "id": "b" * 32,
                "name": "Riassunto lezioni",
                "prompt": "Riassumi le lezioni di oggi",
                "days": [],
                "time": "",
                "schedule_enabled": False,
            })
        app.user_memory_loader = lambda: ["Ho l'esame di storia il 20 novembre"]
        status, payload = self.get("/api/search?q=matematica")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["kind"], "task")
        self.assertEqual(payload["results"][0]["title"], "Verifica di matematica")
        status, payload = self.get("/api/search?q=storia")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["kind"], "nota")

    def test_the_hosted_branch_can_add_conversations(self):
        app.search_extra_provider = lambda: [
            make_document("chat", "chat-1", "Studio di fisica", "La lezione sul pendolo"),
        ]
        status, payload = self.get("/api/search?q=pendolo")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["kind"], "chat")
        self.assertEqual(payload["results"][0]["title"], "Studio di fisica")

    def test_the_endpoint_needs_a_usable_query(self):
        status, payload = self.get("/api/search?q=...")
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
