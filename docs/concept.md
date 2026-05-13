# MemeVault
Local-first AI-assisted meme archival and retrieval system.

---

# Overview

MemeVault is a local-only desktop utility designed to organize large meme
collections using AI-assisted tagging, OCR extraction, human review workflows,
and searchable metadata.

The system is designed specifically for chaotic internet image collections such
as:
- manhwa memes
- reaction images
- anime screenshots
- shitposts
- cropped edits
- template variants

Unlike traditional gallery software, MemeVault treats memes as searchable
semantic artifacts rather than ordinary photos.

The workflow combines:
- automated AI analysis
- human verification
- structured metadata
- fast local search

The system is intentionally:
- keyboard-first
- offline-first
- database-driven
- minimal in dependencies
- Linux-friendly

---

# Core Design Principles

## Local-only
All processing occurs on-device.

No cloud APIs.
No external storage.
No telemetry.

---

## Human-in-the-loop
AI suggestions are never trusted blindly.

The workflow is:

```txt
image
  ↓
AI analysis
  ↓
human review
  ↓
approved archive
```

This is critical because memes contain:
- irony
- sarcasm
- fandom references
- layered humor
- intentionally misleading imagery

---

## Database-driven state
Filesystem structure is not used to represent workflow state.

The database is the source of truth.

Files remain stable after ingestion.

---

## Immutable media storage
Files are never renamed or moved after ingestion.

Each file is identified using its SHA256 hash.

This avoids:
- duplicate ingestion
- sync instability
- broken references
- rename conflicts

---

# System Architecture

## Components

### tagger.py
AI analysis worker.

Responsibilities:
- image caption generation
- tag suggestion
- OCR extraction
- embedding generation (future)

Produces metadata for ingestion into the database.

---

### review.py
Interactive review application.

Responsibilities:
- display pending review items
- image preview
- metadata editing
- approval/rejection workflow

Primary human interaction interface.

---

### search.py
Search and retrieval interface.

Responsibilities:
- tag search
- OCR text search
- semantic retrieval (future)
- archive browsing

---

### database.py
Shared database abstraction layer.

Responsibilities:
- SQLite connection management
- query helpers
- schema initialization
- transaction handling

Shared across all scripts.

---

### ingest.py
Filesystem ingestion pipeline.

Responsibilities:
- scan configured directories
- compute SHA256 hashes
- detect duplicates
- register new files
- trigger processing workflow

---

# Workflow

## 1. Ingestion

User places images into configured ingestion directory.

Example:

```txt
~/Pictures/memes/incoming
```

The system:
- scans for files
- computes SHA256
- checks for duplicates
- registers new entries in SQLite

New entries are marked:

```txt
status = "new"
```

---

## 2. Processing

Unprocessed items are analyzed by `tagger.py`.

Generated metadata may include:
- tags
- caption
- OCR text
- confidence values
- embeddings (future)

Items are then marked:

```txt
status = "review"
```

---

## 3. Review

`review.py` presents pending items to the user.

The user may:
- approve
- edit metadata
- reject
- skip

Similar items are shown in parallel to the current item to confirm possible
duplicates detected via perceptual hashing.

Approved items become:

```txt
status = "approved"
```

Rejected items become:

```txt
status = "rejected"
```

---

## 4. Search

`search.py` allows retrieval using:
- tags
- OCR text
- captions
- semantic similarity (future)

---

# Database Design

## memes

Primary archive table.

Suggested fields:

| Field | Purpose |
|---|---|
| id | internal identifier |
| sha256 | content hash |
| path | absolute filesystem path |
| status | workflow state |
| caption | AI-generated caption |
| ocr_text | extracted text |
| created_at | ingestion timestamp |
| processed_at | AI processing timestamp |
| reviewed_at | human review timestamp |

---

## tags

Normalized tag registry.

| Field | Purpose |
|---|---|
| id | tag identifier |
| name | canonical tag |

---

## meme_tags

Many-to-many relationship table.

| Field | Purpose |
|---|---|
| meme_id | linked meme |
| tag_id | linked tag |
| source | ai/manual |
| confidence | optional score |

---

# Planned Features

## Semantic Search
Embedding-based similarity retrieval.

Example:

```txt
"find memes with exhausted existential energy"
```

---

## Duplicate Detection
- SHA256-based
- Perceptual hash-based (p-hash or something that's common for this case)

---

## Keyboard-first Workflow
Designed for:
- fast moderation
- low-friction review
- power-user interaction

---

## Future Metadata Export
Potential support for:
- XMP
- EXIF
- sidecar JSON export

Not required for core functionality.

---

# Non-Goals

The system intentionally avoids:
- cloud sync logic
- social features
- web deployment
- mobile clients
- heavy GUI frameworks
- filesystem state management
- automatic approval pipelines

---

# Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| Database | SQLite |
| OCR | Tesseract OCR |
| AI Models | Local vision-language models |
| UI | Qt (PyQt/PySide) |
| Search | SQLite FTS / vector search (future) |

---

# Long-term Vision

MemeVault aims to become a personal semantic archive for internet culture
artifacts.

The goal is not merely storing images.

The goal is making chaotic visual information:
- searchable
- contextual
- retrievable
- curated
- understandable
over long periods of time.
