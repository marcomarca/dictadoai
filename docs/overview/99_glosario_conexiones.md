# Glosario y Conexiones: Dictado AI

Este documento define la terminología específica del proyecto y las integraciones con servicios externos para facilitar la comprensión técnica del sistema.

## Términos Internos y Entidades

-   **ASR (Automatic Speech Recognition):** El proceso de convertir ondas de sonido en texto. Usamos Whisper para esto.
-   **VAD (Voice Activity Detection):** Tecnología que permite al programa saber cuándo el usuario está hablando y cuándo hay silencio.
-   **Utterance (Enunciado):** Una unidad de habla capturada entre dos silencios significativos. Cada utterance tiene un ID único para trazabilidad.
-   **Partial Transcript:** Texto que se genera en tiempo real mientras el usuario habla, antes de que la frase esté terminada.
-   **Final Transcript:** Texto definitivo una vez que el usuario ha dejado de hablar y el LLM lo ha refinado.
-   **Tokens de Puntuación:** Comandos especiales como `<DOT>`, `<BR>` o `<COMMA>` inyectados en el texto para guiar al modelo de lenguaje.
-   **Hallucination (Alucinación):** Texto generado por el modelo de IA que no corresponde con lo que realmente se dijo (un problema común en Whisper con silencios largos).

## Servicios e Integraciones Externas

### Motores de Inferencia Voz-Texto
-   **Whisper.cpp / whisper-server.exe:** Servidor local de alto rendimiento que ejecuta modelos GGUF de OpenAI Whisper.

### Proveedores de Modelos de Lenguaje (LLM)
-   **Ollama:** Servicio local que permite ejecutar modelos como Gemma 2B o Llama 3 para corrección gramatical privada.
-   **Google Gemini (Flash/Pro):** API en la nube utilizada para correcciones de alta calidad mediante `google-genai`.
-   **Groq:** Proveedor de inferencia ultra-rápida en la nube compatible con la API de OpenAI.

## Arquitectura de Conexiones

| Componente A | Relación | Componente B | Motivo |
| :--- | :--- | :--- | :--- |
| `Controller` | Dispara | `MediaManager` | Pausar música al empezar a dictar. |
| `AudioCapture` | Alimenta | `InferenceWorker` | Pasar buffers de audio para su transcripción. |
| `InferenceWorker` | Consulta | `LlmClient` | Refinar texto si hay un proveedor activo. |
| `AppRuntime` | Comunica | `Qt UI` | Actualizar la interfaz desde hilos de trabajo. |
| `TextProcessing` | Limpia | `Whisper Output` | Eliminar ruidos y alucinaciones antes de mostrar al usuario. |

## Abreviaturas Comunes en el Código
-   **`cfg`**: Configuración (`Settings`).
-   **`rt`**: Runtime (`AppRuntime`).
-   **`ctrl`**: Controlador (`DictationController`).
-   **`asr`**: Automatic Speech Recognition.
-   **`vad`**: Voice Activity Detection.
