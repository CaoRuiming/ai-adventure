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

CREATE INDEX turns_session_parent_idx ON turns(session_id, parent_turn_id);

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
