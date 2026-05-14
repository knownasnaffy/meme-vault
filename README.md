# MemeVault

Local-first AI-assisted meme archival and retrieval system.

Organises image collections using a local vision-language model (Qwen2.5-VL-3B), perceptual hashing, and a keyboard-driven review UI. Everything runs on-device — no cloud APIs.

## Requirements

- Python 3.10+
- NVIDIA GPU with ~2 GB VRAM (for 4-bit VLM inference)
- CUDA toolkit matching your PyTorch build
- (Optional) [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed system-wide for standalone OCR

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Download the model

```bash
.venv/bin/hf download Qwen/Qwen2.5-VL-3B-Instruct --local-dir ./models/qwen2.5-vl-3b
```

The model path is configured in `config.py` (`VLM_MODEL`). Change it if you store the model elsewhere or use a different model.

## Configuration

Edit `config.py` to adjust defaults:

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `~/.memevault/vault.db` | SQLite database location |
| `INCOMING_DIR` | `~/Pictures/memes/incoming` | Default ingestion directory |
| `PHASH_THRESHOLD` | `10` | Hamming distance for duplicate detection |
| `SUPPORTED_EXTENSIONS` | jpg, jpeg, png, gif, webp | Image formats to scan |
| `VLM_MODEL` | `./models/qwen2.5-vl-3b` | HuggingFace repo ID or local path |

## Workflow

```
ingest → tag → review → search
```

### 1. Ingest

Scan a directory and register new images into the database:

```bash
.venv/bin/python ingest.py /path/to/images
```

Output: `N new, N skipped (duplicates)`

Duplicate detection is SHA256-based — re-ingesting the same directory is safe.

### 2. Tag

Process all `new` memes with the VLM to generate captions and tags:

```bash
.venv/bin/python tagger.py
```

Each image is captioned and tagged by Qwen2.5-VL (4-bit quantised). Results are written to the database and status is set to `review`.

Tesseract OCR runs automatically if installed; otherwise the VLM handles embedded text.

### 3. Review

Launch the interactive review UI:

```bash
.venv/bin/python review.py
```

| Key | Action |
|---|---|
| `A` | Approve — saves any edits, marks approved |
| `R` | Reject |
| `Space` | Skip — move to next without changing status |

The right panel shows editable caption, tags (comma-separated), and OCR text. Perceptually similar memes are shown as thumbnails below the metadata fields.

### 4. Search

Search approved memes by tag, caption, or OCR text:

```bash
.venv/bin/python search.py "query"
```

Include non-approved memes:

```bash
.venv/bin/python search.py "query" --all
```

Output:

```
[id] /path/to/file.jpg
  caption: ...
  tags: tag1, tag2
  ocr: ...
```

## File Overview

| File | Purpose |
|---|---|
| `config.py` | Shared constants |
| `database.py` | SQLite schema and connection helpers |
| `ingest.py` | Filesystem scanner and ingestion pipeline |
| `tagger.py` | VLM-based caption and tag generation |
| `review.py` | Qt review UI |
| `search.py` | CLI search interface |
| `search_ui.py` | Qt visual search browser with clipboard copy |
