"""search.py — CLI search interface for MemeVault.

Usage:
    python search.py <query> [--all]

Options:
    --all   Include non-approved memes (review, rejected, new)
"""

import argparse
import sys

from config import DB_PATH
from database import get_db


def search(query: str, include_all: bool = False):
    conn = get_db(str(DB_PATH))
    conn.row_factory = lambda cur, row: dict(zip([c[0] for c in cur.description], row))

    status_filter = "" if include_all else "AND m.status = 'approved'"

    # 1. Tag match
    tag_rows = conn.execute(
        f"""
        SELECT m.id, m.path, m.caption, m.ocr_text, m.status,
               GROUP_CONCAT(t.name, ', ') AS tags,
               COUNT(*) AS score
        FROM memes m
        JOIN meme_tags mt ON mt.meme_id = m.id
        JOIN tags t ON t.id = mt.tag_id
        WHERE t.name LIKE ? {status_filter}
        GROUP BY m.id
        """,
        (f"%{query}%",),
    ).fetchall()

    # 2. FTS match on caption + ocr_text
    try:
        fts_rows = conn.execute(
            f"""
            SELECT m.id, m.path, m.caption, m.ocr_text, m.status,
                   (SELECT GROUP_CONCAT(t.name, ', ')
                    FROM meme_tags mt JOIN tags t ON t.id = mt.tag_id
                    WHERE mt.meme_id = m.id) AS tags,
                   1 AS score
            FROM memes_fts f
            JOIN memes m ON m.id = f.rowid
            WHERE memes_fts MATCH ? {status_filter}
            """,
            (query,),
        ).fetchall()
    except Exception:
        fts_rows = []

    # 3. Merge and deduplicate, summing scores
    merged: dict[int, dict] = {}
    for row in tag_rows + fts_rows:
        rid = row["id"]
        if rid in merged:
            merged[rid]["score"] += row["score"]
        else:
            merged[rid] = dict(row)

    results = sorted(merged.values(), key=lambda r: r["score"], reverse=True)
    return results


def print_results(results):
    if not results:
        print("No results found.")
        return
    for r in results:
        print(f"[{r['id']}] {r['path']}")
        if r.get("caption"):
            snippet = r["caption"][:120].replace("\n", " ")
            print(f"  caption: {snippet}")
        if r.get("tags"):
            print(f"  tags: {r['tags']}")
        if r.get("ocr_text"):
            snippet = r["ocr_text"][:120].replace("\n", " ")
            print(f"  ocr: {snippet}")
        if r.get("status") != "approved":
            print(f"  status: {r['status']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Search MemeVault")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="Include non-approved memes")
    args = parser.parse_args()

    results = search(args.query, args.include_all)
    print(f"{len(results)} result(s) for '{args.query}'\n")
    print_results(results)


if __name__ == "__main__":
    main()
