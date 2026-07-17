# Architecture

`content` safely loads authored TOML and Markdown. `state` owns runtime models, event validation, and pure reducers. `storage` owns SQLite and migrations; `lore` indexes and retrieves Markdown; `context` assembles bounded deterministic prompts; `llm` owns the backend protocol and LM Studio transport. `app` coordinates session and turn use cases, while `cli` only presents commands.

For a turn, the app loads cached/replayed state, synchronizes lore, assembles context, calls the model, parses a `TurnProposal`, validates events against current state, applies them in memory, then atomically appends the turn/events and moves the session head. Narration is displayed only after that commit. Invalid output gets at most one repair attempt.

Turns form a parent-linked graph. Undo moves a session head and rebuilds its cache; it never deletes history. A branch copies the current head and state cache into a new session, so ancestors may be shared. The model cannot write files, SQL, or state directly.

The first release intentionally stays synchronous, local, terminal-based, and embedding-free. Prompt skills are prose only; no world Python, shell tools, plugins, remote providers, or browser UI execute in this version.
