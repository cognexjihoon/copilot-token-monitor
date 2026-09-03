"""Draws the tray icon on the fly (a status-colored ring + percentage,
transparent inside) instead of shipping image assets."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

# Drawn well above the ~16-32px a Windows tray icon actually renders at, so
# Qt's downscale has room to antialias cleanly; raising this further has no
# visible effect since the OS caps the displayed size regardless.
SIZE = 64
_MARGIN = 1  # just enough room for the antialiased edge, ring fills the rest
_INNER = SIZE - 2 * _MARGIN
# a slightly rounded square instead of a circle: a circle inscribed in a
# square only covers ~79% of its area (pi/4), so at the same canvas size a
# rounded square lets the glyph be noticeably bigger.
_CORNER_RADIUS = _INNER * 0.18
_RING_WIDTH = 5.5
# A solid-filled badge meant the digit's readability depended on that one
# status color's contrast (poor for the mid-brightness "on track" blue). A
# transparent interior instead blends with the taskbar itself - the same
# reason the system clock/IME indicator text reads clearly regardless of
# color - with only a status-colored ring around the edge for at-a-glance
# color coding.
_TEXT_FIT_FACTOR = 0.82


def _system_is_dark() -> bool:
    """Best-effort dark/light taskbar detection so the digit (drawn on a
    transparent background, no fill of its own for contrast) picks a color
    that actually shows up against it."""
    app = QGuiApplication.instance()
    if app is None:
        return True  # Windows 11 defaults to a dark taskbar
    try:
        from PySide6.QtCore import Qt as _Qt

        scheme = app.styleHints().colorScheme()
        if scheme == _Qt.ColorScheme.Dark:
            return True
        if scheme == _Qt.ColorScheme.Light:
            return False
    except AttributeError:
        pass  # colorScheme() needs Qt 6.5+
    window_color = app.palette().window().color()
    luminance = 0.2126 * window_color.redF() + 0.7152 * window_color.greenF() + 0.0722 * window_color.blueF()
    return luminance < 0.5


def _max_fitting_font(text: str) -> QFont:
    """Largest bold point size whose tight bounding box still fits inside
    the ring, so 1-, 2-digit and "!"/"?" glyphs are all drawn as big as
    possible."""
    limit = (_INNER - 2 * _RING_WIDTH) * _TEXT_FIT_FACTOR
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

    painter.setPen(QPen(QColor(color), _RING_WIDTH))
    painter.setBrush(Qt.NoBrush)
    ring_inset = _RING_WIDTH / 2
    painter.drawRoundedRect(
        QRectF(_MARGIN + ring_inset, _MARGIN + ring_inset, _INNER - _RING_WIDTH, _INNER - _RING_WIDTH),
        _CORNER_RADIUS,
        _CORNER_RADIUS,
    )

    font = _max_fitting_font(text)
    text_color = QColor("#ffffff") if _system_is_dark() else QColor("#000000")

    # Qt.AlignCenter centers the font's *line box* (ascent+descent), not
    # the glyphs' actual ink - digits have no descender ink, so that left
    # the number looking off-center. Center the tight ink bounding box
    # itself instead, which is accurate regardless of the active font.
    ink = QFontMetrics(font).tightBoundingRect(text)
    x = SIZE / 2 - ink.width() / 2 - ink.left()
    y = SIZE / 2 - ink.height() / 2 - ink.top()

    painter.setPen(Qt.NoPen)
    painter.setBrush(text_color)
    path = QPainterPath()
    path.addText(QPointF(x, y), font, text)
    painter.drawPath(path)

    painter.end()
    return QIcon(pixmap)


def make_icon(pct: float, color: str) -> QIcon:
    text = f"{int(min(pct, 99))}" if pct < 100 else "!"
    return _draw_badge(color, text)


def make_error_icon() -> QIcon:
    return _draw_badge("#7f8c8d", "?")
