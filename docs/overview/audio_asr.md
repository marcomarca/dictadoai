# Audio y Procesamiento ASR: El Motor de Voz

**Ruta:** `dictado_ai/audio.py`, `dictado_ai/asr.py`, `dictado_ai/server.py`

### Propósito
Este conjunto de módulos se encarga de la transducción física del sonido en texto. Resuelve el problema de capturar audio en tiempo real, filtrar el silencio para evitar procesar ruido y comunicarse con el backend de inferencia Whisper.

### Responsabilidad Principal
Capturar flujos de audio desde el micrófono, detectar actividad de voz (VAD) y transformar esos buffers binarios en cadenas de texto mediante una arquitectura cliente-servidor de baja latencia.

### Conexiones Principales
- **Consume:** Librerías `sounddevice` (audio) y `silero-vad` (inteligencia de voz).
- **Se conecta con:** `whisper-server.exe` (proceso externo independiente).
- **Alimenta a:** `InferenceWorker` (en `workers.py`) mediante una cola de audio-chunks.
- **Coordina:** `WhisperServerManager` asegura que el binario de C++ esté listo antes de cualquier petición.

### Piezas Importantes
- **`AudioCaptureWorker` (`audio.py`)**: Hilo persistente que lee del micrófono. Utiliza Silero VAD para separar el habla del silencio y emite "utterances" (frases completas) cuando detecta una pausa natural.
- **`WhisperServerManager` (`server.py`)**: Orquestador del binario externo. Maneja argumentos de línea de comandos, puertos y la carga de modelos en VRAM.
- **`WhisperCppClient` (`asr.py`)**: Cliente HTTP que envía audio PCM en formato WAV al servidor y retorna la transcripción JSON. Gestiona reintentos y verificaciones de salud del servidor.

### Flujo dentro del Sistema
1. El `AudioCaptureWorker` monitorea el micrófono constantemente.
2. Cuando el controlador activa el dictado, el worker empieza a acumular audio.
3. El motor VAD detecta cuando el usuario deja de hablar.
4. El buffer de audio se envía al `WhisperCppClient`.
5. El cliente hace una petición POST al servidor local.
6. El texto resultante se devuelve para su post-procesamiento.

### Resumen Ejecutivo
Este es el componente más intensivo en recursos. Al separar la captura (Python) de la inferencia (C++ vía Whisper.cpp), el sistema logra una transcripción veloz capaz de aprovechar la aceleración por hardware (CUDA) en Windows.
