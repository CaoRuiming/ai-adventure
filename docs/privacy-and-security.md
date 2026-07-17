# Privacy and security

Runtime data remains local in `.local-adventure/` or `LOCAL_ADVENTURE_HOME`: SQLite state/history, optional exports, and logs. Back up this directory before changing machines or deleting it. By default the engine stores request hashes but not full prompts; it stores model responses, parsed proposals, and validation errors according to world audit settings. Exports deliberately omit audit data, system prompts, and raw responses.

Only the configured LM Studio HTTP endpoint receives game data. Loopback is the default; non-loopback endpoints receive a validation/doctor warning because prompts and lore leave the machine. Use LM Studio authentication when appropriate; the named token environment variable is never logged or persisted.

World files are data, not code. The loader rejects traversal and symlinks outside the world root, does not import world Python, bounds text files, and never executes model-generated text. SQLite uses parameterized queries and foreign keys. The model proposes narration/events only; application validators, reducers, permissions, persistence, and context selection remain authoritative.

Prompt skills are non-executable prose. This release has no executable plugins, shell tools, network skills, MCP, cloud synchronization, or telemetry. The practical threat model assumes trusted local users and world authors; inspect worlds before playing and protect filesystem/database backups like any local game save.
