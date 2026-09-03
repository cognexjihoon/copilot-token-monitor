"""Draws the tray icon on the fly (colored circle + percentage) instead of
shipping image assets."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap

SIZE = 64
# leave a small margin so the glyph doesn't touch the circle's edge
_TEXT_BUDGET = SIZE * 0.8
_TEXT_COLOR = QColor("#000000")


def _max_fitting_font(text: str) -> QFont:
    """Largest bold point size whose bounding box still fits inside the
    circle, so 1-, 2-digit and "!"/"?" glyphs are all drawn as big as
    possible instead of a size picked by digit-count guesswork."""
    font = QFont("Segoe UI", 1, QFont.Bold)
    for size in range(48, 5, -1):
        font.setPointSize(size)
        rect = QFontMetrics(font).tightBoundingRect(text)
        if rect.width() <= _TEXT_BUDGET and rect.height() <= _TEXT_BUDGET:
            break
    return font


def _draw_badge(color: str, text: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(2, 2, SIZE - 4, SIZE - 4))

    painter.setFont(_max_fitting_font(text))
    painter.setPen(_TEXT_COLOR)
    painter.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, text)

    painter.end()
    return QIcon(pixmap)


def make_icon(pct: float, color: str) -> QIcon:
    text = f"{int(min(pct, 99))}" if pct < 100 else "!"
    return _draw_badge(color, text)


def make_error_icon() -> QIcon:
    return _draw_badge("#7f8c8d", "?")
