# Local Adventure Engine — Implementation Plan

> **Working project name:** `local-adventure`  
> **Primary implementation language:** Python 3.12 or newer  
> **Primary local model runtime:** LM Studio  
> **Initial interface:** synchronous terminal application  
> **License target:** Apache-2.0  
> **Plan status:** implementation-ready  
> **Audience:** Codex CLI or another coding agent operating with limited context and moderate reasoning ability

---

## 0. Instructions to the implementing agent

This document is the authoritative implementation specification for the first usable version of Local Adventure Engine.

Follow these rules while implementing it:

1. Work through the milestones in order.
2. Do not begin a milestone until all acceptance criteria for the previous milestone pass.
3. Do not introduce a new runtime dependency unless the user explicitly approves it.
4. Prefer readable, explicit code over metaprogramming, framework conventions, or abstraction for its own sake.
5. Keep all model-provider-specific behavior behind the model backend interface.
6. Keep all database access behind repository classes.
7. Keep state mutation inside the reducer and validator modules.
8. Never let model-generated text directly execute Python, shell commands, SQL, or filesystem operations.
9. Do not call a remote service. The only permitted network destination in the initial implementation is the configured local LM Studio HTTP endpoint.
10. Do not silently repair malformed world content. Report actionable validation errors containing the file path and field name.
11. Every behavior change must include or update tests.
12. After each milestone:
    - run the required test commands;
    - update `docs/implementation-status.md`;
    - update relevant documentation;
    - make one focused Git commit if the working environment permits commits.
13. If this plan conflicts with an existing root `AGENTS.md`, stop and report the conflict rather than guessing.
14. When a requirement appears ambiguous, choose the behavior explicitly stated in the “Required behavior” or “Acceptance criteria” sections. Do not invent a broader feature.
15. Do not implement optional roadmap items until the required milestones are complete.

### Required implementation commands

All commands must work from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m unittest discover -s tests -v
python -m compileall local_adventure tests
python -m local_adventure doctor
```

On Windows PowerShell, the activation command may be replaced with:

```powershell
.venv\Scripts\Activate.ps1
```

---

## 1. Product definition

Local Adventure Engine is a fully local, open-source, Git-friendly interactive fiction engine inspired by AI-driven narrative games.

The engine must:

- accept free-form player actions in a terminal;
- use a locally hosted language model to produce narration;
- maintain authoritative structured world state separately from prose;
- retrieve relevant lore from human-readable Markdown files;
- persist all sessions locally in SQLite;
- autosave every committed turn;
- support undo and session branching;
- expose enough diagnostic information to understand why a response was produced;
- remain usable without a cloud account, telemetry service, hosted database, or proprietary API;
- keep world content, prompts, rules, and skill instructions readable and editable in an ordinary text editor;
- remain model-agnostic behind a small backend interface.

The first release is a single-player, single-process terminal program. It is not a general autonomous agent platform.

---

## 2. Goals and non-goals

### 2.1 Required goals

The first usable release must provide:

1. A sample world stored entirely in Git-trackable text files.
2. World and scenario validation before play begins.
3. A terminal game loop.
4. A local LM Studio backend using structured JSON output.
5. An in-memory typed representation of authoritative state.
6. SQLite persistence with schema migrations.
7. An append-only turn and state-event history.
8. Deterministic state reducers.
9. Lore indexing and retrieval using SQLite FTS5, with a basic fallback search.
10. Context construction with deterministic character budgets.
11. One repair attempt when model output is invalid.
12. Automatic saves.
13. Undo by moving the session head to its parent turn.
14. Branching a new session from the current turn.
15. Human-readable session export to Markdown and JSON.
16. Unit and integration tests that do not require LM Studio.
17. A `doctor` command that checks the local environment.
18. Privacy-conscious audit logs with configurable prompt retention.
19. Clear authoring documentation.

### 2.2 Explicit non-goals for the initial release

Do **not** implement these before all required milestones are complete:

- a browser UI;
- Textual, Rich, Typer, Click, or another CLI framework;
- multiplayer;
- cloud synchronization;
- remote model providers;
- authentication or user accounts;
- image generation;
- speech input or output;
- vector databases;
- embedding-based retrieval;
- a general-purpose agent loop;
- arbitrary Python plugins;
- arbitrary shell-command skills;
- network-enabled skills;
- MCP integration;
- procedural map rendering;
- combat systems beyond generic state changes;
- a graphical world editor;
- model fine-tuning;
- asynchronous Python;
- background workers;
- database servers;
- Docker as a requirement;
- automatic Git commits during play.

These can be added later behind stable interfaces.

---

## 3. Fixed architectural decisions

These decisions are mandatory unless the user explicitly changes the plan.

| Area | Decision | Reason |
|---|---|---|
| Language | Python 3.12+ | Strong standard library, local-model ecosystem, readable implementation |
| Runtime dependencies | Pydantic 2.x only | Reliable validation and JSON Schema generation are core functionality |
| CLI | `argparse`, `input()`, and standard output | Avoid a UI framework while retaining portability |
| Database | SQLite through `sqlite3` | Local, transactional, auditable, no server |
| Full-text search | SQLite FTS5 | Included in most SQLite builds and sufficient for the first release |
| Authored configuration | TOML | Human-readable and parsed by standard-library `tomllib` |
| Lore and prompts | Markdown, with optional TOML front matter | Easy to edit and Git-diff |
| Runtime payloads | JSON | Stable interchange format and native SQLite storage |
| Model runtime | LM Studio OpenAI-compatible REST API | Already installed for the primary user, local operation, portable API shape, and JSON-schema-constrained output |
| HTTP client | `urllib.request` | Avoid another dependency |
| Concurrency | Single process, synchronous | Simplifies consistency and debugging |
| State model | Initial state plus deterministic events | Enables replay, undo, branching, and audits |
| Save behavior | Autosave each valid turn | Avoid data loss and eliminate a confusing manual save model |
| Context budgeting | Character counts, not tokenizer counts | No tokenizer dependency and deterministic behavior |
| Extension model | Prompt skills first; executable plugins later | Safe, readable, and easy to customize |
| World instructions file | `WORLD.md`, not nested `AGENTS.md` | Avoid mixing game instructions with coding-agent instructions |
| Repository instructions | Root `AGENTS.md` | Codex automatically uses repository guidance |
| Testing | Standard-library `unittest` | No test framework dependency |
| Packaging | Run with `python -m local_adventure` | Avoid requiring a build/install step for development |

### 3.1 Why Pydantic is the sole required Python dependency

Structured model output is the security and consistency boundary of the engine. Pydantic must be used for:

- validating world configuration;
- validating entity files;
- validating model responses;
- expressing discriminated event unions;
- generating the JSON Schema sent to LM Studio;
- generating clear validation errors.

Do not replace this with an incomplete custom general-purpose schema validator.

### 3.2 Why LM Studio is the initial backend

LM Studio is the initial backend because the primary user already has it
installed and running. Its OpenAI-compatible Chat Completions endpoint supports
JSON Schema structured output while keeping the adapter portable.

The engine must not depend on the LM Studio GUI:

- users may start the server from LM Studio's Developer tab;
- users may start it with `lms server start`;
- headless deployments may use llmster;
- the engine communicates only through HTTP.

LM Studio-specific model management remains outside the engine. This minimizes
scope and avoids coupling game persistence to model loading behavior.

### 3.3 Why the model is not authoritative

The language model may propose narration and state events. It may not:

- write directly to the database;
- alter files;
- decide whether an event is valid;
- mutate state outside the reducer;
- fabricate entity IDs and have them silently accepted;
- execute commands;
- determine the current session head;
- choose which private audit data is stored.

Application code is authoritative.

---

## 4. Dependency policy

Create `requirements.txt` containing exactly:

```text
pydantic>=2.10,<3
```

Do not add other runtime dependencies.

The initial implementation must use these standard-library modules where appropriate:

- `argparse`
- `dataclasses`
- `datetime`
- `hashlib`
- `json`
- `logging`
- `pathlib`
- `re`
- `sqlite3`
- `textwrap`
- `tomllib`
- `typing`
- `urllib.error`
- `urllib.request`
- `uuid`
- `unittest`
- `unittest.mock`

An optional formatter or linter may be documented, but it must not be required by tests, runtime, or setup.

---

## 5. Repository layout

Create this layout. Avoid adding new top-level directories without a clear requirement.

```text
local-adventure/
├── AGENTS.md
├── CHANGELOG.md
├── LICENSE
├── README.md
├── IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── local_adventure/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── errors.py
│   ├── paths.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── commands.py
│   │   ├── game_service.py
│   │   └── turn_service.py
│   ├── content/
│   │   ├── __init__.py
│   │   ├── frontmatter.py
│   │   ├── loader.py
│   │   ├── models.py
│   │   └── validator.py
│   ├── context/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── budget.py
│   │   └── formatter.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── backend.py
│   │   ├── lm_studio.py
│   │   ├── schemas.py
│   │   └── scripted.py
│   ├── lore/
│   │   ├── __init__.py
│   │   ├── indexer.py
│   │   ├── query.py
│   │   └── models.py
│   ├── state/
│   │   ├── __init__.py
│   │   ├── events.py
│   │   ├── models.py
│   │   ├── reducer.py
│   │   └── validator.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   ├── repositories.py
│   │   └── schema/
│   │       ├── 0001_initial.sql
│   │       └── 0002_lore_fts.sql
│   ├── export/
│   │   ├── __init__.py
│   │   └── session_exporter.py
│   └── util/
│       ├── __init__.py
│       ├── clocks.py
│       ├── hashing.py
│       └── json_tools.py
├── worlds/
│   └── ember_hollow/
│       ├── world.toml
│       ├── WORLD.md
│       ├── prompts/
│       │   ├── narrator.md
│       │   └── repair.md
│       ├── rules/
│       │   ├── narrative.md
│       │   └── state.md
│       ├── scenarios/
│       │   └── opening.toml
│       ├── entities/
│       │   ├── actors/
│       │   │   ├── player.toml
│       │   │   └── mark.toml
│       │   ├── items/
│       │   │   └── brass_key.toml
│       │   ├── locations/
│       │   │   ├── observatory.toml
│       │   │   └── west_gate.toml
│       │   └── quests/
│       │       └── west_gate.toml
│       ├── lore/
│       │   ├── setting.md
│       │   ├── factions/
│       │   │   └── iron_league.md
│       │   └── locations/
│       │       ├── observatory.md
│       │       └── west_gate.md
│       └── skills/
│           └── cautious_npc/
│               ├── skill.toml
│               └── SKILL.md
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── model_responses/
│   │   └── worlds/
│   ├── test_cli.py
│   ├── test_content_loader.py
│   ├── test_context_builder.py
│   ├── test_database.py
│   ├── test_frontmatter.py
│   ├── test_lore_search.py
│   ├── test_lm_studio_backend.py
│   ├── test_reducer.py
│   ├── test_replay.py
│   ├── test_session_branching.py
│   └── test_turn_service.py
└── docs/
    ├── architecture.md
    ├── data-model.md
    ├── implementation-status.md
    ├── privacy-and-security.md
    ├── troubleshooting.md
    └── world-authoring.md
