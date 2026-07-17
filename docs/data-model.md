# Data model

Authored entities are actors, locations, items, quests, scenarios, lore documents, and prompt skills. `world.toml` supplies model, context, gameplay, and audit settings. IDs are stable lowercase identifiers matching `^[a-z][a-z0-9_]{1,63}$`.

Runtime `GameState` contains authored entities in canonical JSON plus mutable locations, item holders, quest statuses, flags, stats, and relationships. Supported events are `move_actor`, `transfer_item`, `set_flag`, `adjust_stat`, `adjust_relationship`, and `set_quest_status`. Events are validated semantically before deterministic reduction; entities are never created or removed by model output.

SQLite stores `worlds`, `sessions`, `turns`, `state_events`, `state_cache`, `model_calls`, `named_checkpoints`, `summaries`, and lore tables. A cache is disposable: replay follows the parent chain from a session's initial state. Branches can share ancestors. Markdown and JSON exports include only the current ancestry, current replayed state, and that session's checkpoints—not audit requests or raw responses.
