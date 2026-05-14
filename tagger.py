import os
import re
import subprocess
import sys
from datetime import datetime, timezone

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

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

CAPTION_PROMPT = "Describe this image in one sentence."
TAGS_PROMPT = "List up to 8 short tags for this image, comma-separated, no explanation."


def _gpu_max_memory() -> dict | None:
    """Cap GPU usage at 90% of free VRAM, spill remainder to CPU RAM."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, _ = torch.cuda.mem_get_info(0)
        cap_mib = int(free * 0.90 / 1024 ** 2)
        return {0: f"{cap_mib}MiB", "cpu": "16GiB"}
    except Exception:
        return None


def load_vlm():
    """Load Qwen2.5-VL processor and model once. Returns (processor, model) or None."""
    try:
        from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
        processor = AutoProcessor.from_pretrained(config.VLM_MODEL)
        model = AutoModelForImageTextToText.from_pretrained(
            config.VLM_MODEL,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True),
            device_map="auto",
            max_memory=_gpu_max_memory(),
        )
        return processor, model
    except ImportError as e:
        print(f"Warning: VLM unavailable ({e}) — skipping captioning", file=sys.stderr)
        return None


_MAX_IMAGE_SIZE = 512  # cap longest edge to limit visual tokens


def _resize(image: Image.Image) -> Image.Image:
    w, h = image.size
    if max(w, h) <= _MAX_IMAGE_SIZE:
        return image
    scale = _MAX_IMAGE_SIZE / max(w, h)
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _query(processor, model, image: Image.Image, prompt: str) -> str:
    import torch
    messages = [{"role": "user", "content": [
        {"type": "image", "image": _resize(image.convert("RGB"))},
        {"type": "text", "text": prompt},
    ]}]
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt",
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=100)
    result = processor.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
    del inputs, out
    torch.cuda.empty_cache()
    return result


def run_vlm(image: Image.Image, vlm) -> tuple[str, list[str]]:
    """Return (caption, tags) from Qwen2.5-VL."""
    if vlm is None:
        return "", []

    processor, model = vlm
    caption = _query(processor, model, image, CAPTION_PROMPT)
    tags_raw = _query(processor, model, image, TAGS_PROMPT)

    # Parse comma-separated tags, normalise to lowercase
    stopwords = {
        "with", "that", "this", "from", "have", "there", "their", "they",
        "when", "after", "before", "about", "would", "could", "should",
    }
    # Parse tags: split on commas, newlines, or spaces; normalise to lowercase
    tags = [t.strip().lower() for t in re.split(r"[,\n\s]+", tags_raw) if t.strip()]
    tags = [re.sub(r"[^a-z0-9 _-]", "", t) for t in tags]
    tags = [t for t in tags if t and t not in stopwords][:8]

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
# Embeddings: jina-embeddings-v5-omni-small
# ---------------------------------------------------------------------------

def load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(
            config.EMBEDDING_MODEL,
            trust_remote_code=True,
            model_kwargs={"modality": "vision"},
            device_map="auto",
            max_memory=_gpu_max_memory(),
        )
    except ImportError as e:
        print(f"Warning: sentence-transformers unavailable ({e}) — skipping embeddings", file=sys.stderr)
        return None


def run_embedding(embedder, image: Image.Image):
    import numpy as np
    vec = embedder.encode_document(image)
    return np.array(vec, dtype="float32").tobytes()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_vlm_pass(db_path: str):
    """Pass 1: VLM (caption, tags, OCR)."""
    conn = database.get_db(db_path)
    rows = conn.execute("SELECT id, path FROM memes WHERE status = 'new'").fetchall()
    if not rows:
        return
    vlm = load_vlm()
    for meme_id, path in rows:
        print(f"[VLM] [{meme_id}] {path}")
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


def run_emb_pass(db_path: str):
    """Pass 2: Embeddings."""
    conn = database.get_db(db_path)
    rows = conn.execute(
        """SELECT m.id, m.path FROM memes m
           LEFT JOIN meme_embeddings e ON e.meme_id = m.id
           WHERE m.status = 'review' AND e.meme_id IS NULL"""
    ).fetchall()
    if not rows:
        return
    embedder = load_embedder()
    if embedder is None:
        return
    for meme_id, path in rows:
        print(f"[EMB] [{meme_id}] {path}")
        try:
            image = Image.open(path)
        except Exception as e:
            print(f"  Error opening image: {e}", file=sys.stderr)
            continue
        blob = run_embedding(embedder, image)
        conn.execute(
            "INSERT OR REPLACE INTO meme_embeddings (meme_id, embedding) VALUES (?, ?)",
            (meme_id, blob),
        )
        conn.commit()


def _wait_for_gpu_memory(min_free_mib: int = 2048, timeout: int = 30):
    """Poll nvidia-smi until at least min_free_mib MiB is free on GPU 0."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                text=True,
            )
            free_mib = int(out.strip().splitlines()[0])
            if free_mib >= min_free_mib:
                return
        except Exception:
            return  # nvidia-smi unavailable, proceed anyway
        time.sleep(1)
    print(f"Warning: GPU did not free {min_free_mib} MiB within {timeout}s, proceeding anyway.", file=sys.stderr)


def run(db_path: str = str(config.DB_PATH)):
    conn = database.get_db(db_path)
    rows = conn.execute("SELECT id, path FROM memes WHERE status = 'new'").fetchall()
    if not rows:
        print("No new memes to process.")
        return
    print(f"Processing {len(rows)} meme(s) in two passes...")
    subprocess.run([sys.executable, __file__, "--vlm-only", db_path], check=True)
    _wait_for_gpu_memory()
    subprocess.run([sys.executable, __file__, "--emb-only", db_path], check=True)
    print(f"Done. Processed {len(rows)} meme(s).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--vlm-only":
        run_vlm_pass(sys.argv[2] if len(sys.argv) > 2 else str(config.DB_PATH))
    elif len(sys.argv) > 1 and sys.argv[1] == "--emb-only":
        run_emb_pass(sys.argv[2] if len(sys.argv) > 2 else str(config.DB_PATH))
    else:
        run()
