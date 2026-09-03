"""Draws the tray icon on the fly (colored circle + percentage) instead of
shipping image assets."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

SIZE = 64


def make_icon(pct: float, color: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(2, 2, SIZE - 4, SIZE - 4))

    text = f"{int(min(pct, 99))}" if pct < 100 else "!"
    font = QFont("Segoe UI", 26 if len(text) < 2 else 22, QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, text)

    painter.end()
    return QIcon(pixmap)


def make_error_icon() -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#7f8c8d"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(2, 2, SIZE - 4, SIZE - 4))
    painter.setFont(QFont("Segoe UI", 26, QFont.Bold))
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, "?")
    painter.end()
    return QIcon(pixmap)
