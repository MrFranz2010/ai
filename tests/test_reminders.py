import datetime
import unittest

import reminders

NOW = datetime.datetime(
    2026, 11, 9, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1))
)


class ParseReminderTests(unittest.TestCase):
    def test_tomorrow_with_a_time(self):
        draft = reminders.parse_reminder(
            "Riunione con cliente domani alle 10", NOW
        )
        self.assertEqual(draft["title"], "Riunione con cliente")
        self.assertEqual(draft["starts_at"], "2026-11-10T10:00")
        self.assertEqual(draft["due_date"], "2026-11-10")
        self.assertEqual(draft["label"], "domani alle 10:00")

    def test_day_of_the_month_without_a_time(self):
        draft = reminders.parse_reminder("Scade la rata il 20", NOW)
        self.assertEqual(draft["title"], "Scade la rata")
        self.assertIsNone(draft["starts_at"])
        self.assertEqual(draft["due_date"], "2026-11-20")
        self.assertEqual(draft["label"], "20 novembre")

    def test_weekday_resolves_to_the_next_one(self):
        draft = reminders.parse_reminder("verifica venerdì alle 9", NOW)
        self.assertEqual(draft["starts_at"], "2026-11-13T09:00")
        self.assertEqual(draft["label"], "venerdì alle 09:00")

    def test_relative_hours_keep_the_clock_time(self):
        draft = reminders.parse_reminder("Chiama mamma tra 2 ore", NOW)
        self.assertEqual(draft["starts_at"], "2026-11-09T12:00")
        self.assertIn("tra 2 ore", draft["label"])

    def test_a_time_without_a_date_moves_to_tomorrow_when_past(self):
        draft = reminders.parse_reminder("sveglia alle 8", NOW)
        self.assertEqual(draft["starts_at"], "2026-11-10T08:00")
        self.assertEqual(draft["label"], "domani alle 08:00")

    def test_promemoria_prefix_is_not_part_of_the_title(self):
        draft = reminders.parse_reminder(
            "/promemoria: dentista dopodomani alle 15:30", NOW
        )
        self.assertEqual(draft["title"], "dentista")
        self.assertEqual(draft["starts_at"], "2026-11-11T15:30")

    def test_a_deadline_is_required(self):
        with self.assertRaises(ValueError) as raised:
            reminders.parse_reminder("Compito di storia", NOW)
        self.assertIn("Indica quando", str(raised.exception))

    def test_an_impossible_clock_time_is_rejected(self):
        with self.assertRaises(ValueError):
            reminders.parse_reminder("riunione domani alle 27", NOW)


class DueSoonRemindersTests(unittest.TestCase):
    def test_a_task_starting_soon_is_announced(self):
        soon = (NOW + datetime.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M")
        items = reminders.build_due_soon_reminders(
            NOW, [{"id": "abc123", "title": "Riunione", "starts_at": soon}]
        )
        self.assertEqual(len(items), 1)
        self.assertIn("Tra 25 minuti", items[0]["message"])
        self.assertIn("Riunione", items[0]["message"])
        self.assertEqual(items[0]["key"], f"soon:abc123:{soon}")

    def test_a_task_further_away_is_ignored(self):
        later = (NOW + datetime.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(
            reminders.build_due_soon_reminders(
                NOW, [{"id": "abc123", "title": "Riunione", "starts_at": later}]
            ),
            [],
        )

    def test_completed_and_untimed_tasks_are_ignored(self):
        soon = (NOW + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(
            reminders.build_due_soon_reminders(NOW, [
                {"id": "a1", "title": "Fatto", "starts_at": soon, "completed": True},
                {"id": "a2", "title": "Senza ora"},
            ]),
            [],
        )


if __name__ == "__main__":
    unittest.main()
