# Inteligencia y Refinamiento de Texto

**Ruta:** `dictado_ai/llm_client.py`, `dictado_ai/text_processing.py`

### Propósito
Estos módulos transforman la transcripción cruda y potencialmente errónea de Whisper en texto pulido, profesional y con formato correcto. Resuelven problemas de alucinaciones de IA, falta de puntuación y gramática incorrecta.

### Responsabilidad Principal
Aplicar una capa de "limpieza" mecánica y otra de "inteligencia" semántica. Valida la calidad de la transcripción, inyecta puntuación mediante comandos de voz y utiliza modelos de lenguaje para corregir el estilo.

### Conexiones Principales
- **Consume:** APIs externas (Ollama local, Google Gemini, Groq).
- **Transforma:** Texto crudo de `asr.py` en texto procesado para la UI.
- **Valida:** La veracidad de la transcripción frente a ruidos de fondo.
- **Coordina:** `InferenceWorker` llama a estos módulos secuencialmente.

### Piezas Importantes
- **`LlmClient` (`llm_client.py`)**: Fachada para múltiples proveedores. Maneja estrategias de reintentos y asegura que el LLM solo devuelva el texto corregido sin explicaciones adicionales ("Chain of Thought").
- **`pre_process_tokens` (`text_processing.py`)**: Convierte comandos de voz (ej: "comando punto") en tokens seguros (ej: `<DOT>`) para que el LLM sepa exactamente dónde colocar la puntuación.
- **`looks_hallucinatory` (`text_processing.py`)**: Filtra frases típicas de alucinación de Whisper (ej: "Suscríbete al canal", "Amara.org") basándose en duración de audio y patrones de texto.
- **`postprocess_transcript`**: Función maestra que orquesta la limpieza, normalización de espacios y corrección de mayúsculas/minúsculas.

### Flujo dentro del Sistema
1. El texto llega desde Whisper.
2. Se valida si es una alucinación (si lo es, se descarta).
3. Se inyectan tokens deterministas si el usuario usó comandos de voz.
4. Si el LLM está activo, se envía para corrección gramatical.
5. El texto final se limpia de tokens y se formatea para su escritura.

### Resumen Ejecutivo
Este módulo es el diferencial del proyecto. Convierte un simple conversor de voz en una herramienta de redacción inteligente, permitiendo que el usuario se olvide de la ortografía y el formato para centrarse en el contenido.
