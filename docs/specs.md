# MemeVault — File Specifications

---

## `database.py`

Shared SQLite abstraction layer. All other modules import from this.

**Responsibilities:**
- Open and return a connection to the SQLite database
- Initialize schema on first run (create tables if not exist)
- Provide lightweight query helpers (fetch one, fetch many, execute)
- Handle transactions

**Schema to initialize:**

```sql
CREATE TABLE IF NOT EXISTS memes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256       TEXT NOT NULL UNIQUE,
    path         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'new',  -- new | review | approved | rejected
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
    source     TEXT NOT NULL,  -- 'ai' | 'manual'
    confidence REAL,
    PRIMARY KEY (meme_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memes_fts USING fts5(
    caption, ocr_text, content='memes', content_rowid='id'
);
```

**Public interface:**
- `get_connection(db_path: str) -> sqlite3.Connection`
- `init_schema(conn)`
- `get_db(db_path: str) -> sqlite3.Connection` — opens + initializes in one call

---

## `ingest.py`

CLI script. Scans a directory and registers new images into the database.

**Responsibilities:**
- Accept a directory path as argument
- Recursively find image files (jpg, jpeg, png, gif, webp)
- Compute SHA256 for each file
- Skip files already present in `memes` (by sha256)
- Insert new rows with `status = 'new'`

**CLI usage:**
```
python ingest.py <directory>
```

**Key logic:**
- Use `hashlib.sha256` with chunked reads for large files
- Store absolute path in `memes.path`
- Print a summary: N new, N skipped (duplicates)

---

## `tagger.py`

CLI/worker script. Processes `status = 'new'` memes and generates metadata.

**Responsibilities:**
- Query all memes with `status = 'new'`
- For each meme:
  - Run OCR via Tesseract (`pytesseract`)
  - Run caption + tag generation via a local vision-language model
  - Insert tags into `tags` and `meme_tags` (source = 'ai')
  - Update `memes` row: set caption, ocr_text, processed_at, status = 'review'

**CLI usage:**
```
python tagger.py
```

**Notes:**
- Model loading should happen once before the loop, not per image
- Confidence values should be stored in `meme_tags.confidence` where available
- OCR result stored as-is in `memes.ocr_text`
- VLM: Qwen2.5-VL-3B-Instruct loaded in 4-bit via `bitsandbytes` (~2GB VRAM)
- VLM is prompted to return JSON `{"caption": "...", "tags": [...]}` for structured output
- Tesseract OCR is optional; Qwen2.5-VL handles embedded text extraction adequately

---

## `review.py`

Interactive Qt GUI. Presents `status = 'review'` memes for human approval.

**Responsibilities:**
- Show one meme at a time with its image preview
- Display and allow editing of: caption, tags, ocr_text
- Actions: Approve, Reject, Skip (keyboard shortcuts)
- On approve: set `status = 'approved'`, save any edits, set `reviewed_at`
- On reject: set `status = 'rejected'`, set `reviewed_at`
- On skip: move to next without changing status
- Show perceptual-hash similar memes alongside the current item (duplicate hint)

**UI layout (single window):**
- Left panel: image preview
- Right panel: metadata fields (caption, tags, ocr_text) — editable
- Bottom bar: Approve / Reject / Skip buttons with keyboard shortcuts
- Side panel or overlay: similar memes thumbnails (if any)

**Keyboard shortcuts:**
- `A` — Approve
- `R` — Reject
- `S` or `Space` — Skip

**Perceptual hashing:**
- Use `imagehash` library (e.g., `phash`)
- On load, compute phash for current image
- Query recent approved/review memes, compare hamming distance
- Show thumbnails of matches below a configurable threshold (e.g., ≤ 10)

---

## `search.py`

CLI search interface. Queries approved memes by tag, text, or caption.

**Responsibilities:**
- Accept a query string as argument
- Search across: tags (by name), OCR text (FTS), caption (FTS)
- Print results: path, status, matched tags, caption snippet

**CLI usage:**
```
python search.py <query>
```

**Search strategy:**
1. Tag match: find memes linked to tags whose name matches the query (LIKE or exact)
2. FTS match: query `memes_fts` for caption and ocr_text hits
3. Merge and deduplicate results, rank by number of matches
4. Only return `status = 'approved'` memes by default; `--all` flag includes others

**Output format (stdout):**
```
[id] path/to/file.jpg
  caption: ...
  tags: tag1, tag2
  ocr: ...
```

---

## `config.py`

Shared configuration constants. Imported by all modules.

**Contents:**
- `DB_PATH` — path to the SQLite database file (default: `~/.memevault/vault.db`)
- `INCOMING_DIR` — default ingestion directory (default: `~/Pictures/memes/incoming`)
- `PHASH_THRESHOLD` — hamming distance threshold for duplicate detection (default: `10`)
- `SUPPORTED_EXTENSIONS` — set of image extensions to scan
- `VLM_MODEL` — HuggingFace model ID or local path for the vision-language model (default: `Qwen/Qwen2.5-VL-3B-Instruct`)

---

## File Tree

```
memevault/
├── config.py
├── database.py
├── ingest.py
├── tagger.py
├── review.py
├── search.py
└── docs/
    ├── concept.md
    └── specs.md
```

---

## Status Flow

```
new  →  review  →  approved
                →  rejected
```

All transitions are written to the database. No filesystem moves occur.
