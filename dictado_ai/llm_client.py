import logging
from typing import Optional

import requests

from .config import Settings, LlmProvider

logger = logging.getLogger(__name__)


class LlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def correct_text(
        self,
        text: str,
        system_prompt_override: str | None = None,
        vocabulary_hints: list[str] | None = None,
    ) -> Optional[str]:
        if not text or not text.strip():
            return text

        provider = self.settings.active_provider
        if provider == LlmProvider.DISABLED:
            return text

        # Si se usa local y está deshabilitado en config
        if provider == LlmProvider.OLLAMA and not self.settings.ollama.enabled:
            return text

        base_prompt = system_prompt_override or self.settings.ollama.system_prompt
        if "{text}" in base_prompt:
            system_prompt = base_prompt.replace("{text}", text)
        else:
            system_prompt = f"{base_prompt}\n\nTexto transcrito a formatear:\n{text}"

        if vocabulary_hints:
            vocab_text = ", ".join(vocabulary_hints)
            system_prompt += f"\n\nVOCABULARIO CLAVE (respeta estrictamente la ortografía y mayúsculas de estos términos):\n{vocab_text}"

        try:
            logger.debug("Enviando texto a %s para corrección: '%s'", provider.value, text)
            
            if provider == LlmProvider.OLLAMA:
                return self._call_ollama(system_prompt, text)
            elif provider == LlmProvider.GROQ:
                return self._call_groq(system_prompt, text)
            elif provider == LlmProvider.GEMINI:
                return self._call_gemini(system_prompt, text)
            elif provider == LlmProvider.OPENROUTER:
                return self._call_openrouter(system_prompt, text)

            else:
                return text

        except Exception as e:
            logger.error("Error inesperado procesando con %s: %s", provider.value, e)
            return text

    def _call_ollama(self, prompt: str, original_text: str) -> str:
        url = f"{self.settings.ollama.url.rstrip('/')}/api/generate"
        payload = {
            "model": self.settings.ollama.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "top_k": 10, "top_p": 0.5},
        }
        res = requests.post(url, json=payload, timeout=self.settings.ollama.timeout)
        res.raise_for_status()
        corrected = res.json().get("response", "").strip()
        return self._clean_quotes(corrected) or original_text

    def _call_groq(self, prompt: str, original_text: str) -> str:
        api_key = self.settings.api_keys.groq
        if not api_key:
            logger.warning("GROQ_API_KEY no configurada.")
            return original_text

        from groq import Groq
        client = Groq(api_key=api_key)
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        corrected = res.choices[0].message.content.strip()
        return self._clean_quotes(corrected) or original_text

    def _call_gemini(self, prompt: str, original_text: str) -> str:
        # ==========================================
        # GEMINI (texto->texto) - FREE TIER REAL
        # ==========================================
        api_key = self.settings.api_keys.gemini
        if not api_key:
            logger.warning("GEMINI_API_KEY no configurada.")
            return original_text

        from google import genai
        client = genai.Client(api_key=api_key)

        for model_name in (
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-2.5-flash-lite",
        ):
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"temperature": 0.0}
                )
                corrected = res.text.strip() if res.text else ""
                if corrected:
                    return self._clean_quotes(corrected) or original_text
            except Exception as e:
                logger.warning("Gemini falló con %s: %s", model_name, e)

        return original_text

    def _call_openrouter(self, prompt: str, original_text: str) -> str:
        # ===============================
        # OPENROUTER (texto) - FREE TIER
        # ===============================
        api_key = self.settings.api_keys.openrouter
        if not api_key:
            logger.warning("OPENROUTER_API_KEY no configurada.")
            return original_text

        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        res = client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        corrected = res.choices[0].message.content.strip()
        return self._clean_quotes(corrected) or original_text

    def _clean_quotes(self, corrected: str) -> str:
        if not corrected:
            return ""

        # Intentar extraer el "corrected_text" de un JSON (incluso si está envuelto en markdown)
        try:
            import json
            import re

            json_str = corrected
            # Extraer bloque de código si el LLM devuelve ```json ... ```
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', corrected, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1)

            data = json.loads(json_str)
            if isinstance(data, dict) and "corrected_text" in data:
                return str(data["corrected_text"]).strip()
        except Exception:
            pass

        # Fallback clásico: si no fue JSON válido, solo quitar comillas externas si existen
        if corrected.startswith('"') and corrected.endswith('"') and len(corrected) > 1:
            return corrected[1:-1].strip()
        elif corrected.startswith("'") and corrected.endswith("'") and len(corrected) > 1:
            return corrected[1:-1].strip()
        return corrected
