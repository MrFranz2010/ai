import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import nokk_cli
import updater
from nokk_cli import Config

try:
    from nokk_tui import (
        NokkTuiApp,
        SettingsScreen,
        SudoPasswordScreen,
        collect_file_context,
        git_output,
    )
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
        self.cancelled = []
        self.last_model = None

    def health(self):
        return {
            "provider": "openai",
            "model": "fake-model",
            "configured": True,
            "terminal_enabled": True,
            "approval_mode": "manual",
        }

    def start_chat(
        self, messages, mode=None, provider=None, model=None, stream=False,
        terminal_enabled=None, local_terminal=False,
    ):
        self.last_model = (provider, model)
        self.last_stream = stream
        self.last_terminal = (terminal_enabled, local_terminal)
        return "a" * 32

    def job(self, job_id):
        self.jobs += 1
        if self.replies:
            return {"status": "complete", "reply": self.replies.pop(0)}
        return {"status": "complete", "reply": "Fatto."}

    def approve(self, job_id, action_id, approved):
        self.approvals.append((job_id, action_id, approved))
        return {"ok": True}

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return {"ok": True, "status": "cancelled"}


class AgentClient(FakeClient):
    def job(self, job_id):
        self.jobs += 1
        if self.jobs == 1:
            return {
                "status": "complete",
                "reply": "Eseguo.\n```nokk-run\necho locale\n```",
            }
        return {"status": "complete", "reply": "Fatto."}


