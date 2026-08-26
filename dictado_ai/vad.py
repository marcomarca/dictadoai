import logging
import numpy as np
from typing import Optional
from .config import Settings

logger = logging.getLogger(__name__)

class SileroVadVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.vad_class = None
        self._load_model()

    def _load_model(self):
        try:
            from silero_vad_lite import SileroVAD
            self.vad_class = SileroVAD
            logger.info("Silero VAD Lite cargado correctamente.")
        except Exception:
            logger.exception("Error cargando Silero VAD Lite. Verifique que 'silero-vad-lite' esté instalado.")

    def contains_speech(self, audio_data: np.ndarray) -> bool:
        """
        Verifica si hay voz humana en el audio_data (mono, float32).
        Procesa en ráfagas de 512 muestras.
        """
        if self.vad_class is None:
            logger.warning("VAD no disponible. Saltando verificación.")
            return True # Por seguridad, si falla el VAD, permitimos la transcripción

        try:
            # Asegurarse de que audio_data sea float32
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Inicializamos una nueva instancia para no mezclar el estado de la verificación
            vad = self.vad_class(self.settings.vad.sample_rate)

            # Procesamos en bloques de 512 muestras (que es el default requerido para 16kHz)
            FRAME_SAMPLES = 512
            FLOAT32_BYTES = 4
            FRAME_BYTES = FRAME_SAMPLES * FLOAT32_BYTES

            # Creamos un bytearray del tamaño exacto necesario
            buffer = bytearray(FRAME_BYTES)
            view = memoryview(buffer)
            
            threshold = self.settings.vad.threshold

            total_samples = len(audio_data)
            processed_samples = 0
            
            while processed_samples < total_samples:
                # Tomamos 512 samples o lo que quede
                end_sample = min(processed_samples + FRAME_SAMPLES, total_samples)
                
                # Extraemos el chunk
                chunk = audio_data[processed_samples:end_sample]
                
                # Convertimos los floats a bytes y los copiamos al buffer
                chunk_bytes = chunk.tobytes()
                bytes_to_copy = len(chunk_bytes)
                view[:bytes_to_copy] = chunk_bytes
                
                # Si el chunk es menor a FRAME_BYTES, llenamos el resto con ceros
                if bytes_to_copy < FRAME_BYTES:
                    view[bytes_to_copy:] = b"\x00" * (FRAME_BYTES - bytes_to_copy)
                
                # Procesamos el frame
                speech_prob = float(vad.process(buffer))
                
                if speech_prob >= threshold:
                    logger.debug("VAD: Detectado habla (prob: %.2f >= %.2f)", speech_prob, threshold)
                    return True
                
                processed_samples += FRAME_SAMPLES

            logger.debug("VAD: No se detectó habla (por debajo del umbral de %.2f)", threshold)
            return False
            
        except Exception:
            logger.exception("Error durante la verificación VAD")
            return True # Fallback seguro
