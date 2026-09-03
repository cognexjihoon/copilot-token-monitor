"""Draws the tray icon on the fly (colored badge + percentage) instead of
shipping image assets."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Drawn well above the ~16-32px a Windows tray icon actually renders at, so
# Qt's downscale has room to antialias cleanly; raising this further has no
# visible effect since the OS caps the displayed size regardless.
SIZE = 64
_MARGIN = 1  # just enough room for the antialiased edge, badge fills the rest
_INNER = SIZE - 2 * _MARGIN
# a slightly rounded square instead of a circle: a circle inscribed in a
# square only covers ~79% of its area (pi/4), so at the same canvas size a
# rounded square lets the glyph be noticeably bigger - the readability the
# user asked for outweighs a perfectly round badge look.
_CORNER_RADIUS = _INNER * 0.18
# unlike fitting inside a circle (which needs a diagonal check), a
# rectangle's width/height can be checked independently against a square.
_TEXT_FIT_FACTOR = 0.90
_TEXT_FILL = QColor("#000000")
_TEXT_OUTLINE = QColor("#ffffff")
_OUTLINE_WIDTH = 3.0
# black digits read fine against every status color except the mid-brightness
# blue "on track" tier - measuring it, its perceived brightness sits almost
# exactly on the black/white text crossover point, so *neither* pure color
# has strong contrast there. A white outline around black fill reads clearly
# against every badge color instead of picking per-color text colors.


def _max_fitting_font(text: str) -> QFont:
    """Largest bold point size whose tight bounding box still fits inside
    the badge (leaving room for the outline stroke), so 1-, 2-digit and
    "!"/"?" glyphs are all drawn as big as possible."""
    limit = _INNER * _TEXT_FIT_FACTOR - _OUTLINE_WIDTH
    font = QFont("Segoe UI", 1, QFont.Bold)
    for size in range(72, 5, -1):
        font.setPointSize(size)
        rect = QFontMetrics(font).tightBoundingRect(text)
        if rect.width() <= limit and rect.height() <= limit:
            break
    return font


def _draw_badge(color: str, text: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(_MARGIN, _MARGIN, _INNER, _INNER), _CORNER_RADIUS, _CORNER_RADIUS)

    font = _max_fitting_font(text)

    # Qt.AlignCenter centers the font's *line box* (ascent+descent), not
    # the glyphs' actual ink - digits have no descender ink, so that left
    # the number looking off-center (reported: sitting toward the bottom).
    # Center the tight ink bounding box itself instead, which is accurate
    # regardless of the active font's metrics.
    ink = QFontMetrics(font).tightBoundingRect(text)
    x = SIZE / 2 - ink.width() / 2 - ink.left()
    y = SIZE / 2 - ink.height() / 2 - ink.top()

    path = QPainterPath()
    path.addText(QPointF(x, y), font, text)
    painter.setPen(QPen(_TEXT_OUTLINE, _OUTLINE_WIDTH))
    painter.setBrush(_TEXT_FILL)
    painter.drawPath(path)

    painter.end()
    return QIcon(pixmap)


def make_icon(pct: float, color: str) -> QIcon:
    text = f"{int(min(pct, 99))}" if pct < 100 else "!"
    return _draw_badge(color, text)


def make_error_icon() -> QIcon:
    return _draw_badge("#7f8c8d", "?")
