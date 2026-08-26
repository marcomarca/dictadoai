# Orquestación y Control: DictationController

**Ruta:** `dictado_ai/controller.py`

### Propósito
El `DictationController` es el centro neurálgico del sistema. Su existencia se justifica por la necesidad de coordinar múltiples subsistemas asíncronos (servidor Whisper, workers de audio, sistema de hotkeys, interfaz gráfica) en una máquina de estados coherente.

### Responsabilidad Principal
Gestionar el ciclo de vida completo de la aplicación y la transición de estados entre "Esperando" y "Dictando". Resuelve el arranque del hardware y software necesario y asegura una salida limpia al cerrar.

### Conexiones Principales
- **Coordina:** `AudioCaptureWorker` e `InferenceWorker` para el flujo de datos.
- **Gestiona:** `WhisperServerManager` para el levantamiento del binario C++.
- **Consume:** `Settings` para aplicar configuraciones de usuario.
- **Dispara:** Comandos a `MediaManager` para controlar el audio del sistema.
- **Actualiza:** `AppRuntime` para reflejar cambios de estado en la UI.
- **Registra:** `HotkeyManager` para capturar eventos de teclado.

### Piezas Importantes
- `DictationController`: Clase principal que unifica la lógica.
- `initialize_system`: Método crítico que limpia procesos previos, verifica VRAM de la GPU, lanza el servidor Whisper y registra hotkeys.
- `set_dictation_state`: Gestiona el encendido/apagado del micrófono, reproduce beeps de estado y activa la pausa inteligente de multimedia.
- `toggle_dictation`: Punto de entrada unificado para alternar el dictado via hotkey o tray icon.
- `shutdown`: Garantiza que el servidor de Whisper y los workers se detengan correctamente, liberando recursos de GPU.

### Flujo dentro del Sistema
Cuando el usuario pulsa la tecla rápida, el controlador recibe la instrucción, verifica si el sistema está listo, cambia el estado visual en el `AppRuntime`, pausa cualquier música sonando via `MediaManager` y le indica al `AudioCaptureWorker` que empiece a encolar audio.

### Resumen Ejecutivo
Sin este módulo, el sistema sería una colección de herramientas aisladas. El controlador transforma estas herramientas en un producto funcional mediante la sincronización de eventos y la gestión de recursos de hardware.