class SudoAgentClient(FakeClient):
    def job(self, job_id):
        self.jobs += 1
        if self.jobs == 1:
            return {
                "status": "complete",
                "reply": "Serve sudo.\n```nokk-run\nsudo id\n```",
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
                topbar = app.query_one("#topbar").render().plain
                self.assertIn("NOKK", topbar)
                self.assertIn("agente", topbar)
                self.assertTrue(app.query_one("#composer"))
                self.assertTrue(app.query_one("#prompt"))

    async def test_update_command_applies_a_safe_update(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
                auto_yes=True,
            )
            status = updater.UpdateStatus(
                root=directory,
                branch="main",
                remote="origin",
                local_sha="a" * 40,
                remote_sha="b" * 40,
                behind=1,
                ahead=0,
                dirty=False,
                changed_files=("nokk_tui.py",),
                commits=("abc1234\tNuova versione",),
            )
            result = updater.UpdateResult(
                branch="main",
                previous_sha=status.local_sha,
                new_sha=status.remote_sha,
                changed_files=status.changed_files,
                requirements_changed=False,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                with (
                    patch.object(
                        updater, "check_for_update", return_value=status,
                    ) as check,
                    patch.object(
                        updater, "apply_update", return_value=result,
                    ) as apply,
                ):
                    await app.handle_command("/update")
                self.assertTrue(check.called)
                self.assertTrue(apply.called)

    async def test_clicking_an_item_removed_by_refresh_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cli.json"
            app = NokkTuiApp(Config(), path, client=FakeClient())
            async with app.run_test(size=(120, 44)) as pilot:
                await pilot.pause()
                listview = app.query_one("#chats")
                item = next(iter(listview.children))
                listview.clear()
                await pilot.pause()
                listview._on_list_item_child_clicked(
                    SimpleNamespace(item=item, stop=lambda: None)
                )

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

    async def test_sudo_command_asks_for_a_hidden_password(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def runner(command, cwd, sudo_password=None):
                calls.append((command, Path(cwd), sudo_password))
                return nokk_cli.LocalResult(command, 0, "ok")

            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=SudoAgentClient(),
                auto_yes=True,
                cwd=directory,
                runner=runner,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#prompt").value = "serve sudo"
                await pilot.press("enter")
                shown = await wait_until(
                    pilot, lambda: isinstance(app.screen, SudoPasswordScreen)
                )
                self.assertTrue(shown)
                field = app.screen.query_one("#sudo-password")
                self.assertTrue(field.password)
                field.value = "segreta"
                await pilot.press("enter")
                self.assertTrue(await wait_until(pilot, lambda: not app.busy))
        self.assertEqual(calls[0][0], "sudo id")
        self.assertEqual(calls[0][2], "segreta")

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

    async def test_settings_persist_terminal_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cli.json"
            app = NokkTuiApp(Config(), path, client=FakeClient())
            async with app.run_test(size=(120, 44)) as pilot:
                await pilot.pause()
                app.action_settings()
                await pilot.pause()
                screen = app.screen
                screen.query_one("#settings-cwd").value = directory
                screen.query_one("#settings-timeout").value = "45"
                screen.query_one("#settings-rounds").value = "3"
                screen.query_one("#settings-auto-approve").value = True
                screen.query_one("#settings-stream").value = False
                screen.query_one("#settings-save-sessions").value = False
                screen.query_one("#settings-bell").value = True
                screen.query_one("#settings-banner").value = False
                screen.query_one("#settings-save").focus()
                await pilot.press("enter")
                self.assertTrue(
                    await wait_until(pilot, lambda: not isinstance(app.screen, SettingsScreen))
                )
            saved = nokk_cli.read_config(path)
        self.assertEqual(saved.initial_cwd, str(Path(directory).resolve()))
        self.assertEqual(saved.job_timeout, 45)
        self.assertEqual(saved.max_rounds, 3)
        self.assertTrue(saved.auto_approve)
        self.assertFalse(saved.stream)
        self.assertFalse(saved.save_sessions)
        self.assertTrue(saved.bell_on_finish)
        self.assertFalse(saved.show_banner)
        self.assertEqual(app.job_timeout, 45)
        self.assertEqual(app.max_rounds, 3)
        self.assertTrue(app.auto_yes)
        self.assertFalse(app.stream)
        self.assertFalse(app.save_sessions_enabled)

    async def test_export_writes_the_chat_as_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
                cwd=directory,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.active_chat.messages.extend([
                    {"role": "user", "content": "Ciao"},
                    {"role": "assistant", "content": "**Risposta**"},
                    {"role": "user", "content": "nascosto", "hidden": True},
                ])
                await app.handle_command("/export chat.md")
                exported = (Path(directory) / "chat.md").read_text(encoding="utf-8")
                self.assertIn("# NOKK · Chat 1", exported)
                self.assertIn("## Tu\n\nCiao", exported)
                self.assertIn("## NOKK\n\n**Risposta**", exported)
                self.assertNotIn("nascosto", exported)

    async def test_ctrl_e_exports_without_opening_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
                cwd=directory,
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.active_chat.messages.append(
                    {"role": "user", "content": "scorciatoia"}
                )
                await pilot.press("ctrl+e")
                await pilot.pause()
                exported = list(Path(directory).glob("nokk-chat-*.md"))
                self.assertEqual(len(exported), 1)
                self.assertIn("scorciatoia", exported[0].read_text(encoding="utf-8"))

    async def test_copy_last_answer_and_older_replies(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(),
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.active_chat.messages.extend([
                    {"role": "user", "content": "prima"},
                    {"role": "assistant", "content": "prima risposta"},
                    {"role": "user", "content": "seconda"},
                    {"role": "assistant", "content": "seconda risposta"},
                ])
                await pilot.press("ctrl+y")
                await pilot.pause()
                self.assertEqual(app._clipboard, "seconda risposta")
                await app.handle_command("/copy 2")
                self.assertEqual(app._clipboard, "prima risposta")
                await app.handle_command("/copy all")
                self.assertIn("seconda risposta", app._clipboard)
                self.assertIn("# NOKK · Chat 1", app._clipboard)

    async def test_retry_replaces_the_last_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NokkTuiApp(
                Config(),
                Path(directory) / "cli.json",
                client=FakeClient(["prima risposta", "seconda risposta"]),
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await app.ask("domanda")
                await app.handle_command("/retry")
                self.assertEqual(
                    app.active_chat.messages,
                    [
                        {"role": "user", "content": "domanda"},
                        {"role": "assistant", "content": "seconda risposta"},
                    ],
                )

    async def test_sessions_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cli.json"
            first = NokkTuiApp(Config(), path, client=FakeClient(["memorizzata"]))
            async with first.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await first.ask("domanda persistente")
            second = NokkTuiApp(Config(), path, client=FakeClient())
            async with second.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(second.chats[0].title, "domanda persistente")
                self.assertEqual(
                    second.chats[0].messages[-1]["content"], "memorizzata"
                )

    async def test_model_override_is_sent_with_the_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            app = NokkTuiApp(Config(), Path(directory) / "cli.json", client=client)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.change_model("openai/gpt-test")
                await app.ask("ciao")
                self.assertEqual(client.last_model, ("openai", "gpt-test"))
                self.assertTrue(client.last_stream)

    def test_file_mentions_become_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nota.txt"
            path.write_text("contenuto importante", encoding="utf-8")
            context = collect_file_context("leggi @nota.txt", directory)
            self.assertIn("File: nota.txt", context)
            self.assertIn("contenuto importante", context)

    def test_git_output_reports_a_dirty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=directory, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=directory, check=True,
            )
            Path(directory, "file.txt").write_text("x", encoding="utf-8")
            code, output = git_output(directory, ["status", "--short"])
            self.assertEqual(code, 0)
            self.assertIn("file.txt", output)

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