```

### 5.1 Runtime directory

Runtime files must not be stored inside tracked world directories.

Default runtime root:

```text
.local-adventure/
├── local-adventure.sqlite3
├── exports/
└── logs/
```

Resolve the path in this order:

1. `LOCAL_ADVENTURE_HOME` environment variable, if set;
2. `<repository-root>/.local-adventure` when running from the source repository;
3. a user data directory can be added in a later packaging milestone.

For the first release, rule 2 is sufficient as the default.

Add `.local-adventure/` to `.gitignore`.

---

## 6. Root configuration files

### 6.1 `pyproject.toml`

Use `pyproject.toml` only for project metadata and tool-independent Python settings. Do not require installation to run the program.

Minimum content:

```toml
[project]
name = "local-adventure"
version = "0.1.0"
description = "A local, open-source, Git-friendly AI interactive fiction engine"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.10,<3",
]
license = { text = "Apache-2.0" }

[tool.local-adventure]
schema-version = 1
```

Do not add a build backend in the initial release unless packaging is explicitly requested.

### 6.2 `.gitignore`

Include:

```gitignore
.venv/
__pycache__/
*.py[cod]
.local-adventure/
.coverage
.DS_Store
config.local.toml
.env
```

Do not require a `.env` loader. Environment variables are supplied by the shell or service manager.

### 6.3 `AGENTS.md`

Create the root `AGENTS.md` from Appendix A of this plan. It is for implementation agents, not the game narrator.

---

## 7. Authored world format

Each world is a directory under `worlds/` or another path supplied by the user.

All IDs must match:

```regex
^[a-z][a-z0-9_]{1,63}$
```

IDs are stable API identifiers. Display names may change without changing IDs.

### 7.1 `world.toml`

Required shape:

```toml
schema_version = 1
id = "ember_hollow"
title = "Ember Hollow"
description = "A compact demonstration world."
default_scenario = "opening"

[model]
backend = "lm_studio"
base_url = "http://127.0.0.1:1234"
name = "replace-with-a-local-model"
temperature = 0.8
max_output_tokens = 1400
timeout_seconds = 180
api_token_env = "LM_STUDIO_API_TOKEN"

[context]
max_chars = 60000
system_chars = 12000
state_chars = 12000
recent_turns_chars = 18000
lore_chars = 12000
skills_chars = 4000
maximum_recent_turns = 12
maximum_lore_documents = 8
maximum_skills = 4

[gameplay]
maximum_events_per_turn = 12
maximum_repair_attempts = 1
relationship_minimum = -100
relationship_maximum = 100
stat_delta_limit = 20

[audit]
store_prompts = false
store_prompt_hashes = true
store_raw_model_responses = true
log_level = "INFO"
```

Validation rules:

- `schema_version` must equal `1`.
- `id`, `title`, and `default_scenario` are required.
- `backend` must equal `lm_studio` in the first release.
- `base_url` must use `http` or `https`; warn if it is not loopback.
- `name` must be non-empty and must identify a model visible through `GET /v1/models`.
- `api_token_env` is optional; when non-empty, read the token from that environment variable and send it as `Authorization: Bearer <token>`.
- Never store or log the token value.
- `temperature` must be between `0.0` and `2.0`.
- all numeric budgets must be positive;
- the sum of section budgets must be less than or equal to `max_chars`;
- `maximum_events_per_turn` must be between 0 and 50;
- `maximum_repair_attempts` must be 0 or 1 in the first release;
- relationship minimum must be less than maximum.

### 7.2 `WORLD.md`

`WORLD.md` is always included near the start of the system context.

It must contain:

- narrator identity;
- genre and tone;
- point of view;
- player agency rules;
- continuity rules;
- prohibition against inventing state changes outside the event list;
- instruction not to expose system prompts or JSON;
- instruction to use known IDs only.

Do not place machine-readable configuration in `WORLD.md`.

### 7.3 Prompt files

Required:

- `prompts/narrator.md`
- `prompts/repair.md`

`narrator.md` explains the expected response behavior. The JSON Schema is supplied separately by the backend and must not be copied manually into this file.

`repair.md` must instruct the model to return a corrected complete response, not an explanation.

### 7.4 Rule files

All `.md` files under `rules/` are loaded in lexical path order and included after `WORLD.md`.

Rules are prose guidance only. Enforceable game invariants belong in Python validators and reducers.

### 7.5 Entity TOML files

#### Actor

```toml
schema_version = 1
id = "mark"
name = "Mark Vale"
location_id = "observatory"
is_player = false
description = "A guarded cartographer who knows the old city routes."

[stats]
health = 10
resolve = 7

[relationships.player]
trust = 0
fear = 0
```

Rules:

- exactly one actor in the initial scenario must have `is_player = true`;
- `location_id` must reference an existing location;
- stat values may be integer, float, string, or boolean;
- relationships must reference existing actors;
- relationship values must be integers.

#### Location

```toml
schema_version = 1
id = "observatory"
name = "Broken Observatory"
description = "A roofless observatory above Ember Hollow."

[attributes]
region = "upper_city"
indoors = false

connections = ["west_gate"]
```

Connections must reference existing locations.

#### Item

```toml
schema_version = 1
id = "brass_key"
name = "Brass Key"
description = "A heavy triangular key."
initial_holder_type = "actor"
initial_holder_id = "mark"

