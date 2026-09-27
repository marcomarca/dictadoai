# Guía de Comandos Frecuentes - Dictado AI

Este documento resume los comandos más utilizados para el desarrollo, ejecución, pruebas y empaquetado del proyecto.

---

## 1. Entorno y Dependencias

El proyecto utiliza [`uv`](https://github.com/astral-sh/uv) para la gestión de dependencias y entornos virtuales (Python >= 3.12).

### Sincronizar / Instalar dependencias
```powershell
uv sync
```

### Agregar una nueva dependencia
```powershell
uv add <nombre-paquete>
```

### Agregar una dependencia de desarrollo
```powershell
uv add --dev <nombre-paquete>
```

### Configuración inicial de variables de entorno
```powershell
# Copiar plantilla base
cp .env.example .env
```

---

## 2. Ejecución de la Aplicación

### Modo Desarrollo (Consola con logs en vivo)
```powershell
uv run python main.py
```
*O ejecutando el paquete directamente:*
```powershell
uv run python -m dictado_ai
```

### Modo Segundo Plano (Sin ventana de consola)
```powershell
uv run pythonw main.py
```
*O mediante el acceso directo por lotes:*
```powershell
.\main.bat
```

---

## 3. Pruebas Unitarias (Tests)

Las pruebas están implementadas con la suite nativa `unittest`.

### Ejecutar toda la suite de pruebas
```powershell
uv run python -m unittest discover -s tests
```

### Ejecutar un archivo de test específico
```powershell
uv run python -m unittest tests/test_asr_router_fallback.py
uv run python -m unittest tests/test_config_persistence.py
uv run python -m unittest tests/test_audio_devices_resilience.py
```

### Ejecutar un método o clase de test en particular
```powershell
uv run python -m unittest tests.test_config_persistence.TestConfigPersistence.test_save_and_load
```

---

## 4. Empaquetado y Distribución Standalone

Genera la versión autónoma en `dist/DictadoAI/` junto con el archivo ZIP de distribución listo para compartir (`dist/DictadoAI-windows-x64.zip`).

### Compilar y empaquetar
```powershell
uv run python scripts/build_dist.py
```

### Compilar manualmente con PyInstaller usando spec
```powershell
uv run pyinstaller DictadoAI.spec --noconfirm
```

---

## 5. Gestión de Procesos y Liberación de Recursos

Si la aplicación o el servidor de Whisper quedan bloqueados en segundo plano impidiendo reconstruir o volver a iniciar:

### Detener instancias huérfanas en Windows
```powershell
taskkill /F /IM DictadoAI.exe /IM whisper-server.exe /IM pythonw.exe >$null 2>&1
```
*En símbolo del sistema (CMD):*
```cmd
taskkill /F /IM DictadoAI.exe /IM whisper-server.exe /IM pythonw.exe >nul 2>&1
```

---

## 6. Recursos Locales (Modelos y Binarios)

Estructura de carpetas requerida para transcripción local offline:

```text
dictado_ai/
├── bin/
│   ├── whisper-server.exe
│   └── *.dll (CUDA / cuBLAS / GGML)
└── models/
    └── ggml-large-v3-turbo-q5_0.bin
```

### Probar el servidor Whisper local de forma independiente
```powershell
.\bin\whisper-server.exe -m .\models\ggml-large-v3-turbo-q5_0.bin --port 8080
```
