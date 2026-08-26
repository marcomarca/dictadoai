from __future__ import annotations

import logging
import re
from typing import Optional

from .runtime import RuntimeState

logger = logging.getLogger(__name__)


def normalize_spaces(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def clean_raw_transcript(text: str) -> str:
    text = re.sub(
        r"\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*",
        "",
        text,
    )
    text = normalize_spaces(text)
    return text.strip(" \t\n\r\ufeff")


def is_suspicious_transcript(text: str, suspicious_list: list[str]) -> bool:
    """
    Verifica si el texto coincide con una lista de patrones sospechosos (hallucinations comunes).
    """
    if not text:
        return False
    
    lowered = text.lower().strip()
    # Limpiar puntuación para comparar
    stripped = re.sub(r"[^\w\s]", "", lowered).strip()
    
    for pattern in suspicious_list:
        p = pattern.lower().strip()
        # Si el patrón está contenido en el texto (sin importar el largo)
        if p in stripped:
            return True
            
    # También incluimos los tokens de traducción/música típicos
    if "amara.org" in lowered or "traducido por" in lowered or "[música]" in lowered or "(risas)" in lowered:
        return True

    return False


def looks_hallucinatory(text: str, audio_duration_s: float) -> bool:
    if not text:
        logger.debug("looks_hallucinatory: texto vacío")
        return True

    lowered = text.lower()
    
    # Marcadores universales de alucinación que no suelen ser susurros reales
    if "amara.org" in lowered or "traducido por" in lowered:
        logger.debug("looks_hallucinatory: token de traducción encontrado en '%s'", text)
        return True

    # Revisar si el texto (sin puntuación) es una de las palabras basura comunes
    stripped = re.sub(r"[^\w\s]", "", lowered).strip()
    default_blacklist = {
        "música", "musica", "subtítulos", "subtitulos", "suscríbete", "suscribete", 
        "silencio", "gracias por ver", "gracias por ver el video", "gracias"
    }
    
    if stripped in default_blacklist or "amara.org" in lowered:
        logger.debug("looks_hallucinatory: ruido exacto '%s' detectado en '%s'", stripped, text)
        return True
        
    # Verificar si es una etiqueta tipo [Música] o (Risas) que ocupa toda la transcripción
    if re.match(r"^[\[\(].*?[\]\)]\.?$", lowered.strip()):
        logger.debug("looks_hallucinatory: etiqueta de sonido aislada detectada '%s'", text)
        return True

    alnum_count = len(re.sub(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]", "", text, flags=re.UNICODE))
    if alnum_count < 2:
        logger.debug("looks_hallucinatory: muy pocos caracteres alfanuméricos (%d) en '%s'", alnum_count, text)
        return True

    punctuation_count = len(re.findall(r"[.,;:!?…-]", text))
    if len(text) <= 8 and punctuation_count >= max(3, len(text) // 2):
        logger.debug("looks_hallucinatory: demasiada puntuación para un texto corto en '%s'", text)
        return True

    if re.search(r"([!?,;:])\1{2,}", text):
        logger.debug("looks_hallucinatory: puntuación repetida más de 3 veces consecutivas en '%s'", text)
        return True

    words = re.findall(r"\b\w+\b", lowered, flags=re.UNICODE)
    if len(words) >= 4:
        uniq_ratio = len(set(words)) / len(words)
        if uniq_ratio < 0.35:
            logger.debug("looks_hallucinatory: repetición excesiva de palabras (ratio %.2f) en '%s'", uniq_ratio, text)
            return True

    if audio_duration_s > 0 and len(text) / max(audio_duration_s, 0.01) > 55:
        logger.debug("looks_hallucinatory: velocidad de habla incoherente (%.2f chars/s) en '%s'", len(text) / audio_duration_s, text)
        return True

    return False


def normalize_punctuation(text: str) -> str:
    text = re.sub(r"\.{3,}", ".", text)
    text = re.sub(r"([,;:!?]){2,}", r"\1", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([¿¡])(\s+)", r"\1", text)
    return text.strip()


def adapt_leading_case(text: str, runtime_state: RuntimeState) -> str:
    if not text:
        return text

    if text[0].isalpha() and text[0].isupper() and not runtime_state.last_text_ended_sentence():
        text = text[0].lower() + text[1:]
    return text


def postprocess_transcript(
    text: str,
    audio_duration_s: float,
    is_partial: bool,
    runtime_state: RuntimeState,
    force_allow: bool = False,
) -> Optional[str]:
    original_text = text
    text = clean_raw_transcript(text)
    if not text:
        logger.debug("postprocess_transcript: el texto '%s' quedó vacío tras limpiar raw transcript", original_text)
        return None

    if not force_allow and looks_hallucinatory(text, audio_duration_s):
        logger.info("postprocess_transcript: texto descartado como alucinación: '%s'", text)
        return None

    text = normalize_punctuation(text)

    if not is_partial:
        text = adapt_leading_case(text, runtime_state)

    text = normalize_spaces(text)
    return text or None
