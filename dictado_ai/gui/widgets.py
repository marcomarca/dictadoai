from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..config import UiTheme


class LevelMeter(QWidget):
    def __init__(self, theme: UiTheme, parent: Optional[QWidget] = None, bar_count: int = 28):
        super().__init__(parent)
        self.theme = theme
        self._level = 0.0
        self.bar_count = bar_count
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        if abs(self._level - level) > 0.01:
            self._level = level
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 4, 0, -4)
        if rect.width() <= 0:
            return

        spacing = 4
        total_spacing = spacing * (self.bar_count - 1)
        bar_width = max(3, (rect.width() - total_spacing) / self.bar_count)
        max_height = rect.height()
        active_bars = int(round(self._level * self.bar_count))

        for i in range(self.bar_count):
            x = rect.x() + i * (bar_width + spacing)
            ratio = (i + 1) / self.bar_count
            bar_h = max(4, ratio * max_height)
            y = rect.bottom() - bar_h + 1
            color = QColor(self.theme.color_level if i < active_bars else self.theme.color_level_bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRect(int(x), int(y), int(bar_width), int(bar_h)), 3, 3)
        painter.end()
