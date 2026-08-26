# Interfaz de Usuario y Gestión de Estado

**Ruta:** `dictado_ai/runtime.py`, `dictado_ai/gui/`

### Propósito
Estos módulos gestionan la interacción visual con el usuario y el estado interno de la aplicación en tiempo real. Resuelven la necesidad de proporcionar feedback visual sobre el nivel de audio, el estado del dictado y la previsualización del texto procesado sin bloquear los hilos de cálculo.

### Responsabilidad Principal
Mantener una única fuente de verdad (`RuntimeState`) para toda la aplicación y proyectarla en una interfaz fluida basada en PySide6. Orquesta la comunicación asíncrona entre los hilos de IA y el hilo principal de la interfaz gráfica.

### Conexiones Principales
- **Coordina:** `DictationQtApp` (Hilo principal de Qt).
- **Expone:** `AppRuntime` como interfaz para que los hilos envíen mensajes a la UI.
- **Consume:** `RuntimeState` para conocer si el programa está escuchando o procesando.
- **Depende de:** PySide6 para la renderización de ventanas y el icono de la bandeja.

### Piezas Importantes
- **`AppRuntime` (`runtime.py`)**: Fachada que contiene las colas de mensajes (`queue.Queue`). Permite que cualquier parte del código envíe texto o actualizaciones de estado a la UI de forma segura.
- **`DictationQtApp` (`gui/app.py`)**: El contenedor principal de la aplicación Qt. Procesa la cola de mensajes y la distribuye a las ventanas correspondientes.
- **`OverlayWindow` (`gui/overlay.py`)**: Ventana flotante semi-transparente que muestra el audio-metro (nivel de voz) y el texto que se está dictando o procesando.
- **`TrayController` (`gui/tray.py`)**: Gestiona el menú contextual de la bandeja del sistema, permitiendo cambiar de proveedor de IA (Ollama, Gemini, etc.) u otras opciones sobre la marcha.

### Flujo dentro del Sistema
1. Un worker produce texto y llama a `runtime.push_text()`.
2. El mensaje entra en una cola de hilos segura.
3. El timer de `DictationQtApp` lee la cola en el hilo principal.
4. Se actualiza el `OverlayWindow` con el nuevo texto.
5. El estado visual cambia (ej: de azul a naranja) según lo que reporte el controlador.

### Resumen Ejecutivo
Este componente separa la complejidad de la IA de la experiencia del usuario. Gracias al `AppRuntime`, la lógica de procesamiento puede ignorar cómo se dibuja la interfaz, centrándose solo en reportar datos, lo que garantiza una aplicación reactiva y sin congelamientos.
