from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Optional

import numpy as np
import sounddevice as sd

from .audio_devices import find_input_device_by_key, negotiate_input_device_params, resample_audio
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
        base_block_size = self.settings.audio.block_size
        target_sample_rate = self.settings.audio.sample_rate

        # Rechazar audios de menos de medio segundo o sera puro ruido de click
        min_utterance_samples = int(0.5 * target_sample_rate)

        while not self.runtime.stop_event.is_set():
            # Estado IDLE: el microfono permanece completamente cerrado
            # para no degradar el audio de auriculares Bluetooth (A2DP vs HFP/HSP)
            if not self.runtime.state.is_listening():
                self.runtime.listen_event.wait(timeout=0.05)
                if not self.runtime.state.is_listening() or self.runtime.stop_event.is_set():
                    continue

            # Iniciar sesion de grabacion on-demand
            active_frames: list[np.ndarray] = []
            active_utterance_id = self.runtime.state.next_utterance_id()
            self.runtime.state.set_live_utterance_id(active_utterance_id)
            logger.info("AudioCaptureWorker: Grabacion iniciada. utterance_id=%d", active_utterance_id)

            selected_key = self.settings.audio.input_device_key
            selected_label = self.settings.audio.input_device_label
            input_device_index: int | None = None

            if selected_key is not None:
                selected_device = find_input_device_by_key(selected_key, force_refresh=False)
                if selected_device is None:
                    logger.warning(
                        "Microfono seleccionado no disponible: %s. Fallback automático a Sistema predeterminado.",
                        selected_label,
                    )
                    self.settings.audio = replace(
                        self.settings.audio,
                        input_device_key=None,
                        input_device_label="Sistema predeterminado",
                    )
                    self.settings.save()
                    self.runtime.push_status("[ MICRÓFONO REASIGNADO ]", self.settings.ui.color_busy)
                    self.runtime.push_text(
                        f"Micrófono '{selected_label}' desconectado. Usando predeterminado del sistema."
                    )
                    input_device_index = None
                else:
                    input_device_index = selected_device.index

            # Negociar tasa de muestreo y canales compatibles con el hardware
            stream_sr, stream_channels = negotiate_input_device_params(
                input_device_index,
                target_sr=target_sample_rate,
                channels=self.settings.audio.channels,
            )
            stream_block_size = max(64, int(base_block_size * (stream_sr / target_sample_rate)))
            last_level_time = 0.0

            try:
                try:
                    stream_ctx = sd.InputStream(
                        samplerate=stream_sr,
                        channels=stream_channels,
                        dtype="float32",
                        blocksize=stream_block_size,
                        device=input_device_index,
                    )
                except Exception as open_err:
                    if input_device_index is not None:
                        logger.warning(
                            "Fallo al abrir stream en dispositivo %s (index=%s): %s. Reintentando con Sistema predeterminado...",
                            selected_label,
                            input_device_index,
                            open_err,
                        )
                        input_device_index = None
                        self.settings.audio = replace(
                            self.settings.audio,
                            input_device_key=None,
                            input_device_label="Sistema predeterminado",
                        )
                        self.settings.save()
                        self.runtime.push_status("[ MICRÓFONO REASIGNADO ]", self.settings.ui.color_busy)
                        self.runtime.push_text("Fallo en dispositivo anterior. Usando predeterminado del sistema.")
                        stream_sr, stream_channels = negotiate_input_device_params(
                            None,
                            target_sr=target_sample_rate,
                            channels=self.settings.audio.channels,
                        )
                        stream_block_size = max(64, int(base_block_size * (stream_sr / target_sample_rate)))
                        stream_ctx = sd.InputStream(
                            samplerate=stream_sr,
                            channels=stream_channels,
                            dtype="float32",
                            blocksize=stream_block_size,
                            device=None,
                        )
                    else:
                        raise open_err

                with stream_ctx as stream:
                    logger.info(
                        "AudioCaptureWorker: Stream abierto on-demand. Microfono=%s device_index=%s sr=%d ch=%d",
                        self.settings.audio.input_device_label,
                        input_device_index,
                        stream_sr,
                        stream_channels,
                    )
                    while not self.runtime.stop_event.is_set() and self.runtime.state.is_listening():
                        if self.runtime.audio_reconnect_event.is_set():
                            logger.info("AudioCaptureWorker: reconectando stream por cambio de microfono")
                            self.runtime.audio_reconnect_event.clear()
                            break

                        frame, overflowed = stream.read(stream_block_size)
                        if frame.ndim > 1 and frame.shape[1] > 1:
                            frame_mono = np.mean(frame, axis=1).astype(np.float32)
                        else:
                            frame_mono = np.asarray(frame, dtype=np.float32).flatten()

                        now = time.time()

                        if overflowed:
                            logger.warning("Overflow en captura de audio")

                        if now - last_level_time >= self.settings.audio.level_update_interval:
                            rms = float(np.sqrt(np.mean(np.square(frame_mono)))) if frame_mono.size else 0.0
                            normalized_level = min(1.0, rms / 0.12)
                            self.runtime.push_level(normalized_level)
                            last_level_time = now

                        active_frames.append(frame_mono.copy())

            except Exception as e:
                logger.error("Error en captura de audio on-demand: %s", e)
                self.runtime.push_status("[ ERROR AUDIO ]", self.settings.ui.color_paused)
                self.runtime.push_text(f"Fallo de captura en micrófono: {e}")
                self.runtime.state.set_is_listening(False)
                self.runtime.listen_event.clear()

            finally:
                # Al salir del bloque with sd.InputStream, el stream se cierra
                # y Windows libera el endpoint de captura, regresando el auricular Bluetooth a A2DP
                self.runtime.push_level(0.0)

            # Procesar el audio capturado
            if active_frames and active_utterance_id is not None:
                raw_audio = np.concatenate(active_frames, axis=0).astype(np.float32, copy=False)
                if stream_sr != target_sample_rate:
                    audio_data = resample_audio(raw_audio, orig_sr=stream_sr, target_sr=target_sample_rate)
                    logger.debug(
                        "Audio remuestreado: %d samples (%d Hz) -> %d samples (%d Hz)",
                        len(raw_audio),
                        stream_sr,
                        len(audio_data),
                        target_sample_rate,
                    )
                else:
                    audio_data = raw_audio

                if len(audio_data) >= min_utterance_samples:
                    self._enqueue_final_utterance(active_utterance_id, audio_data)
                else:
                    logger.info("AudioCaptureWorker: grabacion descartada por ser muy corta (%d samples)", len(audio_data))
                    self.runtime.state.set_live_utterance_id(None)
                    self.runtime.state.set_is_processing(False)
                    self.runtime.show_paused_ui()
            else:
                self.runtime.state.set_live_utterance_id(None)
                self.runtime.state.set_is_processing(False)
                self.runtime.show_paused_ui()

