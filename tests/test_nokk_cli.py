import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nokk_cli


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeClient:
    base_url = "http://127.0.0.1:8000"
    api_key = ""
    versioned = False

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.jobs = 0
        self.approvals = []

    def start_chat(self, messages, mode=None):
        self.sent.append([dict(message) for message in messages])
        return "a" * 32

    def job(self, _job_id):
        self.jobs += 1
        return {"status": "complete", "reply": self.replies.pop(0)}

    def approve(self, job_id, action_id, approved):
        self.approvals.append((job_id, action_id, approved))


class CliParsingTests(unittest.TestCase):
    def test_extracts_only_nokk_run_blocks(self):
        reply = (
            "Prima controllo.\n"
            "```nokk-run\npython -m unittest\n```\n"
            "```bash\nrm -rf /tmp/example\n```\n"
            "```nokk-run\necho fatto\n```"
        )
        self.assertEqual(
            nokk_cli.extract_run_commands(reply),
            ["python -m unittest", "echo fatto"],
        )

    def test_ignores_unclosed_blocks(self):
        self.assertEqual(
            nokk_cli.extract_run_commands("```nokk-run\necho ciao"),
            [],
        )

    def test_normalizes_urls(self):
        self.assertEqual(
            nokk_cli.normalize_base_url("nokk.example.com/"),
            "http://nokk.example.com",
        )
        self.assertEqual(
            nokk_cli.normalize_base_url("https://nokk.example.com/api/v1"),
            "https://nokk.example.com",
        )
        self.assertEqual(
            nokk_cli.normalize_base_url("http://127.0.0.1:8000/base/"),
            "http://127.0.0.1:8000/base",
        )

    def test_rejects_foreign_urls(self):
        with self.assertRaises(nokk_cli.CliError):
            nokk_cli.normalize_base_url("ftp://nokk.example.com")

    def test_masks_keys(self):
        self.assertEqual(nokk_cli.mask_key(""), "(nessuna)")
        self.assertEqual(nokk_cli.mask_key("nokk_1234567890abcdef"), "nokk_1…cdef")


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "cli.json"
            expected = nokk_cli.Config(
                base_url="https://nokk.example.com",
                api_key="nokk_secret",
                mode="codice",
                agent=False,
            )
            nokk_cli.save_config(expected, path)
            loaded = nokk_cli.read_config(path)
            self.assertEqual(loaded.base_url, expected.base_url)
            self.assertEqual(loaded.api_key, expected.api_key)
            self.assertEqual(loaded.mode, expected.mode)
            self.assertEqual(loaded.agent, expected.agent)
            self.assertEqual(loaded.profile, "hosting")
            self.assertEqual(loaded.local_url, nokk_cli.DEFAULT_BASE_URL)

    def test_keeps_local_and_hosting_profiles_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cli.json"
            nokk_cli.save_config(nokk_cli.Config(
                base_url="http://127.0.0.1:8000",
                api_key="local-key",
                mode="codice",
                agent=True,
                profile="local",
                local_url="http://127.0.0.1:8000",
                local_api_key="local-key",
                hosting_url="https://nokk.example.com",
                hosting_api_key="hosting-key",
            ), path)
            loaded = nokk_cli.read_config(path)
            self.assertEqual(loaded.profile, "local")
            self.assertEqual(loaded.local_url, "http://127.0.0.1:8000")
            self.assertEqual(loaded.local_api_key, "local-key")
            self.assertEqual(loaded.hosting_url, "https://nokk.example.com")
            self.assertEqual(loaded.hosting_api_key, "hosting-key")

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config = nokk_cli.read_config(Path(directory) / "missing.json")
            self.assertEqual(config.base_url, nokk_cli.DEFAULT_BASE_URL)
            self.assertEqual(config.api_key, "")