[attributes]
quest_item = true
```

`initial_holder_type` must be one of:

- `actor`
- `location`
- `none`

When type is `none`, `initial_holder_id` must be omitted or empty.

#### Quest

```toml
schema_version = 1
id = "west_gate"
name = "The West Gate"
description = "Learn what lies beyond the sealed west gate."
initial_status = "inactive"
allowed_statuses = ["inactive", "active", "completed", "failed"]
```

### 7.6 Scenario file

```toml
schema_version = 1
id = "opening"
title = "Ash Above the Observatory"
opening_narration = """
Ash drifts through the broken dome as Mark studies the sealed brass mechanism.
"""
player_actor_id = "player"
starting_location_id = "observatory"
active_actor_ids = ["player", "mark"]
active_quest_ids = []

[initial_flags]
met_mark = true
west_gate_open = false
```

The scenario selects initial entities but does not duplicate their definitions.

### 7.7 Lore Markdown with TOML front matter

Format:

```markdown
+++
schema_version = 1
id = "observatory_lore"
title = "Broken Observatory"
kind = "location"
entity_ids = ["observatory"]
aliases = ["old observatory", "star tower"]
tags = ["upper_city", "astronomy", "ruins"]
priority = 0.8
+++

# Broken Observatory

The observatory predates the Iron League...
```

Front matter rules:

- opening delimiter must be `+++` on the first line;
- closing delimiter must be another line containing only `+++`;
- front matter is parsed with `tomllib`;
- body begins after the closing delimiter;
- files without front matter are valid, but derive:
  - `id` from the relative path;
  - `title` from the first Markdown H1 or filename;
  - `priority = 0.5`;
  - empty lists for aliases, tags, and entity IDs;
- reject files larger than 1 MiB;
- normalize line endings to `\n`;
- preserve the body exactly apart from line-ending normalization.

### 7.8 Prompt skills

Prompt skills are conditional instruction fragments. They do not execute code.

`skill.toml`:

```toml
schema_version = 1
id = "cautious_npc"
name = "Cautious NPC Behavior"
description = "Guidance for guarded NPCs who reveal information gradually."
priority = 0.6
always_include = false
trigger_terms = ["cautious", "guarded", "interrogate", "trust"]
entity_ids = ["mark"]
maximum_chars = 3000
```

`SKILL.md` contains prose instructions.

Selection rules:

1. include all `always_include = true` skills;
2. add skills whose `entity_ids` intersect active scene entities;
3. add skills whose trigger terms occur case-insensitively in player input;
4. sort by:
   - `always_include` descending;
   - number of matched entity IDs descending;
   - number of matched trigger terms descending;
   - priority descending;
   - ID ascending;
5. include at most `maximum_skills`;
6. truncate each skill at a paragraph boundary to its own `maximum_chars`;
7. enforce the total skills character budget.

---

## 8. Runtime state model

Use Pydantic models. State must be serializable to canonical JSON.

### 8.1 Canonical game state

Required conceptual shape:

```json
{
  "schema_version": 1,
  "world_id": "ember_hollow",
  "scenario_id": "opening",
  "player_actor_id": "player",
  "actors": {
    "player": {
      "id": "player",
      "name": "Traveler",
      "location_id": "observatory",
      "is_player": true,
      "description": "The player character.",
      "stats": {
        "health": 10
      },
      "relationships": {
        "mark": {
          "trust": 0
        }
      }
    }
  },
  "locations": {},
  "items": {
    "brass_key": {
      "id": "brass_key",
      "name": "Brass Key",
      "description": "A heavy triangular key.",
      "holder_type": "actor",
      "holder_id": "mark",
      "attributes": {
        "quest_item": true
      }
    }
  },
  "quests": {
    "west_gate": {
      "id": "west_gate",
      "name": "The West Gate",
      "description": "...",
      "status": "inactive",
      "allowed_statuses": [
        "inactive",
        "active",
        "completed",
        "failed"
      ]
    }
  },
  "flags": {
    "met_mark": true
  }
}
```

### 8.2 State invariants

Validate after every applied event:

- all actor locations exist;
- the player actor exists and has `is_player = true`;
- item holder references are valid;
- quest statuses are allowed by the quest;
- relationship targets exist;
- relationship numeric values are within configured bounds;
- dictionaries are keyed by the same ID stored inside each value;
- IDs never change during a session;
- no event removes an authored entity;
- no model event creates a new entity in the first release.

---

## 9. State event model

Use a Pydantic discriminated union with the discriminator field `type`.

### 9.1 Supported event types

#### `move_actor`

```json
{
  "type": "move_actor",
  "actor_id": "player",
  "location_id": "west_gate",
  "reason": "The player walks to the gate."
}
```

Validation:

- actor exists;
- destination exists;
- either the destination is connected to the actor’s current location or the event sets `allow_unconnected = true`;
- `allow_unconnected` defaults to `false`;
- model-generated events may never set `allow_unconnected = true`;
- internal commands may use it for scenario administration.

#### `transfer_item`

```json
{
  "type": "transfer_item",
  "item_id": "brass_key",
  "holder_type": "actor",
  "holder_id": "player",
  "reason": "Mark gives the key to the player."
}
```

Validation:

- item exists;
- holder type is `actor`, `location`, or `none`;
- referenced holder exists;
- `holder_id` is absent when holder type is `none`.

#### `set_flag`

```json
{
  "type": "set_flag",
  "key": "west_gate_open",
  "value": true,
  "reason": "The mechanism unlocks."
}
```

Validation:

- key matches the ID regex;
- value must be JSON-compatible scalar data: string, integer, float, boolean, or null;
- nested dictionaries and lists are not accepted in the first release.

#### `adjust_stat`

```json
{
  "type": "adjust_stat",
  "actor_id": "player",
  "stat": "health",
  "delta": -2,
  "reason": "Falling debris strikes the player."
}
```

Validation:

- actor exists;
- stat already exists;
- current stat is numeric but not boolean;
- delta is within the configured absolute limit;
- the resulting value must be finite.

#### `adjust_relationship`

```json
{
  "type": "adjust_relationship",
  "source_actor_id": "mark",
  "target_actor_id": "player",
  "dimension": "trust",
  "delta": 2,
  "reason": "The player keeps Mark's confidence."
}
```

Validation:

- both actors exist;
- dimension matches the ID regex;
- delta is within the configured absolute limit;
- missing dimensions begin at 0;
- result is clamped to configured relationship bounds;
- the stored committed event must record both requested delta and applied delta if clamping occurs.

#### `set_quest_status`

```json
{
  "type": "set_quest_status",
  "quest_id": "west_gate",
  "status": "active",
  "reason": "Mark reveals the gate's significance."
}
```

Validation:

- quest exists;
- status is in its allowed status list.

### 9.2 Event conventions

Every event must include a concise `reason`. It is audit metadata and is not shown to the player by default.

The model may emit zero events for a purely conversational or observational turn.

The model may not emit more than `maximum_events_per_turn`.

The reducer must:

- accept a state and one validated event;
- return a new state object;
- never mutate its input object;
- contain no database or model calls;
- be deterministic;
- raise a typed `StateInvariantError` when a postcondition fails.

---

## 10. Model response schema

Define `TurnProposal` in `local_adventure/llm/schemas.py`.

Required shape:

```json
{
  "narration": "Mark hesitates, then presses the brass key into your hand.",
  "events": [
    {
      "type": "transfer_item",
      "item_id": "brass_key",
      "holder_type": "actor",
      "holder_id": "player",
      "reason": "Mark voluntarily gives the key to the player."
    },
    {
      "type": "adjust_relationship",
      "source_actor_id": "mark",
      "target_actor_id": "player",
      "dimension": "trust",
      "delta": 2,
      "reason": "The player earned Mark's trust."
    }
  ]
}
```

Validation requirements:

- `narration` must contain non-whitespace text;
- narration maximum is 16,000 characters;
- `events` defaults to an empty list;
- unknown fields are forbidden at every schema level;
- event count is checked against world configuration after Pydantic parsing;
- no chain-of-thought or analysis field exists;
- no Markdown code fence may surround the JSON;
- the LM Studio backend requests `response_format.type = "text"` and the prompt requires one JSON object; application-side Pydantic and event validation enforce the turn-proposal schema. This avoids LM Studio grammar-size limits and unsupported `json_object` mode in some compatibility servers.

---

## 11. Database design

SQLite is the durable runtime store.

### 11.1 Connection behavior

Every connection must execute:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

Use row factories that permit named-column access.

Open one connection per application service operation or one well-owned connection per CLI process. Do not use a module-global connection.

### 11.2 Migration system

Create a `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
```

Migration filenames use:

```text
NNNN_description.sql
```

Migration rules:

- apply in numeric order;
- wrap each migration in a transaction;
- record it only after successful execution;
- fail if two files have the same version;
- fail if a previously applied migration file is missing;
- applying migrations twice must be safe;
- do not edit an applied migration after release; add another migration.

### 11.3 Initial schema

`0001_initial.sql` must define at least:

```sql
CREATE TABLE worlds (
    world_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    world_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    head_turn_id TEXT,
    initial_state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

CREATE TABLE turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_turn_id TEXT,
    turn_number INTEGER NOT NULL,
    player_input TEXT NOT NULL,
    narration TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('committed', 'failed')),
    model_call_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (parent_turn_id) REFERENCES turns(turn_id)
);

