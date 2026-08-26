# Dictado AI

> **Sistema de dictado por voz inteligente y de alta precisión para Windows**, impulsado por Whisper (local GPU/CPU o Groq API en la nube) y formateo gramatical con Modelos de Lenguaje (LLM).

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: >=3.12](https://img.shields.io/badge/Python->=3.12-blue.svg)](https://www.python.org/)
[![UI: PySide6](https://img.shields.io/badge/UI-PySide6-green.svg)](https://doc.qt.io/qtforpython-6/)

---

## Características Principales

* 🎙️ **Transcripción Dual (Local & Cloud):**
  * **Local:** Servidor nativo `whisper.cpp` con aceleración CUDA (NVIDIA GPU) o CPU.
  * **Cloud:** API de Groq (`whisper-large-v3-turbo` / `whisper-large-v3`) para transcripción ultrarrápida con latencia mínima.
* 🧠 **Formateo y Corrección Inteligente (LLM):**
  * Proveedores compatibles: **Gemini** (Google AI Studio), **Groq**, **OpenRouter** y **Ollama** (local).
  * Convierte dictado natural en texto limpio con puntuación, mayúsculas y párrafos correctos sin inventar contenido.
* ⚡ **Control Total por Atajos de Teclado:**
  * Modos de activación: **Toggle** (un clic inicia, otro finaliza) o **Push-To-Talk** (mantener presionado).
  * Atajo global predeterminado: `Ctrl + Alt + X` (configurable).
* 🎵 **Pausa Inteligente de Multimedia (WinRT):**
  * Pausa automáticamente la reproducción de música o videos (Spotify, navegadores Chrome/Edge/Firefox, reproductores multimedia) durante el dictado y la reanuda al finalizar.
* 🖥️ **Interfaz Minimalista y No Invasiva:**
  * Overlay flotante semitransparente con medidor de nivel de voz en tiempo real.
  * Icono dinámico en la bandeja del sistema (System Tray) con cambio de color por estado (activo, procesando, inicializando, error, pausa).
* 📋 **Inyección Automática:**
  * Escribe el texto transcrito directamente en la aplicación activa mediante emulación de teclado Win32 y copia al portapapeles.

---

## Requisitos del Sistema

* **Sistema Operativo:** Windows 10 o Windows 11 (64-bit).
* **Python:** 3.12 o superior (administrado con [`uv`](https://github.com/astral-sh/uv) o pip).
* **Hardware para modo local (opcional):** Tarjeta gráfica NVIDIA compatible con CUDA para ejecución local acelerada de Whisper.

---

## Instalación y Configuración

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/dictado-ai.git
cd dictado-ai
```

### 2. Configurar el entorno con `uv`

```powershell
# Crear y sincronizar el entorno virtual
uv sync
```

### 3. Variables de Entorno (`.env`)

Copia el archivo `.env.example` como `.env`:

```powershell
cp .env.example .env
```

Edita `.env` con tus claves de API si deseas usar transcripción online con Groq o formateo LLM:

```env
GROQ_API_KEY=tu_clave_groq_aqui
GEMINI_API_KEY=tu_clave_gemini_aqui
OPENROUTER_API_KEY=tu_clave_openrouter_aqui
```

> **Nota:** También puedes configurar las API keys directamente desde el menú del System Tray mediante la opción *"Configurar API Keys (.env)..."*.

### 4. Configuración de Whisper Local (Opcional)

Si prefieres usar transcripción 100% local y offline (sin enviar audio a la nube):

1. **Descargar el modelo Whisper:**
   * Puedes descargar el modelo `ggml-large-v3-turbo-q5_0.bin` (o `ggml-large-v3-turbo-q8_0.bin`) directamente desde el repositorio oficial de Hugging Face:
     👉 **[Hugging Face — ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp/tree/main)**
   * Coloca el archivo `.bin` descargado dentro de la carpeta `models/`:
     ```text
     models/
     └── ggml-large-v3-turbo-q5_0.bin
     ```

2. **Binarios del servidor (`bin/`):**
   * Descarga los binarios compilados de Windows (con soporte CUDA o CPU) desde los [Releases de whisper.cpp](https://github.com/ggerganov/whisper.cpp/releases) y coloca `whisper-server.exe` junto a sus DLLs en la carpeta `bin/`.

---

## Uso

### Ejecutar desde código fuente

```powershell
uv run python main.py
```

O usando el script batch para Windows:

```powershell
.\main.bat
```

### Atajos y Controles

* **`Ctrl + Alt + X`**: Activar / Pausar dictado.
* **Menú de Bandeja (System Tray):**
  * **Micrófono:** Seleccionar dispositivo de entrada de audio activo.
  * **Motor de Transcripción:** Alternar entre Groq API (Cloud) y Whisper Local (GPU / CPU).
  * **Proveedor LLM:** Desactivado / Gemini / Groq / OpenRouter / Ollama.
  * **Modo de Activación:** Toggle / Push-To-Talk.
  * **Auto-pausar multimedia:** Activar/desactivar control de reproducción WinRT.
  * **Configurar API Keys (.env):** Abre el archivo de configuración en tu editor predeterminado.

---

## Empaquetar como Ejecutable Standalone (`dist/`)

Para generar una versión distribuible y autónoma que contenga el ejecutable, modelos y librerías necesarias:

```powershell
uv run python scripts/build_dist.py
```

El resultado se generará en `dist/DictadoAI/`:
* `DictadoAI.exe`: Ejecutable compilado sin consola.
* `bin/`: Binarios y DLLs del servidor Whisper.
* `models/`: Modelo de lenguaje.
* `.env`: Archivo local para persistir claves.

---

## Estructura del Proyecto

```text
dictado_ai/
├── dictado_ai/              # Paquete principal
│   ├── assets/              # Iconos oficiales (app y tray por estado)
│   ├── gui/                 # Componentes UI (PySide6 overlay, tray, temas)
│   ├── asr.py               # Enrutador y clientes ASR (Local Whisper & Groq)
│   ├── audio.py             # Captura y buffers de audio (sounddevice)
│   ├── config.py            # Esquema de configuración y resolución de rutas
│   ├── controller.py        # Orquestador del ciclo de vida y eventos
│   ├── hotkeys.py           # Gestión de atajos globales Win32
│   ├── llm_client.py        # Clientes para formateo con LLMs
│   ├── media_control.py     # Control multimedia nativo con WinRT
│   ├── text_processing.py   # Limpieza y heurísticas de texto
│   ├── vad.py               # Voice Activity Detection (Silero VAD)
│   └── workers.py           # Hilos de procesamiento en segundo plano
├── scripts/                 # Scripts de construcción y utilidades
│   └── build_dist.py        # Compilador standalone con PyInstaller
├── tests/                   # Suite de tests unitarios
├── main.py                  # Punto de entrada de la aplicación
├── pyproject.toml           # Metadatos y dependencias del proyecto
└── LICENSE                  # Licencia MIT
```

---

## Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.
