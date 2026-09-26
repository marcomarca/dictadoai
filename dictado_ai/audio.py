from __future__ import annotations

import logging
import time
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

from .audio_devices import find_input_device_by_key
from .config import Settings
from .runtime import AppRuntime

logger = logging.getLogger(__name__)


class AudioCaptureWorker:
    def __init__(self, settings: Settings, runtime: AppRuntime):
        self.settings = settings
        self.runtime = runtime

    def _enqueue_final_utterance(self, utterance_id: int, audio_data: np.ndarray) -> None:
        logger.info("AudioCaptureWorker: encolando final_utterance_id=%d, len=%d", utterance_id, len(audio_data))
        self.runtime.state.set_live_utterance_id(None)
        
        self.runtime.push_status("[ PROCESANDO ]", self.settings.ui.color_busy)
        self.runtime.push_text("Transformando audio a texto...")
        
        context = self.runtime.state.build_context_prompt(self.settings.asr.max_context_chars)
        base_prompt = self.settings.asr.initial_prompt
        
        prompt = base_prompt
        if context:
            prompt = f"{base_prompt}\n{context}"
            
        self.runtime.final_queue.put(
            {
                "utterance_id": utterance_id,
                "audio": audio_data,
                "prompt": prompt,
            }
        )

    def run(self) -> None:
        block_size = self.settings.audio.block_size
        sample_rate = self.settings.audio.sample_rate

        active_frames: list[np.ndarray] = []
        active_utterance_id: Optional[int] = None
        last_level_time = 0.0
        was_listening = False
        last_voice_activity_time = time.time()
        silence_threshold_rms = 0.01

        # Rechazar audios de menos de medio segundo o será puro ruido de click
        min_utterance_samples = int(0.5 * sample_rate)

        while not self.runtime.stop_event.is_set():
            try:
                selected_key = self.settings.audio.input_device_key
                selected_label = self.settings.audio.input_device_label
                input_device_index = None

                if selected_key is not None:
                    selected_device = find_input_device_by_key(selected_key, force_refresh=True)
                    if selected_device is None:
                        logger.error("Micrófono seleccionado no disponible: %s", selected_label)
                        self.runtime.push_status("[ ERROR AUDIO ]", self.settings.ui.color_paused)
                        self.runtime.push_text(
                            f"Micrófono no disponible: {selected_label}. Selecciona otro o vuelve a conectarlo."
                        )
                        time.sleep(2.0)
                        continue

                    input_device_index = selected_device.index

                with sd.InputStream(
                    samplerate=sample_rate,
                    channels=self.settings.audio.channels,
                    dtype="float32",
                    blocksize=block_size,
                    device=input_device_index,
                ) as stream:
                    logger.info(
                        "AudioCaptureWorker: Stream abierto. Micrófono=%s device_index=%s",
                        selected_label,
                        input_device_index,
                    )
                    while not self.runtime.stop_event.is_set():
                        if self.runtime.audio_reconnect_event.is_set():
                            logger.info("AudioCaptureWorker: reconectando stream por cambio de micrófono")
                            self.runtime.audio_reconnect_event.clear()
                            active_frames = []
                            active_utterance_id = None
                            self.runtime.state.set_live_utterance_id(None)
                            self.runtime.push_level(0.0)
                            was_listening = False
                            break

                        frame, overflowed = stream.read(block_size)
                        frame = np.asarray(frame, dtype=np.float32).flatten()
                        now = time.time()

                        if overflowed:
                            logger.warning("Overflow en captura de audio")

                        listening = self.runtime.state.is_listening()
                        
                        if listening and not was_listening:
                            active_frames = []
                            active_utterance_id = self.runtime.state.next_utterance_id()
                            self.runtime.state.set_live_utterance_id(active_utterance_id)
                            logger.info("AudioCaptureWorker: Grabación iniciada. utterance_id=%d", active_utterance_id)
                            last_voice_activity_time = time.time()
                            
                            self.runtime.push_status("[ GRABANDO ]", self.settings.ui.color_active)
                            self.runtime.push_text("Escuchando...")
                            
                        elif not listening and was_listening:
                            # Se ha finalizado la grabación
                            has_data = active_frames and active_utterance_id is not None
                            if has_data:
                                audio_data = np.concatenate(active_frames, axis=0).astype(np.float32, copy=False)
                                if len(audio_data) >= min_utterance_samples:
                                    self._enqueue_final_utterance(active_utterance_id, audio_data)
                                else:
                                    logger.info("AudioCaptureWorker: grabación descartada por ser muy corta")
                                    self.runtime.show_paused_ui()
                            else:
                                # Si no había datos (ej. se activó y desactivó al instante)
                                # debemos asegurarnos de volver al estado pausado en la UI
                                self.runtime.show_paused_ui()
                            
                            active_frames = []
                            active_utterance_id = None
                            self.runtime.state.set_live_utterance_id(None)
                            self.runtime.push_level(0.0)

                        was_listening = listening

                        if now - last_level_time >= self.settings.audio.level_update_interval:
                            rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
                            normalized_level = min(1.0, rms / 0.12)
                            
                            if listening:
                                self.runtime.push_level(normalized_level)
                                
                            last_level_time = now

                        if not listening:
                            time.sleep(0.01) # Reduce CPU usage while idle
                            continue

                        active_frames.append(frame.copy())
            
            except Exception as e:
                if self.runtime.stop_event.is_set():
                    break
                logger.error("Error en captura de audio: %s. Reintentando en 2s...", e)
                # Notificar a la UI discretamente o mediante status
                self.runtime.push_status("[ ERROR AUDIO ]", self.settings.ui.color_paused)
                self.runtime.push_text("Fallo de audio. Intentando reconectar micrófono...")
                time.sleep(2.0)
