# MemeVault — Task Plan

---

## Phase 1: Foundation

- [x] **1.1** Create `config.py` with DB_PATH, INCOMING_DIR, PHASH_THRESHOLD, SUPPORTED_EXTENSIONS
- [x] **1.2** Create `database.py`: connection, schema init, `get_db()`
- [x] **1.3** Verify schema creates correctly on a fresh SQLite file (manual test)

---

## Phase 2: Ingestion

- [x] **2.1** Create `ingest.py`: recursive file scan, SHA256 hashing, duplicate detection, insert `status = 'new'`
- [x] **2.2** Test ingestion with a sample directory: confirm new files inserted, duplicates skipped, summary printed

---

## Phase 3: Tagging

- [x] **3.1** Create `tagger.py`: query `status = 'new'`, run Tesseract OCR, store `ocr_text`
- [x] **3.2** Integrate local vision-language model: generate caption and tags
- [x] **3.3** Write tags to `tags` and `meme_tags` (source = 'ai', confidence where available)
- [x] **3.4** Update meme row: caption, processed_at, `status = 'review'`
- [x] **3.5** Test tagger end-to-end on a small batch

---

## Phase 4: Review UI

- [ ] **4.1** Scaffold `review.py` Qt window: image preview panel, metadata panel, action bar
- [ ] **4.2** Load next `status = 'review'` meme on launch and after each action
- [ ] **4.3** Implement Approve (A), Reject (R), Skip (Space) with DB writes and `reviewed_at`
- [ ] **4.4** Make caption, tags, ocr_text fields editable; persist edits on approve
- [ ] **4.5** Implement perceptual hash computation (`imagehash.phash`) on image load
- [ ] **4.6** Query and display similar meme thumbnails (hamming distance ≤ PHASH_THRESHOLD)
- [ ] **4.7** End-to-end review test: approve, reject, skip, verify DB state

---

## Phase 5: Search

- [ ] **5.1** Create `search.py`: tag match (LIKE), FTS match on caption + ocr_text, merge + deduplicate results
- [ ] **5.2** Add `--all` flag to include non-approved memes
- [ ] **5.3** Test queries: tag-only, text-only, mixed, `--all`

---

## Phase 6: Polish

- [ ] **6.1** Add `requirements.txt` (pytesseract, imagehash, PySide6 or PyQt6, and any model deps)
- [ ] **6.2** Add a top-level `README.md` with setup and usage instructions for each script
- [ ] **6.3** Smoke test full workflow: ingest → tag → review → search
