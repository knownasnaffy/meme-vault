import json
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
        return ""  # Qwen2.5-VL handles text extraction; Tesseract is optional


# ---------------------------------------------------------------------------
# VLM: caption + tags via Qwen2.5-VL
# ---------------------------------------------------------------------------

PROMPT = (
    "Describe this image in one sentence, then list up to 8 relevant tags. "
    "Respond as JSON: {\"caption\": \"...\", \"tags\": [\"...\"]}"
)


def load_vlm():
    """Load Qwen2.5-VL processor and model once. Returns (processor, model) or None."""
    try:
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
        processor = AutoProcessor.from_pretrained(config.VLM_MODEL)
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            config.VLM_MODEL,
            load_in_4bit=True,  # ~2GB VRAM via bitsandbytes
        )
        return processor, model
    except ImportError as e:
        print(f"Warning: VLM unavailable ({e}) — skipping captioning", file=sys.stderr)
        return None


def run_vlm(image: Image.Image, vlm) -> tuple[str, list[str]]:
    """Return (caption, tags) from Qwen2.5-VL."""
    if vlm is None:
        return "", []

    processor, model = vlm
    messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image.convert("RGB")], return_tensors="pt").to(model.device)

    import torch
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200)

    # Decode only the newly generated tokens
    generated = out[:, inputs["input_ids"].shape[1]:]
    response = processor.decode(generated[0], skip_special_tokens=True).strip()

    # Parse JSON response; fall back to raw text as caption if malformed
    try:
        data = json.loads(response[response.index("{"):response.rindex("}") + 1])
        caption = data.get("caption", "").strip()
        tags = [t.strip().lower() for t in data.get("tags", []) if t.strip()]
    except (ValueError, KeyError):
        caption = response
        tags = list({w for w in re.findall(r"[a-z]{4,}", response.lower())
                     if w not in {"with", "that", "this", "from", "have", "there", "their", "they"}})

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
