"""recheck.py — Remove database entries whose files no longer exist on disk.

Usage:
    python recheck.py [--dry-run]
"""

import argparse
from pathlib import Path

from config import DB_PATH
from database import get_db


def main():
    parser = argparse.ArgumentParser(description="Remove DB entries for missing files")
    parser.add_argument("--dry-run", action="store_true", help="Report without deleting")
    args = parser.parse_args()

    conn = get_db(str(DB_PATH))
    rows = conn.execute("SELECT id, path FROM memes").fetchall()

    missing = [(id_, path) for id_, path in rows if not Path(path).exists()]

    if not missing:
        print("All entries accounted for.")
        return

    for id_, path in missing:
        print(f"Missing [{id_}]: {path}")

    if args.dry_run:
        print(f"\n{len(missing)} entry/entries would be removed (dry run).")
        return

    conn.executemany("DELETE FROM memes WHERE id = ?", [(id_,) for id_, _ in missing])
    conn.commit()
    print(f"\nRemoved {len(missing)} entry/entries.")


if __name__ == "__main__":
    main()
