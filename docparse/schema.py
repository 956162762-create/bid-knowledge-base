"""
struct.db SQLite Schema — 条款树 + 表格库 + 条款号索引
"""
import sqlite3
from pathlib import Path


SCHEMA_SQL = """
-- 条款树
CREATE TABLE IF NOT EXISTS clause_nodes (
    id              INTEGER PRIMARY KEY,
    parent_id       INTEGER REFERENCES clause_nodes(id),
    node_type       TEXT NOT NULL CHECK(node_type IN ('volume','part','chapter','section','clause','subclause')),
    number          TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    level           INTEGER NOT NULL DEFAULT 0,
    page_start      INTEGER,
    path            TEXT NOT NULL DEFAULT '',
    is_red          INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_clause_number ON clause_nodes(number);
CREATE INDEX IF NOT EXISTS idx_clause_parent ON clause_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_clause_path ON clause_nodes(path);
CREATE INDEX IF NOT EXISTS idx_clause_level ON clause_nodes(level);

-- 表格库
CREATE TABLE IF NOT EXISTS tables (
    id              INTEGER PRIMARY KEY,
    table_number    TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    caption         TEXT NOT NULL DEFAULT '',
    chapter_ref     TEXT NOT NULL DEFAULT '',
    page_number     INTEGER,
    rows_json       TEXT NOT NULL DEFAULT '[]',
    checkbox_json   TEXT NOT NULL DEFAULT '{}',
    merged_json     TEXT NOT NULL DEFAULT '[]',
    row_count       INTEGER NOT NULL DEFAULT 0,
    col_count       INTEGER NOT NULL DEFAULT 0,
    raw_html        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_table_number ON tables(table_number);
CREATE INDEX IF NOT EXISTS idx_table_chapter ON tables(chapter_ref);

-- 条款号 O(1) 哈希索引
CREATE TABLE IF NOT EXISTS clause_number_index (
    number          TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('clause','table')),
    entity_id       INTEGER NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 文档元数据
CREATE TABLE IF NOT EXISTS document_meta (
    id              INTEGER PRIMARY KEY,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    page_count      INTEGER,
    clause_count    INTEGER NOT NULL DEFAULT 0,
    table_count     INTEGER NOT NULL DEFAULT 0,
    parsed_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """初始化 struct.db"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
