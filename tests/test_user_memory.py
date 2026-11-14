import re
import unittest

import user_memory


class FakeApp:
    def run_chat_job(self, *_args, **_kwargs):
        raise AssertionError("chat job should not run in this test")


class FakeHandler:
    _user_memory_installed = False

    def do_GET(self):
        raise AssertionError("GET should not run in this test")

    def do_POST(self):
        raise AssertionError("POST should not run in this test")

    def _require_authentication(self):
        return True

    def _read_json(self):
        return {"action": "save", "memories": ["Preferisco risposte brevi."]}

    def _send_json(self, status, payload):
        self.status = status
        self.payload = payload


class UserMemoryErrorTests(unittest.TestCase):
    def test_save_failure_returns_a_reference_code(self):
        def save_memories(_memories):
            raise RuntimeError("database unavailable")

        user_memory.install(FakeApp(), FakeHandler, lambda: [], save_memories)
        handler = FakeHandler()
        handler.path = "/api/memory"

        handler.do_POST()

        self.assertEqual(handler.status, 500)
        self.assertIn("Impossibile salvare la memoria", handler.payload["error"])
        self.assertRegex(handler.payload["error_id"], re.compile(r"^[a-f0-9]{8}$"))

class MemoryRelevanceTests(unittest.TestCase):
    def test_a_short_memory_is_returned_unchanged(self):
        facts = ["Mangio vegetariano.", "Studio fisica."]
        selected = user_memory.select_relevant_memories(
            facts, [{"role": "user", "content": "Come procede fisica?"}]
        )
        self.assertEqual(selected, facts)

    def test_a_long_memory_keeps_the_facts_closest_to_the_request(self):
        facts = [f"Cosa numero {index} su argomento {index}." for index in range(30)]
        facts.append("Il mio progetto si chiama NOKK.")
        selected = user_memory.select_relevant_memories(
            facts, [{"role": "user", "content": "Come procede il progetto NOKK?"}]
        )
        self.assertLessEqual(len(selected), user_memory.MEMORY_RELEVANCE_LIMIT)
        self.assertIn("Il mio progetto si chiama NOKK.", selected)

    def test_the_latest_user_message_drives_the_selection(self):
        facts = [f"Fatto {index} sul tema {index}." for index in range(25)]
        facts.append("Uso Debian sul portatile.")
        facts.append("Il gatto si chiama Nocciola.")
        selected = user_memory.select_relevant_memories(
            facts,
            [
                {"role": "user", "content": "Parliamo del gatto"},
                {"role": "assistant", "content": "Certo."},
                {"role": "user", "content": "Che sistema uso sul portatile?"},
            ],
        )
        self.assertIn("Uso Debian sul portatile.", selected)
        self.assertNotIn("Il gatto si chiama Nocciola.", selected)


class ChatJobModeTests(unittest.TestCase):
    def test_the_memory_wrapper_forwards_the_chat_mode(self):
        calls = []

        class Recorder:
            def run_chat_job(self, *args, **kwargs):
                calls.append((args, kwargs))
                return "ok"

        class Handler(FakeHandler):
            _user_memory_installed = False

        recorder = Recorder()
        user_memory.install(
            recorder,
            Handler,
            lambda: ["Preferisco risposte brevi."],
            lambda _memories: None,
        )
        config = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "chiave-di-prova",
            "base_url": "",
            "system_prompt": "",
        }
        result = recorder.run_chat_job(
            "job-id",
            [{"role": "user", "content": "Scrivi una funzione."}],
            config,
            "code",
        )
        self.assertEqual(result, "ok")
        args, kwargs = calls[0]
        forwarded = kwargs.get("mode", args[3] if len(args) > 3 else None)
        self.assertEqual(forwarded, "code")


if __name__ == "__main__":
    unittest.main()
