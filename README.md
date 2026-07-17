# Local Adventure Engine

Local Adventure Engine is a local, open-source, Git-friendly interactive-fiction engine. You write worlds in TOML and Markdown, play from a terminal, and keep authoritative state and append-only history in local SQLite. The model proposes prose and typed events; the engine validates, reduces, and persists them.

## Privacy and prerequisites

Python 3.12+ and a locally running LM Studio server are required for model play. Tests, world validation, session creation, replay, branching, and exports are offline. The engine has no telemetry or cloud account. Prompts and game content are sent only to the model endpoint in `world.toml`; a non-loopback endpoint deserves particular care. Model licenses are separate from this engine's Apache-2.0 license.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

In LM Studio, start the local server, then set `model.name` in `worlds/ember_hollow/world.toml` to the exact identifier reported by `/v1/models`. The engine requests text mode with an explicit JSON-output contract, then independently validates the model's proposed narration and events before saving a turn.

## Run the sample world

```bash
python -m local_adventure doctor --world worlds/ember_hollow
python -m local_adventure validate-world --world worlds/ember_hollow
python -m local_adventure play --world worlds/ember_hollow --name "First Journey"
```

Useful commands include `sessions list`, `sessions create`, `reindex`, `play --session`, and `export --session ID --format markdown|json --output PATH`. In play, type `/help` for state inspection, undo, branches, checkpoints, reload, context diagnostics, and `/export markdown PATH` or `/export json PATH`.

Runtime data is under `.local-adventure/` by default (or `LOCAL_ADVENTURE_HOME`): the SQLite database, exports you choose to place there, and logs. Back up that directory to retain sessions.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall local_adventure tests
python -m local_adventure doctor
```

See [architecture](docs/architecture.md), [data model](docs/data-model.md), [world authoring](docs/world-authoring.md), [privacy and security](docs/privacy-and-security.md), [troubleshooting](docs/troubleshooting.md), and [implementation status](docs/implementation-status.md).
