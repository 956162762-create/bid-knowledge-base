"""
系统数据库 Schema — system.db + project.db 建表与迁移
"""
import sqlite3
from pathlib import Path


SYSTEM_DB_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    struct_db_path  TEXT NOT NULL,
    chroma_path     TEXT NOT NULL,
    meta_db_path    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS system_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

PROJECT_DB_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    doc_type        TEXT NOT NULL DEFAULT 'tender_doc'
                    CHECK(doc_type IN ('tender_doc','addendum','clarification','template','bid_doc','other')),
    version         TEXT DEFAULT '1.0',
    parent_doc_id   INTEGER REFERENCES documents(id),
    is_latest       INTEGER DEFAULT 1,
    change_summary  TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','parsing','struct_parsed','vectorized','ready','error')),
    page_count      INTEGER DEFAULT 0,
    clause_count    INTEGER DEFAULT 0,
    table_count     INTEGER DEFAULT 0,
    xref_count      INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    parsed_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_doc_parent ON documents(parent_doc_id);
CREATE INDEX IF NOT EXISTS idx_doc_status ON documents(status);

CREATE TABLE IF NOT EXISTS memory_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL CHECK(category IN ('preference','correction','output','note')),
    key             TEXT NOT NULL,
    value           TEXT NOT NULL,
    source          TEXT DEFAULT 'user' CHECK(source IN ('user','system','agent')),
    importance      REAL DEFAULT 0.5,
    access_count    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category);

CREATE TABLE IF NOT EXISTS rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_entry_id INTEGER REFERENCES memory_entries(id),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    rule_type       TEXT NOT NULL CHECK(rule_type IN (
                        'source_label','checkbox_format','include_always',
                        'priority_collections','return_table','return_clause','custom')),
    condition_json  TEXT NOT NULL DEFAULT '{}',
    action_json     TEXT NOT NULL DEFAULT '{}',
    priority        INTEGER DEFAULT 0,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rules_enabled ON rules(enabled);

CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    metadata_json   TEXT DEFAULT '{}',
    token_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(created_at);

CREATE TABLE IF NOT EXISTS generated_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_hash     TEXT NOT NULL,
    output_text     TEXT NOT NULL,
    output_type     TEXT DEFAULT 'answer' CHECK(output_type IN ('answer','summary','extraction','template')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_system_db(db_path: str) -> sqlite3.Connection:
    """初始化 system.db"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SYSTEM_DB_SQL)
    conn.commit()
    return conn


def init_project_db(db_path: str) -> sqlite3.Connection:
    """初始化 project.db"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(PROJECT_DB_SQL)
    conn.commit()
    return conn
