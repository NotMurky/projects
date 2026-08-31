# Luna transcript relay

## Purpose

Posts **Luna-only** voice interaction transcripts to Discord channel `#hermes-transcript`.

Each entry contains the Home Assistant transcription and Luna's plain reply. It does not log audio, bearer tokens, tool call internals, or Jarvis-only requests.

## Data path

```text
Hey Luna → ESP32 P4 → Home Assistant STT → Luna/Hermes backend
       → local HA custom integration → <INTERNAL_IP_REDACTED>.12:8644 relay
       → Discord #hermes-transcript
```

## Security boundary

- Relay binds only `<INTERNAL_IP_REDACTED>.12:8644`.
- It rejects every source except Home Assistant `<INTERNAL_IP_REDACTED>.212`.
- The Discord bot token remains in `/home/<USERNAME_REDACTED>/.hermes/.env` and is read at runtime only.
- Transcript text is mention-sanitized, capped to Discord's 2,000-character limit, and never treated as commands.

## Service

`luna-transcript-relay.service` is enabled as a systemd user service on Serpine.

## Rollback

```bash
systemctl --user disable --now luna-transcript-relay.service
```

Then remove the `post_luna_transcript(...)` task from the HA custom integration and restart Home Assistant. Jarvis and Luna voice functions remain otherwise unaffected.
