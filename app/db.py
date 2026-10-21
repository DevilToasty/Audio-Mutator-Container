# small SQL storage to make user files accessable
import os 
import sqlite3

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "app.db")

SCRIPT = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    rendered_filename TEXT,
    chain_json TEXT NOT NULL DEFAULT '[]',
    grid_row INTEGER NOT NULL DEFAULT 0,
    grid_col INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    is_dirty INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'chain',
    chain_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows are dicts
    conn.execute("PRAGMA foreign_keys = ON")  # enforce ON DELETE CASCADE lets you delete all child rows of parent
    return conn

def init_db():
    conn = get_db()
    conn.executescript(SCRIPT)
    conn.commit()
    conn.close()