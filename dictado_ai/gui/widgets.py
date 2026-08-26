from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..config import UiTheme


class LevelMeter(QWidget):
    def __init__(self, theme: UiTheme, parent: Optional[QWidget] = None, bar_count: int = 32):
        super().__init__(parent)
        self.theme = theme
        self._level = 0.0
        self.bar_count = bar_count
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        if abs(self._level - level) > 0.008:
            self._level = level
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if rect.width() <= 0:
            return

        spacing = 3
        total_spacing = spacing * (self.bar_count - 1)
        bar_width = max(2.5, (rect.width() - total_spacing) / self.bar_count)
        center_y = rect.height() / 2.0
        max_half_h = (rect.height() - 2) / 2.0
        active_bars = int(round(self._level * self.bar_count))

        for i in range(self.bar_count):
            x = rect.x() + i * (bar_width + spacing)
            
            # Curva suave en campana para dar sensación orgánica de onda de audio
            normalized_pos = abs(i - (self.bar_count / 2.0)) / (self.bar_count / 2.0)
            envelope = 1.0 - (normalized_pos * 0.45)
            
            if i < active_bars:
                intensity = max(0.2, (self._level * envelope))
                half_h = max(2.0, intensity * max_half_h)
                color = QColor(self.theme.color_level)
            else:
                half_h = 2.0
                color = QColor(self.theme.color_level_bg)

            y = center_y - half_h
            h = half_h * 2.0
            radius = bar_width / 2.0

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRect(int(x), int(y), int(bar_width), int(h)), radius, radius)
            
        painter.end()
