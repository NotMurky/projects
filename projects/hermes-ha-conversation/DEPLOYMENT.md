# Hermes dual-wake Home Assistant deployment

## Production routing

- **Hey Jarvis** → `Jarvis` Assist pipeline → `conversation.jarvis_qwen_3_5_4b`
- **Hey Luna** → `Luna` Assist pipeline → `conversation.luna` → HA-only proxy → Hermes Agent backend

Jarvis uses `en_GB-alan-medium`; Luna uses the bundled American female `en_US-amy-medium` voice with a brief Luna-only pause between multiple sentences. Luna keeps spoken answers to 22 words or fewer unless explicitly asked for detail, then asks before expanding. Both pipelines reuse local `stt.faster_whisper` and `tts.piper`. The ESPHome panel remains in **On device** wake-word mode and uses Home Assistant's native primary/secondary wake-word pipeline selectors.

## Network boundary

`hermes-ha-api-proxy.service` binds `<INTERNAL_IP_REDACTED>.12:8643` and accepts only source `<INTERNAL_IP_REDACTED>.212/32`, forwarding to the bearer-protected Hermes API on `127.0.0.1:8642`. No NPM, <FIREWALL_VENDOR_REDACTED>, public ingress, or VPS route was added.

## Installed Home Assistant files

`/config/custom_components/hermes_conversation/`

The config entry stores the bearer key in Home Assistant's config-entry storage. No credential is present in this repository.

## Rollback

1. Set `select.waveshare_p4_box_wake_word_2` to `no_wake_word`.
2. Set `select.waveshare_p4_box_assistant_2` to `preferred`.
3. Disable the `Hermes Agent Conversation` config entry in Home Assistant.
4. Stop and disable `hermes-ha-api-proxy.service` on Serpine.

The Jarvis primary pipeline is independent and remains available throughout rollback.

## Verification completed

- Seven local automated tests passed.
- HA → Hermes API authenticated relay returned HTTP 200.
- Home Assistant conversation endpoint returned `I'm Luna.` through `conversation.luna`, and Luna's Piper TTS media was generated successfully in 2.21 seconds.
- HA selector states persisted for Jarvis/Hey Jarvis and Luna/Hey Luna.
- Panel ESPHome API handshake succeeded at `<INTERNAL_IP_REDACTED>.72`.
- Physical wake routing and identity tests passed: `Hey Jarvis` activated the Jarvis/Qwen lane; `Hey Luna` activated the Luna/Hermes lane and identified itself as Luna.
- Luna transcript relay posted and was read back from Discord `#hermes-transcript`; it logs Luna text/replies only, not audio or Jarvis-only interactions.
