import datetime
import unittest
from unittest.mock import patch

import app
import user_memory


class TimetableParsingTests(unittest.TestCase):
    def test_pdf_memory_keeps_the_source_file_name(self):
        facts = user_memory.memory_facts_from_file(
            "orario.pdf", "Lunedì   Italiano   Matematica\nMartedì   Storia"
        )
        self.assertEqual(
            facts,
            [
                "[orario.pdf] Lunedì   Italiano   Matematica",
                "[orario.pdf] Martedì   Storia",
            ],
        )

    def test_pdf_space_aligned_table_is_read(self):
        facts = [
            "[orario.pdf] Ora    Lunedì    Martedì    Mercoledì",
            "[orario.pdf] 8:00    Italiano    Matematica    Storia",
            "[orario.pdf] 9:00    Scienze    Arte    Musica",
        ]
        schedule = app.timetable_from_memories(facts)
        self.assertEqual(schedule[0], ["Italiano", "Scienze"])
        self.assertEqual(schedule[1], ["Matematica", "Arte"])
        self.assertEqual(schedule[2], ["Storia", "Musica"])

    def test_pdf_cells_on_separate_lines_are_read(self):
        facts = [
            "[orario.pdf] Lunedì",
            "[orario.pdf] Italiano",
            "[orario.pdf] Matematica",
            "[orario.pdf] Martedì",
            "[orario.pdf] Storia",
        ]
        schedule = app.timetable_from_memories(facts)
        self.assertEqual(schedule[0], ["Italiano", "Matematica"])
        self.assertEqual(schedule[1], ["Storia"])

    def test_reminder_uses_the_requested_day(self):
        facts = ["[orario.pdf] Venerdì: Storia, Scienze"]
        now = datetime.datetime(2026, 11, 6, 7, 0)
        message = app.build_timetable_reminder(now, facts)
        self.assertIn("venerdì 6 novembre", message)
        self.assertIn("• Storia", message)
        self.assertIsNone(
            app.build_timetable_reminder(
                datetime.datetime(2026, 11, 7, 7, 0), facts
            )
        )

    def test_new_pdf_replaces_the_previous_timetable(self):
        first = user_memory.merge_memory_file(
            ["Preferisco risposte brevi."], "orario.pdf", "Lunedì: Italiano"
        )
        second = user_memory.merge_memory_file(
            first, "orario.pdf", "Lunedì: Storia"
        )
        self.assertIn("Preferisco risposte brevi.", second)
        self.assertIn("[orario.pdf] Lunedì: Storia", second)
        self.assertNotIn("[orario.pdf] Lunedì: Italiano", second)


class TelegramReminderSettingsTests(unittest.TestCase):
    def test_defaults_and_validation(self):
        defaults = app.default_telegram_reminder()
        self.assertTrue(defaults["reminder_enabled"])
        self.assertEqual(defaults["reminder_time"], "07:00")
        self.assertEqual(
            app.normalize_telegram_reminder({
                "reminder_time": "08:15",
            })["reminder_time"],
            "08:15",
        )
        with self.assertRaises(ValueError):
            app.normalize_telegram_reminder({"reminder_time": "8:15"})
        with self.assertRaises(ValueError):
            app.normalize_telegram_reminder({"reminder_enabled": "sì"})

    def test_reminder_sends_only_once_on_the_selected_day(self):
        now = datetime.datetime(2026, 11, 6, 7, 2)
        config = {
            "token": "123456:abcdefghijklmnopqrstuvwxyzABCDEFG",
            "bot_username": "NokkBot",
            "authorized_chats": ["12345"],
            "offset": 0,
            "reminder_enabled": True,
            "reminder_time": "07:00",
            "reminder_last_sent": None,
        }
        with (
            patch.object(app, "telegram_config", config),
            patch.object(app, "telegram_reminder_sent_day", None),
            patch.object(
                app,
                "_telegram_memory_facts",
                return_value=["[orario.pdf] Venerdì: Storia, Scienze"],
            ),
            patch.object(app, "_send_telegram_message") as send,
            patch.object(app, "save_telegram_file"),
        ):
            self.assertTrue(app._maybe_send_telegram_reminder(now))
            send.assert_called_once()
            self.assertFalse(app._maybe_send_telegram_reminder(now))


class WorkflowScheduleTests(unittest.TestCase):
    def workflow(self, **overrides):
        value = {
            "id": "a" * 32,
            "name": "Controllo",
            "prompt": "Controlla le attività di oggi.",
            "schedule_enabled": True,
            "schedule_time": "07:00",
            "schedule_days": [4],
            "last_run": None,
            "last_status": None,
            "last_result": None,
        }
        value.update(overrides)
        return value

    def test_due_only_on_selected_day_and_time_window(self):
        workflow = self.workflow()
        self.assertTrue(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 6, 7, 0)
        ))
        self.assertTrue(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 6, 7, 14)
        ))
        self.assertFalse(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 6, 6, 59)
        ))
        self.assertFalse(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 6, 7, 16)
        ))
        self.assertFalse(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 5, 7, 0)
        ))

    def test_workflow_does_not_run_twice_in_the_same_day(self):
        workflow = self.workflow(last_run="2026-11-06T07:00:00+01:00")
        self.assertFalse(app._workflow_is_due(
            workflow, datetime.datetime(2026, 11, 6, 7, 5)
        ))

    def test_disabled_or_unscheduled_workflow_is_not_due(self):
        now = datetime.datetime(2026, 11, 6, 7, 0)
        self.assertFalse(app._workflow_is_due(
            self.workflow(schedule_enabled=False), now
        ))
        self.assertFalse(app._workflow_is_due(
            self.workflow(schedule_days=[]), now
        ))

    def test_schedule_validation_rejects_missing_days_and_bad_times(self):
        with self.assertRaises(ValueError):
            app.validate_workflows([self.workflow(schedule_days=[])])
        with self.assertRaises(ValueError):
            app.validate_workflows([self.workflow(schedule_time="25:00")])
        with self.assertRaises(ValueError):
            app.validate_workflows([self.workflow(schedule_days=[7])])

    def test_scheduled_workflow_records_the_result(self):
        workflow = self.workflow()

        def complete(job_id, _messages, _config):
            app._finish_job(job_id, "complete", reply="Tutto in ordine.")

        with (
            patch.object(app, "config", {"api_key": "chiave", "workspace": "/tmp"}),
            patch.object(app, "run_chat_job", side_effect=complete),
            patch.object(app, "record_workflow_run") as record,
        ):
            app.run_scheduled_workflow(workflow)
        record.assert_called_once_with(workflow["id"], "ok", "Tutto in ordine.")

    def test_scheduled_workflow_records_a_failure(self):
        workflow = self.workflow()
        with (
            patch.object(app, "config", {"api_key": "chiave", "workspace": "/tmp"}),
            patch.object(app, "run_chat_job", side_effect=RuntimeError("rete")),
            patch.object(app, "record_workflow_run") as record,
        ):
            app.run_scheduled_workflow(workflow)
        record.assert_called_once()
        self.assertEqual(record.call_args.args[1], "error")

    def test_schedule_round_trips_through_validation(self):
        validated = app.validate_workflows([self.workflow()])[0]
        self.assertTrue(validated["schedule_enabled"])
        self.assertEqual(validated["schedule_time"], "07:00")
        self.assertEqual(validated["schedule_days"], [4])


if __name__ == "__main__":
    unittest.main()
