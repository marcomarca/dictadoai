# Especificación y Roadmap: Interfaz Gráfica Super Whisper para DictadoAI

Este documento define la arquitectura, diseño visual y desglose funcional del panel de control de **DictadoAI**, inspirado en la estética y capacidades de **Super Whisper**, adaptado sobre **PySide6 + QtWebEngineView (`QWebChannel`)**.

---

## 1. Filosofía de Diseño y Estética Visual

* **Inspiración**: Super Whisper (macOS / Windows 11 Fluent Design).
* **Paleta y Acabado**:
  * Modo Oscuro nativo con soporte a modo claro y tema del sistema.
  * Superficies con contraste sutil: fondo `#0F1117`, barra lateral `#161922`, tarjetas `#1E222D`, bordes finos `#2E3444`.
  * Acentos de color:
    * Primario / Botones: Azul royal vibrante (`#2563EB` / `#3B82F6`).
    * Estados activos / Micrófono: Verde esmeralda (`#10B981`).
    * Home / Naranja: `#F97316`.
    * Modos / Cyan: `#06B6D4`.
    * Vocabulario / Azul: `#3B82F6`.
    * Configuración / Gris Slate: `#64748B`.
    * Sonido / Púrpura: `#8B5CF6`.
    * Historial / Índigo: `#6366F1`.
  * Tipografía: `Segoe UI Variable Text`, `Inter`, `-apple-system`, `sans-serif`.
  * Micro-interacciones: Transiciones suaves en pestañas, elevación de tarjetas en hover, chips de atajos con estilo de teclas físicas (keycaps).

---

## 2. Estructura de Ventana y Navegación

### Barra Superior (Top Bar)
* **Botón colapsar barra lateral**: Alterna entre barra lateral extendida e icon-only.
* **Selector rápido de micrófono**: Dropdown con icono de micrófono, etiqueta del dispositivo activo y medidor VU en vivo.
* **Controles de ventana**: Minimizar (`—`), Maximizar/Restaurar (`□`), Cerrar al tray (`✕`).
* **Región de arrastre**: Permite mover la ventana arrastrando la barra superior.

### Barra Lateral (Sidebar)
* 🏠 **Home**: Panel resumen con estadísticas de productividad, accesos directos y novedades.
* ✦ **Modes**: Gestión de modos de dictado (Default, Código, Correo, Reunión, Raw, Traducción).
* 📖 **Vocabulary**: Diccionario personalizado de palabras difíciles, nombres y reglas de reemplazo.
* ⚙️ **Configuration**: Estilo de ventana de grabación (Classic / Mini), atajos de teclado y opciones del sistema.
* 🔊 **Sound**: Configuración de dispositivos de audio, ganancia, umbral VAD y sonidos de notificación.
* 🐚 **History**: Historial completo y persistente de transcripciones, buscador, métricas y acciones rápidas.
* **Pie de barra**: Badge pill `DictadoAI [PRO / LOCAL]`.

---

## 3. Desglose Detallado por Pantalla

### 3.1. Pantalla: Home (Inicio)
* **Fila de Métricas (Dashboard Cards)**:
  * `WPM Promedio`: Velocidad calculada de dictado vs. escritura manual.
  * `Palabras esta semana`: Total de palabras transcritas acumuladas.
  * `Apps usadas`: Conteo de programas distintos donde se ha inyectado texto.
  * `Minutos ahorrados`: Tiempo estimado ahorrado comparado con teclear a 40 WPM.
* **Sección "Comenzar" (Get Started)**:
  * `Iniciar dictado`: Tarjeta con icono y atajo global visible (`Ctrl + Alt + X` o configurado).
  * `Personalizar atajos`: Acceso directo a la pestaña de configuración.
  * `Crear un modo`: Acceso directo para configurar un nuevo prompt de LLM.
  * `Agregar vocabulario`: Acceso directo para añadir palabras al diccionario.
