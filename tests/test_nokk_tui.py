import asyncio
import tempfile
import unittest
from pathlib import Path

import nokk_cli
from nokk_cli import Config

try:
    from nokk_tui import NokkTuiApp, SettingsScreen
    HAS_TUI = True
except ImportError:
    HAS_TUI = False


class FakeClient:
    base_url = "http://127.0.0.1:8000"
    api_key = ""

    def __init__(self, replies=None):
        self.replies = list(replies or ["Ciao dalla TUI."])
        self.jobs = 0
        self.approvals = []

    def health(self):
        return {
            "provider": "openai",
            "model": "fake-model",
            "configured": True,
            "terminal_enabled": True,
            "approval_mode": "manual",
        }

    def start_chat(self, messages, mode=None):
        return "a" * 32

    def job(self, job_id):
        self.jobs += 1
        if self.replies:
            return {"status": "complete", "reply": self.replies.pop(0)}
        return {"status": "complete", "reply": "Fatto."}

    def approve(self, job_id, action_id, approved):
        self.approvals.append((job_id, action_id, approved))
        return {"ok": True}


class AgentClient(FakeClient):
    def job(self, job_id):
        self.jobs += 1
        if self.jobs == 1:
            return {
                "status": "complete",
                "reply": "Eseguo.\n```nokk-run\necho locale\n```",
            }
        return {"status": "complete", "reply": "Fatto."}


class ServerClient(FakeClient):
    def job(self, job_id):
        self.jobs += 1
        if self.jobs == 1:
            return {
                "status": "awaiting_approval",
                "action": {
                    "id": "call-1",
                    "command": "pwd",
                    "workspace": "/srv/nokk",
                },
            }
        return {"status": "complete", "reply": "Approvato."}


async def wait_until(pilot, predicate, attempts=50):
    for _ in range(attempts):
        await pilot.pause()
        await asyncio.sleep(0.02)
        if predicate():
            return True
    return False


@unittest.skipUnless(HAS_TUI, "Textual non installato")
class NokkTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_mounts_chat_sidebar_agents_and_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertTrue(app.query_one("#sidebar"))
                self.assertIn("NOKK API", app.query_one("#agents").render().plain)
                self.assertIn("CPU", app.query_one("#resources").render().plain)
                self.assertIn("Chat", app.query_one("#widgets").render().plain)
                self.assertIn("online", app.query_one("#statusline").render().plain)

    async def test_chat_reply_is_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(["Ciao dalla TUI."]),
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#prompt").value = "ciao"
                await pilot.press("enter")
                self.assertTrue(await wait_until(pilot, lambda: not app.busy))
                self.assertEqual(
                    app.active_chat.messages[-1],
                    {"role": "assistant", "content": "Ciao dalla TUI."},
                )

    async def test_agent_loop_runs_a_local_command(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=AgentClient(),
                auto_yes=True,
                cwd=directory,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#prompt").value = "controlla"
                await pilot.press("enter")
                self.assertTrue(await wait_until(pilot, lambda: not app.busy))
                self.assertEqual(
                    app.active_chat.messages[-1]["content"], "Fatto."
                )
                self.assertTrue(any(
                    "exit code: 0" in message["content"]
                    and "locale" in message["content"]
                    for message in app.active_chat.messages
                ))

    async def test_server_command_is_approved_from_a_modal(self):
        client = ServerClient()
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=client,
                auto_yes=False,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#prompt").value = "ciao"
                await pilot.press("enter")
                shown = await wait_until(
                    pilot, lambda: type(app.screen).__name__ == "ConfirmScreen"
                )
                self.assertTrue(shown)
                self.assertIn("server", app.screen.query_one("#dialog-title").render().plain)
                await pilot.click("#yes")
                self.assertTrue(await wait_until(pilot, lambda: not app.busy))
                self.assertEqual(client.approvals[0][1], "call-1")
                self.assertEqual(
                    app.active_chat.messages[-1]["content"], "Approvato."
                )

    async def test_settings_switch_between_local_and_hosting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cli.json"
            app = NokkTuiApp(
                Config(
                    base_url="http://127.0.0.1:8000",
                    api_key="local-key",
                    profile="local",
                    local_url="http://127.0.0.1:8000",
                    local_api_key="local-key",
                    hosting_url="https://nokk.example.com",
                    hosting_api_key="hosting-key",
                ),
                path,
                client=FakeClient(),
            )
            async with app.run_test(size=(120, 44)) as pilot:
                await pilot.pause()
                app.action_settings()
                await pilot.pause()
                self.assertIsInstance(app.screen, SettingsScreen)
                screen = app.screen
                screen.query_one("#settings-profile").value = "hosting"
                await pilot.pause()
                self.assertEqual(
                    screen.query_one("#settings-url").value,
                    "https://nokk.example.com",
                )
                screen.query_one("#settings-url").value = "https://new.example.com"
                screen.query_one("#settings-key").value = "new-key"
                screen.query_one("#settings-save").focus()
                await pilot.press("enter")
                self.assertTrue(await wait_until(pilot, lambda: app.profile == "hosting"))
                self.assertEqual(app.client.base_url, "https://new.example.com")
                self.assertEqual(app.client.api_key, "new-key")
                saved = nokk_cli.read_config(path)
                self.assertEqual(saved.hosting_url, "https://new.example.com")
                self.assertEqual(saved.hosting_api_key, "new-key")
                self.assertEqual(saved.local_url, "http://127.0.0.1:8000")

    async def test_narrow_terminal_hides_the_sidebar(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
            )
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                self.assertTrue(app.screen.has_class("narrow"))
                self.assertEqual(
                    app.query_one("#sidebar").styles.display, "none"
                )


if __name__ == "__main__":
    unittest.main()
