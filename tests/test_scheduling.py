import datetime
import io
import json
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

    def test_flat_pdf_grid_is_read_as_five_days_of_six_subjects(self):
        facts = [
            "[orario.pdf] STO-FILOSOFIA MATEM-FISICA RELIG-M.ALT "
            "ITAL-LATINO DISEGNO-ARTE DISEGNO-ARTE ITAL-LATINO "
            "STO-FILOSOFIA STO-FILOSOFIA INGLESE MATEM-FISICA SCIENZE "
            "SCIENZE STO-FILOSOFIA SC-MOTORIE SC-MOTORIE MATEM-FISICA "
            "ITAL-LATINO STO-FILOSOFIA ITAL-LATINO ITAL-LATINO SCIENZE "
            "MATEM-FISICA MATEM-FISICA MATEM-FISICA MATEM-FISICA "
            "ITAL-LATINO ITAL-LATINO INGLESE INGLESE"
        ]
        schedule = app.timetable_from_memories(facts)
        self.assertEqual(len(schedule), 5)
        self.assertEqual(schedule[0], [
            "STO-FILOSOFIA", "MATEM-FISICA", "RELIG-M.ALT",
            "ITAL-LATINO", "DISEGNO-ARTE", "DISEGNO-ARTE",
        ])
        self.assertEqual(schedule[1][:3], [
            "ITAL-LATINO", "STO-FILOSOFIA", "STO-FILOSOFIA",
        ])
        self.assertEqual(schedule[4], [
            "MATEM-FISICA", "MATEM-FISICA", "ITAL-LATINO",
            "ITAL-LATINO", "INGLESE", "INGLESE",
        ])

    def test_memory_file_upload_preserves_flat_timetable_order(self):
        text = "\n".join(
            "STO-FILOSOFIA MATEM-FISICA RELIG-M.ALT ITAL-LATINO "
            "DISEGNO-ARTE DISEGNO-ARTE ITAL-LATINO STO-FILOSOFIA "
            "STO-FILOSOFIA INGLESE MATEM-FISICA SCIENZE SCIENZE "
            "STO-FILOSOFIA SC-MOTORIE SC-MOTORIE MATEM-FISICA "
            "ITAL-LATINO STO-FILOSOFIA ITAL-LATINO ITAL-LATINO SCIENZE "
            "MATEM-FISICA MATEM-FISICA MATEM-FISICA MATEM-FISICA "
            "ITAL-LATINO ITAL-LATINO INGLESE INGLESE".split()
        )
        facts = user_memory.merge_memory_file(
            ["Marco merrino è uno scrittore"], "orario.pdf", text
        )
        self.assertEqual(len(facts), 31)
        schedule = app.timetable_from_memories(facts)
        self.assertEqual(schedule[0], [
            "STO-FILOSOFIA", "MATEM-FISICA", "RELIG-M.ALT",
            "ITAL-LATINO", "DISEGNO-ARTE", "DISEGNO-ARTE",
        ])
        self.assertEqual(schedule[4], [
            "MATEM-FISICA", "MATEM-FISICA", "ITAL-LATINO",
            "ITAL-LATINO", "INGLESE", "INGLESE",
        ])

    def test_explicit_timetable_keeps_double_periods(self):
        facts = [
            "[orario] Venerdì: ITAL-LATINO, SCIENZE, MATEM-FISICA, "
            "MATEM-FISICA, MATEM-FISICA"
        ]
        message = app.build_timetable_reminder(
            datetime.datetime(2026, 11, 6, 7, 0), facts
        )
        self.assertEqual(message.count("• MATEM-FISICA"), 3)
        self.assertEqual(message.count("• ITAL-LATINO"), 1)

    def test_weekly_message_contains_all_saved_days(self):
        facts = ["[orario.pdf] Lunedì: Storia", "[orario.pdf] Sabato: Inglese"]
        now = datetime.datetime(2026, 11, 6, 7, 0)
        message = app.build_weekly_timetable(now, facts)
        self.assertIn("Orario settimanale", message)
        self.assertIn("Lunedì: Storia", message)
        self.assertIn("Sabato: Inglese", message)

    def test_current_date_context_is_explicit(self):
        now = datetime.datetime(2026, 11, 6, 7, 0)
        context = app.build_current_datetime_context(now)
        self.assertIn("venerdì 6 novembre 2026", context)
        self.assertIn("2026-11-06", context)
        self.assertIn("Non usare anni passati", context)
        self.assertEqual(
            app.current_datetime_data(now)["weekday"], "venerdì"
        )
        self.assertIn(
            "Oggi è venerdì 6 novembre 2026",
            app.build_current_datetime_message(now),
        )

    def test_save_timetable_tool_replaces_previous_schedule(self):
        days = {
            "lunedi": ["Italiano", "Storia"],
            "martedi": ["Matematica"],
            "mercoledi": [],
            "giovedi": ["Fisica"],
            "venerdi": ["Inglese"],
            "sabato": [],
        }
        with (
            patch.object(
                app, "user_memory_loader",
                return_value=["Preferisco risposte brevi.", "[orario] vecchio"],
            ),
            patch.object(app, "user_memory_saver") as saver,
        ):
            result = app.save_timetable_from_tool(days)
        self.assertTrue(result["ok"])
        saved = saver.call_args.args[0]
        self.assertIn("Preferisco risposte brevi.", saved)
        self.assertIn("[orario] Lunedì: Italiano, Storia", saved)
        self.assertNotIn("[orario] vecchio", saved)

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


