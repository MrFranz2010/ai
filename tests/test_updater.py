import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updater


class GitRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.remote = base / "remote.git"
        self.source = base / "source"
        self.work = base / "work"
        self.git(base, "init", "--bare", str(self.remote))
        self.git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(base, "init", "-b", "main", str(self.source))
        self.configure(self.source)
        self.write(self.source / "README.md", "versione 1\n")
        self.commit(self.source, "prima versione")
        self.git(self.source, "remote", "add", "origin", str(self.remote))
        self.git(self.source, "push", "-u", "origin", "main")
        self.git(base, "clone", str(self.remote), str(self.work))
        self.configure(self.work)

    def git(self, cwd, *arguments):
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        ).stdout

    def configure(self, cwd):
        self.git(cwd, "config", "user.name", "NOKK Test")
        self.git(cwd, "config", "user.email", "nokk@example.invalid")

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, cwd, message):
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-m", message)

    def advance(self, content="versione 2\n", path="README.md", message="nuova versione"):
        self.write(self.source / path, content)
        self.commit(self.source, message)
        self.git(self.source, "push", "origin", "main")


class UpdateTests(GitRepositoryTestCase):
    def test_detects_and_applies_a_fast_forward(self):
        self.advance()
        status = updater.check_for_update(self.work)
        self.assertTrue(status.available)
        self.assertEqual(status.behind, 1)
        self.assertEqual(status.ahead, 0)
        self.assertIn("README.md", status.changed_files)
        self.assertTrue(status.commits)

        result = updater.apply_update(status)

        self.assertEqual(
            (self.work / "README.md").read_text(encoding="utf-8"),
            "versione 2\n",
        )
        self.assertEqual(result.new_sha, status.remote_sha)
        self.assertFalse(result.requirements_changed)

    def test_reports_when_dependencies_changed(self):
        self.advance("textual>=0.80\n", "requirements-tui.txt")
        status = updater.check_for_update(self.work)
        self.assertTrue(status.requirements_changed)
        self.assertTrue(updater.apply_update(status).requirements_changed)

    def test_dirty_worktree_blocks_the_update(self):
        self.advance()
        self.write(self.work / "README.md", "modifica locale\n")
        status = updater.check_for_update(self.work)
        self.assertTrue(status.dirty)
        with self.assertRaises(updater.UpdateError):
            updater.apply_update(status)
        self.assertEqual(
            (self.work / "README.md").read_text(encoding="utf-8"),
            "modifica locale\n",
        )

    def test_unpublished_local_commits_block_the_update(self):
        self.advance()
        self.write(self.work / "local.txt", "solo locale\n")
        self.commit(self.work, "commit locale")
        status = updater.check_for_update(self.work)
        self.assertEqual(status.ahead, 1)
        self.assertGreaterEqual(status.behind, 1)
        with self.assertRaises(updater.UpdateError):
            updater.apply_update(status)
        self.assertTrue((self.work / "local.txt").exists())

    def test_auto_update_applies_when_safe(self):
        self.advance()
        messages = []
        result = updater.auto_update(
            notify=messages.append,
            start=self.work,
        )
        self.assertIsInstance(result, updater.UpdateResult)
        self.assertEqual(
            (self.work / "README.md").read_text(encoding="utf-8"),
            "versione 2\n",
        )
        self.assertTrue(any("aggiornato" in message for message in messages))

    def test_auto_update_waits_when_dependencies_change(self):
        self.advance("textual>=0.80\n", "requirements-tui.txt")
        messages = []
        result = updater.auto_update(
            notify=messages.append,
            start=self.work,
        )
        self.assertIsInstance(result, updater.UpdateStatus)
        self.assertFalse((self.work / "requirements-tui.txt").exists())
        self.assertTrue(any("dipendenze" in message for message in messages))

    def test_auto_update_can_be_disabled(self):
        self.advance()
        with patch.dict(os.environ, {"NOKK_AUTO_UPDATE": "0"}):
            self.assertIsNone(updater.auto_update(start=self.work))
        self.assertEqual(
            (self.work / "README.md").read_text(encoding="utf-8"),
            "versione 1\n",
        )

    def test_missing_remote_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.git(directory, "init", "-b", "main")
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(directory)

    def test_non_repository_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(updater.UpdateError):
                updater.check_for_update(directory)

    def test_no_update_is_available_on_the_current_commit(self):
        status = updater.check_for_update(self.work)
        self.assertFalse(status.available)
        self.assertEqual(status.behind, 0)
        self.assertFalse(status.changed_files)
