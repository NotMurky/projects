import importlib.util
import json
from pathlib import Path
import unittest

CLIENT_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "hermes_conversation"
    / "client.py"
)
SPEC = importlib.util.spec_from_file_location("hermes_conversation_client", CLIENT_PATH)
assert SPEC and SPEC.loader
CLIENT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT_MODULE)
HermesApiError = CLIENT_MODULE.HermesApiError
HermesClient = CLIENT_MODULE.HermesClient
add_luna_pacing = CLIENT_MODULE.add_luna_pacing
pick_filler = CLIENT_MODULE.pick_filler
post_luna_transcript = CLIENT_MODULE.post_luna_transcript
VOICE_SYSTEM_PROMPT = CLIENT_MODULE.VOICE_SYSTEM_PROMPT


class FakeResponse:
    def __init__(self, status=200, payload=None, sse_lines=None):
        self.status = status
        self._payload = payload
        self.content = _FakeContent(sse_lines or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


class _FakeContent:
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for line in self._lines:
            yield line if isinstance(line, bytes) else line.encode("utf-8")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class HermesClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_sends_authenticated_concise_voice_request(self):
        session = FakeSession(
            FakeResponse(payload={"choices": [{"message": {"content": "Done."}}]})
        )
        client = HermesClient(session, "http://<INTERNAL_IP_REDACTED>.12:8643", "secret", 90)

        result = await client.chat("Turn on the family lights", "voice-abc")

        self.assertEqual(result, "Done.")
        url, request = session.calls[0]
        self.assertEqual(url, "http://<INTERNAL_IP_REDACTED>.12:8643/v1/chat/completions")
        self.assertEqual(request["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(
            request["headers"]["X-Hermes-Session-Key"],
            "ha-luna-voice-v2-voice-abc",
        )
        self.assertEqual(request["json"]["model"], "hermes-agent")
        self.assertIs(request["json"]["stream"], False)
        self.assertEqual(
            request["json"]["messages"][-1]["content"],
            "This is the dedicated Luna voice lane activated by Hey Luna. "
            "Your identity in this lane is Luna, never Jarvis or Hermes. "
            "User request: Turn on the family lights",
        )
        self.assertIn(
            "Talk like a real", request["json"]["messages"][0]["content"]
        )

    async def test_chat_rejects_http_error_without_leaking_token(self):
        session = FakeSession(
            FakeResponse(status=503, payload={"error": "offline"})
        )
        client = HermesClient(session, "http://host", "top-secret", 90)

        with self.assertRaisesRegex(HermesApiError, "HTTP 503") as caught:
            await client.chat("hello", "abc")

        self.assertNotIn("top-secret", str(caught.exception))

    async def test_chat_rejects_malformed_success_response(self):
        session = FakeSession(FakeResponse(payload={"choices": []}))
        client = HermesClient(session, "http://host", "secret", 90)

        with self.assertRaisesRegex(HermesApiError, "malformed"):
            await client.chat("hello", "abc")

    def test_base_url_is_normalized(self):
        session = FakeSession(FakeResponse())
        client = HermesClient(session, "http://host///", "secret", 90)
        self.assertEqual(client.base_url, "http://host")

    def test_add_luna_pacing_adds_one_natural_pause_between_sentences(self):
        self.assertEqual(
            add_luna_pacing("I am Luna. How may I help?"),
            "I am Luna... How may I help?",
        )
        self.assertEqual(add_luna_pacing("Done."), "Done.")

    def test_voice_prompt_requires_one_short_conversational_answer(self):
        self.assertIn("Talk like a real person", VOICE_SYSTEM_PROMPT)
        self.assertIn("want the details?", VOICE_SYSTEM_PROMPT)
        self.assertIn("Never read lists", VOICE_SYSTEM_PROMPT)
        self.assertIn("contractions", VOICE_SYSTEM_PROMPT)

    async def test_posts_transcript_to_ha_only_relay(self):
        session = FakeSession(FakeResponse(status=201, payload={"status": "posted"}))
        posted = await post_luna_transcript(session, "turn on lights", "Done.")
        self.assertTrue(posted)
        url, request = session.calls[0]
        self.assertEqual(url, "http://<INTERNAL_IP_REDACTED>.12:8644/luna-transcript")
        self.assertEqual(
            request["json"],
            {"transcript": "turn on lights", "reply": "Done."},
        )

    def test_pick_filler_is_safe_stable_and_nonempty(self):
        safe_set = set(CLIENT_MODULE._FILLERS)
        first = pick_filler("what's the weather")
        self.assertTrue(first)
        self.assertIn(first, safe_set)
        self.assertEqual(first, pick_filler("what's the weather"))
        for probe in ("a", "turn on the lights", "how many people live in Paris"):
            self.assertIn(pick_filler(probe), safe_set)

    async def test_chat_stream_yields_chunks_with_auth_and_stream_flag(self):
        sse_lines = [
            'data: {"choices":[{"delta":{"role":"assistant"}}]}',
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" there"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":"."}}]}',
            "data: [DONE]",
            'data: {"choices":[{"delta":{"content":"ignored"}}]}',
        ]
        session = FakeSession(FakeResponse(sse_lines=sse_lines))
        client = HermesClient(session, "http://<INTERNAL_IP_REDACTED>.12:8643", "secret", 90)

        chunks = [c async for c in client.chat_stream("Say hi", "voice-xyz")]

        self.assertEqual("".join(chunks), "Hello there.")
        url, request = session.calls[0]
        self.assertEqual(url, "http://<INTERNAL_IP_REDACTED>.12:8643/v1/chat/completions")
        self.assertEqual(request["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(
            request["headers"]["X-Hermes-Session-Key"],
            "ha-luna-voice-v2-voice-xyz",
        )
        self.assertIs(request["json"]["stream"], True)

    async def test_chat_stream_raises_on_http_error(self):
        session = FakeSession(FakeResponse(status=502))
        client = HermesClient(session, "http://host", "top-secret", 90)

        with self.assertRaisesRegex(HermesApiError, "HTTP 502") as caught:
            [c async for c in client.chat_stream("hi", "abc")]

        self.assertNotIn("top-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
