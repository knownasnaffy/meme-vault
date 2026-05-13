import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import database


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest(directory: str, db_path: str = str(config.DB_PATH)):
    conn = database.get_db(db_path)
    root = Path(directory).resolve()

    files = [p for p in root.rglob("*") if p.suffix.lower() in config.SUPPORTED_EXTENSIONS]

    new_count = skipped_count = 0
    for path in files:
        digest = sha256(path)
        exists = conn.execute("SELECT 1 FROM memes WHERE sha256 = ?", (digest,)).fetchone()
        if exists:
            skipped_count += 1
            continue
        conn.execute(
            "INSERT INTO memes (sha256, path, status, created_at) VALUES (?, ?, 'new', ?)",
            (digest, str(path), datetime.now(timezone.utc).isoformat()),
        )
        new_count += 1

    conn.commit()
    conn.close()
    print(f"{new_count} new, {skipped_count} skipped (duplicates)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python ingest.py <directory>")
        sys.exit(1)
    ingest(sys.argv[1])
