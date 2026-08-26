from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def get_asset_icon_path(relative_name: str) -> Path:
    """Devuelve la ruta absoluta a un icono dentro de assets/icons."""
    base_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
    return base_dir / relative_name


def get_app_icon() -> QIcon:
    """Obtiene el icono principal de la aplicación."""
    path = get_asset_icon_path("app.ico")
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()


def get_tray_icon(name: str, fallback_color: str = "#7B879C") -> QIcon:
    """Carga un icono de bandeja desde los assets de marca con fallback procedural."""
    path = get_asset_icon_path(f"tray/{name}.ico")
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return create_tray_icon(fallback_color)


def create_microphone_pixmap(size: int, accent: str) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    rect = QRect(0, 0, size, size)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0E1628"))
    painter.drawEllipse(rect.adjusted(2, 2, -2, -2))

    painter.setBrush(QColor(accent))
    painter.drawEllipse(rect.adjusted(8, 8, -8, -8))

    painter.setBrush(QColor("#F8FAFC"))
    capsule_w = int(size * 0.22)
    capsule_h = int(size * 0.28)
    capsule_x = (size - capsule_w) // 2
    capsule_y = int(size * 0.22)
    painter.drawRoundedRect(capsule_x, capsule_y, capsule_w, capsule_h, capsule_w / 2, capsule_w / 2)

    stem_pen = QPen(QColor("#F8FAFC"), max(2, size // 18), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(stem_pen)
    painter.drawLine(size // 2, capsule_y + capsule_h, size // 2, int(size * 0.66))
    painter.drawArc(int(size * 0.31), int(size * 0.33), int(size * 0.38), int(size * 0.40), 200 * 16, 140 * 16)
    painter.drawLine(int(size * 0.37), int(size * 0.73), int(size * 0.63), int(size * 0.73))
    painter.end()
    return pixmap


def create_tray_icon(color: str) -> QIcon:
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0A0F1F"))
    painter.drawRoundedRect(QRect(4, 4, size - 8, size - 8), 18, 18)

    painter.setBrush(QColor(color))
    painter.drawEllipse(QRect(12, 12, size - 24, size - 24))

    pen = QPen(QColor("white"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QColor("white"))
    painter.drawRoundedRect(QRect(26, 18, 12, 18), 6, 6)
    painter.drawLine(32, 36, 32, 46)
    painter.drawArc(QRect(20, 22, 24, 26), 200 * 16, 140 * 16)
    painter.drawLine(24, 48, 40, 48)
    painter.end()
    return QIcon(pixmap)
