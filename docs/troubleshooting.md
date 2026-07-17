# Troubleshooting

**Connection refused:** start LM Studio's local server (Developer tab or `lms server start`), then run `doctor --world PATH`. Confirm `base_url` is reachable.

**Model not found:** set `[model].name` to an exact ID from LM Studio `GET /v1/models`; `doctor --require-model --world PATH` verifies it.

**Invalid model JSON or event:** the engine requests LM Studio text mode but explicitly requires one JSON object. It discards safe no-op events (for example, a move to an actor's current location), and otherwise makes one repair request containing the original response, validation error, and current state. It commits nothing if that repair is still invalid. Use `/debug last-error` and keep prompts/rules clear.

**LM Studio grammar-complexity error:** the engine deliberately uses text mode rather than strict JSON Schema, because its nested event schema can exceed LM Studio grammar limits. The prompt requires JSON, and the application validates every JSON field and event before saving a turn.

**LM Studio HTTP error:** the displayed error includes up to 8 KiB of LM Studio's response body, with the configured API token redacted. It can identify an unsupported request field, context limit, or server-side model problem.

**FTS5 unavailable:** this is a warning, not a failure. Lore retrieval automatically uses deterministic fallback search.

**Stale or corrupt state cache:** replay is authoritative. Reopen/play the session; the game service rebuilds a cache whose head does not match. If SQLite itself is damaged, restore a `.local-adventure` backup.

**Invalid world references:** run `validate-world --world PATH`; errors name authored paths/fields. Check IDs, entity references, scenario player/location selections, and item holders.

**Context budget overflow:** increase compatible `[context]` budgets or shorten `WORLD.md`, rules, state-heavy content, skills, lore, or player input. Mandatory system/state/input content must fit.

**Logs:** the default log location is `.local-adventure/logs/local-adventure.log`. It avoids full prompts, narration, lore, and raw model output at INFO level.
