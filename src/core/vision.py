"""
JARVIS - Computer Vision Module
Allows the assistant to "see" the screen using mss for screenshots
and Google Gemini 1.5 Flash for multimodal image analysis.
"""

import io
import logging
import time
from typing import Optional

import requests
import mss
from PIL import Image

try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
except ImportError:
    genai = None

logger = logging.getLogger("jarvis.core.vision")

# System prompt specialized for screen analysis
VISION_PROMPT = """Você é o JARVIS, um assistente virtual visualizando a tela do usuário.
Você recebeu uma captura de tela (screenshot) do computador dele junto com a pergunta ou comando dele.
Regras da análise:
- Seja extremamente conciso, vá direto ao ponto.
- Responda apenas o que foi perguntado, baseando-se na imagem.
- Se o usuário pedir um resumo de um texto na tela, resuma a parte principal.
- Se houver código na tela e for solicitado para analisar, foque no código visível.
- Fale de forma objetiva, em português do Brasil.
"""


class VisionSystem:
    def __init__(self, gemini_api_key: str = "") -> None:
        self.enabled = False
        
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY not set. Vision capabilities (Screen Awareness) disabled.")
            return
            
        if not genai:
            logger.error("google-generativeai module not found. Vision disabled.")
            return
            
        try:
            genai.configure(api_key=gemini_api_key)
            self._model = genai.GenerativeModel("gemini-2.0-flash")
            self.enabled = True
            logger.info("Vision System initialized with Gemini 1.5 Flash.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Vision: {e}")

    def capture_screen(self) -> Optional[Image.Image]:
        """Captures the primary monitor and returns a PIL Image."""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # The primary monitor
                sct_img = sct.grab(monitor)
                # Convert to PIL Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # Optional optimization: resize image if it is too massive 
                # (e.g., 4k screen) to save upload time to Gemini (let's restrict width to ~1920)
                if img.width > 1920:
                    ratio = 1920 / img.width
                    new_size = (1920, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                return img
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            return None

    async def analyze_screen(self, user_prompt: str) -> str:
        """
        Takes a screenshot, sends it to Gemini 1.5 Flash with the prompt,
        and returns the AI's textual description/answer.
        """
        if not self.enabled:
            return "Erro: O sistema de visão está desativado. Verifique a chave GEMINI_API_KEY no arquivo .env."
            
        img = self.capture_screen()
        if not img:
            return "Erro: Falha ao capturar a tela."
            
        logger.info(f"Analyzing screen with prompt: '{user_prompt}'")
        
        try:
            # We enforce blocking safety settings to not block coding/hacking questions by accident
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # This is a synchronous call wrapped visually; ideally could use asyncio.to_thread 
            # if we wanted it perfectly non-blocking, but for now it's okay.
            import asyncio
            
            def _generate():
                response = self._model.generate_content(
                    [VISION_PROMPT, f"Usuário: {user_prompt}", img],
                    safety_settings=safety_settings
                )
                return response.text
                
            prediction = await asyncio.to_thread(_generate)
            return prediction
            
        except Exception as e:
            logger.error(f"Gemini vision error: {e}", exc_info=True)
            return f"Desculpe, senhor. Houve um erro na análise visual: {str(e)}"