class ClientTests(unittest.TestCase):
    def test_without_key_uses_browser_routes(self):
        with patch(
            "nokk_cli.urllib.request.urlopen",
            return_value=FakeResponse({"job_id": "b" * 32}),
        ) as urlopen:
            client = nokk_cli.NokkClient("127.0.0.1:8000")
            self.assertEqual(
                client.start_chat([{"role": "user", "content": "ciao"}]),
                "b" * 32,
            )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/chat")
        self.assertIsNone(request.get_header("X-api-key"))

    def test_with_key_uses_v1_and_sends_the_key(self):
        with patch(
            "nokk_cli.urllib.request.urlopen",
            return_value=FakeResponse({"job_id": "c" * 32}),
        ) as urlopen:
            client = nokk_cli.NokkClient(
                "https://nokk.example.com", "nokk_secret", timeout=5,
            )
            client.start_chat([{"role": "user", "content": "ciao"}], "studio")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://nokk.example.com/api/v1/chat",
        )
        self.assertEqual(request.get_header("X-api-key"), "nokk_secret")
        self.assertEqual(json.loads(request.data)["mode"], "studio")

    def test_approval_uses_the_v1_job_route(self):
        with patch(
            "nokk_cli.urllib.request.urlopen",
            return_value=FakeResponse({"ok": True}),
        ) as urlopen:
            client = nokk_cli.NokkClient("https://nokk.example.com", "nokk_secret")
            client.approve("d" * 32, "call-1", True)
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            f"https://nokk.example.com/api/v1/jobs/{'d' * 32}/approval",
        )
        self.assertEqual(
            json.loads(request.data),
            {"action_id": "call-1", "approved": True},
        )

    def test_http_errors_are_reported_with_a_hint(self):
        error = nokk_cli.urllib.error.HTTPError(
            "https://nokk.example.com/api/v1/chat",
            401,
            "Unauthorized",
            {},
            None,
        )
        with patch("nokk_cli.urllib.request.urlopen", side_effect=error):
            client = nokk_cli.NokkClient("https://nokk.example.com", "bad")
            with self.assertRaises(nokk_cli.CliError) as raised:
                client.start_chat([{"role": "user", "content": "ciao"}])
        self.assertIn("401", str(raised.exception))
        self.assertIn("chiave", raised.exception.hint)


class SessionTests(unittest.TestCase):
    def test_agent_executes_a_local_command_and_returns_its_output(self):
        client = FakeClient([
            "Controllo la cartella.\n```nokk-run\npwd\n```",
            "Fatto.",
        ])
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def runner(command, cwd):
                calls.append((command, Path(cwd)))
                return nokk_cli.LocalResult(command, 0, "/tmp/progetto\n")

            lines = []
            session = nokk_cli.Session(
                client,
                Path(directory) / "cli.json",
                agent=True,
                auto_yes=True,
                interactive=False,
                cwd=directory,
                out=lines.append,
                runner=runner,
            )
            self.assertTrue(session.ask("dove sono?"))
        self.assertEqual(calls[0][0], "pwd")
        self.assertEqual(session.last_reply, "Fatto.")
        self.assertEqual(session.messages[-1]["content"], "Fatto.")
        self.assertTrue(any(
            "exit code: 0" in message["content"]
            and "/tmp/progetto" in message["content"]
            for message in session.messages
        ))
        self.assertEqual(len(client.sent), 2)

    def test_local_command_is_added_to_context(self):
        client = FakeClient([])
        with tempfile.TemporaryDirectory() as directory:
            session = nokk_cli.Session(
                client,
                Path(directory) / "cli.json",
                agent=False,
                interactive=False,
                cwd=directory,
                out=lambda _line: None,
                runner=lambda command, _cwd: nokk_cli.LocalResult(
                    command, 0, "ok",
                ),
            )
            self.assertTrue(session.run_local_and_remember("echo ok"))
        self.assertIn("echo ok", session.messages[-1]["content"])
        self.assertIn("ok", session.messages[-1]["content"])


class WorkingDirectoryTests(unittest.TestCase):
    def test_resolves_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                nokk_cli.resolve_working_directory(directory),
                Path(directory).resolve(),
            )

    def test_rejects_a_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "assente"
            with self.assertRaises(nokk_cli.CliError):
                nokk_cli.resolve_working_directory(str(missing))

    def test_parser_accepts_the_initial_directory(self):
        args = nokk_cli.build_parser().parse_args(["--cwd", "/"])
        self.assertEqual(args.cwd, "/")

    def test_agent_rules_allow_paths_outside_the_working_directory(self):
        rules = nokk_cli.AGENT_RULES.format(cwd="/home/utente/progetto")
        self.assertIn("tutto il sistema", rules)
        self.assertIn("percorso assoluto", rules)


class LocalCommandTests(unittest.TestCase):
    def test_runs_in_the_given_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = nokk_cli.run_local("echo ciao", directory)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output.strip(), "ciao")

    def test_reports_a_failing_command(self):
        result = nokk_cli.run_local("exit 7", Path.cwd())
        self.assertEqual(result.exit_code, 7)


if __name__ == "__main__":
    unittest.main()
