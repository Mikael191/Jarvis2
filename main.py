"""
JARVIS - Main Orchestrator
Entry point for the JARVIS AI Desktop Assistant.

Startup sequence:
1. Initialize structured logging (daily rotating log files)
2. Load config from .env via pydantic-settings
3. Boot memory manager (TinyDB + long-term memory)
4. Register Groq tools (function calling)
5. Initialize Groq client
6. Initialize TTS engine
7. Initialize STT engine
8. (Optional) Start wake word detection loop
9. Event-driven: on wake word → record → transcribe → AI → speak
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
    # ElevenLabs — sign up free at https://elevenlabs.io
    # You can supply multiple keys separated by commas (e.g. key1,key2) for automatic rotation when credits run out
    elevenlabs_api_key: str = Field("", description="ElevenLabs API key (free tier: 10k chars/month)")
    elevenlabs_voice_id: str = Field("", description="ElevenLabs voice ID (default: George)")
    # Gemini (Google) - Vision model required for "seeing" the screen (1,500 free requests/day)
    gemini_api_key: str = Field("", description="Google Gemini API key for Computer Vision")


# ── Log Setup ──────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure structured, daily-rotating file logging + console output."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=logs_dir / "jarvis.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    try:
        from rich.logging import RichHandler
        console_handler = RichHandler(level=logging.INFO, rich_tracebacks=True, show_time=True)
    except ImportError:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "edge_tts.communicate"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Logger (declared here so it is available to all module-level code below) ───
logger = logging.getLogger("jarvis.main")


# ── Intent Router ──────────────────────────────────────────────────────────────
# Detects trivial commands and routes them directly to tools, bypassing the LLM.
# Reduces response latency from ~2s to near-instant for common OS commands.

_INTENT_PATTERNS: list[tuple[re.Pattern, str, object]] = [
    # Volume: "volume 70", "coloca o volume em 70", "aumenta o volume para 80%"
    (re.compile(r"(?:volume|som)\s*(?:em|para|a)?\s*(\d+)", re.I),    "set_volume",    lambda m: {"level": int(m.group(1))}),
    # Brightness: "brilho 50", "coloca o brilho em 50"
    (re.compile(r"brilho\s*(?:em|para|a)?\s*(\d+)", re.I),            "set_brightness", lambda m: {"level": int(m.group(1))}),
    # Get volume: "volume atual", "qual o volume", "quanto ta o volume"
    (re.compile(r"(?:volume|som)\s+atual|qual\s+(?:e|ta|est[aá])\s+o\s+(?:volume|som)", re.I), "get_volume", lambda m: {}),
    # Lock: "bloquear tela", "bloqueia o pc"
    (re.compile(r"bloquea?r?\s+(?:a\s+)?(?:tela|pc|computador|tudo)", re.I), "lock_screen", lambda m: {}),
    # Next track
    (re.compile(r"(?:pr[oóô]xim\w*|next|avan[cç]a)\s+(?:m[uú]sica|faixa|track|can[cç]ão)", re.I), "control_media", lambda m: {"action": "next"}),
    # Previous track
    (re.compile(r"(?:anterior|previous|voltar|volta)\s+(?:m[uú]sica|faixa|track)", re.I), "control_media", lambda m: {"action": "previous"}),
    # Play/pause
    (re.compile(r"^(?:pausar?|play|reproduzir|tocar|continuar?)\s*$", re.I), "control_media", lambda m: {"action": "play_pause"}),
]


def _try_intent_route(user_input: str) -> tuple[str, dict] | None:
    """
    Match user_input against intent patterns for instant tool dispatch.
    Returns (tool_name, args) if matched, else None.
    """
    for pattern, tool_name, args_fn in _INTENT_PATTERNS:
        m = pattern.search(user_input)
        if m:
            args = args_fn(m)
            logger.info("Intent router matched '%s' → %s(%s)", user_input, tool_name, args)
            return tool_name, args
    return None


# ── Main Application ───────────────────────────────────────────────────────────

class JarvisApp:
    """Central application class that owns and orchestrates all subsystems."""

    def __init__(self, config: JarvisConfig, json_ui: bool = False) -> None:
        self._config = config
        self._is_processing = False
        self._json_ui = json_ui

        # Import subsystems
        from src.core.memory_manager import MemoryManager
        from src.core.groq_client import GroqClient
        from src.audio.text_to_speech import TextToSpeech
        from src.audio.speech_to_text import SpeechToText
        from src.tools.registry import ToolExecutor, GROQ_TOOLS
        from src.core.vision import VisionSystem
        from src.tools import windows_os

        # Inject OpenWeatherMap key and VisionSystem into the tools module
        windows_os._OPENWEATHERMAP_API_KEY = config.openweathermap_api_key
        
        self._vision = VisionSystem(gemini_api_key=config.gemini_api_key)
        windows_os._VISION_SYSTEM = self._vision

        self._memory = MemoryManager(
            db_path=Path("data") / "memory.json",
            max_turns=config.memory_max_turns,
            max_minutes=config.memory_max_minutes,
        )
        self._tool_executor = ToolExecutor()
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

        self._memory.record_session_start()
        logger.info("JarvisApp subsystems initialized.")

    # ── Callbacks (real methods — NOT nested functions) ─────────────────────────

    def _set_state(self, state: str) -> None:
        """Update Jarvis's internal state mechanism."""
        if self._json_ui:
            import json
            print(json.dumps({"jarvis_ipc": {"type": "state", "status": state}}), flush=True)
        else:
            logger.debug("State changed to: %s", state)

    def _log(self, sender: str, text: str) -> None:
        """Log conversation trace."""
        if self._json_ui:
            import json
            print(json.dumps({"jarvis_ipc": {"type": "log", "sender": sender, "text": text}}), flush=True)
        else:
            logger.info("[%s] %s", sender.upper(), text)

    # ── Voice pipeline ──────────────────────────────────────────────────────────

    async def _on_wake_word(self) -> None:
        """Called on wake word detection. Interrupts TTS if speaking."""
        if self._is_processing:
            # Interrupt ongoing TTS so Jarvis listens immediately
            self._tts.stop()
            logger.debug("Wake word during processing — TTS interrupted.")
            return

        self._is_processing = True
        try:
            await self._handle_voice_command()
        finally:
            self._is_processing = False

    async def _handle_voice_command(self) -> None:
        """Full pipeline: record → STT → (intent router OR LLM) → TTS."""
        import io

        logger.info("Wake word triggered. Recording...")
        self._set_state("listening")
        self._log("system", "Wake word detectado. Gravando...")

        # 1. Record voice
        audio_bytes = await self._stt.record()
        if not audio_bytes:
            logger.info("No speech captured.")
            self._set_state("idle")
            return

        self._set_state("thinking")

        # 2. Transcribe via Groq Whisper
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
            logger.error("STT failed: %s", exc, exc_info=True)
            self._set_state("idle")
            return

        if not user_text:
            self._set_state("idle")
            return

        logger.info("User said: '%s'", user_text[:100])
        self._log("user", user_text)

        # 3. Intent router (fast path — skips LLM call)
        intent = _try_intent_route(user_text)
        if intent:
            tool_name, tool_args = intent
            result = await self._tool_executor.execute(tool_name, tool_args)
            # Generate a brief confirmation via LLM
            prompt = (
                f"O usuário disse: '{user_text}'. "
                f"A ferramenta '{tool_name}' foi chamada com resultado: {result}. "
                "Confirme brevemente o que foi feito em no máximo 1 frase curta."
            )
            ai_response = await self._groq.send_message(prompt, None)
        else:
            # 4. Full LLM pipeline with tool calling
            ai_response = await self._groq.send_message(user_text, self._tool_executor)

        if not ai_response:
            self._set_state("idle")
            return

        self._log("jarvis", ai_response)
        logger.info("JARVIS response: '%s'", ai_response[:100])

        # 5. Speak
        self._set_state("speaking")
        await self._tts.speak(ai_response)
        self._set_state("idle")

    async def _proactive_loop(self) -> None:
        """
        Background task that allows Jarvis to take proactive actions
        without being explicitly called by the user.
        """
        from datetime import datetime
        logger.info("Proactive loop started.")
        while True:
            await asyncio.sleep(60) # Only check conditions once per minute
            
            if self._is_processing:
                continue
                
            now = datetime.now()
            # Simple example: Proactive greeting specifically at these exact hours (minute 0)
            if now.minute == 0 and now.hour in (8, 12, 15, 18, 20):
                self._is_processing = True
                try:
                    logger.info("Triggering proactive time-based action...")
                    prompt = (
                        f"System Event: It is now {now.hour}:00. "
                        "Traga uma fala proativa, curta e natural avisando o usuário sobre a hora, "
                        "e sugira algo (ex: almoço, beber água, pausa, boa noite). Sem formatação."
                    )
                    ai_response = await self._groq.send_message(prompt, None)
                    if ai_response:
                        self._log("jarvis", "Ação Proativa: " + ai_response)
                        self._set_state("speaking")
                        await self._tts.speak(ai_response)
                        self._set_state("idle")
                except Exception as exc:
                    logger.error("Proactive action failed: %s", exc)
                finally:
                    self._is_processing = False

    # ── Text mode (dev / no microphone) ────────────────────────────────────────

    async def _text_mode(self) -> None:
        """Interactive text-based mode for development and testing."""
        logger.info("Starting text mode. Type 'sair' to quit.")
        try:
            from rich.console import Console
            console = Console()
            def _print_jarvis(text: str) -> None:
                console.print(f"\n[bold green][JARVIS][/bold green] {text}\n")
            def _print_thinking() -> None:
                console.print("[cyan]Pensando...[/cyan]")
        except ImportError:
            def _print_jarvis(text: str) -> None:
                print(f"\n[JARVIS] {text}\n")
            def _print_thinking() -> None:
                print("Pensando...")

        while True:
            try:
                user_input = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: input("\n[Mikael] > ")
                )
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "sair"):
                break

            _print_thinking()

            intent = _try_intent_route(user_input)
            if intent:
                tool_name, tool_args = intent
                result = await self._tool_executor.execute(tool_name, tool_args)
                prompt = (
                    f"O usuário disse: '{user_input}'. "
                    f"Ferramenta '{tool_name}' executada, resultado: {result}. "
                    "Confirme brevemente."
                )
                response = await self._groq.send_message(prompt, None)
            else:
                response = await self._groq.send_message(user_input, self._tool_executor)

            _print_jarvis(response)
            await self._tts.speak(response)

    # ── Run ────────────────────────────────────────────────────────────────────

    async def run(self, text_mode: bool = False) -> None:
        """Main async run loop."""
        logger.info("=" * 60)
        logger.info("JARVIS starting. Model: %s", self._config.groq_model)
        logger.info("=" * 60)

        if text_mode:
            await self._text_mode()
            return

        if not self._config.picovoice_access_key:
            # When running under Electron (--json-ui) without a wake word key,
            # we must NOT fall into text mode because stdin is not a real console
            # and input() will raise EOFError immediately, crashing the process.
            if self._json_ui:
                logger.warning("PICOVOICE_ACCESS_KEY not set — running in Electron UI mode (no voice).")
                self._set_state("idle")
                # Start proactive loop and sleep indefinitely
                loop = asyncio.get_running_loop()
                proactive_task = loop.create_task(self._proactive_loop())
                try:
                    while True:
                        await asyncio.sleep(1)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    proactive_task.cancel()
                finally:
                    self._memory.close()
                return
            else:
                logger.warning("PICOVOICE_ACCESS_KEY not set — falling back to text mode.")
                await self._text_mode()
                return

        from src.audio.wake_word import WakeWordDetector

        loop = asyncio.get_running_loop()
        keyword_paths = None
        keywords = None

        if self._config.wake_word_path and Path(self._config.wake_word_path).exists():
            keyword_paths = [self._config.wake_word_path]
            logger.info("Using custom wake word: %s", self._config.wake_word_path)
        else:
            keywords = ["jarvis"]
            logger.info("Using built-in wake word: 'jarvis'")

        detector = WakeWordDetector(
            access_key=self._config.picovoice_access_key,
            loop=loop,
            on_detected=self._on_wake_word,
            keywords=keywords,
            keyword_paths=keyword_paths,
        )

        detector.start()
        logger.info("JARVIS is ready. Say 'Jarvis' to activate.")

        # Start proactive background tasks
        proactive_task = loop.create_task(self._proactive_loop())

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutdown requested.")
            proactive_task.cancel()
        finally:
            detector.stop()
            self._memory.close()
            logger.info("JARVIS shut down gracefully.")


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Bootstrap JARVIS."""
    setup_logging()

    try:
        config = JarvisConfig()
    except Exception as exc:
        print(f"[FATAL] Configuration error: {exc}")
        print("Copy .env.example to .env and fill in required values.")
        sys.exit(1)

    app = JarvisApp(config, json_ui="--json-ui" in sys.argv)
    text_mode = "--text" in sys.argv

    try:
        asyncio.run(app.run(text_mode=text_mode))
    except KeyboardInterrupt:
        logger.info("JARVIS terminated by user.")


if __name__ == "__main__":
    main()
