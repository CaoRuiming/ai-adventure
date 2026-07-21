# Creating local worlds

This guide is the reference for hand-authoring a Local Adventure Engine world. Start by copying `worlds/ember_hollow`; it is a complete, valid example. Then validate early and often:

```bash
python -m local_adventure validate-world --world PATH
python -m local_adventure reindex --world PATH
```

Validation is offline. It checks TOML schemas, unknown fields, cross-file references, duplicate IDs, required files, UTF-8 text, and paths that escape the world root. `reindex` writes the world's Markdown lore to the local SQLite search index; creating a session also reindexes it.

## The authoring model

The important distinction is **truth versus guidance**:

| Put it in | Use it for | Do not use it for |
| --- | --- | --- |
| Entity TOML | Named, persistent game objects and their machine-readable initial facts: people, places, objects, quests, locations, holders, stats, connections, and allowed quest statuses. | Long backstory, scene-writing advice, or conditional story logic that has no supported state representation. |
| Scenario TOML | A selectable opening: its player, starting place, opening prose, initial flags, and the actors/quests it names. | A later chapter, a trigger, or a branching rule. Scenarios are only chosen when a session is created. |
| Lore Markdown | Searchable setting knowledge, history, secrets, descriptions, factions, customs, and detailed facts the narrator may need when relevant. | Authoritative mutable state or instructions for how the narrator must respond. |
| `WORLD.md` | Always-present creative contract: voice, point of view, genre, agency, and global fiction constraints. | A long encyclopedia, a list of per-character behavior rules, or state that can change during play. |
| `prompts/narrator.md` | Always-present narration behavior, especially concrete output and player-agency guidance. | Information that should be retrieved only when relevant. |
| `rules/*.md` | Always-present, concise rules that apply across turns, such as tone or consequences. | Conditional rules tied to one NPC, item, or scene. |
| Prompt skill | A short, conditional instruction that changes *how* the model handles a situation (for example, a guarded NPC or a mystery reveal). | Executable behavior, hidden world facts, or a substitute for an entity and its state. |
| `prompts/repair.md` | The instruction used only to repair invalid model output. | Normal narration or lore. |
| `world.toml` | Engine configuration: model endpoint, context budgets, validation limits, and audit retention. | Story content. |

The model only proposes narration and typed events. The engine validates events against the current state, then applies them. A fact that must remain correct after a turn belongs in an entity, scenario flag, or another supported state field—not solely in prose.

## Directory layout and loading

```text
my_world/
├── world.toml
├── WORLD.md
├── prompts/
│   ├── narrator.md
│   └── repair.md
├── rules/                         # optional; all .md files are loaded
├── scenarios/                     # all .toml files are loaded recursively
├── entities/
│   ├── actors/
│   ├── locations/
│   ├── items/
│   └── quests/
├── lore/                          # optional; all .md files are indexed recursively
└── skills/                        # optional; each skill has both files below
    └── example/
        ├── skill.toml
        └── SKILL.md
```

`world.toml`, `WORLD.md`, `prompts/narrator.md`, and `prompts/repair.md` are required. The loader discovers `.toml` and `.md` files recursively in the directories shown, so subfolders are useful for organization but do not create namespaces. IDs must still be globally unique within each kind where applicable.

Every authored TOML model rejects unknown fields. This deliberately turns typos into errors instead of silently ignoring them. IDs use `^[a-z][a-z0-9_]{1,63}$`: begin with a lowercase letter; then use lowercase letters, digits, or underscores. Keep IDs stable once sessions exist—saved state and references use them.

World files must remain inside the selected root after symlinks are resolved. Use UTF-8 text and never put executable code, shell commands, SQL, or Python in a world.

## `world.toml`: engine configuration

All fields below are required unless an example shows an empty string. `schema_version` is currently always `1`.

```toml
schema_version = 1
id = "my_world"
title = "My World"
description = "A short human-facing description."
default_scenario = "opening"

[model]
backend = "lm_studio"
base_url = "http://127.0.0.1:1234"
name = "the-exact-model-id"
temperature = 0.8
max_output_tokens = 1400
timeout_seconds = 180
api_token_env = "LM_STUDIO_API_TOKEN" # optional; empty string means no token

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
relaxed_item_management = false
relaxed_quest_management = false
relationship_minimum = -100
relationship_maximum = 100
stat_delta_limit = 20

[audit]
store_prompts = false
store_prompt_hashes = true
store_raw_model_responses = true
log_level = "INFO"
```

