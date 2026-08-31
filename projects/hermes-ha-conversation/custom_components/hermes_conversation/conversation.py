"""Conversation platform backed by the local Hermes Agent API."""

from __future__ import annotations

import logging
from typing import Literal, override

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import (
    HermesApiError,
    HermesClient,
    pick_filler,
    post_luna_transcript,
)
from .const import CONF_API_KEY, CONF_BASE_URL, CONF_TIMEOUT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Hermes conversation entity."""
    async_add_entities([HermesConversationEntity(entry)])


class HermesConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """A Home Assistant conversation agent that invokes Hermes."""

    _attr_has_entity_name = True
    _attr_name = "Luna"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL
    _attr_supports_streaming = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity without exposing its bearer token."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    @override
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Support every language accepted by the selected Hermes model."""
        return MATCH_ALL

    @override
    async def async_added_to_hass(self) -> None:
        """Register this entity as a conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Unregister the conversation agent."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    @override
    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Stream a transcribed voice request to Hermes as spoken text."""
        session = async_get_clientsession(self.hass)
        client = HermesClient(
            session,
            self.entry.data[CONF_BASE_URL],
            self.entry.data[CONF_API_KEY],
            self.entry.data[CONF_TIMEOUT],
        )
        conversation_id = (
            user_input.conversation_id
            or user_input.satellite_id
            or user_input.device_id
            or "jarvis-p4-panel"
        )
        filler = pick_filler(user_input.text) + " "
        answer_parts: list[str] = []

        async def deltas():
            yield {"role": "assistant"}
            yield {"content": filler}
            try:
                async for chunk in client.chat_stream(
                    user_input.text, conversation_id
                ):
                    answer_parts.append(chunk)
                    yield {"content": chunk}
            except HermesApiError as err:
                _LOGGER.warning("Hermes voice stream failed: %s", err)
                if not answer_parts:
                    fallback = "Luna is unavailable right now. Jarvis is still available."
                    answer_parts.append(fallback)
                    yield {"content": fallback}

        async for _ in chat_log.async_add_delta_content_stream(
            user_input.agent_id, deltas()
        ):
            pass

        answer = "".join(answer_parts)
        self.hass.async_create_task(
            post_luna_transcript(session, user_input.text, answer),
            "luna_transcript_post",
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(filler + answer)
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id,
        )
