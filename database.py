import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open and return a connection to the SQLite database."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_schema(conn: sqlite3.Connection):
    """Initialize database schema if not exists."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256       TEXT NOT NULL UNIQUE,
            path         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'new',
            caption      TEXT,
            ocr_text     TEXT,
            created_at   TEXT NOT NULL,
            processed_at TEXT,
            reviewed_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS meme_tags (
            meme_id    INTEGER NOT NULL REFERENCES memes(id),
            tag_id     INTEGER NOT NULL REFERENCES tags(id),
            source     TEXT NOT NULL,
            confidence REAL,
            PRIMARY KEY (meme_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS meme_embeddings (
            meme_id   INTEGER PRIMARY KEY REFERENCES memes(id),
            embedding BLOB NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memes_fts USING fts5(
            caption, ocr_text, content='memes', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS memes_ai AFTER INSERT ON memes BEGIN
            INSERT INTO memes_fts(rowid, caption, ocr_text) VALUES (new.id, new.caption, new.ocr_text);
        END;

        CREATE TRIGGER IF NOT EXISTS memes_ad AFTER DELETE ON memes BEGIN
            INSERT INTO memes_fts(memes_fts, rowid, caption, ocr_text) VALUES ('delete', old.id, old.caption, old.ocr_text);
        END;

        CREATE TRIGGER IF NOT EXISTS memes_au AFTER UPDATE ON memes BEGIN
            INSERT INTO memes_fts(memes_fts, rowid, caption, ocr_text) VALUES ('delete', old.id, old.caption, old.ocr_text);
            INSERT INTO memes_fts(rowid, caption, ocr_text) VALUES (new.id, new.caption, new.ocr_text);
        END;
    """)
    conn.commit()


def get_db(db_path: str) -> sqlite3.Connection:
    """Open connection and initialize schema in one call."""
    conn = get_connection(db_path)
    init_schema(conn)
    return conn
