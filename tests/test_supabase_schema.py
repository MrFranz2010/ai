import re
import unittest
from pathlib import Path

from supabase_store import STATE_FILES


class SupabaseSchemaTests(unittest.TestCase):
    def test_every_state_file_is_allowed_by_the_key_constraint(self):
        root = Path(__file__).resolve().parents[1]
        # The schema plus the newest migration that redefines the constraint:
        # older migrations are history and must not be rewritten.
        newest = sorted((root / "supabase" / "migrations").glob("*.sql"))[-1]
        for relative_path in (
            "supabase/schema.sql",
            str(newest.relative_to(root)),
        ):
            with self.subTest(path=relative_path):
                sql = (root / relative_path).read_text(encoding="utf-8")
                match = re.search(
                    r"app_state_key_check check \((.*?)\);", sql, re.DOTALL
                )
                self.assertIsNotNone(match)
                allowed = set(re.findall(r"'([^']+)'", match.group(1)))
                self.assertEqual(allowed, set(STATE_FILES))


if __name__ == "__main__":
    unittest.main()
