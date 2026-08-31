# Prominence updater contract

## Upload flow
- GUI accepts only a ZIP uploaded by the administrator.
- Uploads are stored in `staging/` and inspected before any extraction.
- The GUI derives the candidate pack version from the archive name/manifest and records it as the available version.

## Immutable server content
The updater must never overwrite or delete:
- `importantmods/`
- `fabric.jar`
- `server.properties`
- `variables.txt`
- `world/`, `worldnopregen/`, and all player/world data
- named custom mods: YetTwo, DarkTimer, FabricProxy, CrossStitch, FabricProxyYML
- user-configured protected paths

## Apply operation
1. Verify Crafty reports zero real players. The normal button refuses otherwise.
2. Put the proxy/backend in maintenance mode.
3. Create a timestamped backup and staged rollback manifest.
4. Apply only files permitted by the exclusion plan.
5. Set the server-list MOTD to `Prominence II Hasturian Era v<installed-version>`.
6. Restart through Crafty, wait for health/ready state, then clear maintenance mode.
7. Record result, installed version, backup location, and changed/excluded paths.

## Force update
- Force is a separate, red, confirmation-gated action.
- It bypasses the zero-player gate only; it does not bypass archive inspection, backups, immutable paths, maintenance mode, validation, or health checks.
