"""Draws the tray icon on the fly (just the percentage, tinted with the
status color, on a fully transparent background) instead of shipping image
assets."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap

# Drawn well above the ~16-32px a Windows tray icon actually renders at, so
# Qt's downscale has room to antialias cleanly; raising this further has no
# visible effect since the OS caps the displayed size regardless.
SIZE = 64
_MARGIN = 1
_INNER = SIZE - 2 * _MARGIN
# No badge shape at all now - just the digit, transparent everywhere else,
# so it blends with the taskbar the same way the system clock/IME indicator
# text does (tray space is narrow; a ring or fill only ate into how big the
# number itself could be).
_TEXT_FIT_FACTOR = 0.94
# Same hue as the status color, but relit for the current theme - straight
# status-color-on-transparent read fine on Windows 11's default dark
# taskbar, but several status colors (yellow, green) drop to ~1.6-2:1
# contrast against a *light* taskbar, well below legible. Keeping the hue
# preserves the at-a-glance color coding; only lightness changes per theme.
_DARK_THEME_LIGHTNESS = 0.62
_LIGHT_THEME_LIGHTNESS = 0.32


def _system_is_dark() -> bool:
    """Best-effort dark/light taskbar detection."""
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


def _tray_digit_color(status_color: str) -> QColor:
    color = QColor(status_color)
    h, s, _l, a = color.getHslF()
    target_l = _DARK_THEME_LIGHTNESS if _system_is_dark() else _LIGHT_THEME_LIGHTNESS
    color.setHslF(h if h >= 0 else 0.0, s, target_l, a)
    return color


def _max_fitting_font(text: str) -> QFont:
    """Largest bold point size whose tight bounding box still fits inside
    the canvas, so 1-, 2-digit and "!"/"?" glyphs are all drawn as big as
    possible."""
    limit = _INNER * _TEXT_FIT_FACTOR
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

    font = _max_fitting_font(text)
    fill = _tray_digit_color(color)

    # Qt.AlignCenter centers the font's *line box* (ascent+descent), not
    # the glyphs' actual ink - digits have no descender ink, so that left
    # the number looking off-center. Center the tight ink bounding box
    # itself instead, which is accurate regardless of the active font.
    ink = QFontMetrics(font).tightBoundingRect(text)
    x = SIZE / 2 - ink.width() / 2 - ink.left()
    y = SIZE / 2 - ink.height() / 2 - ink.top()

    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
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
