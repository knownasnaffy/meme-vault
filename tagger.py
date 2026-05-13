import re
import sys
from datetime import datetime, timezone

from PIL import Image

import config
import database


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def run_ocr(image: Image.Image) -> str:
    try:
        import pytesseract
        return pytesseract.image_to_string(image).strip()
    except ImportError:
        print("Warning: pytesseract not installed — skipping OCR", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# VLM: caption + tags
# ---------------------------------------------------------------------------

def load_vlm():
    """Load VLM processor and model once. Returns (processor, model) or None."""
    try:
        from transformers import BlipProcessor, BlipForConditionalGeneration
        processor = BlipProcessor.from_pretrained(config.VLM_MODEL)
        model = BlipForConditionalGeneration.from_pretrained(config.VLM_MODEL)
        return processor, model
    except ImportError:
        print("Warning: transformers not installed — skipping VLM captioning", file=sys.stderr)
        return None


def run_vlm(image: Image.Image, vlm) -> tuple[str, list[str]]:
    """Return (caption, tags). Tags are words extracted from the caption."""
    if vlm is None:
        return "", []
    processor, model = vlm
    import torch
    inputs = processor(image.convert("RGB"), return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=50)
    caption = processor.decode(out[0], skip_special_tokens=True).strip()
    # Derive simple tags: lowercase words ≥4 chars, no stopwords
    stopwords = {"with", "that", "this", "from", "have", "there", "their", "they"}
    tags = list({w for w in re.findall(r"[a-z]{4,}", caption.lower()) if w not in stopwords})
    return caption, tags


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def upsert_tag(conn, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]


def write_tags(conn, meme_id: int, tags: list[str]):
    for tag in tags:
        tag_id = upsert_tag(conn, tag)
        conn.execute(
            "INSERT OR IGNORE INTO meme_tags (meme_id, tag_id, source) VALUES (?, ?, 'ai')",
            (meme_id, tag_id),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(db_path: str = str(config.DB_PATH)):
    conn = database.get_db(db_path)
    rows = conn.execute("SELECT id, path FROM memes WHERE status = 'new'").fetchall()

    if not rows:
        print("No new memes to process.")
        return

    vlm = load_vlm()

    for meme_id, path in rows:
        print(f"Processing [{meme_id}] {path}")
        try:
            image = Image.open(path)
        except Exception as e:
            print(f"  Error opening image: {e}", file=sys.stderr)
            continue

        ocr_text = run_ocr(image)
        caption, tags = run_vlm(image, vlm)
        write_tags(conn, meme_id, tags)

        conn.execute(
            """UPDATE memes
               SET ocr_text = ?, caption = ?, processed_at = ?, status = 'review'
               WHERE id = ?""",
            (ocr_text or None, caption or None, datetime.now(timezone.utc).isoformat(), meme_id),
        )
        conn.commit()
        print(f"  caption: {caption!r}  tags: {tags}  ocr: {ocr_text[:60]!r}")

    print(f"Done. Processed {len(rows)} meme(s).")


if __name__ == "__main__":
    run()