`model.backend` must be `"lm_studio"`; `base_url` must begin with `http://` or `https://`. A non-loopback URL produces a warning because world content and prompts will be sent there. The five section character budgets may not exceed `max_chars`. They are character counts, not token counts. Leave headroom: `WORLD.md`, narrator prompt, rules, the output contract, current-state projection, and the player input must fit as well.

Keep `maximum_repair_attempts` at `0` or `1`; the present schema permits no higher value. `relationship_minimum` must be below `relationship_maximum`. Set `relaxed_item_management = true` only when a smaller model frequently invents item IDs or invalid item holders. In that mode, invalid model-generated `transfer_item` events are discarded and the rest of the turn may commit; the engine never creates an item, records an invalid holder, or relaxes validation for application-generated events. Set `relaxed_quest_management = true` only when a smaller model frequently invents quest IDs or unrecognized quest statuses. It discards those invalid model-generated `set_quest_status` events; it never creates quests, adds statuses to a quest's vocabulary, or relaxes application-generated validation. Both options default to `false`, so normal worlds still repair invalid events. Audit settings control local storage only; use `store_prompts = false` if retaining full prompts is not appropriate.

## Entities: initial, authoritative game objects

All entity files begin with:

```toml
schema_version = 1
id = "stable_id"
name = "Display Name"
description = "Short factual description useful in the current-state context."
```

Descriptions are copied into runtime state. Keep them concise, concrete, and stable; move fuller history or secrets to lore. Entity file names are for humans only—the `id` field is authoritative.

### Actors

Use actors for the player and named characters. An actor always has a location, including off-screen characters.

```toml
schema_version = 1
id = "warden_sera"
name = "Warden Sera"
description = "A watchful gate warden with ash on her blue coat."
location_id = "west_gate"
is_player = false

[stats]
health = 10
resolve = 4
has_heard_alarm = false

[relationships.player]
trust = -1
```

`stats` values may be strings, integers, floats, or booleans. `relationships` maps a target actor ID to integer dimensions. Use a stable, bounded numeric dimension such as `trust`; it can later change through `adjust_relationship`. Relationship target IDs and `location_id` must exist.

### Locations

Use locations for places an actor can occupy and move between.

```toml
schema_version = 1
id = "west_gate"
name = "West Gate"
description = "A sealed gate beneath cracked stone towers."
connections = ["observatory"]

[attributes]
region = "upper_city"
indoors = false
```

Connections must name existing locations. They are not automatically bidirectional: list both directions when travel should work both ways. `attributes` accepts the same scalar values as actor stats. Use it for concise facts that should survive in state, not paragraphs of atmosphere.

### Items

Use items for named things whose holder or concise attributes may matter. The starting holder is required for `actor` and `location`, and must be empty for `none`.

```toml
schema_version = 1
id = "brass_key"
name = "Brass Key"
description = "A heavy triangular key."
initial_holder_type = "actor" # actor, location, or none
initial_holder_id = "warden_sera"

[attributes]
quest_item = true
opens = "west_gate"
```

Use `initial_holder_type = "none"` and `initial_holder_id = ""` for an item that starts unplaced. An item can later be moved only through a `transfer_item` event.

### Quests

Use quests for tracked objectives with a small explicit status vocabulary.

```toml
schema_version = 1
id = "open_west_gate"
name = "Open the West Gate"
description = "Learn how to unseal the gate."
initial_status = "inactive"
allowed_statuses = ["inactive", "active", "completed", "failed"]
```

The initial status must be present in `allowed_statuses`. The model may later use `set_quest_status` only with a status from that list. Put richer objectives, clues, and alternate approaches in lore; the quest is the durable mechanical tracker.

## Scenarios: session openings

