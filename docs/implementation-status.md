# Implementation status

Last updated: 2026-07-17

This checklist tracks the milestone sequence in `IMPLEMENTATION_PLAN.md`.

## Milestones

- [x] Milestone 1 — Repository skeleton and environment
  - Created the repository metadata, package namespaces, root instructions,
    initial documentation, and offline CLI placeholder.
  - Acceptance commands: all passed on 2026-07-16.
- [x] Milestone 2 — Content models and world validation
  - Added Pydantic authored-content models, secure TOML and Markdown loading,
    cross-reference validation, the Ember Hollow sample world, and the
    `validate-world` command.
  - Acceptance commands: all passed on 2026-07-16.
- [x] Milestone 3 — State, events, and reducer
  - Added canonical runtime state models, discriminated typed events, semantic
    event validation, deterministic pure reducers, scenario-based initial-state
    construction, and a readable state projection.
  - Acceptance commands: all passed on 2026-07-16.
- [x] Milestone 4 — SQLite persistence, replay, undo, and branch
  - Added configured SQLite connections, transactional migration application,
    the initial runtime schema, explicit repositories, canonical persistence,
    replay-backed state-cache recovery, non-destructive undo, shared-history
    branching, and named checkpoints.
  - Acceptance commands: all passed on 2026-07-16.
- [x] Milestone 5 — Lore indexing and deterministic context
  - Added the lore schema migration with optional FTS5 support, incremental and
    safe Markdown indexing, deterministic FTS/fallback retrieval, prompt-skill
    selection, two-message context assembly, exact character budgets, and
    context diagnostics.
  - Added `reindex --world PATH`; sessions now automatically synchronize lore
    during creation.
  - Acceptance commands: all passed on 2026-07-16.
- [x] Milestone 6 — LM Studio backend and structured proposals
  - Added provider-neutral model request/response models, strict structured
    `TurnProposal` validation, the LM Studio Chat Completions and model-list
    adapter, response-size limits, typed transport errors, and an offline
    scripted backend.
  - Added privacy-conscious model-call audit persistence and expanded `doctor`
    with local runtime, SQLite, migration, world, authentication-variable, and
    optional-model diagnostics. LM Studio remains a warning unless
    `--require-model` is supplied.
  - Acceptance commands: all passed on 2026-07-16 (47 offline tests).
- [x] Milestone 7 — Complete turn service and repair path
  - Added a complete `TurnService`: input and session/world checks, automatic
    lore synchronization, deterministic context/request creation, semantic
    event validation, one repair attempt, and commit-after-validation behavior.
  - Successful model-call audit completion is recorded in the same transaction
    as the turn, ordered events, state cache, and session-head update.
  - Added process-local last-error diagnostics and deterministic extractive
    scene summaries every 10 committed turns, capped at 12,000 characters.
  - Acceptance commands: all passed on 2026-07-16 (51 offline tests).
- [x] Milestone 8 — Interactive CLI
  - Added `sessions` and `play` commands, including durable session creation,
    resume-by-ID, and the synchronous terminal game loop.
  - Added in-game state, location, inventory, history, context, undo, branch,
    checkpoint, restore, session-listing, reload, and debug commands. Reload
    reindexes lore while preserving the authoritative session state.
  - Added clean EOF/Ctrl-C input exits and cancellation handling that returns
    to the prompt without committing a partial model turn.
  - Export command shapes are visible but intentionally report that exports
    arrive in Milestone 9, where their required formats are specified.
  - Acceptance commands: offline checks passed on 2026-07-17 (55 tests).
- [x] Milestone 9 — Export, documentation, and release hardening
  - Added privacy-safe Markdown and JSON exports for current session history,
    replayed state, and named checkpoints. Exports omit prompts, system
    instructions, model-call audit records, and raw model responses.
  - Completed architecture, data-model, authoring, privacy/security, and
    troubleshooting documentation; added the 0.1.0 changelog entry; and added
    an offline scripted end-to-end test covering turn history, undo, branch,
    and export.
  - Acceptance commands: all passed on 2026-07-17 (59 offline tests).

## Verification

Environment setup:

- `python3 -m venv .venv` — PASS
- `python -m pip install --upgrade pip` — PASS
- `python -m pip install -r requirements.txt` — PASS

Milestone 1 acceptance commands, run with `.venv` activated:

- `python -m unittest discover -s tests -v` — PASS (3 tests)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure --help` — PASS

Milestone 2 acceptance commands, run with `.venv` activated:

- `python -m unittest discover -s tests -v` — PASS (14 tests)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure validate-world --world worlds/ember_hollow` — PASS

Milestone 3 acceptance and required repository commands, run with `.venv`
activated:

- `python -m pip install -r requirements.txt` — PASS (Pydantic already installed)
- `python -m unittest discover -s tests -v` — PASS (26 tests)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure --help` — PASS
- `python -m local_adventure doctor` — PASS (Milestone 1 placeholder)

Required repository diagnostic, run with `.venv` activated:

- `python -m local_adventure doctor` — PASS (Milestone 1 placeholder)

Additional Milestone 1 behavior check:

- `python -m local_adventure doctor` — PASS (placeholder diagnostic)

Most recent passing test command: `python -m unittest discover -s tests -v`
(59 tests, 2026-07-17).

Milestone 4 acceptance and required repository commands, run with `.venv`
activated:

- `python -m pip install -r requirements.txt` — PASS (Pydantic already installed)
- `python -m unittest discover -s tests -v` — PASS (35 tests)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS (Milestone 1 placeholder)

Focused commits were not created because the environment does not permit
writing `.git/index.lock`.

Milestone 5 acceptance and required repository commands, run with `.venv`
activated:

- `python -m pip install -r requirements.txt` — PASS (Pydantic already installed)
- `python -m unittest discover -s tests -v` — PASS (39 tests)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS (Milestone 1 placeholder)
- `python -m local_adventure reindex --world worlds/ember_hollow` — PASS (FTS5)

Milestone 6 acceptance and required repository commands, run with `.venv`
activated:

- `python -m pip install -r requirements.txt` — PASS (Pydantic already installed)
- `python -m unittest discover -s tests -v` — PASS (47 tests; no live model calls)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS for local engine checks; LM Studio
  endpoint and configured token were unavailable and correctly reported as
  warnings.
- `python -m local_adventure validate-world --world worlds/ember_hollow` — PASS

Milestone 7 acceptance and required repository commands, run with `.venv`
activated:

- `python -m pip install -r requirements.txt` — PASS (Pydantic already installed)
- `python -m unittest discover -s tests -v` — PASS (51 tests; no live model calls)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS for local engine checks; LM Studio
  endpoint and configured token were unavailable and correctly reported as
  warnings.
- `python -m local_adventure validate-world --world worlds/ember_hollow` — PASS

Milestone 8 acceptance and required repository commands, run with `.venv`
activated:

- `python -m unittest discover -s tests -v` — PASS (55 tests; no live model calls)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS for local engine checks; LM Studio
  endpoint and configured token were unavailable and correctly reported as
  warnings.
- `python -m local_adventure validate-world --world worlds/ember_hollow` — PASS
- `python -m local_adventure sessions create --world worlds/ember_hollow --name
  "Milestone 8 Verification"` — PASS
- Manual LM Studio play acceptance was not run because no local LM Studio server
  or configured token was available. Offline CLI tests cover the loop,
  autosave, EOF, and model-request cancellation paths.

Milestone 9 acceptance commands, run with `.venv` activated:

- `python -m unittest discover -s tests -v` — PASS (59 tests; no live model
  calls)
- `python -m compileall local_adventure tests` — PASS
- `python -m local_adventure doctor` — PASS for local engine checks; the
  configured LM Studio token and endpoint were unavailable and correctly
  reported as warnings.
- `python -m local_adventure validate-world --world worlds/ember_hollow` — PASS
- `python -m local_adventure sessions create --world worlds/ember_hollow --name
  "Release Test"` — PASS

Manual Milestone 9 acceptance remains pending a configured local LM Studio
server. The scripted integration test covers two turns, undo, branching,
reopening/exporting both histories, and current-state verification offline.
