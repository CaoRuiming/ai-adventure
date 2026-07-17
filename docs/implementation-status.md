# Implementation status

Last updated: 2026-07-16

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
- [ ] Milestone 6 — LM Studio backend and structured proposals
- [ ] Milestone 7 — Complete turn service and repair path
- [ ] Milestone 8 — Interactive CLI
- [ ] Milestone 9 — Export, documentation, and release hardening

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
(39 tests, 2026-07-16).

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