CREATE INDEX turns_session_parent_idx
ON turns(session_id, parent_turn_id);

CREATE TABLE state_events (
    event_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (turn_id, sequence_number),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);

CREATE TABLE state_cache (
    session_id TEXT PRIMARY KEY,
    head_turn_id TEXT,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE model_calls (
    model_call_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_turn_id TEXT,
    attempt_number INTEGER NOT NULL,
    backend TEXT NOT NULL,
    model_name TEXT NOT NULL,
    request_json TEXT,
    request_hash TEXT NOT NULL,
    response_json TEXT,
    response_hash TEXT,
    parsed_response_json TEXT,
    validation_errors_json TEXT,
    prompt_eval_count INTEGER,
    eval_count INTEGER,
    duration_ms INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE named_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
);

CREATE TABLE summaries (
    summary_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    through_turn_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('scene', 'campaign')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (through_turn_id) REFERENCES turns(turn_id)
);
```

### 11.4 Lore schema

`0002_lore_fts.sql` must create a regular table first:

```sql
CREATE TABLE lore_documents (
    document_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    modified_ns INTEGER NOT NULL,
    indexed_at TEXT NOT NULL,
    UNIQUE (world_id, relative_path),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);
```

Attempt to create:

```sql
CREATE VIRTUAL TABLE lore_documents_fts USING fts5(
    document_id UNINDEXED,
    world_id UNINDEXED,
    title,
    aliases,
    tags,
    body
);
```

If FTS5 creation fails because the SQLite build lacks FTS5:

- record the capability as unavailable;
- do not fail database initialization;
- use the fallback retrieval algorithm;
- display a warning in `doctor`;
- ensure tests cover both modes.

### 11.5 Canonical JSON

Implement a helper that serializes with:

```python
json.dumps(
    value,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

Use canonical JSON for:

- hashing;
- stored state;
- stored event payloads;
- request and response hashes;
- deterministic tests.

Pretty JSON is permitted only in user-facing export files.

---

## 12. Session history, undo, and branching

### 12.1 Turn graph

Each committed turn points to its parent. The first turn has `parent_turn_id = NULL`.

A session’s current position is `sessions.head_turn_id`.

A session may share historical turns with another session after branching. Therefore, traversal must follow `parent_turn_id`, not assume that every ancestor has the same `session_id`.

### 12.2 Creating a session

When creating a session:

1. load and validate the world;
2. build initial state from the selected scenario;
3. upsert the world record and content hash;
4. create a session with no head turn;
5. create a matching state cache containing the initial state;
6. index lore;
7. return the session ID and opening narration.

Do not create a synthetic model turn for the scenario opening.

### 12.3 Committing a turn

A valid turn commit must be atomic:

1. read the expected parent head;
2. create a new turn ID;
3. begin an immediate transaction;
4. verify the session head still equals the expected parent;
5. insert the turn;
6. insert ordered events;
7. write the new state cache;
8. update the session head and timestamp;
9. insert or update the successful model call audit row;
10. commit.

If the head changed, raise `ConcurrentSessionUpdateError`. Do not retry automatically.

### 12.4 Undo

`/undo` behavior:

- if there is no head turn, print “Already at the beginning of the session.”
- otherwise:
  - set the session head to the current turn’s parent;
  - rebuild state by replaying from initial state to the new head;
  - replace state cache;
  - preserve all old turns and events;
  - print the new turn number.

Undo is an administrative action, not a model turn.

### 12.5 Branch

`/branch NAME` behavior:

- validate the name is non-empty and at most 80 characters;
- create a new session:
  - same world;
  - same scenario;
  - same initial state;
  - head equal to the current session head;
  - state cache copied from the current state;
- switch the CLI to the new session;
- never modify the original session.

### 12.6 Checkpoints

`/checkpoint NAME` records the current head in `named_checkpoints`.

`/restore NAME` moves the current session head to the checkpoint and rebuilds the cache. It does not delete later turns.

---

## 13. Lore indexing and retrieval

### 13.1 Indexing

Index all `.md` files under the world’s `lore/` directory.

For each file:

1. reject paths escaping the world directory;
2. enforce the 1 MiB size limit;
3. parse front matter;
4. compute SHA-256 of normalized content;
5. compare with existing `content_hash`;
6. insert or update only changed documents;
7. remove database documents whose files no longer exist;
8. keep FTS rows synchronized in the same transaction.

Expose:

```bash
python -m local_adventure reindex --world worlds/ember_hollow
```

Also reindex automatically when a session is created and when `/reload` is run.

### 13.2 Query construction

Build retrieval terms from:

- the exact player input;
- current location ID and display name;
- active actor IDs and display names;
- active quest IDs and display names;
- aliases of exact entity mentions.

Do not ask the model to generate the retrieval query in the first release.

### 13.3 Candidate scoring

When FTS5 is available:

1. query up to 30 FTS candidates using sanitized terms joined by `OR`;
2. calculate a Python-side score:

```text
score =
    exact_entity_match * 100
  + current_location_match * 80
  + active_actor_match * 60
  + active_quest_match * 50
  + exact_alias_match * 40
  + tag_match_count * 10
  + priority * 10
  + normalized_fts_score * 20
```

3. sort by score descending, then document ID ascending;
4. select at most the configured maximum.

Do not pass raw player input directly as FTS query syntax. Tokenize it into Unicode word sequences, quote tokens, discard one-character tokens except digits, and cap at 40 terms.

### 13.4 Fallback scoring

Without FTS5:

- lowercase and tokenize query and documents;
- score title matches higher than body matches;
- apply the same entity, alias, tag, and priority bonuses;
- scan only the current world’s lore;
- this can be linear because initial worlds are small.

### 13.5 Lore formatting

Each selected document is formatted:

```text
--- LORE: <title> [<relative_path>] ---
<body>
--- END LORE ---
```

Truncate at paragraph boundaries. Always include the title and source path.

---

## 14. Context construction

### 14.1 Deterministic section order

Construct context in this exact order:

1. `WORLD.md`
2. narrator prompt
3. rule files
4. output behavior reminder
5. current state
6. selected prompt skills
7. selected lore
8. latest campaign or scene summary, if present
9. recent turns
10. player input

Use separate chat messages:

- one `system` message containing sections 1–4;
- one `user` message containing sections 5–10.

Do not represent old narration as prior assistant chat messages in the first release. Format it inside the user context so that context truncation is centrally controlled.

### 14.2 State projection

Do not send the entire internal state blindly.

Send a stable, readable projection containing:

- current player actor;
- current location and connections;
- actors currently at the same location;
- items held by those actors or located at the current location;
- active quests;
- all flags;
- all relationships involving active actors;
- explicit lists of valid entity IDs that may be referenced by events.

Use pretty JSON for the projection.

### 14.3 Recent turns

Traverse parent links from the current head.

Include newest turns until either:

- `maximum_recent_turns` is reached; or
- the recent-turn character budget would be exceeded.

Render in chronological order:

```text
TURN 4
PLAYER:
I ask Mark why he has the key.

NARRATOR:
Mark closes his hand around the key...

STATE EVENTS:
- adjust_relationship: mark -> player trust -1
```

If one turn is larger than the remaining budget, truncate narration at a paragraph boundary but preserve the player input and event summaries.

### 14.4 Character budgets

Use exact Python string lengths after formatting.

Rules:

- never exceed `max_chars`;
- never truncate the output schema because it is not placed in prompt text;
- system content is highest priority;
- state is second priority;
- player input is never truncated unless it exceeds 16,000 characters, in which case reject it before model invocation;
- drop the lowest-scoring lore document before truncating a higher-scoring one;
- drop the lowest-ranked skill before truncating a higher-ranked one;
- remove oldest recent turns first;
- include explicit notices such as `[Older history omitted due to context budget.]`;
- fail with `ContextBudgetError` if mandatory system content, state, and player input cannot fit.

### 14.5 Context inspection

`/context` prints:

- total characters;
- characters by section;
- included lore paths and scores;
- included skill IDs;
- included turn numbers;
- omitted counts;
- request SHA-256;
- whether raw prompts are being stored.

By default it must not print the full prompt.

`/context full` prints the complete assembled messages after an explicit confirmation prompt:

```text
This may expose private game content and model instructions. Print it? [y/N]
```

---

## 15. Model backend interface

Define an abstract protocol or ABC in `llm/backend.py`.

Required request model:

```python
class ModelRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    api_token: str | None = None
```

Required response model:

```python
class ModelResponse(BaseModel):
    content: str
    raw_response: dict[str, object]
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    duration_ms: int | None = None
```

Required backend method:

```python
class ModelBackend(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse:
        ...
```

### 15.1 LM Studio backend

Use LM Studio's OpenAI-compatible Chat Completions endpoint rather than its
stateful native chat endpoint. The compatibility endpoint keeps each request
self-contained, maps naturally to `ModelRequest`, and makes a future
OpenAI-compatible local backend straightforward.

POST to:

```text
<base_url>/v1/chat/completions
```

Request body:

```json
{
  "model": "<configured model>",
  "messages": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": "..."
    }
  ],
  "response_format": {
    "type": "text"
  },
  "temperature": 0.8,
  "max_tokens": 1400,
  "stream": false
}
```

`response_format.type` must be `text`. The prompt requires one JSON object;
the application validates it against `TurnProposal` and validates each proposed
event before persisting a turn.

Backend rules:

- set `Content-Type: application/json`;
- when an API token is configured, set `Authorization: Bearer <token>`;
- never log, persist, hash, or include the API token in `request_json`;
- use the configured timeout;
- read at most 32 MiB from the response;
- include a bounded (8 KiB), API-token-redacted HTTP error body in transport errors when LM Studio provides one;
- decode UTF-8;
- require HTTP 200;
- require a top-level JSON object;
- require `choices` to be a non-empty list;
- require `choices[0].message.content` to be a string;
- parse token counts from `usage.prompt_tokens` and
  `usage.completion_tokens` when present;
- measure wall-clock duration locally with `time.monotonic_ns()`;
- never log the raw prompt at INFO level;
- convert connection failures into `ModelConnectionError`;
- convert timeout into `ModelTimeoutError`;
- convert malformed or incomplete responses into `ModelProtocolError`;
- include safe troubleshooting context without private prompt content.

The model identifier is supplied by `world.toml`. The engine must not download,
load, unload, or reconfigure models automatically in the first release. The
user manages models through the LM Studio GUI or `lms` CLI.

For diagnostics and model validation, GET:

```text
<base_url>/v1/models
```

A model is available when an item in the returned `data` list has an `id`
exactly equal to the configured model name. LM Studio may expose downloaded
models through this endpoint when Just-in-Time loading is enabled, so the engine
must not assume that every listed model is already resident in memory.

Do not depend on the `lmstudio-python` or OpenAI Python SDK. Use
`urllib.request` directly.

### 15.2 Scripted backend

Implement a deterministic backend for tests.

It receives a queue of response strings or exceptions and returns them in order. It must record received `ModelRequest` objects for assertions.

Default tests must never call LM Studio.

---

## 16. Turn lifecycle

Implement the complete lifecycle in `TurnService`.

### 16.1 Input validation

Before any model call:

- strip trailing newline but preserve other whitespace;
- reject empty or whitespace-only input;
- reject input over 16,000 characters;
- commands beginning with `/` are handled by the CLI and never sent as player actions;
- ensure session and world still exist;
- ensure the world on disk still has the same ID as the session;
- automatically reindex changed lore, but do not automatically reload changed entity definitions into an existing session.

### 16.2 Build request

1. load current state cache;
2. verify cache head matches session head;
3. if mismatched, rebuild by replay;
4. retrieve lore;
5. select skills;
6. build context;
7. construct `ModelRequest`;
8. calculate canonical request hash;
9. record an audit call entry.

### 16.3 Parse proposal

1. extract `message.content`;
2. parse with `json.loads`;
3. validate with `TurnProposal.model_validate`;
4. validate event count;
5. validate all event semantics against current state;
6. apply events in memory in order;
7. validate invariants after every event;
8. retain the final candidate state.

### 16.4 Repair behavior

On JSON, Pydantic, semantic, or invariant failure:

- if repair attempts remain, make exactly one repair request;
- use temperature `0.2`;
- include:
  - the original player action;
  - the original invalid response;
  - a concise numbered list of validation errors;
  - the same state projection;
  - the repair prompt;
- use the same response schema;
- do not include Python tracebacks;
- cap validation error text at 8,000 characters;
- record the repair as attempt number 2.

If repair fails:

- commit no turn and no state events;
- mark model call records with validation errors;
- print a concise user-facing error;
- allow `/debug last-error` to show more detail;
- leave session head unchanged.

### 16.5 Commit

Commit only after the complete proposal and final state are valid.

Display narration only after commit succeeds. This prevents the terminal from showing a story event that was not persisted.

### 16.6 Summary updates

Do not call a second model for summaries in the first implementation milestone.

Implement a deterministic placeholder summary system in a later required milestone:

- every 10 committed turns, create a scene summary from truncated concatenated turn text;
- label it clearly as an extractive summary;
- retain no more than 12,000 characters;
- a model-generated summary backend may replace this later.

This keeps the first release reliable without doubling model cost.

---

## 17. Terminal interface

Use `argparse` for top-level commands.

### 17.1 Top-level commands

Required:

```text
python -m local_adventure doctor
python -m local_adventure validate-world --world PATH
python -m local_adventure reindex --world PATH
python -m local_adventure sessions list
python -m local_adventure sessions create --world PATH [--scenario ID] [--name NAME]
python -m local_adventure play --session SESSION_ID
python -m local_adventure play --world PATH [--scenario ID] [--name NAME]
python -m local_adventure export --session SESSION_ID --format markdown --output PATH
python -m local_adventure export --session SESSION_ID --format json --output PATH
```

When `play --world` is used without a session, create and enter a new session.

### 17.2 Game loop output

At startup:

```text
Ember Hollow
Session: First Journey
Model: <configured model>
Type /help for commands.

Ash drifts through the broken dome...
```

Prompt:

```text
> 
```

Narration is printed as plain wrapped text. Use `textwrap.fill` only when output is attached to an interactive terminal. Preserve paragraphs.

Do not use ANSI colors in the first release.

### 17.3 In-game commands

Required commands:

| Command | Behavior |
|---|---|
| `/help` | Show commands |
| `/quit` | Exit cleanly |
| `/state` | Show readable state projection |
| `/where` | Show current location and connections |
| `/inventory` | Show items held by player |
| `/history [N]` | Show latest N turns; default 5, max 50 |
| `/context` | Show context diagnostics |
| `/context full` | Confirm, then show full most recent context |
| `/undo` | Move head to parent turn |
| `/branch NAME` | Create and switch to branch session |
| `/checkpoint NAME` | Name current head |
| `/restore NAME` | Restore named head |
| `/sessions` | List sessions for current world |
| `/reload` | Reload prose rules, prompts, lore, and prompt skills |
| `/debug on` | Enable additional terminal diagnostics for current process |
| `/debug off` | Disable diagnostics |
| `/debug last-error` | Show last model or validation error |
| `/export markdown PATH` | Export current session |
| `/export json PATH` | Export current session |

Unknown commands must print:

```text
Unknown command. Type /help for available commands.
```

### 17.4 Reload semantics

`/reload` reloads:

- `WORLD.md`;
- prompt files;
- rule Markdown;
- lore Markdown;
- prompt skills;
- world configuration fields that affect model and context behavior.

It does **not** replace current actors, locations, items, quests, scenario, or initial state. Print a warning if entity files changed since session creation.

---

## 18. Exports

### 18.1 Markdown export

Required structure:

````markdown
# Session Name

- World: Ember Hollow
- Scenario: Ash Above the Observatory
- Session ID: ...
- Exported: ...
- Current turn: 7

## Opening

...

## Turn 1

**Player**

...

**Narrator**

...

**State changes**

- Mark transferred Brass Key to Player.
- Mark's trust toward Player changed by +2.

## Current State

```json
...
```
````

Escape content safely so player text cannot break the document structure unexpectedly.

### 18.2 JSON export

Required top-level keys:

```json
{
  "export_schema_version": 1,
  "session": {},
  "world": {},
  "opening_narration": "...",
  "turns": [],
  "current_state": {},
  "checkpoints": []
}
```

Use pretty, sorted UTF-8 JSON.

Exports must not contain raw prompts, hidden system instructions, or raw model responses unless a future explicit `--include-audit` option is added.

---

## 19. Audit, privacy, and security

### 19.1 Default privacy behavior

By default:

- store request hash;
- do not store full prompt/request;
- store raw model response;
- store parsed proposal;
- store validation errors;
- do not transmit telemetry;
- do not read environment variables other than documented configuration variables, including the optional LM Studio API-token variable named by `world.toml`;
- do not scan files outside the selected world and runtime directories;
- do not load Python from a world directory;
- do not follow symlinks that resolve outside the world directory.

### 19.2 Prompt storage

If `audit.store_prompts = true`, store canonical request JSON in `model_calls.request_json`.

If false, store `NULL`.

Always store `request_hash` when configured.

### 19.3 File safety

All world-relative paths must be resolved and checked with `Path.resolve()`.

Reject:

- lore symlinks that escape the world root;
- export paths that point to a directory;
- files larger than configured limits;
- world IDs that do not match the directory’s loaded identity;
- NUL bytes in text files.

### 19.4 Local endpoint warning

`doctor` and world validation must warn when the LM Studio `base_url` is not loopback.

Do not block a non-loopback URL, because a user may run LM Studio or llmster on a trusted LAN machine. The warning must state that game prompts and content will be sent to that endpoint and recommend enabling LM Studio API authentication.

### 19.5 Logging

Use Python `logging`.

Default log file:

```text
.local-adventure/logs/local-adventure.log
```

Do not log at INFO:

- full player input;
- full narration;
- prompts;
- world lore body;
- raw model output.

Permitted INFO fields:

- session ID;
- turn ID;
- model name;
- request hash;
- response hash;
- durations;
- counts;
- validation success or failure;
- file paths relative to world root.

DEBUG may contain more information, but full prompts still require `store_prompts = true`.

---

## 20. Error model

Create typed exceptions in `errors.py`.

Required hierarchy:

```text
LocalAdventureError
├── ConfigurationError
├── WorldValidationError
├── ContentParseError
├── DatabaseError
├── MigrationError
├── LoreIndexError
├── ContextBudgetError
├── ModelError
│   ├── ModelConnectionError
│   ├── ModelTimeoutError
│   └── ModelProtocolError
├── ProposalValidationError
├── StateEventValidationError
├── StateInvariantError
├── SessionNotFoundError
├── CheckpointNotFoundError
└── ConcurrentSessionUpdateError
```

CLI behavior:

- expected user/configuration errors: one concise message, exit code 2;
- model connectivity errors: exit code 3 outside play mode;
- database errors: exit code 4;
- unexpected errors: exit code 1 and log traceback;
- `--debug` prints traceback for unexpected errors.

Do not print raw exception repr by default.

---

## 21. Documentation requirements

Create and maintain:

### `README.md`

Must include:

- project purpose;
- privacy statement;
- prerequisites;
- LM Studio server setup assumption;
- installation;
- setting a model name;
- running the sample world;
- key commands;
- test command;
- links to detailed docs;
- statement that model licenses are separate from the engine license.

### `docs/architecture.md`

Must document:

- component boundaries;
- turn sequence;
- state authority;
- event graph;
- model backend boundary;
- why initial features are intentionally limited.

### `docs/data-model.md`

Must document:

- authored entities;
- runtime state;
- event types;
- SQLite tables;
- replay and branching.

### `docs/world-authoring.md`

Must document:

- complete directory layout;
- every TOML field;
- lore front matter;
- prompt skills;
- IDs and references;
- validation command;
- a tutorial for copying and modifying the sample world.

### `docs/privacy-and-security.md`

Must document:

- local data locations;
- prompt storage setting;
- model endpoint implications;
- plugin limitations;
- threat model;
- backup guidance.

### `docs/troubleshooting.md`

Must include:

- LM Studio connection refused;
- model not found;
- model returns invalid JSON;
- FTS5 unavailable;
- corrupt or stale state cache;
- invalid world references;
- context budget overflow;
- where logs are stored.

### `docs/implementation-status.md`

Use a checklist keyed to the milestones below. Include the date and most recent passing test command.

---

## 22. Test strategy

Use `unittest`. Tests must be deterministic and offline.

### 22.1 General rules

- each bug fix gets a regression test;
- use temporary directories and temporary SQLite files;
- do not share mutable databases between tests;
- use a fixed clock helper in tests;
- use stable UUID injection where exact IDs are asserted;
- do not depend on test execution order;
- do not call a real LM Studio service;
- keep fixture worlds intentionally small;
- verify user-facing errors, not just exception types.

### 22.2 Required unit tests

#### Front matter

- valid TOML front matter;
- no front matter;
- missing closing delimiter;
- invalid TOML;
- oversized file;
- H1 title derivation;
- path-derived ID normalization.

#### Content loading

- valid sample world;
- duplicate IDs;
- invalid ID format;
- missing references;
- two player actors;
- no player actor;
- invalid item holder;
- invalid quest status;
- scenario references missing actor;
- connection to missing location.

#### Reducer

At least one test for each event type:

- successful event;
- missing referenced entity;
- invalid delta;
- clamped relationship;
- input state is not mutated;
- deterministic repeated application;
- invariant failure.

#### Database and migrations

- empty database migration;
- repeated migration;
- missing migration file detection;
- foreign keys enabled;
- WAL requested;
- session creation;
- turn commit transaction;
- failed optimistic concurrency check.

#### Replay

- replay zero turns equals initial state;
- replay several turns equals state cache;
- undo rebuild equals expected state;
- branch shares history and diverges correctly.

#### Lore retrieval

- exact entity match outranks body-only match;
- current location bonus;
- alias match;
- stable tie ordering;
- FTS token sanitization;
- fallback mode;
- deleted file removed from index.

#### Context builder

- fixed section order;
- no budget overflow;
- oldest turns removed first;
- low-score lore removed first;
- player input preserved;
- mandatory content overflow raises error;
- context diagnostics match actual lengths.

#### LM Studio backend

Mock `urllib.request.urlopen` and test:

- correct URL;
- correct JSON body;
- text mode requested with `response_format.type = "text"`;
- `stream` false;
- optional authorization header;
- token absent from stored request and logs;
- model-list response parsing;
- successful response parsing;
- HTTP error;
- timeout;
- malformed JSON;
- missing message content;
- oversized response.

#### Turn service

- valid proposal commits;
- zero-event turn commits;
- invalid JSON triggers repair;
- invalid event triggers repair;
- repair success commits only repaired output;
- repair failure leaves head unchanged;
- commit failure does not print narration;
- model call metadata stored according to audit config.

#### CLI

Use `subprocess` or direct main-function invocation:

- `--help`;
- `doctor`;
- valid world validation;
- invalid world validation exit code;
- sessions list;
- export;
- unknown in-game command;
- clean EOF exit.

### 22.3 Integration smoke test

Create a scripted two-turn session:

1. player asks Mark for the key;
2. scripted model transfers key and increases trust;
3. player walks to west gate;
4. scripted model moves player;
5. assert exported state and transcript;
6. undo;
7. branch;
8. assert original and branch heads differ after a new branch turn.

---

## 23. Milestone plan

Each milestone ends with all tests passing.

### Milestone 1 — Repository skeleton and environment

Create:

- repository files;
- package directories;
- root `AGENTS.md`;
- `requirements.txt`;
- `pyproject.toml`;
- license;
- initial README;
- implementation status document;
- basic CLI with `--help` and placeholder `doctor`.

Required behavior:

- `python -m local_adventure --help` works;
- unsupported Python versions produce a clear error;
- no import side effects create files.

Acceptance:

```bash
python -m unittest discover -s tests -v
python -m compileall local_adventure tests
python -m local_adventure --help
```

Commit suggestion:

```text
chore: initialize local adventure project
```

### Milestone 2 — Content models and world validation

Implement:

- Pydantic authored-content models;
- TOML loading;
- Markdown front matter;
- secure path handling;
- cross-reference validation;
- sample world;
- `validate-world`.

Required behavior:

```bash
python -m local_adventure validate-world --world worlds/ember_hollow
```

prints a success summary including counts of actors, locations, items, quests, lore files, and skills.

Acceptance:

- all content-loader and front-matter tests pass;
- sample world is valid;
- deliberately broken fixture worlds fail with exact path context.

Commit suggestion:

```text
feat: add human-readable world format and validation
```

### Milestone 3 — State, events, and reducer

Implement:

- canonical state models;
- event union;
- semantic event validator;
- pure reducer;
- initial-state builder from scenario;
- readable state projection.

Acceptance:

- all reducer tests pass;
- state serialization is deterministic;
- replaying the same events twice from the same initial state produces equal output;
- input state objects remain unchanged.

Commit suggestion:

```text
feat: add authoritative event-driven world state
```

### Milestone 4 — SQLite persistence, replay, undo, and branch

Implement:

- connection setup;
- migration runner;
- schema;
- repositories;
- state cache;
- replay;
- session service;
- undo;
- branching;
- checkpoints.

Acceptance:

- migration and database tests pass;
- replay always matches cache in integration tests;
- branch can share an ancestor turn owned by another session;
- no turn or event is deleted by undo.

Commit suggestion:

```text
feat: persist branching sessions in sqlite
```

### Milestone 5 — Lore indexing and deterministic context

Implement:

- lore tables;
- FTS5 capability detection;
- fallback search;
- indexing;
- candidate scoring;
- prompt-skill selection;
- context budgeting;
- context diagnostics.

Acceptance:

- lore and context tests pass in FTS and fallback modes;
- assembled context never exceeds configured maximum;
- retrieval order is deterministic;
- no model is needed.

Commit suggestion:

```text
feat: add local lore retrieval and context assembly
```

### Milestone 6 — LM Studio backend and structured proposals

Implement:

- model backend models;
- LM Studio OpenAI-compatible `/v1/chat/completions` adapter;
- optional bearer-token authentication through a named environment variable;
- `/v1/models` capability and configured-model checks;
- response-size limit;
- Pydantic response schema;
- scripted backend;
- model audit records;
- `doctor` LM Studio checks.

`doctor` checks:

1. Python version;
2. runtime directory writable;
3. SQLite version;
4. FTS5 availability;
5. database migrations;
6. world sample validation;
7. LM Studio endpoint reachability;
8. configured model visibility when a world is supplied;
9. presence of the configured token environment variable when authentication is configured.

Do not require LM Studio for `doctor` to complete. Report failures individually
and return nonzero only for hard local engine failures. An unavailable LM Studio
service is a warning unless `--require-model` is supplied.

Acceptance:

- all backend tests pass;
- no default test makes a network call;
- request uses generated JSON Schema under `response_format`;
- successful parsing reads `choices[0].message.content`;
- model discovery uses `/v1/models`;
- bearer authentication is tested without exposing the token;
- sensitive content is not stored when prompt audit is disabled.

Commit suggestion:

```text
feat: add local lm studio structured-output backend
```

### Milestone 7 — Complete turn service and repair path

Implement:

- full turn lifecycle;
- semantic validation;
- repair request;
- transactional commit;
- last-error diagnostics;
- extractive scene summaries every 10 turns.

Acceptance:

- turn-service tests pass;
- invalid first output plus valid repaired output creates one committed turn;
- failed repair creates no committed turn;
- narration is displayed only after commit;
- state cache and replay match after every integration turn.

Commit suggestion:

```text
feat: orchestrate validated narrative turns
```

### Milestone 8 — Interactive CLI

Implement:

- top-level commands;
- game loop;
- in-game command dispatch;
- history, inventory, location, state, reload, context, debug;
- graceful Ctrl-C and EOF handling.

Required Ctrl-C behavior:

- while waiting for player input: print a newline and exit cleanly;
- while waiting for model response: print a cancellation message, do not commit, and return to the prompt when practical;
- no partial state commit.

Acceptance:

- CLI tests pass;
- sample world can be played manually with LM Studio;
- all commands in Section 17 exist;
- autosave works without `/save`.

Commit suggestion:

```text
feat: add terminal play interface
```

### Milestone 9 — Export, documentation, and release hardening

Implement:

- Markdown export;
- JSON export;
- full documentation;
- privacy review;
- error messages;
- final sample-world polish;
- changelog entry;
- end-to-end scripted integration test.

Acceptance commands:

```bash
python -m unittest discover -s tests -v
python -m compileall local_adventure tests
python -m local_adventure doctor
python -m local_adventure validate-world --world worlds/ember_hollow
python -m local_adventure sessions create \
  --world worlds/ember_hollow \
  --name "Release Test"
```

Manual acceptance:

- configure a valid local LM Studio model;
- play at least three turns;
- inspect state;
- undo;
- branch;
- play one branch turn;
- export Markdown and JSON;
- reopen both sessions;
- confirm histories and states are correct.

Commit suggestion:

```text
docs: complete first local adventure release
```

---

## 24. Required class and module responsibilities

Keep these boundaries clear.

### `content.models`

Only authored-file Pydantic models.

No database calls, model calls, or runtime session classes.

### `content.loader`

- locate files;
- read bounded text;
- parse TOML;
- parse Markdown front matter;
- instantiate authored models;
- return a `LoadedWorld`.

### `content.validator`

- cross-file reference checks;
- ID uniqueness;
- scenario consistency;
- world budget consistency.

### `state.models`

Runtime state Pydantic models.

### `state.events`

Pydantic event union.

### `state.validator`

Validate an event against current state and world gameplay configuration. It may normalize a valid event into a committed form, such as recording an applied clamped delta.

### `state.reducer`

Pure state transformations only.

### `storage.repositories`

Explicit repository classes:

- `WorldRepository`
- `SessionRepository`
- `TurnRepository`
- `ModelCallRepository`
- `LoreRepository`
- `CheckpointRepository`
- `SummaryRepository`

Do not create a generic active-record layer.

### `lore.indexer`

Synchronize Markdown lore into SQLite.

### `lore.query`

Build sanitized terms, retrieve candidates, and score them.

### `context.builder`

Coordinate all context sections and budgets.

### `llm.lm_studio`

Only LM Studio OpenAI-compatible transport and protocol handling.

### `app.turn_service`

Coordinate the complete turn. It is the only module allowed to depend directly on content, context, LLM, state, and storage layers together.

### `app.game_service`

Session creation, loading, undo, branch, checkpoints, reload, and state inspection.

### `cli`

Argument parsing, terminal presentation, and command dispatch. No SQL and no state mutation logic.

---

## 25. Implementation conventions

### 25.1 Code style

- four spaces;
- type hints on all public functions;
- docstrings on public classes and non-obvious functions;
- functions generally under 60 lines;
- modules generally under 500 lines;
- avoid deep inheritance;
- prefer immutable Pydantic models for state and events where practical;
- use descriptive names;
- no wildcard imports;
- no mutable default arguments;
- no broad `except Exception` except at the outer CLI boundary;
- do not use `assert` for user-input validation.

### 25.2 Time and IDs

Use UTC ISO 8601 with `Z`.

Example:

```text
2026-07-17T04:22:31.123456Z
```

Create an injectable clock function and ID factory so tests can be deterministic.

### 25.3 Hashes

Use SHA-256 lowercase hexadecimal.

Hashes must cover canonical content, not Python object repr.

### 25.4 SQL

- parameterized SQL only;
- no user-controlled SQL identifiers;
- SQL keywords uppercase;
- one statement per logical block;
- repositories return typed records or Pydantic models, not raw tuples.

### 25.5 User-facing text

- concise;
- actionable;
- include file path and field for content errors;
- do not expose stack traces by default;
- avoid anthropomorphizing the engine;
- distinguish warnings from errors.

---

## 26. Sample world requirements

The sample world must demonstrate:

- two connected locations;
- one player actor;
- one NPC;
- one transferable item;
- one quest;
- at least three lore files;
- one prompt skill;
- at least one relationship;
- one numeric stat;
- one boolean flag;
- an opening that naturally permits:
  - dialogue;
  - receiving the key;
  - moving to the second location;
  - activating the quest.

The sample world should be compact. Its purpose is testing and authoring guidance, not a full campaign.

The narrator prompt must remind the model:

- never speak for the player beyond unavoidable physical consequences;
- do not decide the player’s private thoughts;
- remain consistent with state;
- use second person present tense;
- keep ordinary turns between roughly 120 and 500 words;
- do not mention state-event JSON;
- propose only state events justified by narration;
- emit no event for implied facts that are not mechanically relevant;
- use only IDs listed in the supplied valid-ID section.

---

## 27. `doctor` command output contract

Example:

```text
Local Adventure Doctor

[PASS] Python 3.12.8
[PASS] Runtime directory writable: .local-adventure
[PASS] SQLite 3.45.3
[PASS] SQLite FTS5 available
[PASS] Database schema at version 2
[PASS] Sample world valid
[WARN] LM Studio is not reachable at http://127.0.0.1:1234
       Start the LM Studio local server before playing, or update world.toml.

Result: usable for authoring and tests; model play unavailable.
```

Exit behavior:

- exit 0 when the engine can run tests and author worlds, even if LM Studio is unavailable;
- exit 1 for broken Python/runtime/database installation;
- with `--require-model`, an unavailable LM Studio server or configured model returns exit 1.

Do not make `doctor` download models.

---

## 28. Definition of done for version 0.1.0

Version 0.1.0 is complete only when all statements are true:

- [ ] All nine milestones are complete.
- [ ] `requirements.txt` contains only Pydantic.
- [ ] Default tests run without internet or LM Studio.
- [ ] A user can validate the sample world.
- [ ] A user can create a session.
- [ ] A user can play through the LM Studio backend.
- [ ] Every valid turn is automatically persisted.
- [ ] Invalid model output cannot mutate state.
- [ ] Replay equals cached state.
- [ ] Undo preserves old turns.
- [ ] Branching creates an independent session head.
- [ ] Lore retrieval works without embeddings.
- [ ] FTS5 has a tested fallback.
- [ ] Full prompts are not stored by default.
- [ ] No world file can execute code.
- [ ] No world path can escape its root through traversal or symlink.
- [ ] Markdown and JSON export work.
- [ ] Documentation matches actual commands and formats.
- [ ] The sample-world manual acceptance flow succeeds.
- [ ] `CHANGELOG.md` includes a 0.1.0 entry.
- [ ] `docs/implementation-status.md` records the final passing commands.

---

## 29. Deliberately deferred extension interfaces

Design boundaries should permit these later, but do not implement them now.

### 29.1 Additional local model backends

Future backends may include:

- Ollama;
- llama.cpp server;
- MLX-LM server;
- vLLM;
- another OpenAI-compatible local endpoint.

They must implement the same `ModelBackend` protocol.

### 29.2 Model-generated summaries

Add a separate `SummaryBackend` or use `ModelBackend` with a different schema. Summaries must never become authoritative state.

### 29.3 Executable tools

A future tool loop should:

- use a separate typed tool registry;
- expose only allowlisted tools;
- cap iterations;
- record every call and result;
- keep state mutation inside the same validators and reducers;
- never expose generic shell or filesystem tools to the narrator.

### 29.4 Executable skills

If executable skills are eventually implemented, use an explicit subprocess JSON protocol and opt-in trust configuration. Do not import arbitrary world Python into the engine process.

### 29.5 MCP

Add MCP as an adapter around the stable game service, not as an internal requirement. Candidate resources and tools:

```text
Resources:
  session://current/state
  world://current/lore/<id>
  session://current/history

Tools:
  game.submit_turn
  game.inspect
  game.undo
  game.branch
  game.export
```

### 29.6 Dedicated TUI or web UI

A future UI must call application services rather than access SQLite directly.

### 29.7 Embeddings

Only add embeddings after measuring FTS retrieval failures. Preserve exact-match and graph/entity bonuses even if semantic search is added.

---

## Appendix A — Required root `AGENTS.md`

Create this file verbatim, adjusting commands only if the repository layout itself is intentionally changed with user approval.

````markdown
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
````

---

## Appendix B — Suggested initial implementation prompt for Codex CLI

Run Codex from the empty or initialized repository root and provide:

```text
Read IMPLEMENTATION_PLAN.md and AGENTS.md completely.

Implement Milestone 1 only. Do not begin Milestone 2. Follow the dependency and
architecture constraints exactly. Run every Milestone 1 acceptance command,
fix failures, and update docs/implementation-status.md with the results.

At the end, report:
1. files created or changed;
2. commands run and whether they passed;
3. any deviation from the plan;
4. the next milestone, without implementing it.
```

For later milestones, replace `Milestone 1` with the next milestone number.

Do not ask Codex to implement all milestones in one prompt. Smaller milestone-sized sessions reduce drift and make review easier.

---

## Appendix C — Manual model smoke-test procedure

After Milestone 8:

1. Start LM Studio and enable its local server from the Developer tab, or run `lms server start`.
2. Load or make available a local chat model that supports structured JSON output.
3. Edit `worlds/ember_hollow/world.toml` and set `model.name` to the exact ID shown by `GET /v1/models` or the LM Studio Developer interface.
4. Run:

```bash
python -m local_adventure doctor --world worlds/ember_hollow --require-model
python -m local_adventure play --world worlds/ember_hollow --name "Smoke Test"
```

5. Enter:

```text
I ask Mark what the brass key opens.
```

6. Verify:
   - narration is shown;
   - no raw JSON is printed;
   - `/history 1` shows the turn;
   - `/state` remains valid;
   - `/context` shows included lore and character counts.

7. Enter:

```text
I promise to keep her secret and ask for the key.
```

8. Verify:
   - a transfer event occurs only if the narration supports it;
   - the key appears in `/inventory`;
   - replay tests still pass after exiting.

9. Run:

```text
/undo
/branch Alternate Choice
```

10. Verify:
    - the key is no longer in inventory after undo if that transfer was undone;
    - the branch has the expected head;
    - the original session remains listed.

---

## Appendix D — External references

These references explain the platform capabilities used by the design. They are not substitutes for the requirements in this plan.

- LM Studio structured output through Chat Completions:  
  https://lmstudio.ai/docs/developer/openai-compat/structured-output
- LM Studio OpenAI-compatible endpoints:  
  https://lmstudio.ai/docs/developer/openai-compat
- LM Studio model listing endpoint:  
  https://lmstudio.ai/docs/developer/openai-compat/models
- LM Studio local server and headless operation:  
  https://lmstudio.ai/docs/developer/core/server  
  https://lmstudio.ai/docs/developer/core/headless
- LM Studio API authentication:  
  https://lmstudio.ai/docs/developer/core/authentication
- Python `tomllib`:  
  https://docs.python.org/3/library/tomllib.html
- SQLite FTS5:  
  https://www.sqlite.org/fts5.html
- Codex `AGENTS.md` guidance:  
  https://developers.openai.com/codex/agent-configuration/agents-md
- Codex best practices:  
  https://developers.openai.com/codex/learn/best-practices

---

## Appendix E — Final review checklist for the human maintainer

Before accepting the implementation, review these points manually:

### Architecture

- Does CLI code avoid SQL and reducer logic?
- Does model transport avoid world-state decisions?
- Are reducers deterministic and isolated?
- Can the engine run tests without a model?

### Readability

- Can a world be understood by reading `world.toml`, `WORLD.md`, entity TOML,
  and lore Markdown?
- Are IDs and references obvious?
- Are errors tied to exact files and fields?
- Are there unnecessary abstractions or generic frameworks?

### Privacy

- Is full prompt storage disabled by default?
- Does the engine warn for non-loopback model endpoints?
- Are runtime files ignored by Git?
- Can world symlinks escape the root?

### Durability

- Does replay match state cache?
- Does undo preserve history?
- Do branches diverge without corrupting shared history?
- Are migrations idempotent?
- Can exports be read without the engine?

### Model safety and consistency

- Can malformed model JSON mutate state?
- Can a model invent an entity ID and have it accepted?
- Is narration withheld until persistence succeeds?
- Is only one repair attempt made?
- Is failure recoverable without restarting the session?

### Dependency control

- Is Pydantic still the only runtime Python dependency?
- Is each standard-library facility used directly and clearly?
- Has any optional feature introduced a hidden external service?

If any answer is unsatisfactory, correct it before adding roadmap features.
