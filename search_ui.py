"""search_ui.py — Visual meme browser with filter and clipboard copy."""

import hashlib
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, QMimeData, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut, QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QCheckBox, QListWidget, QListWidgetItem, QLabel,
    QSplitter, QSizePolicy, QPushButton, QStatusBar,
)

from search import search, list_all

THUMB_SIZE = 96
PREVIEW_MAX = 480
THUMB_DIR = Path.home() / ".cache" / "memevault" / "thumbnails"
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def _thumb_path(row: dict) -> Path:
    key = row.get("sha256") or hashlib.sha256(row["path"].encode()).hexdigest()
    return THUMB_DIR / f"{key}_{THUMB_SIZE}.jpg"


def _get_thumb(row: dict) -> QPixmap:
    tp = _thumb_path(row)
    if tp.exists():
        return QPixmap(str(tp))
    pix = QPixmap(row["path"])
    if pix.isNull():
        return pix
    thumb = pix.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    thumb.save(str(tp), "JPEG", 85)
    return thumb


# ------------------------------------------------------------------ widgets --

class SearchInput(QLineEdit):
    """QLineEdit with extra word-navigation shortcuts and Enter-to-grid."""

    def __init__(self, on_enter, **kwargs):
        super().__init__(**kwargs)
        self._on_enter = on_enter

    def keyPressEvent(self, e: QKeyEvent):
        key, mod = e.key(), e.modifiers()
        alt = mod == Qt.AltModifier

        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._on_enter()
            return

        if alt and key == Qt.Key_W:          # delete word backward
            self._delete_word_back()
            return
        if alt and key == Qt.Key_D:          # delete word forward
            self._delete_word_forward()
            return
        if alt and key == Qt.Key_B:          # move back one word
            self.cursorWordBackward(False)
            return
        if alt and key == Qt.Key_F:          # move forward one word
            self.cursorWordForward(False)
            return

        super().keyPressEvent(e)

    def _delete_word_back(self):
        pos = self.cursorPosition()
        text = self.text()
        # skip trailing spaces then find word boundary
        i = pos
        while i > 0 and text[i - 1] == " ":
            i -= 1
        while i > 0 and text[i - 1] != " ":
            i -= 1
        self.setText(text[:i] + text[pos:])
        self.setCursorPosition(i)

    def _delete_word_forward(self):
        pos = self.cursorPosition()
        text = self.text()
        i = pos
        while i < len(text) and text[i] == " ":
            i += 1
        while i < len(text) and text[i] != " ":
            i += 1
        self.setText(text[:pos] + text[i:])
        self.setCursorPosition(pos)


class MemeItem(QListWidgetItem):
    def __init__(self, row: dict):
        super().__init__()
        self.row = row
        thumb = _get_thumb(row)
        if not thumb.isNull():
            self.setIcon(thumb)
        label = (row.get("tags") or row.get("caption") or row["path"].split("/")[-1])[:60]
        self.setText(label)
        self.setToolTip(row["path"])
        self.setSizeHint(QSize(THUMB_SIZE + 16, THUMB_SIZE + 32))


# ------------------------------------------------------------------ widgets --

