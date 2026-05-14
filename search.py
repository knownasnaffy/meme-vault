"""search.py — CLI search interface for MemeVault.

Usage:
    python search.py [<query>] [--all] [--semantic]
    python search.py --id <id>

Options:
    --all       Include non-approved memes (review, rejected, new)
    --id        Return a single entry by ID (cannot be used with query)
    --semantic  Use embedding-based cosine similarity instead of keyword/FTS search

Omit <query> to list all entries.
"""

import argparse
import sys

import numpy as np

from config import DB_PATH, EMBEDDING_MODEL
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


def list_all(include_all: bool = False):
    conn = get_db(str(DB_PATH))
    conn.row_factory = lambda cur, row: dict(zip([c[0] for c in cur.description], row))
    status_filter = "" if include_all else "WHERE m.status = 'approved'"
    return conn.execute(
        f"""
        SELECT m.id, m.path, m.caption, m.ocr_text, m.status,
               (SELECT GROUP_CONCAT(t.name, ', ')
                FROM meme_tags mt JOIN tags t ON t.id = mt.tag_id
                WHERE mt.meme_id = m.id) AS tags
        FROM memes m {status_filter}
        ORDER BY m.id
        """
    ).fetchall()


def fetch_by_id(meme_id: int):
    conn = get_db(str(DB_PATH))
    conn.row_factory = lambda cur, row: dict(zip([c[0] for c in cur.description], row))
    return conn.execute(
        """
        SELECT m.id, m.path, m.caption, m.ocr_text, m.status,
               (SELECT GROUP_CONCAT(t.name, ', ')
                FROM meme_tags mt JOIN tags t ON t.id = mt.tag_id
                WHERE mt.meme_id = m.id) AS tags
        FROM memes m WHERE m.id = ?
        """,
        (meme_id,),
    ).fetchall()


def semantic_search(query: str, include_all: bool = False, top_k: int = 20):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True, model_kwargs={"modality": "vision"})
    query_vec = model.encode_query(query)

    conn = get_db(str(DB_PATH))
    conn.row_factory = lambda cur, row: dict(zip([c[0] for c in cur.description], row))
    status_filter = "" if include_all else "AND m.status = 'approved'"

    rows = conn.execute(
        f"""
        SELECT m.id, m.path, m.caption, m.ocr_text, m.status,
               (SELECT GROUP_CONCAT(t.name, ', ')
                FROM meme_tags mt JOIN tags t ON t.id = mt.tag_id
                WHERE mt.meme_id = m.id) AS tags,
               e.embedding
        FROM meme_embeddings e
        JOIN memes m ON m.id = e.meme_id
        WHERE 1=1 {status_filter}
        """
    ).fetchall()

    if not rows:
        return []

    embeddings = np.stack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
    scores = embeddings @ query_vec / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec) + 1e-9
    )

    ranked = sorted(zip(scores, rows), key=lambda x: x[0], reverse=True)[:top_k]
    results = []
    for score, row in ranked:
        r = dict(row)
        del r["embedding"]
        r["score"] = float(score)
        results.append(r)
    return results


def main():
    parser = argparse.ArgumentParser(description="Search MemeVault")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("query", nargs="?", help="Search query (omit to list all)")
    group.add_argument("--id", dest="meme_id", type=int, help="Fetch a single entry by ID")
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="Include non-approved memes")
    parser.add_argument("--semantic", action="store_true",
                        help="Use embedding-based cosine similarity search")
    args = parser.parse_args()

    if args.meme_id is not None:
        results = fetch_by_id(args.meme_id)
        if not results:
            print(f"No entry found with id {args.meme_id}.")
            return
        print_results(results)
    elif args.query:
        if args.semantic:
            results = semantic_search(args.query, args.include_all)
            print(f"{len(results)} result(s) for '{args.query}' (semantic)\n")
        else:
            results = search(args.query, args.include_all)
            print(f"{len(results)} result(s) for '{args.query}'\n")
        print_results(results)
    else:
        results = list_all(args.include_all)
        print(f"{len(results)} total entries\n")
        print_results(results)


if __name__ == "__main__":
    main()
