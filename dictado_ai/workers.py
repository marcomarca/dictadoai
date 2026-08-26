from __future__ import annotations

import logging
import queue
import re
import json
import os
from datetime import datetime
import numpy as np

from .hotkeys import set_clipboard_text, send_paste_command, ClipboardGuard
import time

from .asr import AsrClientRouter
from .config import Settings, LlmProvider
from .llm_client import LlmClient
from .runtime import AppRuntime

logger = logging.getLogger(__name__)


class InferenceWorker:
    def __init__(self, settings: Settings, runtime: AppRuntime, asr_client: AsrClientRouter, llm_client: LlmClient):
        self.settings = settings
        self.runtime = runtime
        self.asr_client = asr_client
        self.llm_client = llm_client

    def run(self) -> None:
        while not self.runtime.stop_event.is_set():
            try:
                # Wait for explicitly completed audio blocks from the PTT toggle
                item = self.runtime.final_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                continue

            utterance_id = int(item["utterance_id"])
            audio_data = item["audio"]
            prompt = item.get("prompt", "")
            
            logger.info("InferenceWorker: Procesando audio completo para utterance_id=%d", utterance_id)
            
            # Request translation strictly as a full sequence (is_partial=False)
            result = self.asr_client.transcribe(audio_data, prompt=prompt, is_partial=False)
            
            text_original_debug = ""
            text = ""
            stats_debug = {}

            if result:
                raw_asr, text = result
                text_original_debug = raw_asr  # Texto bruto real del motor ASR activo
                
                logger.info("InferenceWorker: Texto crudo ASR original: '%s'", raw_asr)
                
                # Apply LLM correction if not disabled
                if self.settings.active_provider != LlmProvider.DISABLED:
                    self.runtime.push_text(f"Mejorando con {self.settings.active_provider.value}...")
                    text = self.llm_client.correct_text(text)
                
                logger.info("InferenceWorker: Texto final a escribir: '%s'", text)
                
                # Inyectar el texto final mediante pegado rápido (Ctrl+V)
                # Si el auto-copy está desactivado, usamos el ClipboardGuard para restaurar el contenido previo
                # y marcamos el clip para que no aparezca en el historial (Win+V)
                must_restore = not self.settings.app.auto_copy_clipboard
                text_to_inject = text + " "
                
                with ClipboardGuard(enabled=must_restore):
                    set_clipboard_text(text_to_inject, exclude_from_history=must_restore)
                    # Deja que el portapapeles quede visible para la app destino y evita
                    # carreras contra el hotkey usado para detener la grabación.
                    time.sleep(0.06)
                    paste_ok = send_paste_command()
                
                self.runtime.state.register_confirmed_text(text)
                if paste_ok:
                    self.runtime.push_text(f"Pegado enviado: {text}")
                else:
                    self.runtime.push_text(f"Copiado al portapapeles; pegado automático falló: {text}")
                
                if self.settings.app.auto_copy_clipboard:
                    self.runtime.push_clipboard(text)

                # Calcular estadísticas
                duration_sec = len(audio_data) / self.settings.audio.sample_rate
                words = re.findall(r'\w+', text)
                word_count = len(words)
                
                if duration_sec > 0 and word_count > 0:
                    wpm = (word_count / duration_sec) * 60
                    # Tiempo que le tomaría escribirlo manualmente (en segundos)
                    typing_speed = self.settings.app.typing_speed_wpm or 40
                    typing_time_sec = (word_count / typing_speed) * 60
                    time_saved_sec = typing_time_sec - duration_sec
                    
                    self.runtime.push_stats(wpm, max(0, time_saved_sec))
                    stats_debug = {
                        "wpm": wpm,
                        "time_saved_sec": time_saved_sec,
                        "word_count": word_count,
                        "duration_sec": duration_sec
                    }
                    logger.info("Estadísticas: %d palabras, %.2fs duración, %.1f WPM, %.1fs ahorro", 
                                word_count, duration_sec, wpm, time_saved_sec)

                logger.info("Texto confirmado y guardado en state: %s", text)
            else:
                self.runtime.push_text("Segmento descartado por el modelo.")
                logger.info("InferenceWorker: Segmento final descartado (texto nulo/vacío) para utterance_id=%d", utterance_id)
                # Mantener el popup visible un momento para mostrar el estado [ PAUSADO ]
                self.runtime.push_preview(2.0)

            self.runtime.push_draft("")
            
            # Guardar datos de debug si está habilitado
            if self.settings.app.save_debug_audio:
                try:
                    self._save_debug_data(
                        audio_data=audio_data,
                        utterance_id=utterance_id,
                        raw_text=text_original_debug,
                        final_text=text,
                        stats=stats_debug,
                        prompt=prompt
                    )
                except Exception as e:
                    logger.error("Error al guardar datos de debug: %s", e)
            
            # Pequeño retardo para asegurar que la UI procese las estadísticas antes de la pausa
            time.sleep(0.05)
            
            if self.runtime.state.is_listening():
                self.runtime.show_active_idle_ui()
            else:
                self.runtime.show_paused_ui()
                
            self.runtime.final_queue.task_done()

    def _save_debug_data(self, audio_data: np.ndarray, utterance_id: int, raw_text: str, final_text: str, stats: dict, prompt: str):
        import scipy.io.wavfile as wavfile
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{timestamp}_u{utterance_id}"
        
        debug_dir = self.settings.paths.debug_audio_dir
        
        # Guardar Audio WAV
        wav_path = debug_dir / f"{base_name}.wav"
        try:
            # Asegurar que esté en int16 para compatibilidad si fuera necesario, 
            # pero whisper-cpp suele trabajar en float32. wavfile maneja float32 bien.
            wavfile.write(wav_path, self.settings.audio.sample_rate, audio_data)
        except Exception as e:
            logger.error("No se pudo escribir el archivo WAV de debug: %s", e)

        # Guardar Metadata JSON
        meta_path = debug_dir / f"{base_name}.json"
        metadata = {
            "timestamp": timestamp,
            "utterance_id": utterance_id,
            "raw_text_asr": raw_text,
            "final_text": final_text,
            "stats": stats,
            "prompt": prompt,
            "settings": {
                "active_provider": self.settings.active_provider.value,
                "vad_enabled": self.settings.vad.enabled
            }
        }
        
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error("No se pudo escribir la metadata JSON de debug: %s", e)
