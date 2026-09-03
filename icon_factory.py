"""Draws the tray icon on the fly (colored circle + percentage) instead of
shipping image assets."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap

SIZE = 64
_MARGIN = 1  # just enough room for the antialiased edge, circle fills the rest
_DIAMETER = SIZE - 2 * _MARGIN
# a rectangle fits inside a circle iff its *diagonal* fits the diameter, not
# each side independently -- checking width/height separately (the previous
# bug) let glyph corners poke outside the circle.
_TEXT_FIT_FACTOR = 0.94
_TEXT_COLOR = QColor("#000000")


def _max_fitting_font(text: str) -> QFont:
    """Largest bold point size whose tight bounding box still fits inside
    the circle (by diagonal), so 1-, 2-digit and "!"/"?" glyphs are all
    drawn as big as possible without corners overflowing the circle."""
    limit = _DIAMETER * _TEXT_FIT_FACTOR
    font = QFont("Segoe UI", 1, QFont.Bold)
    for size in range(56, 5, -1):
        font.setPointSize(size)
        rect = QFontMetrics(font).tightBoundingRect(text)
        if math.hypot(rect.width(), rect.height()) <= limit:
            break
    return font


def _draw_badge(color: str, text: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(_MARGIN, _MARGIN, _DIAMETER, _DIAMETER))

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
