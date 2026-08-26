# Mapa de Módulos: Dictado AI

Este documento describe la geografía del código y cómo los distintos componentes se relacionan entre sí para formar el sistema completo.

## Relaciones Principales (Grafo de Dependencias)

-   **`bootstrap.py`**: Punto de inicio. Orquesta el arranque de `Settings`, `AppRuntime`, `DictationController` y `DictationQtApp`.
-   **`controller.py`**: Eje central. Consume `WhisperServerManager`, `AudioCaptureWorker` e `InferenceWorker`. Coordina los `Hotkeys` y `MediaManager`.
-   **`workers.py`**: Capa de ejecución. `InferenceWorker` coordina el flujo entre `WhisperCppClient` y `LlmClient`.
-   **`audio.py`**: Proveedor de datos. Alimenta la cola de procesamiento consumida por los workers.
-   **`llm_client.py`**: Integración externa. Provee una interfaz unificada para Ollama, Gemini y Groq.
-   **`runtime.py`**: Estado compartido. Centraliza el `RuntimeState` y la cola de mensajes de la UI.

## Categorización de Módulos

### Módulos Centrales (Núcleo)
-   `controller.py`: Orquestación y lógica de negocio de alto nivel.
-   `workers.py`: Gestión de concurrencia para procesamiento de voz.
-   `runtime.py`: Almacén de estado reactivo y comunicación inter-hilos.

### Módulos de Procesamiento
-   `audio.py`: Gestión de dispositivo de entrada y VAD.
-   `asr.py`: Cliente de bajo nivel para el servidor Whisper.
-   `text_processing.py`: Transformación de texto, limpieza de alucinaciones y parseo de tokens.
-   `llm_client.py`: Refinamiento semántico del texto.

### Módulos de Interfaz y Sistema
-   `gui/`: Contiene la aplicación PySide6, el icono de bandeja (tray) y la interfaz flotante (overlay).
-   `hotkeys.py`: Registro de atajos globales de teclado.
-   `media_control.py`: Automatización de pausa y reanudación de multimedia via WinRT.

### Soporte y Configuración
-   `config.py`: Definición de esquemas de configuración y valores por defecto.
-   `server.py`: Gestión del ciclo de vida del proceso `whisper-server.exe`.
-   `logging_config.py`: Configuración de trazabilidad del sistema.

## Flujos de Datos Críticos

### 1. Flujo de Voz a Texto
`audio.py` (Chunks) -> `workers.py` (Inference) -> `asr.py` (Whisper) -> `text_processing.py` (Limpieza) -> `llm_client.py` (Refinamiento) -> `runtime.py` (Display).

### 2. Flujo de Control
`hotkeys.py` (Evento) -> `controller.py` (Toggle) -> `media_control.py` (Pausa Audio) -> `audio.py` (Start/Stop).
