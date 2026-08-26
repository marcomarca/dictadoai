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


def get_badge_pixmap(name: str = "app.png", size: int = 40, dpr: float = 2.0) -> QPixmap:
    """Carga un icono de marca en alta resolución y lo escala con suavizado High-DPI."""
    # Primero buscar en badges/ si es un icono de estado
    badge_path = get_asset_icon_path(f"badges/{name}")
    if badge_path.exists():
        pm = QPixmap(str(badge_path))
    else:
        path = get_asset_icon_path(name)
        if not path.exists():
            return QPixmap()
        pm = QPixmap(str(path))

    if not pm.isNull():
        target_px = int(size * dpr)
        scaled = pm.scaled(
            target_px,
            target_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        return scaled
    return QPixmap()


def get_status_badge_pixmap(status_text: str, size: int = 40, dpr: float = 2.0) -> QPixmap:
    """Retorna el icono de marca en alta resolución (256x256) correspondiente al estado actual."""
    st = (status_text or "").upper()
    if "[ GRABANDO" in st or "[ ACTIVO" in st:
        pm = get_badge_pixmap("active_green.png", size, dpr)
        if not pm.isNull():
            return pm
    elif "[ PROCESANDO" in st or "[ DESCARGANDO" in st or "[ LLM" in st or "[ TRANSCRIBIENDO" in st:
        pm = get_badge_pixmap("busy_orange.png", size, dpr)
        if not pm.isNull():
            return pm
    elif "[ INICIANDO" in st or "[ PRECALENTANDO" in st:
        pm = get_badge_pixmap("init_blue.png", size, dpr)
        if not pm.isNull():
            return pm
    elif "[ ERROR" in st:
        pm = get_badge_pixmap("paused_red.png", size, dpr)
        if not pm.isNull():
            return pm
    elif "[ PAUSADO" in st:
        pm = get_badge_pixmap("paused_gray.png", size, dpr)
        if not pm.isNull():
            return pm

    # Fallback principal: icono oficial app.png en alta resolución
    app_pm = get_badge_pixmap("app.png", size, dpr)
    if not app_pm.isNull():
        return app_pm
    return create_microphone_pixmap(size, "#10B981")


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
