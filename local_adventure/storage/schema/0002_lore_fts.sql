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

CREATE VIRTUAL TABLE lore_documents_fts USING fts5(
    document_id UNINDEXED,
    world_id UNINDEXED,
    title,
    aliases,
    tags,
    body
);