class _JsonResponse(io.BytesIO):
    pass


def _json_response(payload):
    return _JsonResponse(json.dumps(payload).encode("utf-8"))


class DeadlineReminderTests(unittest.TestCase):
    def test_lead_time_is_normalized(self):
        self.assertIsNone(app.normalize_remind_days_before(None))
        self.assertIsNone(app.normalize_remind_days_before("  "))
        self.assertEqual(app.normalize_remind_days_before(3), 3)
        self.assertEqual(app.normalize_remind_days_before("2"), 2)
        for invalid in (31, -1, True, "abc"):
            with self.assertRaises(ValueError):
                app.normalize_remind_days_before(invalid)

    def test_reminder_is_built_on_the_lead_day_only(self):
        now = datetime.datetime(2026, 11, 6, 7, 5)
        tasks = [
            {
                "id": "a" * 32,
                "title": "Assicurazione",
                "due_date": "2026-11-09",
                "remind_days_before": 3,
                "completed": False,
            },
            {
                "id": "b" * 32,
                "title": "Bolletta",
                "due_date": "2026-11-20",
                "remind_days_before": 3,
                "completed": False,
            },
            {
                "id": "c" * 32,
                "title": "Rinnovo",
                "due_date": "2026-11-06",
                "remind_days_before": 0,
                "completed": True,
            },
        ]
        reminders = app.build_task_reminders(now, tasks)
        self.assertEqual(len(reminders), 1)
        self.assertIn("Assicurazione", reminders[0]["message"])
        self.assertIn("tra 3 giorni", reminders[0]["message"])
        self.assertIn("9 novembre", reminders[0]["message"])

    def test_same_day_lead_time_says_today(self):
        now = datetime.datetime(2026, 11, 6, 7, 5)
        reminders = app.build_task_reminders(now, [{
            "id": "a" * 32,
            "title": "Consegna",
            "due_date": "2026-11-06",
            "remind_days_before": 0,
            "completed": False,
        }])
        self.assertEqual(len(reminders), 1)
        self.assertIn("oggi", reminders[0]["message"])

    def test_task_reminder_is_sent_once_per_day(self):
        saved_config = app.telegram_config.copy()
        saved_tasks = [item.copy() for item in app.planner["tasks"]]
        self.addCleanup(self._restore, saved_config, saved_tasks)
        with app.config_lock:
            app.planner["tasks"][:] = [{
                "id": "a" * 32,
                "title": "Assicurazione",
                "due_date": "2026-11-09",
                "remind_days_before": 3,
                "completed": False,
            }]
        with app.telegram_lock:
            app.telegram_config.clear()
            app.telegram_config.update({
                "token": "123456789:abcdefghijklmnopqrstuvwxyz0123456789",
                "bot_username": "nokk_test_bot",
                "authorized_chats": ["42"],
                "offset": 0,
                "reminder_enabled": True,
                "reminder_time": "07:00",
                "reminder_last_sent": None,
                "task_reminders_sent": {},
            })
        now = datetime.datetime(2026, 11, 6, 7, 5)
        with patch("app._send_telegram_message") as send_message, patch(
            "app.save_telegram_file"
        ):
            self.assertTrue(app._maybe_send_task_reminders(now))
            self.assertEqual(send_message.call_count, 1)
            self.assertFalse(app._maybe_send_task_reminders(now))
        self.assertEqual(send_message.call_count, 1)
        self.assertEqual(
            app.telegram_config["task_reminders_sent"]["a" * 32 + ":2026-11-09"],
            "2026-11-06",
        )

    def _restore(self, saved_config, saved_tasks):
        with app.telegram_lock:
            app.telegram_config.clear()
            app.telegram_config.update(saved_config)
        with app.config_lock:
            app.planner["tasks"][:] = saved_tasks


