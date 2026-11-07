"""SQLite storage: users, documents, chunks, chat history."""
import sqlite3

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER REFERENCES users(id),      -- NULL for documents from the data folder
    visibility TEXT NOT NULL DEFAULT 'shared',  -- 'shared' (all students) or 'private'
    source TEXT NOT NULL,                       -- 'folder' or 'upload'
    filename TEXT NOT NULL,                     -- original name shown to users
    stored_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    chunks INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ready',       -- 'ready' or 'no_text'
    kind TEXT NOT NULL DEFAULT 'pdf',           -- file extension: pdf, docx, csv, md ...
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    section TEXT,
    location TEXT,                              -- e.g. 'Page 3 of 12', 'Rows 2–41', 'Slide 4 of 20'
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    refs_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # upgrade databases created by the first (PDF-only) version
        doc_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
        if "kind" not in doc_cols:
            conn.execute("ALTER TABLE documents ADD COLUMN kind TEXT NOT NULL DEFAULT 'pdf'")
        chunk_cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        if "location" not in chunk_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN location TEXT")
