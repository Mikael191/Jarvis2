"""
JARVIS - Main Orchestrator
Entry point for the JARVIS AI Desktop Assistant.
"""

import asyncio
import logging
import logging.handlers
import re
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class JarvisConfig(BaseSettings):
    """Runtime configuration loaded from .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(..., description="Groq API key")
    picovoice_access_key: str = Field("", description="Picovoice access key for wake word")
    wake_word_path: str = Field("", description="Path to custom .ppn wake word file")
    tts_voice: str = "pt-BR-AntonioNeural"
    tts_speed: str = "+10%"
    groq_model: str = "llama-3.3-70b-versatile"
    memory_max_turns: int = 20
    memory_max_minutes: int = 60
    audio_sample_rate: int = 16000
    record_silence_timeout: float = 2.5
    openweathermap_api_key: str = Field("", description="OpenWeatherMap API key")
    elevenlabs_api_key: str = Field("", description="ElevenLabs API key")
    elevenlabs_voice_id: str = Field("", description="ElevenLabs voice ID")
    gemini_api_key: str = Field("", description="Google Gemini API key")
    spotify_client_id: str = Field("", description="Spotify Client ID")
    spotify_client_secret: str = Field("", description="Spotify Client Secret")
    spotify_redirect_uri: str = "http://localhost:8888/callback"

# ── Log Setup ──────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure structured, daily-rotating file logging + console output."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=logs_dir / "jarvis.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    file_fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s")
    file_handler.setFormatter(file_fmt)

    try:
        from rich.logging import RichHandler
        console_handler = RichHandler(level=logging.INFO, rich_tracebacks=True, show_time=True)
    except ImportError:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "edge_tts.communicate"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("jarvis.main")

# ── Intent Router ──────────────────────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[re.Pattern, str, object]] = [
    (re.compile(r"(?:volume|som)\s*(?:em|para|a)?\s*(\d+)", re.I),    "set_volume",    lambda m: {"level": int(m.group(1))}),
    (re.compile(r"brilho\s*(?:em|para|a)?\s*(\d+)", re.I),            "set_brightness", lambda m: {"level": int(m.group(1))}),
    (re.compile(r"(?:volume|som)\s+atual|qual\s+(?:e|ta|est[aá])\s+o\s+(?:volume|som)", re.I), "get_volume", lambda m: {}),
    (re.compile(r"bloquea?r?\s+(?:a\s+)?(?:tela|pc|computador|tudo)", re.I), "lock_screen", lambda m: {}),
    (re.compile(r"(?:pr[oóô]xim\w*|next|avan[cç]a)\s+(?:m[uú]sica|faixa|track|can[cç]ão)", re.I), "control_media", lambda m: {"action": "next"}),
    (re.compile(r"(?:anterior|previous|voltar|volta)\s+(?:m[uú]sica|faixa|track)", re.I), "control_media", lambda m: {"action": "previous"}),
    (re.compile(r"^(?:pausar?|play|reproduzir|tocar|continuar?)\s*$", re.I), "control_media", lambda m: {"action": "play_pause"}),
]

def _try_intent_route(user_input: str) -> tuple[str, dict] | None:
    for pattern, tool_name, args_fn in _INTENT_PATTERNS:
        m = pattern.search(user_input)
        if m:
            return tool_name, args_fn(m)
    return None

# ── Main Application ───────────────────────────────────────────────────────────

class JarvisApp:
    def __init__(self, config: JarvisConfig, json_ui: bool = False) -> None:
        self._config = config
        self._is_processing = False
        self._json_ui = json_ui
        self._detector = None

        from src.core.memory_manager import MemoryManager
        from src.core.groq_client import GroqClient
        from src.audio.text_to_speech import TextToSpeech
        from src.audio.speech_to_text import SpeechToText
        from src.tools.registry import ToolExecutor, GROQ_TOOLS
        from src.core.vision import VisionSystem
        from src.tools import windows_os, spotify_control
        
        windows_os._OPENWEATHERMAP_API_KEY = config.openweathermap_api_key
        self._vision = VisionSystem(gemini_api_key=config.gemini_api_key)
        windows_os._VISION_SYSTEM = self._vision

        spotify_control._CLIENT_ID = config.spotify_client_id
        spotify_control._CLIENT_SECRET = config.spotify_client_secret
        spotify_control._REDIRECT_URI = config.spotify_redirect_uri

        self._memory = MemoryManager(
            db_path=Path("data") / "memory.json",
            max_turns=config.memory_max_turns,
            max_minutes=config.memory_max_minutes,
        )
        self._groq = GroqClient(
            api_key=config.groq_api_key,
            model=config.groq_model,
            memory_manager=self._memory,
            tools=GROQ_TOOLS,
        )
        self._tts = TextToSpeech(
            voice=config.tts_voice,
            rate=config.tts_speed,
            elevenlabs_api_key=config.elevenlabs_api_key,
            elevenlabs_voice_id=config.elevenlabs_voice_id,
        )
        self._stt = SpeechToText(
            sample_rate=config.audio_sample_rate,
            silence_timeout=config.record_silence_timeout,
        )
        self._tools = ToolExecutor()
        self._memory.record_session_start()

    def _set_state(self, state: str) -> None:
        if self._json_ui:
            import json
            print(json.dumps({"jarvis_ipc": {"type": "state", "status": state}}), flush=True)

    def _log(self, sender: str, text: str) -> None:
        if self._json_ui:
            import json
            print(json.dumps({"jarvis_ipc": {"type": "log", "sender": sender, "text": text}}), flush=True)
        else:
            logger.info("[%s] %s", sender.upper(), text)

    async def _on_wake_word(self) -> None:
        if self._is_processing:
            self._tts.stop()
            return
        self._is_processing = True
        try:
            await self._handle_voice_command()
        finally:
            self._is_processing = False

    async def _handle_voice_command(self) -> None:
        import io
        self._set_state("listening")
        audio_bytes = await self._stt.record()
        if not audio_bytes:
            self._set_state("idle")
            return

        self._set_state("thinking")
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = "audio.wav"
        try:
            transcription = await asyncio.to_thread(
                self._groq._client.audio.transcriptions.create,
                file=audio_buffer,
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text",
            )
            user_text = str(transcription).strip()
        except Exception as exc:
            logger.error("STT failed: %s", exc)
            self._set_state("idle")
            return

        if not user_text:
            self._set_state("idle")
            return

        self._log("user", user_text)
        intent = _try_intent_route(user_text)
        if intent:
            tool_name, tool_args = intent
            result = await self._tools.execute(tool_name, tool_args)
            prompt = f"O usuário disse: '{user_text}'. Ferramenta '{tool_name}' resultou em: {result}. Responda em uma frase curta."
            ai_response = await self._groq.send_message(prompt, None)
        else:
            ai_response = await self._groq.send_message(user_text, self._tools)

        if ai_response:
            self._log("jarvis", ai_response)
            self._set_state("speaking")
            await self._tts.speak(ai_response)
        self._set_state("idle")

    async def _proactive_loop(self) -> None:
        from datetime import datetime
        while True:
            await asyncio.sleep(60)
            if self._is_processing: continue
            now = datetime.now()
            if now.minute == 0 and now.hour in (8, 12, 15, 18, 20):
                self._is_processing = True
                try:
                    prompt = f"System Event: It is {now.hour}:00. Dê uma saudação proativa e curta."
                    ai_response = await self._groq.send_message(prompt, None)
                    if ai_response:
                        self._log("jarvis", "Ação Proativa: " + ai_response)
                        await self._tts.speak(ai_response)
                except Exception as e:
                    logger.error("Proactive error: %s", e)
                finally:
                    self._is_processing = False

    async def _text_mode(self) -> None:
        print("Entrando em modo de texto. Digite 'sair' para encerrar.")
        while True:
            try:
                user_input = await asyncio.get_running_loop().run_in_executor(None, lambda: input("\n[Mikael] > "))
                if not user_input or user_input.lower() in ("sair", "exit", "quit"): break
                response = await self._groq.send_message(user_input.strip(), self._tools)
                print(f"\n[JARVIS] {response}\n")
                await self._tts.speak(response)
            except (EOFError, KeyboardInterrupt): break

    async def run(self, text_mode: bool = False) -> None:
        logger.info("JARVIS starting...")
        if text_mode:
            await self._text_mode()
            return

        if not self._config.picovoice_access_key:
            if self._json_ui:
                logger.warning("Voz desativada (sem Picovoice Key).")
                self._set_state("idle")
                loop = asyncio.get_running_loop()
                proactive_task = loop.create_task(self._proactive_loop())
                try:
                    while True: await asyncio.sleep(1)
                except (KeyboardInterrupt, asyncio.CancelledError): proactive_task.cancel()
                finally: self._memory.close()
                return
            else:
                await self._text_mode()
                return

        from src.audio.wake_word import WakeWordDetector
        self._detector = WakeWordDetector(
            access_key=self._config.picovoice_access_key,
            loop=asyncio.get_running_loop(),
            on_detected=self._on_wake_word,
            on_failure=self._on_wake_word_failure
        )
        self._detector.start()
        
        loop = asyncio.get_running_loop()
        proactive_task = loop.create_task(self._proactive_loop())
        try:
            while True: await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError): pass
        finally:
            if self._detector: self._detector.stop()
            self._memory.close()
            logger.info("JARVIS shut down gracefully.")

    async def _on_wake_word_failure(self, exc: Exception) -> None:
        error_msg = str(exc)
        msg = "ERRO Picovoice: Limite atingido ou chave inválida." if "Activation" in error_msg else f"ERRO voz: {error_msg}"
        logger.error(msg)
        print(f"\n[AVISO] {msg}\n[SISTEMA] Continuando apenas via TEXTO.")
        if self._json_ui:
            import json
            print(json.dumps({"jarvis_ipc": {"type": "voice_error", "message": msg}}), flush=True)

def main() -> None:
    setup_logging()
    try:
        config = JarvisConfig()
    except Exception as exc:
        print(f"[FATAL] Configuration error: {exc}")
        sys.exit(1)

    app = JarvisApp(config, json_ui="--json-ui" in sys.argv)
    text_mode = "--text" in sys.argv
    try:
        asyncio.run(app.run(text_mode=text_mode))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