* **Sección "Novedades y Modelos" (What's New)**:
  * Tarjetas de estado de motores (Groq Whisper, Gemini 2.5 Flash, Whisper local cpp).

### 3.2. Pantalla: Modes (Modos de Dictado)
* **Cabecera**: Título "Modos", descripción y botón `+ Crear Modo`.
* **Lista de Modos**:
  * `Default`: Dictado estándar con formateo de puntuación inteligente.
  * `Código / Programación`: Sin mayúsculas automáticas innecesarias, soporte para convenciones `camelCase`, `snake_case`, palabras clave técnicas.
  * `Correo / Formal`: Estructura de párrafos, encabezados de cortesía y tono profesional.
  * `Dictado Crudo / Raw`: Transcripción directa de Whisper sin pasar por el LLM (ultra-rápido y literal).
  * `Traducción`: Dictado en español con salida inmediata en inglés (u otros idiomas).
* **Editor / Creador de Modos**:
  * Nombre del modo, icono representativo.
  * Prompt del sistema personalizado para el LLM.
  * Temperatura y modelo asociado.

### 3.3. Pantalla: Vocabulary (Vocabulario y Reemplazos)
* **Cabecera**: Explicación del propósito (nombres propios, siglas, marcas, tecnicismos).
* **Formulario de Adición**:
  * Campo: `Palabra o frase (Input)`.
  * Campo: `Reemplazar por... (Opcional)` (ej. decir "mi correo" $\rightarrow$ "usuario@dominio.com").
  * Botón: `Agregar al vocabulario`.
* **Tabla / Lista de Vocabulario**:
  * Términos guardados con búsqueda en tiempo real.
  * Interruptor para activar/desactivar términos individuales.
  * Botón de eliminación.
  * Inyección automática en los prompts de formateo.

### 3.4. Pantalla: Configuration (Configuración)
* **Ventana de Grabación (Recording Window)**:
  * Selector visual interactivo:
    * `Classic`: Overlay flotante completo con información, estado y texto en vivo.
    * `Mini`: Píldora compacta minimalista con barras de ecualizador.
  * Switch: `Mostrar siempre la ventana mini`.
  * Switch: `Ocultar automáticamente al finalizar el dictado`.
* **Atajos de Teclado (Keyboard Shortcuts)**:
  * `Alternar grabación` (Toggle): Grabador interactivo de combinación de teclas.
  * `Cancelar grabación`: Tecla para descartar el audio actual sin transcribir ni pegar (`Esc`).
  * `Cambiar de modo`: Atajo para alternar entre modos configurados.
  * `Push-to-Talk`: Modo mantener presionado para hablar.
* **Aplicación**:
  * Switch: `Iniciar con Windows` (conecta con `autostart.py`).
  * Switch: `Auto-copiar al portapapeles`.
  * Switch: `Auto-pausar multimedia externa`.
  * Switch: `Registro detallado de errores (Debug Logging)`.
  * Dropdown: `Conservar historial de transcripciones` (Siempre / 30 días / 7 días).
* **Apariencia**:
  * Switch: `Usar tema del sistema`.
  * Switch: `Efectos visuales de ventana (Acrílico / Transparencia)`.

### 3.5. Pantalla: Sound (Audio y Dispositivos)
* **Selector de Dispositivo de Entrada**:
  * Dropdown con dispositivos leídos en vivo mediante `sounddevice`.
  * Barra de nivel de entrada (VU meter activo con medidor de decibelios).
* **Sensibilidad VAD (Silero)**:
  * Control deslizante de sensibilidad para detección de voz y silencio.
* **Efectos de Sonido**:
  * Beep de inicio de dictado (On/Off + control de volumen).
  * Beep de fin de dictado (On/Off).

### 3.6. Pantalla: History (Historial de Transcripciones)
* **Conexión de Datos**: [dictado_ai/history.py](file:///d:/apps-python/dictado_ai/dictado_ai/history.py) (`logs/transcripts_history.jsonl`).
* **Buscador en Tiempo Real**: Filtro instantáneo por texto, fecha o modo.
* **Tarjetas de Transcripción**:
  * Marca de tiempo relativa ("Hace 2 min", "Ayer 18:40").
  * Métricas: Duración de audio, conteo de palabras, velocidad calculada en WPM.
  * Indicador de estado de inyección (Pegado exitoso / Copiado a portapapeles).
  * Texto completo con renderizado tipográfico legible.
  * Acciones de tarjeta:
    * 📋 `Copiar`: Copia inmediata al portapapeles del sistema.
    * 📝 `Re-pegar`: Inyección directa en el cursor activo (`Ctrl+V`).
    * 🗑️ `Eliminar`: Borrado de la entrada del archivo JSONL.
    * 🔊 `Reproducir`: Reproducción de audio si el archivo de depuración existe.

---

## 4. Arquitectura Técnica de Implementación

```mermaid
graph TD
    subgraph Frontend [Frontend Web (Blink / Chromium)]
        HTML[index.html]
        CSS[styles.css - Super Whisper Theme]
        JS[app.js + views/]
        QWC[qwebchannel.js]
    end

    subgraph QtWebEngine [Capa de Integración PySide6]
        QView[QWebEngineView (SuperWhisperWindow)]
        Bridge[WebBridge (QObject)]
    end

    subgraph Backend [Núcleo DictadoAI]
        Controller[DictationController]
        HistoryMgr[HistoryManager]
        SettingsMgr[Settings & Config]
        AudioEngine[AudioCapture & Devices]
    end

    HTML --> QView
    JS <--> QWC
    QWC <--> Bridge
    Bridge <--> Controller
    Bridge <--> HistoryMgr
    Bridge <--> SettingsMgr
    Bridge <--> AudioEngine
```

* **Puente bidireccional (`WebBridge`)**:
  * Señales Qt $\rightarrow$ Eventos JS en tiempo real (`statusChanged`, `historyUpdated`, `audioLevelChanged`, `configUpdated`).
  * Métodos `@Slot` expuestos a JS para operaciones síncronas y asíncronas (`getHistory`, `copyText`, `saveConfig`, `toggleRecording`, `listDevices`).
