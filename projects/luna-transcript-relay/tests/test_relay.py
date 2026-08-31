import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).parents[1] / "luna_transcript_relay.py"
SPEC = importlib.util.spec_from_file_location("luna_transcript_relay", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TranscriptFormattingTests(unittest.TestCase):
    def test_formats_transcript_and_reply_without_pinging_everyone(self):
        output = MODULE.format_discord_message(
            "turn on @everyone lights",
            "Done, @here.",
        )
        self.assertIn("Luna voice transcript", output)
        self.assertIn("@\u200beveryone", output)
        self.assertIn("@\u200bhere", output)
        self.assertNotIn("@everyone", output)
        self.assertNotIn("@here", output)

    def test_truncates_long_fields_to_fit_discord_message_limit(self):
        output = MODULE.format_discord_message("u" * 5000, "r" * 5000)
        self.assertLessEqual(len(output), 2000)
        self.assertIn("…", output)

    def test_only_home_assistant_source_is_allowed(self):
        self.assertTrue(MODULE.is_allowed_source("<INTERNAL_IP_REDACTED>.212"))
        self.assertFalse(MODULE.is_allowed_source("<INTERNAL_IP_REDACTED>.213"))


if __name__ == "__main__":
    unittest.main()
