# Repository instructions

## Purpose

This repository implements Local Adventure Engine, a local, open-source,
Git-friendly AI interactive fiction engine.

## Authoritative plan

Read `IMPLEMENTATION_PLAN.md` before making architectural or cross-cutting
changes. Implement its milestones in order. Do not implement deferred roadmap
features before the required milestones pass.

## Build and test

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall local_adventure tests
python -m local_adventure doctor
```

Default tests must be offline and must not require LM Studio.

## Dependency policy

Pydantic is the only required Python runtime dependency. Use the Python
standard library for the CLI, HTTP, SQLite, TOML, logging, and tests.

Do not add dependencies without explicit user approval and a documented reason.

## Architecture boundaries

- `content` loads and validates authored files.
- `state` owns typed state, event validation, and pure reducers.
- `storage` owns SQLite and migrations.
- `lore` owns indexing and retrieval.
- `context` owns deterministic context assembly.
- `llm` owns model backend protocols and LM Studio transport.
- `app` orchestrates use cases.
- `cli` handles presentation and commands only.

The model proposes narration and typed events. Application code owns truth,
validation, persistence, permissions, and context selection.

## Security

Never execute code, shell commands, SQL, or filesystem operations from
model-generated text. Never import Python from world directories. Reject world
paths and symlinks that escape the selected world root.

Do not send data anywhere except the configured model endpoint.

## Data and migrations

Use parameterized SQL. Enable foreign keys. Do not edit released migrations;
add a new migration. Preserve append-only turns and events. Undo moves a session
head and does not delete history.

## Testing

Every behavior change needs tests. Use standard-library `unittest`. Use a
scripted model backend and temporary databases. Tests must be deterministic and
must not call a live model.

## Readability

Prefer direct, explicit code over clever abstractions. Add type hints to public
functions. Keep errors actionable. Update documentation whenever user-facing
behavior, commands, formats, or security assumptions change.

## Completion

After each milestone, run all tests and update
`docs/implementation-status.md`.
