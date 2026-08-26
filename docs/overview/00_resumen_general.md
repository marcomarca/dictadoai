# Resumen General del Proyecto: Dictado AI

## Propósito Global
**Dictado AI** es una solución de dictado por voz de alto rendimiento diseñada específicamente para el entorno Windows. Su objetivo es transformar el habla en texto corregido gramaticalmente de forma casi instantánea, utilizando un flujo de trabajo que combina inteligencia artificial local (Whisper) con procesamiento opcional en la nube o local (LLMs) para garantizar una salida de texto profesional y lista para usar.

## Dominios Funcionales
El sistema se organiza en cuatro dominios principales:
1.  **Captura y Pre-procesamiento:** Gestión del micrófono y detección de silencio/voz (VAD).
2.  **Inferencia ASR (Speech-to-Text):** Transcripción mediante el servidor `whisper-server.exe` (basado en whisper.cpp).
3.  **Refinamiento de Texto (LLM):** Corrección gramatical, ortográfica e inyección de puntuación mediante modelos como Ollama, Gemini o Groq.
4.  **Integración con el Sistema:** Automatización de copiado al portapapeles, control de medios (pausa de música) y simulación de teclado.

## Arquitectura de Alto Nivel
El proyecto sigue un patrón **conducido por estados (State-Driven)** y basado en **Threads de Trabajo (Workers)**. La coordinación central recae en un controlador que sincroniza el flujo de datos entre los workers de captura y los de inferencia.

### Flujo General
1.  **Activación:** El usuario dispara el sistema vía Hotkey o UI.
2.  **Captura:** `AudioCaptureWorker` escucha y divide el habla en segmentos basados en voz activa (VAD).
3.  **Transcripción:** El audio se envía al servidor Whisper local para obtener texto crudo.
4.  **Refinamiento:** El texto crudo se procesa determinísticamente (tokens de puntuación) y opcionalmente pasa por un LLM.
5.  **Salida:** El texto se escribe en la ventana activa y se copia al portapapeles.

## Puntos de Entrada
-   `main.py` / `bootstrap.py`: Inicializa la configuración, el logging y lanza la aplicación Qt.
-   `controller.py`: Inicializa los servicios secundarios (servidor Whisper, workers).

## Módulos Críticos
-   **`controller.py`**: El cerebro orquestador.
-   **`audio.py`**: Puerta de entrada de la señal física.
-   **`text_processing.py`**: Lógica de negocio para limpieza de alucinaciones y formateo.
-   **`llm_client.py`**: Adaptador para múltiples proveedores de IA.

---
Este sistema prioriza la **baja latencia** y la **robustez operativa**, permitiendo al usuario dictar con comandos naturales ("comando coma", "comando salto de línea") que son interpretados inteligentemente.
