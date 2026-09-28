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
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings, RecordingWindowStyle
from .theme import get_app_icon, get_status_badge_pixmap
from .widgets import LevelMeter


class DictationOverlay(QWidget):
    def __init__(
        self,
        settings: Settings,
        is_listening_supplier: Callable[[], bool],
        is_processing_supplier: Callable[[], bool] | None = None,
    ):
        super().__init__()
        self.settings = settings
        self.theme = settings.ui
        self.is_listening_supplier = is_listening_supplier
        self.is_processing_supplier = is_processing_supplier
        self.force_preview_until = 0.0
        self.current_status = "[ INICIANDO SISTEMA ]"
        self.current_status_color = self.theme.color_init
        self._user_moved = False

        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._build_ui()
        self.update_style()
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
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(4, 4, 4, 4)
        self.root_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. CLASSIC CARD (Full Details)
        # -------------------------------------------------------------
        self.classic_card = QFrame(self)
        self.classic_card.setObjectName("classicCard")

        classic_shadow = QGraphicsDropShadowEffect(self)
        classic_shadow.setBlurRadius(16)
        classic_shadow.setColor(QColor(0, 0, 0, 160))
        classic_shadow.setOffset(0, 4)
        self.classic_card.setGraphicsEffect(classic_shadow)

        classic_layout = QVBoxLayout(self.classic_card)
        classic_layout.setContentsMargins(14, 12, 14, 12)
        classic_layout.setSpacing(6)

        # Header: Icono oficial de marca + Título/Subtítulo + Hotkey chip
        header = QHBoxLayout()
        header.setSpacing(10)

        self.mic_badge = QLabel()
        self.mic_badge.setFixedSize(38, 38)
        self.mic_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mic_badge.setPixmap(get_status_badge_pixmap(self.current_status, 38, 2.0))

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.status_label = QLabel(self.current_status)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet(f"color: {self.theme.color_init}; font-weight: 700; font-size: 13px; letter-spacing: 0.5px;")

        self.subtitle_label = QLabel("Preparando entorno...")
        self.subtitle_label.setObjectName("subtitleLabel")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"color: {self.theme.color_text_muted}; font-size: 12px;")

        title_col.addWidget(self.status_label)
        title_col.addWidget(self.subtitle_label)
        header.addWidget(self.mic_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addLayout(title_col, 1)

        self.hotkey_chip = QLabel(self.settings.app.hotkey.upper())
        self.hotkey_chip.setObjectName("hotkeyChip")
        header.addWidget(self.hotkey_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        # Barra de visualización de audio moderna (ecualizador simétrico)
        self.level_meter = LevelMeter(self.theme, bar_count=32)

        # Texto en tiempo real / borrador transcrito
        self.draft_label = QLabel("Escuchando tu voz...")
        self.draft_label.setObjectName("draftLabel")
        self.draft_label.setWordWrap(True)
        self.draft_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.draft_label.setMinimumHeight(36)
        self.draft_label.setStyleSheet(f"color: {self.theme.color_text_secondary}; font-size: 13px; font-weight: 500;")

        # Barra inferior para estadísticas y estado
        self.footer_label = QLabel("")
        self.footer_label.setObjectName("footerLabel")
        self.footer_label.setStyleSheet(f"color: {self.theme.color_text_muted}; font-size: 11px;")

        classic_layout.addLayout(header)
        classic_layout.addWidget(self.level_meter)
        classic_layout.addWidget(self.draft_label, 1)
        classic_layout.addWidget(self.footer_label)

        # -------------------------------------------------------------
        # 2. MINI CARD (Compact Pill Widget with Post-Dictation WPM)
        # -------------------------------------------------------------
        self.mini_card = QFrame(self)
        self.mini_card.setObjectName("miniCard")

        mini_shadow = QGraphicsDropShadowEffect(self)
        mini_shadow.setBlurRadius(10)
        mini_shadow.setColor(QColor(0, 0, 0, 140))
        mini_shadow.setOffset(0, 2)
        self.mini_card.setGraphicsEffect(mini_shadow)

        mini_layout = QHBoxLayout(self.mini_card)
        mini_layout.setContentsMargins(10, 4, 12, 4)
        mini_layout.setSpacing(8)

        # Punto indicador de estado circular Apple SF Style
        self.mini_mic_dot = QLabel()
        self.mini_mic_dot.setFixedSize(10, 10)
        self._update_mini_dot_color(self.theme.color_init)

        # Contenedor dinámico Stacked (Grabando vs Resultado WPM)
        self.mini_stack_container = QWidget()
        self.mini_stack = QStackedLayout(self.mini_stack_container)
        self.mini_stack.setContentsMargins(0, 0, 0, 0)

        # Página 0: En Vivo (Ecualizador compacto + etiqueta)
        self.mini_live_widget = QWidget()
        mini_live_layout = QHBoxLayout(self.mini_live_widget)
        mini_live_layout.setContentsMargins(0, 0, 0, 0)
        mini_live_layout.setSpacing(6)

        self.mini_level_meter = LevelMeter(self.theme, bar_count=10)
        self.mini_level_meter.setFixedSize(48, 12)

        self.mini_status_text = QLabel("Dictado")
        self.mini_status_text.setObjectName("miniStatusText")
        self.mini_status_text.setStyleSheet(f"color: {self.theme.color_text_primary}; font-weight: 600; font-size: 12px;")

        mini_live_layout.addWidget(self.mini_level_meter, 0, Qt.AlignmentFlag.AlignVCenter)
        mini_live_layout.addWidget(self.mini_status_text, 1, Qt.AlignmentFlag.AlignVCenter)

        # Página 1: Post-Grabación (WPM Speed Tag)
        self.mini_wpm_widget = QWidget()
        mini_wpm_layout = QHBoxLayout(self.mini_wpm_widget)
        mini_wpm_layout.setContentsMargins(0, 0, 0, 0)
        mini_wpm_layout.setSpacing(4)

        self.mini_wpm_label = QLabel("⚡ 145 WPM")
        self.mini_wpm_label.setObjectName("miniWpmLabel")
        self.mini_wpm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini_wpm_label.setStyleSheet(f"color: {self.theme.color_active}; font-weight: 700; font-size: 12px; letter-spacing: 0.5px;")

        mini_wpm_layout.addWidget(self.mini_wpm_label, 1, Qt.AlignmentFlag.AlignCenter)

        self.mini_stack.addWidget(self.mini_live_widget)
        self.mini_stack.addWidget(self.mini_wpm_widget)
        self.mini_stack.setCurrentWidget(self.mini_live_widget)

        mini_layout.addWidget(self.mini_mic_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        mini_layout.addWidget(self.mini_stack_container, 1, Qt.AlignmentFlag.AlignVCenter)

        # -------------------------------------------------------------
        # Root Stack Setup
        # -------------------------------------------------------------
        self.root_stack_widget = QWidget()
        self.root_stack = QStackedLayout(self.root_stack_widget)
        self.root_stack.setContentsMargins(0, 0, 0, 0)
        self.root_stack.addWidget(self.classic_card)
        self.root_stack.addWidget(self.mini_card)

        self.root_layout.addWidget(self.root_stack_widget)

        self.setStyleSheet(
            f"""
            QWidget {{
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
            }}
            QFrame#classicCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(28, 28, 30, 0.97),
                    stop:1 rgba(18, 18, 20, 0.98)
                );
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-top: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: {self.theme.popup_corner_radius}px;
            }}
            QFrame#miniCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(28, 28, 30, 0.97),
                    stop:1 rgba(18, 18, 20, 0.98)
                );
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-top: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 17px;
            }}
            QLabel#hotkeyChip {{
                color: #F5F5F7;
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                padding: 3px 7px;
                font-size: 11px;
                font-weight: 600;
            }}
            """
        )

    def _update_mini_dot_color(self, color_hex: str) -> None:
        self.mini_mic_dot.setStyleSheet(
            f"background-color: {color_hex}; border-radius: 5px; min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px;"
        )

    def update_style(self) -> None:
        style = self.settings.app.recording_window_style
        if style == RecordingWindowStyle.MINI:
            self.root_stack.setCurrentWidget(self.mini_card)
            self.setFixedSize(180, 42)
        else:
            self.root_stack.setCurrentWidget(self.classic_card)
            self.setFixedSize(self.theme.popup_width + 12, self.theme.popup_height + 12)
        self.reposition()

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
        # Guarda de sincronización: si el micrófono sigue activo, no permitir que estados
        # de pausa o finalización rezagados de una tarea anterior sobreescriban la grabación
        is_currently_listening = self.is_listening_supplier() if self.is_listening_supplier else False
        if is_currently_listening and not ("[ GRABANDO" in text or "[ ACTIVO" in text or "[ ERROR" in text):
            text = "[ GRABANDO ]"
            color = self.theme.color_active

        self.current_status = text
        self.current_status_color = color
        accent = color or self.theme.color_active
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {accent}; font-weight: 700; font-size: 13px; letter-spacing: 0.5px;")

        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 2.0
        badge_pixmap = get_status_badge_pixmap(text, 38, dpr)
        if not badge_pixmap.isNull():
            self.mic_badge.setPixmap(badge_pixmap)

        self._update_mini_dot_color(accent)

        if "[ GRABANDO" in text:
            self.mini_status_text.setText("Grabando")
            self.mini_stack.setCurrentWidget(self.mini_live_widget)
            self.clear_stats()
        elif "[ PROCESANDO" in text or "[ TRANSCRIBIENDO" in text:
            self.mini_status_text.setText("Procesando...")
            self.mini_stack.setCurrentWidget(self.mini_live_widget)
        elif "[ MEJORANDO" in text or "[ BUSCANDO" in text:
            self.mini_status_text.setText("Mejorando...")
            self.mini_stack.setCurrentWidget(self.mini_live_widget)
        elif "[ LISTO" in text or "[ COMPLETADO" in text:
            self.mini_status_text.setText("Listo")
        elif "[ ERROR" in text:
            self.mini_status_text.setText("Error")
            self.clear_stats()
            self.mini_stack.setCurrentWidget(self.mini_live_widget)
        elif "[ PAUSADO" in text:
            self.mini_status_text.setText("Pausado")
            if time.time() >= self.force_preview_until:
                self.clear_stats()
                self.mini_stack.setCurrentWidget(self.mini_live_widget)

    def set_info(self, text: str) -> None:
        self.subtitle_label.setText(text)

    def set_draft(self, text: str) -> None:
        if text:
            self.draft_label.setText(text)
            self.draft_label.setStyleSheet(f"color: {self.theme.color_text_primary}; font-size: 14px; font-weight: 600;")
        else:
            self.draft_label.setText("Escuchando tu voz...")
            self.draft_label.setStyleSheet(f"color: {self.theme.color_text_secondary}; font-size: 13px; font-weight: 500;")

    def set_level(self, level: float) -> None:
        self.level_meter.set_level(level)
        self.mini_level_meter.set_level(level)

    def set_stats(self, wpm: float, time_saved_sec: float) -> None:
        if time_saved_sec < 60:
            time_str = f"{int(time_saved_sec)} seg"
        else:
            time_str = f"{time_saved_sec / 60:.1f} min"

        stats_text = f"⚡ {int(wpm)} WPM  ·  ⏱ Ahorro: {time_str}"
        self.footer_label.setText(stats_text)
        self.footer_label.setStyleSheet(f"color: {self.theme.color_active}; font-weight: 600; font-size: 11px;")

        # En modo Mini, el widget transiciona a mostrar la velocidad WPM con dot en verde
        self.mini_wpm_label.setText(f"⚡ {int(wpm)} WPM")
        self.mini_stack.setCurrentWidget(self.mini_wpm_widget)
        self._update_mini_dot_color(self.theme.color_active)
        self.preview(3.5)

    def clear_stats(self) -> None:
        self.footer_label.setText("")
        self.mini_stack.setCurrentWidget(self.mini_live_widget)

    def preview(self, seconds: float = 4.0) -> None:
        self.force_preview_until = time.time() + seconds
        self.show_overlay()

    def should_be_visible(self) -> bool:
        if self.is_listening_supplier and self.is_listening_supplier():
            return True
        if self.is_processing_supplier and self.is_processing_supplier():
            return True
        if any(token in self.current_status for token in ("[ PROCESANDO", "[ MEJORANDO", "[ TRANSCRIBIENDO", "[ DESCARGANDO")):
            return True
        if time.time() < self.force_preview_until:
            return True
        return False

    def show_overlay(self) -> None:
        self.reposition()
        self.show()
        self.raise_()

    def sync_visibility(self) -> None:
        should = self.should_be_visible()
        is_vis = self.isVisible()

        if should:
            if not is_vis:
                self.show_overlay()
            else:
                self.reposition()
        else:
            if is_vis:
                self.hide()

