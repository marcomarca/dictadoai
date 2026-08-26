from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

def build() -> None:
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    output_bundle_dir = dist_dir / "DictadoAI"

    print("=" * 60)
    print(f"Iniciando empaquetado de Dictado AI en: {output_bundle_dir}")
    print("=" * 60)

    # 0. Cerrar instancias previas que puedan bloquear archivos en dist/
    if sys.platform == "win32":
        os.system("taskkill /F /IM DictadoAI.exe /IM whisper-server.exe >nul 2>&1")

    # 1. Comando PyInstaller
    icon_file = project_root / "dictado_ai" / "assets" / "icons" / "app.ico"
    assets_dir = project_root / "dictado_ai" / "assets"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "DictadoAI",
        f"--icon={icon_file}",
        f"--add-data={assets_dir};dictado_ai/assets",
        "--collect-all", "silero_vad_lite",
        "--collect-all", "onnxruntime",
        "--collect-all", "sounddevice",
        "--collect-all", "scipy",
        "--collect-all", "google.genai",
        "--collect-all", "groq",
        "--collect-all", "openai",
        "--hidden-import", "winrt.windows.foundation",
        "--hidden-import", "winrt.windows.foundation.collections",
        "--hidden-import", "winrt.windows.media.control",
        "--hidden-import", "dotenv",
        "--hidden-import", "pyside6",
        str(project_root / "main.py"),
    ]

    print(f"Ejecutando PyInstaller...")
    subprocess.run(cmd, check=True, cwd=str(project_root))

    # 2. Copiar bin/ (whisper-server.exe y DLLs de CUDA/GGML)
    src_bin = project_root / "bin"
    dst_bin = output_bundle_dir / "bin"
    if src_bin.exists():
        print(f"Copiando bin/ ({src_bin}) -> ({dst_bin})...")
        if dst_bin.exists():
            shutil.rmtree(dst_bin)
        shutil.copytree(src_bin, dst_bin)
    else:
        print("[ADVERTENCIA] No se encontró carpeta bin/")

    # 3. Copiar models/ (modelo ggml)
    src_models = project_root / "models"
    dst_models = output_bundle_dir / "models"
    if src_models.exists():
        print(f"Copiando models/ ({src_models}) -> ({dst_models})...")
        if dst_models.exists():
            shutil.rmtree(dst_models)
        shutil.copytree(src_models, dst_models)
    else:
        print("[ADVERTENCIA] No se encontró carpeta models/")

    # 4. Crear o copiar .env y .env.example
    src_env = project_root / ".env"
    dst_env = output_bundle_dir / ".env"
    src_env_example = project_root / ".env.example"
    dst_env_example = output_bundle_dir / ".env.example"

    if src_env_example.exists():
        shutil.copy2(src_env_example, dst_env_example)

    if src_env.exists():
        print(f"Copiando .env actual a la distribución...")
        shutil.copy2(src_env, dst_env)
    elif not dst_env.exists():
        print(f"Creando .env inicial en la distribución...")
        dst_env.write_text(
            "# Configuración de claves API para Dictado AI\n"
            "GROQ_API_KEY=\n"
            "GEMINI_API_KEY=\n"
            "OPENROUTER_API_KEY=\n",
            encoding="utf-8",
        )

    # 5. Copiar assets de iconos
    src_assets = project_root / "dictado_ai" / "assets"
    dst_assets_internal = output_bundle_dir / "_internal" / "dictado_ai" / "assets"
    dst_assets_root = output_bundle_dir / "dictado_ai" / "assets"
    if src_assets.exists():
        print(f"Copiando assets de iconos a la distribución...")
        if dst_assets_internal.exists():
            shutil.rmtree(dst_assets_internal)
        shutil.copytree(src_assets, dst_assets_internal)
        if dst_assets_root.exists():
            shutil.rmtree(dst_assets_root)
        shutil.copytree(src_assets, dst_assets_root)

    # 6. Crear carpeta logs/
    dst_logs = output_bundle_dir / "logs"
    dst_logs.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"¡Empaquetado finalizado con éxito!")
    print(f"Ejecutable disponible en: {output_bundle_dir / 'DictadoAI.exe'}")
    print("=" * 60)


if __name__ == "__main__":
    build()
