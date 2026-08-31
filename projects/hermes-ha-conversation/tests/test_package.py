import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1] / "custom_components" / "hermes_conversation"


class IntegrationPackageTests(unittest.TestCase):
    def test_manifest_is_local_config_flow_integration(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], "hermes_conversation")
        self.assertIs(manifest["config_flow"], True)
        self.assertIn("conversation", manifest["dependencies"])
        self.assertEqual(manifest["iot_class"], "local_polling")

    def test_strings_never_embed_credentials(self):
        for path in (ROOT / "strings.json", ROOT / "translations" / "en.json"):
            content = path.read_text()
            self.assertNotIn("API_SERVER_KEY=", content)
            self.assertIn("api_key", content)

    def test_conversation_platform_has_safe_failure_reply(self):
        content = (ROOT / "conversation.py").read_text()
        self.assertIn("Luna is unavailable right now", content)
        self.assertIn("_attr_supports_streaming = True", content)
        self.assertIn("async_add_delta_content_stream", content)
        self.assertIn("pick_filler", content)
        self.assertIn("ConversationEntityFeature.CONTROL", content)
        self.assertIn("post_luna_transcript", content)
        self.assertNotIn("self._api_key", content)


if __name__ == "__main__":
    unittest.main()
