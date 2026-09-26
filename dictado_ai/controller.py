from __future__ import annotations

import logging
import os
import subprocess
import threading

import winsound

from .asr import AsrClientRouter
from .audio import AudioCaptureWorker
from .config import Settings, AsrDevice, AsrProvider, DictationMode, GroqAsrModel
from .hotkeys import Win32HotkeyManager
from .llm_client import LlmClient
from .runtime import AppRuntime
from .server import WhisperServerManager
from .workers import InferenceWorker
from .media_control import MediaManager, PausedMediaTarget
from .model_downloader import download_whisper_model
from dataclasses import replace

logger = logging.getLogger(__name__)


class DictationController:
    def __init__(self, settings: Settings, runtime: AppRuntime):
        self.settings = settings
        self.runtime = runtime
        self.hotkeys: Win32HotkeyManager | None = None
        self.server_manager = WhisperServerManager(settings)
        self.asr_client = AsrClientRouter(settings, runtime)
        self.llm_client = LlmClient(settings)
        self.media_manager = MediaManager(settings=self.settings)
        self.threads: list[threading.Thread] = []
        self._paused_media_targets: list[PausedMediaTarget] = []

    def _beep(self, frequency: int, duration_ms: int) -> None:
        try:
            winsound.Beep(frequency, duration_ms)
        except Exception:
            logger.debug("No se pudo reproducir beep", exc_info=True)

    def set_dictation_state(self, state: bool) -> None:
        current_state = self.runtime.state.is_listening()
        if current_state == state:
            return
        
        self.runtime.state.set_is_listening(state)
        if state:
            self.runtime.listen_event.set()
            if self.settings.app.auto_pause_media:
                self.runtime.push_text("Pausando multimedia externa...")
                paused_targets = self.media_manager.pause_all()
                self._paused_media_targets = paused_targets
                if paused_targets:
                    backends = sorted({target.backend for target in paused_targets})
                    self.runtime.push_text(f"Pausa solicitada: {', '.join(backends)}")
                else:
                    self.runtime.push_text("No se detectó multimedia activa")

            self._beep(1000, 180)
            self.runtime.show_active_idle_ui()
            logger.info("Dictado activado")
        else:
            self.runtime.listen_event.clear()
            self._beep(500, 180)
            logger.info("Dictado pausado")
            
            if self._paused_media_targets:
                self.runtime.push_text("Reanudando multimedia previa...")
                self.media_manager.resume_all(self._paused_media_targets)
                self._paused_media_targets = []
                logger.info("Multimedia reanudada")

    def toggle_dictation(self) -> None:
        new_state = not self.runtime.state.is_listening()
        self.set_dictation_state(new_state)

    def _start_workers(self) -> None:
        capture_worker = AudioCaptureWorker(self.settings, self.runtime)
        inference_worker = InferenceWorker(self.settings, self.runtime, self.asr_client, self.llm_client)

        capture_thread = threading.Thread(target=capture_worker.run, daemon=True, name="audio-capture")
        inference_thread = threading.Thread(target=inference_worker.run, daemon=True, name="inference")
        self.threads.extend([capture_thread, inference_thread])

        capture_thread.start()
        inference_thread.start()
        logger.info("Workers iniciados")

    def _check_vram(self) -> bool:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            free_mb = int(result.stdout.strip().split('\n')[0])
            logger.info("VRAM libre detectada: %d MB", free_mb)
            if free_mb < 3000:
                self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
                self.runtime.push_text(f"VRAM insuficiente. Requiere ~3000 MB, pero hay {free_mb} MB libres.")
                return False
            return True
        except Exception as e:
            logger.warning("No se pudo revisar nvidia-smi (¿AMD o no instalado?): %s", e)
            return True # Si no sabemos leer la VRAM, permitimos intentar ejecutar.

    def initialize_system(self) -> None:
        self.asr_client.refresh()

        if self.settings.asr.provider == AsrProvider.GROQ_API:
            self._initialize_groq_asr()
            self._launch_asr_prewarm_async()
            return

        self.runtime.push_status("[ INICIANDO SISTEMA ]", self.settings.ui.color_init)
        self.runtime.push_text("Limpiando procesos previos...")

        try:
            os.system("taskkill /F /IM whisper-server.exe >nul 2>&1")
        except Exception:
            pass

        if not self.settings.paths.server_exe_path.exists():
            self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
            self.runtime.push_text(f"No se encontró {self.settings.paths.server_exe_name} en el root del proyecto.")
            logger.error("Falta whisper-server.exe en %s", self.settings.paths.server_exe_path)
            return

        if not self.settings.paths.model_path.exists():
            logger.info("Modelo Whisper no encontrado en %s. Iniciando descarga automática...", self.settings.paths.model_path)
            self.runtime.push_status("[ DESCARGANDO MODELO ]", self.settings.ui.color_busy)
            self.runtime.push_text("Descargando modelo Whisper (~830 MB) desde Hugging Face...")

            def on_progress(downloaded: int, total: int, percent: float) -> None:
                mb_down = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024) if total > 0 else 0
                self.runtime.push_status(f"[ DESCARGANDO {percent:.0f}% ]", self.settings.ui.color_busy)
                self.runtime.push_text(f"Descargando modelo: {mb_down:.1f} MB / {mb_total:.1f} MB ({percent:.1f}%)")

            target_file = self.settings.paths.project_root / self.settings.paths.model_relative_path
            success = download_whisper_model(
                target_path=target_file,
                url=self.settings.paths.model_download_url,
                progress_callback=on_progress,
            )
            if not success:
                self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
                self.runtime.push_text("Error al descargar modelo desde Hugging Face. Verifica tu conexión a internet.")
                logger.error("Fallo al descargar modelo Whisper a %s", self.settings.paths.model_path)
                return
            self.runtime.push_text("Modelo descargado exitosamente. Continuando inicio...")

        device = self.settings.asr.device
        use_gpu = True

        if device == AsrDevice.CPU:
            use_gpu = False
            self.runtime.push_text("Modo CPU seleccionado forzado.")
        elif device == AsrDevice.GPU:
            use_gpu = True
            self.runtime.push_text("Modo GPU seleccionado forzado. Verificando VRAM...")
            if not self._check_vram():
                self.runtime.push_text("[ ADVERTENCIA ] VRAM detectada como insuficiente, pero procediendo por petición de usuario.")
        else: # AUTO
            self.runtime.push_text("Modo AUTOMÁTICO: Verificando VRAM...")
            if not self._check_vram():
                use_gpu = False
                self.runtime.push_text("VRAM insuficiente (<3GB), cambiando a CPU automáticamente.")
            else:
                self.runtime.push_text("VRAM OK, usando GPU.")

        self._start_server_with_possible_fallback(use_gpu)
        self._launch_asr_prewarm_async()

    def _launch_asr_prewarm_async(self) -> None:
        try:
            launched = self.asr_client.prewarm_async()
            if launched:
                logger.info("Groq ASR local prewarm async lanzado")
        except Exception:
            logger.exception("No se pudo lanzar Groq ASR local prewarm async")

    def _initialize_groq_asr(self) -> None:
        self.runtime.push_status("[ ASR ONLINE ]", self.settings.ui.color_init)
        model = self.settings.groq_asr.model.value if isinstance(self.settings.groq_asr.model, GroqAsrModel) else str(self.settings.groq_asr.model)
        self.runtime.push_text(f"Transcripción online lista: Groq API · {model}")

        if not self.settings.api_keys.groq:
            self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
            self.runtime.push_text("GROQ_API_KEY no configurada en .env")
            logger.error("GROQ_API_KEY no configurada para ASR online")
            return

        try:
            self.server_manager.shutdown()
        except Exception:
            logger.exception("Fallo cerrando whisper-server al pasar a Groq ASR")

        if not self.hotkeys:
            self.setup_hotkeys()
            self._start_workers()

        self.runtime.show_paused_ui()

    def _start_server_with_possible_fallback(self, use_gpu: bool) -> None:
        self.runtime.push_status("[ INICIANDO SERVIDOR ]", self.settings.ui.color_init)
        mode_str = "GPU" if use_gpu else "CPU"
        self.runtime.push_text(f"Lanzando whisper-server.exe en modo {mode_str}...")
        if not use_gpu:
            self.runtime.push_text("Nota: En CPU la transcripción será mucho más lenta (hasta 30-60 seg).")
        self.server_manager.start(use_gpu=use_gpu)

        if not self.server_manager.wait_ready():
            if use_gpu and self.settings.asr.device == AsrDevice.AUTO:
                self.runtime.push_text("Fallo al iniciar GPU en modo AUTO. Reintentando con CPU...")
                self.server_manager.shutdown()
                try:
                    os.system("taskkill /F /IM whisper-server.exe >nul 2>&1")
                except Exception: pass
                self.server_manager.start(use_gpu=False)
                if not self.server_manager.wait_ready():
                    self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
                    self.runtime.push_text("No se pudo conectar con whisper-server.exe (incluso en CPU)")
                    return
            else:
                self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
                self.runtime.push_text(f"No se pudo conectar con whisper-server.exe en modo {'GPU' if use_gpu else 'CPU'}")
                return

        self.runtime.push_status("[ CALENTANDO MODELOS ]", self.settings.ui.color_init)
        self.runtime.push_text("Primer warmup de ASR...")
        self.asr_client.warmup()

        if not self.hotkeys:
            self.setup_hotkeys()
            self._start_workers()
        
        self.runtime.show_paused_ui()

    def setup_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.unregister()
            
        if self.settings.app.dictation_mode == DictationMode.PUSH_TO_TALK:
            logger.info("Configurando hotkey en modo PUSH-TO-TALK")
            self.hotkeys = Win32HotkeyManager(
                self.settings.app.hotkey,
                on_press=lambda: self.set_dictation_state(True),
                on_release=lambda: self.set_dictation_state(False)
            )
        else:
            logger.info("Configurando hotkey en modo TOGGLE")
            self.hotkeys = Win32HotkeyManager(
                self.settings.app.hotkey,
                on_press=self.toggle_dictation
            )
        self.hotkeys.register()

    def change_asr_backend(
        self,
        provider: AsrProvider,
        device: AsrDevice | None = None,
        groq_model: GroqAsrModel | None = None,
    ) -> None:
        if self.runtime.state.is_listening():
            self.set_dictation_state(False)

        if provider == AsrProvider.GROQ_API:
            new_asr = replace(self.settings.asr, provider=provider)
            self.settings.asr = new_asr
            if groq_model is not None:
                self.settings.groq_asr = replace(self.settings.groq_asr, model=groq_model)
            logger.info("Cambiando ASR a Groq API: %s", self.settings.groq_asr.model)
        else:
            selected_device = device or self.settings.asr.device
            self.settings.asr = replace(self.settings.asr, provider=provider, device=selected_device)
            logger.info("Cambiando ASR a Whisper local con dispositivo: %s", selected_device)

        self.asr_client.refresh()

        self.server_manager.shutdown()
        try:
            os.system("taskkill /F /IM whisper-server.exe >nul 2>&1")
        except Exception:
            pass

        threading.Thread(target=self.initialize_system, daemon=True, name="reinit-asr").start()

    def restart_asr_server(self, device: AsrDevice) -> None:
        self.change_asr_backend(AsrProvider.WHISPER_CPP, device=device)

    def change_input_device(self, device_key: str | None, device_label: str) -> None:
        self.settings.audio = replace(
            self.settings.audio,
            input_device_key=device_key,
            input_device_label=device_label,
        )

        if self.runtime.state.is_listening():
            self.set_dictation_state(False)

        self.runtime.audio_reconnect_event.set()
        self.runtime.push_status("[ MICRÓFONO ]", self.settings.ui.color_init)
        self.runtime.push_text(f"Micrófono seleccionado: {device_label}")
        self.runtime.push_level(0.0)
        logger.info("Micrófono seleccionado: key=%s label=%s", device_key, device_label)

    def trigger_model_download(self) -> None:
        def task():
            self.runtime.push_status("[ DESCARGANDO MODELO ]", self.settings.ui.color_busy)
            self.runtime.push_text("Descargando modelo Whisper (~830 MB) desde Hugging Face...")

            def on_progress(downloaded: int, total: int, percent: float) -> None:
                mb_down = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024) if total > 0 else 0
                self.runtime.push_status(f"[ DESCARGANDO {percent:.0f}% ]", self.settings.ui.color_busy)
                self.runtime.push_text(f"Descarga de modelo: {mb_down:.1f} MB / {mb_total:.1f} MB ({percent:.1f}%)")

            target_file = self.settings.paths.project_root / self.settings.paths.model_relative_path
            success = download_whisper_model(
                target_path=target_file,
                url=self.settings.paths.model_download_url,
                progress_callback=on_progress,
            )
            if success:
                self.runtime.push_status("[ MODELO LISTO ]", self.settings.ui.color_init)
                self.runtime.push_text("Modelo Whisper descargado y listo.")
            else:
                self.runtime.push_status("[ ERROR ]", self.settings.ui.color_paused)
                self.runtime.push_text("Error descargando el modelo de Hugging Face.")

        threading.Thread(target=task, daemon=True, name="manual-model-download").start()

    def shutdown(self) -> None:
        logger.info("Cerrando aplicación")
        self.runtime.stop_event.set()
        try:
            if self.hotkeys:
                self.hotkeys.unregister()
        except Exception:
            logger.exception("Fallo liberando hotkeys")
        try:
            self.server_manager.shutdown()
        except Exception:
            logger.exception("Fallo cerrando server manager")
        try:
            self.media_manager.stop()
        except Exception:
            logger.exception("Fallo cerrando media manager")
        try:
            os.system("taskkill /F /IM whisper-server.exe >nul 2>&1")
        except Exception:
            logger.exception("Fallo haciendo taskkill de whisper-server.exe")