Each `scenarios/*.toml` file defines an opening selectable with `sessions create --scenario ID` (or the world's `default_scenario`). It is not a dynamic scene trigger.

```toml
schema_version = 1
id = "opening"
title = "Ash at the Gate"
opening_narration = """
Ash lifts from the road as the gate's bells begin to ring.
"""
player_actor_id = "player"
starting_location_id = "west_gate"
active_actor_ids = ["player", "warden_sera"]
active_quest_ids = ["open_west_gate"]

[initial_flags]
met_sera = false
gate_open = false
```

The player actor, starting location, every listed actor, and every listed quest must exist. `active_actor_ids` must include exactly one actor with `is_player = true`, and it must equal `player_actor_id`; that actor's authored `location_id` must equal `starting_location_id`.

Current engine behavior constructs runtime state from **all** authored actors, locations, items, and quests. `active_actor_ids` and `active_quest_ids` are validated scenario metadata, rather than filters that omit unlisted entities or override quest statuses. Make initial actor locations, item holders, and quest statuses in their entity files agree with the opening you want. Use `initial_flags` for simple scenario-specific facts that can change through `set_flag`; values may be strings, numbers, or booleans.

## Lore: searchable world knowledge

Lore is Markdown, indexed locally and included only when the retrieval system considers it relevant. It is the right home for world history, local customs, a faction's aims, a location's sensory detail, hidden context, and material that would otherwise bloat entity descriptions.

Optional TOML front matter must start and end with a line containing `+++`:

```markdown
+++
schema_version = 1
id = "iron_league"
title = "The Iron League"
kind = "faction"
entity_ids = ["warden_sera", "west_gate"]
aliases = ["league", "iron league"]
tags = ["upper_city", "gate"]
priority = 0.8
+++

# The Iron League

The League keeps the upper-city gates closed after dusk. Sera joined after
the last ash storm, but privately doubts the order.
```

Front matter fields are `schema_version` (defaults to `1`), `id`, `title`, `kind`, `entity_ids`, `aliases`, `tags`, and `priority` (defaults to `0.5`, minimum `0`). If there is no front matter, the loader derives an ID and title from the file path; explicit front matter is clearer and safer for material you intend to maintain. Lore IDs must be unique, and `entity_ids` must name existing actors, locations, items, or quests.

Retrieval starts from player input, the current location, actors at that location, active quests, and aliases mentioned in player input. Entity links strongly favor lore tied to the current scene; aliases, tags, title/body word matches, and priority further affect ranking. Split lore by topic, give likely player words as aliases, attach each document to the relevant entity IDs, and keep the most useful facts near the beginning because context budgets can truncate at paragraph boundaries. Do not depend on a lore document always being present on a turn.

## Prompt files, rules, and skills

`WORLD.md`, `prompts/narrator.md`, and every `rules/**/*.md` are added to the system message every turn. They are mandatory behavior and consume `context.system_chars`, so write short, consistent rules rather than repeating the same instruction in every file.

Use `WORLD.md` for the world-wide storytelling identity: voice, tense, player agency, genre, and immutable narrative boundaries. Use `narrator.md` for the narrator's operational behavior, such as approximate response length and when an event is appropriate. Use `rules/*.md` for small, always-on rules that make editorial sense as separate files. `repair.md` is a narrow instruction for correcting invalid structured output and is not included in ordinary turns.

A prompt skill is a pair of files:

```toml
# skills/cautious_npc/skill.toml
schema_version = 1
id = "cautious_npc"
name = "Cautious NPC Behavior"
description = "Guidance for guarded NPCs who reveal information gradually."
priority = 0.6
always_include = false
trigger_terms = ["guarded", "interrogate", "trust"]
entity_ids = ["warden_sera"]
maximum_chars = 1200
```

```markdown
<!-- skills/cautious_npc/SKILL.md -->
When Sera is present, let her offer concrete observations before trust.
She may refuse, redirect, or bargain, but do not force the player's response.
```

`SKILL.md` must be non-empty. A skill is eligible when `always_include` is true, one of its `entity_ids` is an actor at the player's current location, or a `trigger_terms` substring appears in player input. Eligible skills are ordered by always-include status, active entity matches, trigger matches, priority, and ID, then limited by `maximum_skills` and `skills_chars`. The instruction body is additionally truncated to `maximum_chars`.

Make a skill behavioral and narrow: “portray this guarded NPC without forcing disclosure” is appropriate; “the gate is secretly opened by a red key” belongs in lore, while “gate_open” belongs in scenario flags/state. Do not use skills for executable code, tools, network access, shell commands, or state mutations.

## A reliable authoring workflow

1. Copy the sample world, choose stable IDs, and change `world.toml`'s world ID and model name.
2. Define locations first, then actors and items that reference them, then quests.
3. Add one scenario whose player actor and actor location agree. Start with a few simple flags.
4. Put compact canonical facts in entity fields; write detailed, discoverable knowledge as small lore documents with useful aliases and entity links.
5. Add only short global prompts and skills that materially change narrator behavior.
6. Run `validate-world` after each batch of changes. Fix the named path and field; validation never silently repairs content.
7. Run `reindex` after lore changes when you want to inspect retrieval before creating a session. New sessions do this automatically.
8. Create a fresh session to see changed opening content. Existing sessions keep the initial state captured at creation; changing a world does not rewrite their history.
9. During play, use `/context` to inspect selected lore and skills, budget use, and omissions. Reduce or split content when the relevant material is not selected.

Before sharing a world, run:

```bash
python -m local_adventure validate-world --world PATH
python -m local_adventure doctor --world PATH
```

`doctor` may warn that the configured local model is unavailable; that does not prevent offline authoring validation. For a final smoke test, create a new session and play a short turn with your configured local model.
