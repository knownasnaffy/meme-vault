"""review.py — Interactive meme review UI for MemeVault."""

import sys
from datetime import datetime, timezone

import imagehash
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import DB_PATH, PHASH_THRESHOLD
from database import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_next(conn):
    """Return the next meme row with status='review', or None."""
    return conn.execute(
        "SELECT id, path, caption, ocr_text FROM memes WHERE status='review' ORDER BY id LIMIT 1"
    ).fetchone()


def _fetch_tags(conn, meme_id: int) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT t.name FROM tags t JOIN meme_tags mt ON mt.tag_id=t.id WHERE mt.meme_id=?",
            (meme_id,),
        )
    ]


def _upsert_tags(conn, meme_id: int, tags_text: str):
    """Replace all tags for a meme with the given comma-separated string."""
    conn.execute("DELETE FROM meme_tags WHERE meme_id=?", (meme_id,))
    for raw in tags_text.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO meme_tags(meme_id, tag_id, source) VALUES(?,?,'manual')",
            (meme_id, tag_id),
        )


def _find_similar(conn, phash, current_id: int) -> list[str]:
    """Return paths of memes whose phash is within PHASH_THRESHOLD of phash."""
    rows = conn.execute(
        "SELECT id, path FROM memes WHERE id != ? AND status IN ('review','approved') AND phash IS NOT NULL",
        (current_id,),
    ).fetchall()
    similar = []
    for row_id, path in rows:
        stored = conn.execute("SELECT phash FROM memes WHERE id=?", (row_id,)).fetchone()
        if stored and stored[0]:
            try:
                dist = phash - imagehash.hex_to_hash(stored[0])
                if dist <= PHASH_THRESHOLD:
                    similar.append(path)
            except Exception:
                pass
    return similar


class ReviewWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.current = None  # (id, path, caption, ocr_text)
        self.current_phash = None

        self.setWindowTitle("MemeVault — Review")
        self._build_ui()
        self._add_shortcuts()
        self._load_next()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)

        # Left: image preview
        self.image_label = QLabel(alignment=Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(self.image_label, stretch=3)

        # Right: metadata + similar + actions
        right = QVBoxLayout()
        outer.addLayout(right, stretch=2)

        right.addWidget(QLabel("<b>Caption</b>"))
        self.caption_edit = QPlainTextEdit()
        self.caption_edit.setMaximumHeight(80)
        right.addWidget(self.caption_edit)

        right.addWidget(QLabel("<b>Tags</b> (comma-separated)"))
        self.tags_edit = QPlainTextEdit()
        self.tags_edit.setMaximumHeight(60)
        right.addWidget(self.tags_edit)

        right.addWidget(QLabel("<b>OCR Text</b>"))
        self.ocr_edit = QPlainTextEdit()
        self.ocr_edit.setMaximumHeight(80)
        right.addWidget(self.ocr_edit)

        # Similar thumbnails
        right.addWidget(QLabel("<b>Similar memes</b>"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(130)
        self.similar_widget = QWidget()
        self.similar_layout = QHBoxLayout(self.similar_widget)
        self.similar_layout.setAlignment(Qt.AlignLeft)
        scroll.setWidget(self.similar_widget)
        right.addWidget(scroll)

        # Action bar
        bar = QHBoxLayout()
        right.addLayout(bar)
        for label, slot in [("Approve [A]", self.approve), ("Reject [R]", self.reject), ("Skip [Space]", self.skip)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            bar.addWidget(btn)

        self.status_label = QLabel("")
        right.addWidget(self.status_label)

    def _add_shortcuts(self):
        QShortcut(QKeySequence("A"), self).activated.connect(self.approve)
        QShortcut(QKeySequence("R"), self).activated.connect(self.reject)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.skip)

    # ----------------------------------------------------------- data load --

    def _load_next(self):
        self.current = _fetch_next(self.conn)
        if not self.current:
            self._show_empty()
            return

        meme_id, path, caption, ocr_text = self.current
        tags = _fetch_tags(self.conn, meme_id)

        # Image preview
        pix = QPixmap(path)
        if not pix.isNull():
            self.image_label.setPixmap(
                pix.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.image_label.setText("(cannot load image)")

        # Metadata fields
        self.caption_edit.setPlainText(caption or "")
        self.tags_edit.setPlainText(", ".join(tags))
        self.ocr_edit.setPlainText(ocr_text or "")

        # Perceptual hash + similar
        self.current_phash = None
        self._clear_similar()
        try:
            img = Image.open(path)
            self.current_phash = imagehash.phash(img)
            # Persist phash if not stored
            self.conn.execute("UPDATE memes SET phash=? WHERE id=?", (str(self.current_phash), meme_id))
            self.conn.commit()
            similar_paths = _find_similar(self.conn, self.current_phash, meme_id)
            self._show_similar(similar_paths)
        except Exception:
            pass

        self.status_label.setText(f"ID {meme_id} — {path}")

    def _show_empty(self):
        self.image_label.setText("No memes pending review.")
        self.caption_edit.clear()
        self.tags_edit.clear()
        self.ocr_edit.clear()
        self._clear_similar()
        self.status_label.setText("Queue empty.")

    def _clear_similar(self):
        while self.similar_layout.count():
            item = self.similar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_similar(self, paths: list[str]):
        for path in paths[:8]:
            pix = QPixmap(path)
            if pix.isNull():
                continue
            lbl = QLabel()
            lbl.setPixmap(pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl.setToolTip(path)
            self.similar_layout.addWidget(lbl)

    # ------------------------------------------------------------ actions --

    def approve(self):
        if not self.current:
            return
        meme_id = self.current[0]
        caption = self.caption_edit.toPlainText().strip()
        ocr_text = self.ocr_edit.toPlainText().strip()
        tags_text = self.tags_edit.toPlainText()
        self.conn.execute(
            "UPDATE memes SET status='approved', caption=?, ocr_text=?, reviewed_at=? WHERE id=?",
            (caption, ocr_text, _now_iso(), meme_id),
        )
        _upsert_tags(self.conn, meme_id, tags_text)
        self.conn.commit()
        self._load_next()

    def reject(self):
        if not self.current:
            return
        self.conn.execute(
            "UPDATE memes SET status='rejected', reviewed_at=? WHERE id=?",
            (_now_iso(), self.current[0]),
        )
        self.conn.commit()
        self._load_next()

    def skip(self):
        if not self.current:
            return
        # Move to end of queue by bumping id — just reload next excluding current temporarily
        # Simplest: rotate by re-querying excluding current id until wrap
        skipped_id = self.current[0]
        nxt = self.conn.execute(
            "SELECT id, path, caption, ocr_text FROM memes WHERE status='review' AND id != ? ORDER BY id LIMIT 1",
            (skipped_id,),
        ).fetchone()
        if nxt:
            self.current = nxt
            meme_id, path, caption, ocr_text = self.current
            tags = _fetch_tags(self.conn, meme_id)
            pix = QPixmap(path)
            if not pix.isNull():
                self.image_label.setPixmap(
                    pix.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            self.caption_edit.setPlainText(caption or "")
            self.tags_edit.setPlainText(", ".join(tags))
            self.ocr_edit.setPlainText(ocr_text or "")
            self._clear_similar()
            try:
                img = Image.open(path)
                self.current_phash = imagehash.phash(img)
                self.conn.execute("UPDATE memes SET phash=? WHERE id=?", (str(self.current_phash), meme_id))
                self.conn.commit()
                self._show_similar(_find_similar(self.conn, self.current_phash, meme_id))
            except Exception:
                pass
            self.status_label.setText(f"ID {meme_id} — {path}")
        else:
            self.status_label.setText("Only one item in queue — cannot skip.")


def main():
    conn = get_db(str(DB_PATH))
    # Add phash column if missing (schema migration)
    try:
        conn.execute("ALTER TABLE memes ADD COLUMN phash TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists

    app = QApplication(sys.argv)
    win = ReviewWindow(conn)
    win.resize(1100, 650)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
