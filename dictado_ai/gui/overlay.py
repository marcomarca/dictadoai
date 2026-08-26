from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from .theme import create_microphone_pixmap, get_app_icon
from .widgets import LevelMeter


class DictationOverlay(QWidget):
    def __init__(self, settings: Settings, is_listening_supplier: Callable[[], bool]):
        super().__init__()
        self.settings = settings
        self.theme = settings.ui
        self.is_listening_supplier = is_listening_supplier
        self.force_preview_until = 0.0
        self.current_status = "[ INICIANDO SISTEMA ]"
        self.current_status_color = self.theme.color_init
        self._user_moved = False
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self._build_ui()
        self._apply_window_flags()
        self.hide()

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        if hasattr(Qt.WindowType, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _build_ui(self) -> None:
        self.setFixedSize(self.theme.popup_width, self.theme.popup_height)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("card")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.mic_badge = QLabel()
        self.mic_badge.setFixedSize(34, 34)
        self.mic_badge.setPixmap(create_microphone_pixmap(34, self.theme.color_active))

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        self.status_label = QLabel(self.current_status)
        self.status_label.setStyleSheet(f"color: {self.theme.color_text_primary}; font-weight: 700; font-size: 14px;")

        self.subtitle_label = QLabel("Preparando entorno...")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"color: {self.theme.color_text_muted}; font-size: 12px;")

        title_col.addWidget(self.status_label)
        title_col.addWidget(self.subtitle_label)
        header.addWidget(self.mic_badge, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(title_col, 1)

        self.hotkey_chip = QLabel(self.settings.app.hotkey.upper())
        self.hotkey_chip.setStyleSheet(
            """
            QLabel {
                color: #D7E2F2;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )
        header.addWidget(self.hotkey_chip, 0, Qt.AlignmentFlag.AlignTop)

        self.level_meter = LevelMeter(self.theme)

        self.draft_label = QLabel("Escuchando…")
        self.draft_label.setWordWrap(True)
        self.draft_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.draft_label.setStyleSheet(f"color: {self.theme.color_text_secondary}; font-size: 15px; font-weight: 500;")
        self.draft_label.setMinimumHeight(52)

        self.footer_label = QLabel("Overlay de dictado modular inspirado en Dragon/Superwhisper")
        self.footer_label.setStyleSheet(f"color: {self.theme.color_text_muted}; font-size: 11px;")

        card_layout.addLayout(header)
        card_layout.addWidget(self.level_meter)
        card_layout.addWidget(self.draft_label, 1)
        card_layout.addWidget(self.footer_label)
        root.addWidget(card)

        self.setStyleSheet(
            f"""
            QWidget {{
                background: transparent;
            }}
            QFrame#card {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {self.theme.color_card},
                    stop:1 {self.theme.color_card_alt}
                );
                border: 1px solid {self.theme.color_border};
                border-radius: {self.theme.popup_corner_radius}px;
            }}
            """
        )

    def reposition(self) -> None:
        if self._user_moved:
            return
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() - self.width() - self.theme.popup_margin_right
        y = geo.y() + self.theme.popup_margin_top
        
        new_pos = QPoint(x, y)
        if self.pos() != new_pos:
            self.move(new_pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._user_moved = True
            if self.windowHandle():
                self.windowHandle().startSystemMove()
            event.accept()

    def set_status(self, text: str, color: str) -> None:
        self.current_status = text
        self.current_status_color = color
        accent = color or self.theme.color_active
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {accent}; font-weight: 700; font-size: 14px;")
        self.mic_badge.setPixmap(create_microphone_pixmap(34, accent))
        
        # Limpiar estadísticas al empezar a grabar o si hay error
        if "[ GRABANDO ]" in text or "[ ERROR" in text:
            self.clear_stats()
        elif "[ PAUSADO ]" in text and time.time() >= self.force_preview_until:
            # Si entramos en pausa y NO estamos en los 3 segundos de gracia, limpiamos
            self.clear_stats()

    def set_info(self, text: str) -> None:
        self.subtitle_label.setText(text)

    def set_draft(self, text: str) -> None:
        if text:
            self.draft_label.setText(text)
            self.draft_label.setStyleSheet(f"color: {self.theme.color_text_primary}; font-size: 16px; font-weight: 600;")
        else:
            self.draft_label.setText("Escuchando…")
            self.draft_label.setStyleSheet(f"color: {self.theme.color_text_secondary}; font-size: 15px; font-weight: 500;")

    def set_level(self, level: float) -> None:
        self.level_meter.set_level(level)

    def set_stats(self, wpm: float, time_saved_sec: float) -> None:
        # Formatear el tiempo ahorrado
        if time_saved_sec < 60:
            time_str = f"{int(time_saved_sec)} seg"
        else:
            time_str = f"{time_saved_sec / 60:.1f} min"
        
        stats_text = f"Velocidad: {int(wpm)} WPM | Ahorro: {time_str}"
        self.footer_label.setText(stats_text)
        self.footer_label.setStyleSheet(f"color: {self.theme.color_active}; font-weight: 600; font-size: 12px;")
        
        # Activar visibilidad temporal para que el usuario pueda leerlo
        self.preview(3.0)

    def clear_stats(self) -> None:
        self.footer_label.setText("")

    def preview(self, seconds: float = 4.0) -> None:
        self.force_preview_until = time.time() + seconds
        self.show_overlay()

    def should_be_visible(self) -> bool:
        if self.is_listening_supplier():
            return True
        if time.time() < self.force_preview_until:
            return True
        # Solo ocultamos si ya estamos en pausa definitiva
        if "[ PAUSADO ]" in self.current_status:
            return False
        # En cualquier otro caso (Procesando, Inicializando, etc.) lo mantenemos visible
        return True

    def show_overlay(self) -> None:
        self.reposition()
        self.show()
        self.raise_()

    def sync_visibility(self) -> None:
        should = self.should_be_visible()
        is_vis = self.isVisible()

        if should:
            if not is_vis:
                # logger.debug("Overlay: Mostrando por cambio de estado")
                self.show_overlay()
            else:
                self.reposition()
        else:
            if is_vis:
                # logger.debug("Overlay: Ocultando por cambio de estado")
                self.hide()
