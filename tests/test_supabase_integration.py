import os
import unittest

from supabase_store import MISSING, SupabaseJSONStore


@unittest.skipUnless(
    os.environ.get("SUPABASE_TEST_URL")
    and os.environ.get("SUPABASE_TEST_SERVICE_ROLE_KEY")
    and os.environ.get("SUPABASE_TEST_ALLOW_WRITES") == "1",
    "Set SUPABASE_TEST_URL, SUPABASE_TEST_SERVICE_ROLE_KEY and "
    "SUPABASE_TEST_ALLOW_WRITES=1 to run the Supabase integration test.",
)
class SupabaseIntegrationTests(unittest.TestCase):
    """Exercise a real app_state upsert against a disposable test project."""

    def test_memories_round_trip_and_restore_the_previous_row(self):
        from supabase import create_client

        client = create_client(
            os.environ["SUPABASE_TEST_URL"],
            os.environ["SUPABASE_TEST_SERVICE_ROLE_KEY"],
        )
        store = SupabaseJSONStore(client)
        previous = store.load("memories.json")
        test_memories = ["Test di integrazione Supabase."]
        try:
            store.save("memories.json", test_memories)
            self.assertEqual(store.load("memories.json"), test_memories)
        finally:
            if previous is MISSING:
                client.table("app_state").delete().eq(
                    "key", "memories.json"
                ).execute()
            else:
                store.save("memories.json", previous)


if __name__ == "__main__":
    unittest.main()