class MemeGrid(QListWidget):
    """QListWidget with vim-style navigation."""

    def keyPressEvent(self, e: QKeyEvent):
        key = e.key()
        mod = e.modifiers()
        count = self.count()

        if key == Qt.Key_H:
            self._move(-1)
        elif key == Qt.Key_L:
            self._move(1)
        elif key == Qt.Key_K:
            cols = max(1, self._columns())
            self._move(-cols)
        elif key == Qt.Key_J:
            cols = max(1, self._columns())
            self._move(cols)
        elif key == Qt.Key_G and mod == Qt.ShiftModifier:
            self.setCurrentRow(count - 1)
        elif key == Qt.Key_G:
            self.setCurrentRow(0)
        else:
            super().keyPressEvent(e)

    def _move(self, delta: int):
        row = (self.currentRow() or 0) + delta
        row = max(0, min(row, self.count() - 1))
        self.setCurrentRow(row)

    def _columns(self) -> int:
        if not self.count():
            return 1
        item_w = self.sizeHintForColumn(0) + self.spacing() * 2
        return max(1, self.viewport().width() // item_w)


# ------------------------------------------------------------------ window --

class SearchWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MemeVault — Search")
        self._build_ui()
        self._add_shortcuts()
        self._refresh()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self.search_input = SearchInput(
            on_enter=self._focus_grid,
            placeholderText="Search tags, caption, OCR text…  (/ to focus)",
        )
        self.search_input.textChanged.connect(self._on_query_changed)
        bar.addWidget(self.search_input)

        self.all_check = QCheckBox("Include non-approved")
        self.all_check.stateChanged.connect(self._refresh)
        bar.addWidget(self.all_check)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self.grid = MemeGrid()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setSpacing(4)
        self.grid.setMovement(QListWidget.Static)
        self.grid.currentItemChanged.connect(self._on_select)
        self.grid.itemDoubleClicked.connect(self._copy_to_clipboard)
        splitter.addWidget(self.grid)

        right = QWidget()
        right.setMinimumWidth(260)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(240, 240)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setStyleSheet("background:#1a1a1a; border-radius:4px;")
        rl.addWidget(self.preview, stretch=1)

        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setAlignment(Qt.AlignTop)
        self.meta_label.setStyleSheet("color:#aaa; font-size:11px;")
        rl.addWidget(self.meta_label)

        self.copy_btn = QPushButton("Copy to Clipboard  [C]")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        rl.addWidget(self.copy_btn)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._debounce = QTimer(singleShot=True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._refresh)

    def _add_shortcuts(self):
        QShortcut(QKeySequence("C"), self).activated.connect(self._copy_to_clipboard)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.search_input.clear)
        QShortcut(QKeySequence("/"), self).activated.connect(self._focus_input)

    # --------------------------------------------------------- focus helpers --

    def _focus_grid(self):
        if self.grid.count():
            self.grid.setFocus()
            if not self.grid.currentItem():
                self.grid.setCurrentRow(0)

    def _focus_input(self):
        # Only fire when grid (or anything else) has focus, not when already typing
        if self.search_input.hasFocus():
            return
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ----------------------------------------------------------- data load --

    def _on_query_changed(self):
        self._debounce.start()

    def _refresh(self):
        query = self.search_input.text().strip()
        include_all = self.all_check.isChecked()
        results = search(query, include_all) if query else list_all(include_all)

        self.grid.clear()
        for row in results:
            self.grid.addItem(MemeItem(row))

        self.status_bar.showMessage(f"{len(results)} result(s)")
        self._clear_preview()

    # ------------------------------------------------------------ preview --

    def _on_select(self, current, _previous):
        if not isinstance(current, MemeItem):
            self._clear_preview()
            return
        row = current.row
        pix = QPixmap(row["path"])
        if not pix.isNull():
            self.preview.setPixmap(
                pix.scaled(PREVIEW_MAX, PREVIEW_MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.preview.setText("(cannot load)")

        parts = []
        if row.get("caption"):
            parts.append(f"<b>Caption:</b> {row['caption'][:200]}")
        if row.get("tags"):
            parts.append(f"<b>Tags:</b> {row['tags']}")
        if row.get("ocr_text"):
            parts.append(f"<b>OCR:</b> {row['ocr_text'][:200]}")
        parts.append(f"<b>Status:</b> {row.get('status', '—')}")
        self.meta_label.setText("<br>".join(parts))
        self.copy_btn.setEnabled(True)

    def _clear_preview(self):
        self.preview.clear()
        self.meta_label.clear()
        self.copy_btn.setEnabled(False)

    # ----------------------------------------------------------- clipboard --

    def _copy_to_clipboard(self):
        item = self.grid.currentItem()
        if not isinstance(item, MemeItem):
            return
        path = item.row["path"]
        mime = QMimeData()
        img = QImage(path)
        if not img.isNull():
            mime.setImageData(img)
        mime.setUrls([QUrl.fromLocalFile(path)])
        QApplication.clipboard().setMimeData(mime)
        self.status_bar.showMessage(f"Copied: {path}", 3000)


def _qt_message_handler(mode, _ctx, msg):
    if "icc" not in msg.lower():
        print(msg, file=sys.stderr)

def main():
    qInstallMessageHandler(_qt_message_handler)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = SearchWindow()
    win.resize(1100, 680)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
