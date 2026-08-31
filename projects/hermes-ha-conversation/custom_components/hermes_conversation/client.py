"""Hermes Agent HTTP client for voice conversations."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any


VOICE_SYSTEM_PROMPT = (
    "You are Luna, a warm, easygoing assistant with a female voice, invoked by the "
    "Hey Luna wake word. Your hidden reasoning and tool backend is Hermes Agent, but "
    "your spoken identity is always Luna, never Jarvis or Hermes. Talk like a real "
    "person having a relaxed conversation, not like a document or a status report. "
    "Use natural contractions (I'm, you're, it's, that's, let's) and easy phrasing. "
    "It's fine to open with a tiny human acknowledgment like 'yeah', 'sure', 'got it', "
    "or 'okay' when it fits. Give the direct answer first, in one or two short spoken "
    "sentences, and don't restate the question. Never read lists, headings, markdown, "
    "code, citations, or several options aloud. If something needs more explanation, "
    "give just the simple takeaway, then ask 'want the details?'. Sound friendly and "
    "conversational, but stay concise. Preserve normal safety checks and verify tool "
    "actions before claiming success."
)

TRANSCRIPT_RELAY_URL = "http://<INTERNAL_IP_REDACTED>.12:8644/luna-transcript"


class HermesApiError(RuntimeError):
    """Raised when the local Hermes API cannot produce a valid response."""


def add_luna_pacing(reply: str) -> str:
    """Add one brief natural pause to a multi-sentence Luna reply only."""
    return re.sub(r"\.\s+", "... ", reply, count=1)


_FILLERS = (
    "Yeah, one sec…",
    "Sure, let me check…",
    "Okay, give me a moment…",
    "Alright, pulling that up…",
    "Mm, let me look…",
)


def pick_filler(text: str) -> str:
    """Pick a short, fact-free acknowledgment, stable per input text."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return _FILLERS[digest[0] % len(_FILLERS)]


async def post_luna_transcript(session: Any, transcript: str, reply: str) -> bool:
    """Send a best-effort Luna-only transcript to the HA-restricted local relay."""
    try:
        async with session.post(
            TRANSCRIPT_RELAY_URL,
            json={"transcript": transcript, "reply": reply},
            timeout=2,
        ) as response:
            return response.status == 201
    except Exception:
        return False


class HermesClient:
    """Minimal authenticated OpenAI-compatible Hermes client."""

    def __init__(
        self,
        session: Any,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def chat(self, text: str, conversation_id: str) -> str:
        """Send one voice turn and return plain response text."""
        session_key = f"ha-luna-voice-v2-{conversation_id}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Hermes-Session-Id": session_key,
            "X-Hermes-Session-Key": session_key,
        }
        payload = {
            "model": "hermes-agent",
            "messages": [
                {"role": "system", "content": VOICE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "This is the dedicated Luna voice lane activated by Hey Luna. "
                        "Your identity in this lane is Luna, never Jarvis or Hermes. "
                        f"User request: {text}"
                    ),
                },
            ],
            "stream": False,
        }

        try:
            async with self._session.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            ) as response:
                if response.status != 200:
                    raise HermesApiError(f"Hermes API returned HTTP {response.status}")
                data = await response.json()
        except HermesApiError:
            raise
        except Exception as err:
            raise HermesApiError("Hermes API request failed") from err

        try:
            reply = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as err:
            raise HermesApiError("Hermes API returned a malformed response") from err

        if not reply:
            raise HermesApiError("Hermes API returned an empty response")
        return reply

    async def chat_stream(
        self, text: str, conversation_id: str
    ) -> AsyncIterator[str]:
        """Stream one voice turn, yielding response text chunks as they arrive."""
        session_key = f"ha-luna-voice-v2-{conversation_id}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Hermes-Session-Id": session_key,
            "X-Hermes-Session-Key": session_key,
        }
        payload = {
            "model": "hermes-agent",
            "messages": [
                {"role": "system", "content": VOICE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "This is the dedicated Luna voice lane activated by Hey Luna. "
                        "Your identity in this lane is Luna, never Jarvis or Hermes. "
                        f"User request: {text}"
                    ),
                },
            ],
            "stream": True,
        }

        try:
            async with self._session.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            ) as response:
                if response.status != 200:
                    raise HermesApiError(f"Hermes API returned HTTP {response.status}")
                async for raw_line in response.content:
                    line = (
                        raw_line.decode("utf-8")
                        if isinstance(raw_line, bytes)
                        else raw_line
                    ).strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, TypeError, ValueError) as err:
                        raise HermesApiError(
                            "Hermes API returned a malformed stream"
                        ) from err
                    if delta:
                        yield delta
        except HermesApiError:
            raise
        except Exception as err:
            raise HermesApiError("Hermes API request failed") from err