class MachineAlertTests(unittest.TestCase):
    def test_thresholds_produce_alerts(self):
        settings = {"alerts_disk_percent": 80, "alerts_memory_percent": 90}
        disk_only = app.build_machine_alerts(settings, {"disk": 85, "memory": 40})
        self.assertEqual([key for key, _ in disk_only], ["disk"])
        self.assertIn("85%", disk_only[0][1])
        memory_only = app.build_machine_alerts(settings, {"disk": 10, "memory": 95})
        self.assertEqual([key for key, _ in memory_only], ["memory"])
        self.assertEqual(
            app.build_machine_alerts(settings, {"disk": 10, "memory": 10}), []
        )

    def test_alerts_respect_the_cooldown(self):
        saved_config = app.config.copy()
        saved_alerts = dict(app.alert_last_sent)
        self.addCleanup(self._restore, saved_config, saved_alerts)
        with app.config_lock:
            app.config.update({
                "alerts_enabled": True,
                "alerts_disk_percent": 80,
                "alerts_memory_percent": 99,
            })
        with app.telegram_lock:
            app.telegram_config.update({
                "token": "123456789:abcdefghijklmnopqrstuvwxyz0123456789",
                "authorized_chats": ["42"],
            })
        with patch("app.machine_metrics", return_value={"disk": 95, "memory": 10}), patch(
            "app._send_telegram_message"
        ) as send_message:
            start = 10_000_000.0
            self.assertTrue(app._check_machine_alerts(start))
            self.assertFalse(app._check_machine_alerts(start + 60))
            self.assertTrue(
                app._check_machine_alerts(start + app.ALERT_COOLDOWN_SECONDS)
            )
        self.assertEqual(send_message.call_count, 2)

    def _restore(self, saved_config, saved_alerts):
        with app.config_lock:
            app.config.clear()
            app.config.update(saved_config)
        with app.alert_last_sent_lock:
            app.alert_last_sent.clear()
            app.alert_last_sent.update(saved_alerts)


class WeatherTests(unittest.TestCase):
    def setUp(self):
        saved = dict(app.weather_cache)
        self.addCleanup(app.weather_cache.update, saved)
        with app.weather_cache_lock:
            app.weather_cache.update({
                "city": None, "fetched_at": 0.0, "data": None,
            })

    def test_weather_reads_geocoding_and_forecast(self):
        responses = iter([
            _json_response({
                "results": [{
                    "name": "Roma",
                    "country_code": "IT",
                    "latitude": 41.9,
                    "longitude": 12.5,
                }],
            }),
            _json_response({
                "current": {"temperature_2m": 18.4, "weather_code": 1},
                "daily": {
                    "temperature_2m_min": [11.2],
                    "temperature_2m_max": [19.6],
                },
            }),
        ])
        with patch("app.urlopen", side_effect=lambda *_a, **_k: next(responses)):
            data = app.fetch_weather("Roma")
        self.assertEqual(data["city"], "Roma")
        self.assertEqual(data["temperature"], 18)
        self.assertEqual(data["minimum"], 11)
        self.assertEqual(data["maximum"], 20)
        self.assertEqual(data["description"], "prevalentemente sereno")

    def test_weather_is_cached_between_requests(self):
        app.weather_cache.update({
            "city": "Roma",
            "fetched_at": 9_000_000.0,
            "data": {"city": "Roma", "temperature": 20},
        })
        with patch("app.urlopen", side_effect=AssertionError("rete non attesa")), patch(
            "app.time.time", return_value=9_000_001.0
        ):
            data = app.fetch_weather("Roma")
        self.assertEqual(data["temperature"], 20)

    def test_unknown_city_raises(self):
        with patch(
            "app.urlopen",
            side_effect=lambda *_a, **_k: _json_response({"results": []}),
        ):
            with self.assertRaises(RuntimeError):
                app.fetch_weather("Atlantide")

    def test_missing_city_raises(self):
        with self.assertRaises(RuntimeError):
            app.fetch_weather("  ")


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
