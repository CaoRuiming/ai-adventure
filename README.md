# Local Adventure Engine

Local Adventure Engine is a local, open-source, Git-friendly interactive
fiction engine. It is designed to keep world content, prompts, rules, and
runtime state understandable and inspectable on the user's machine.

Milestone 1 provides the repository skeleton and a small command-line entry
point. The authored sample world and gameplay features are added in later
milestones in the order defined by `IMPLEMENTATION_PLAN.md`.

## Privacy

The intended runtime is local. The completed engine will persist sessions in a
local SQLite database and will send prompts only to the configured local model
endpoint. It will not require a cloud account or telemetry service. Model
licenses are separate from the engine's Apache-2.0 license.

## Prerequisites and installation

Python 3.12 or newer is required. Create an environment and install the sole
runtime dependency from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

LM Studio is the initial model-runtime assumption. In a later milestone,
configure `model.name` in the sample world's `world.toml` to the exact local
model ID exposed by LM Studio's local server.

## Current commands

```bash
python -m local_adventure --help
python -m local_adventure doctor
```

`doctor` is currently a Milestone 1 placeholder. World validation, sample-world
play, session management, exports, and the remaining commands are implemented
by later milestones.

## Development

The test suite is intentionally offline and uses Python's standard-library
`unittest` runner:

```bash
python -m unittest discover -s tests -v
python -m compileall local_adventure tests
```

See the [implementation plan](IMPLEMENTATION_PLAN.md) for the authoritative
milestone sequence. Detailed architecture, data-model, authoring, privacy,
troubleshooting, and implementation-status documentation is maintained under
[`docs/`](docs/).
