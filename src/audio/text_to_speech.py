"""
JARVIS - Text to Speech Module

Priority:
  1. ElevenLabs (human-grade neural voice) — if ELEVENLABS_API_KEY is set
  2. Edge-TTS (Microsoft neural voices) — free fallback, always available

ElevenLabs free tier: 10,000 characters/month
Sign up at: https://elevenlabs.io (free account)
"""

import asyncio
import ctypes
import io
import logging
import os
import tempfile
from typing import TYPE_CHECKING

import edge_tts

logger = logging.getLogger("jarvis.audio.text_to_speech")

# ── ElevenLabs defaults ────────────────────────────────────────────────────────
# "George" — calm, warm, professional (ideal for JARVIS)
# Other great options (copy the ID to ELEVENLABS_VOICE_ID in .env):
#   Adam    → pNInz6obpgDQGcFmaJgB  (deep, authoritative)
#   Antoni  → ErXwobaYiN019PkySvjV  (well-rounded, smooth)
#   Josh    → TxGEqnHWrfWFTfGW9XjX  (younger, energetic)
#   Charlie → IKne3meq5aSn9XLyUdCD  (casual, friendly)
ELEVENLABS_DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George
ELEVENLABS_MODEL = "eleven_multilingual_v2"             # Best quality, supports PT-BR

# ── Edge-TTS defaults (fallback) ───────────────────────────────────────────────
EDGE_DEFAULT_VOICE = "pt-BR-AntonioNeural"
EDGE_DEFAULT_RATE = "+0%"
EDGE_DEFAULT_VOLUME = "+0%"


class TextToSpeech:
    """
    Hybrid TTS engine.
    - Primary: ElevenLabs (human-grade voice, requires free API key)
    - Fallback: Microsoft Edge-TTS (neural voices, always free, no key needed)

    The playback engine is native Windows MCI to avoid audio library crashes.
    """

    def __init__(
        self,
        voice: str = EDGE_DEFAULT_VOICE,
        rate: str = EDGE_DEFAULT_RATE,
        volume: str = EDGE_DEFAULT_VOLUME,
        elevenlabs_api_key: str = "",
        elevenlabs_voice_id: str = ELEVENLABS_DEFAULT_VOICE_ID,
    ) -> None:
        self._edge_voice = voice
        self._edge_rate = rate
        self._edge_volume = volume
        self._is_playing = False

        # ElevenLabs clients (supports multiple keys for rotation)
        self._el_clients = []
        self._el_current_idx = 0
        self._el_voice_id = elevenlabs_voice_id or ELEVENLABS_DEFAULT_VOICE_ID
        self._use_elevenlabs = False

        if elevenlabs_api_key:
            try:
                from elevenlabs.client import ElevenLabs
                keys = [k.strip() for k in elevenlabs_api_key.split(",") if k.strip()]
                if keys:
                    self._el_clients = [ElevenLabs(api_key=k) for k in keys]
                    self._use_elevenlabs = True
                    logger.info(
                        "ElevenLabs TTS active with %d key(s). Voice ID: %s | Model: %s",
                        len(keys), self._el_voice_id, ELEVENLABS_MODEL,
                    )
            except ImportError:
                logger.warning(
                    "elevenlabs package not installed. Falling back to Edge-TTS. "
                    "Run: pip install elevenlabs"
                )
        else:
            logger.info(
                "ElevenLabs API key not set. Using Edge-TTS fallback (%s).", voice
            )

    # ── Public interface ────────────────────────────────────────────────────────

    async def speak(self, text: str) -> None:
        """
        Synthesize and play text. Blocks until audio finishes.
        Interrupts any currently playing audio before starting.
        """
        if not text or not text.strip():
            logger.warning("TTS speak() called with empty text.")
            return

        if self._is_playing:
            self.stop()

        # Clean up markdown that sounds bad when spoken aloud
        text = _clean_for_speech(text)

        self._is_playing = True
        logger.info("TTS: '%s...'", text[:60].replace("\n", " "))

        try:
            if self._use_elevenlabs and self._el_clients:
                audio_bytes = await self._synthesize_elevenlabs(text)
                if audio_bytes:
                    await self._play_audio(audio_bytes, ext="mp3")
                    return
                # Fall through to Edge-TTS on error
                logger.warning("ElevenLabs failed — falling back to Edge-TTS.")

            audio_bytes = await self._synthesize_edge(text)
            if audio_bytes:
                await self._play_audio(audio_bytes, ext="mp3")
        except Exception as exc:
            logger.error("TTS speak() failed: %s", exc, exc_info=True)
        finally:
            self._is_playing = False

    def stop(self) -> None:
        """Immediately stop any ongoing audio playback."""
        try:
            ctypes.windll.winmm.mciSendStringW("stop jarvis_speech", None, 0, None)
            ctypes.windll.winmm.mciSendStringW("close jarvis_speech", None, 0, None)
        except Exception:
            pass
        self._is_playing = False
        logger.debug("TTS playback stopped.")

    # ── Synthesis backends ──────────────────────────────────────────────────────

    async def _synthesize_elevenlabs(self, text: str) -> bytes | None:
        """Synthesize via ElevenLabs API with key rotation and return MP3 bytes."""
        last_error = None
        
        while self._el_current_idx < len(self._el_clients):
            current_client = self._el_clients[self._el_current_idx]
            try:
                def _generate() -> bytes:
                    audio_generator = current_client.text_to_speech.convert(
                        text=text,
                        voice_id=self._el_voice_id,
                        model_id=ELEVENLABS_MODEL,
                        output_format="mp3_44100_128",
                    )
                    return b"".join(audio_generator)

                audio_bytes = await asyncio.get_running_loop().run_in_executor(None, _generate)
                logger.debug("ElevenLabs synthesis OK (Key %d): %d bytes", self._el_current_idx, len(audio_bytes))
                return audio_bytes
            except Exception as exc:
                error_str = str(exc).lower()
                last_error = exc
                
                # Rotate key if error is related to quota, auth, or limits
                if any(x in error_str for x in ["quota", "401", "429", "insufficient", "credit", "unauthorized"]):
                    logger.warning(
                        "ElevenLabs key at index %d failed (quota/auth). Rotating to next key. Error: %s", 
                        self._el_current_idx, exc
                    )
                    self._el_current_idx += 1
                else:
                    logger.error("ElevenLabs synthesis fatal error (Key %d): %s", self._el_current_idx, exc)
                    break
                    
        if self._el_current_idx >= len(self._el_clients):
            logger.error("All ElevenLabs keys exhausted or failed. Last error: %s", last_error)

        return None

    async def _synthesize_edge(self, text: str) -> bytes | None:
        """Synthesize via Edge-TTS and return MP3 bytes."""
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self._edge_voice,
                rate=self._edge_rate,
                volume=self._edge_volume,
            )
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            buf.seek(0)
            data = buf.read()
            if not data:
                logger.warning("Edge-TTS synthesis returned empty audio.")
                return None
            logger.debug("Edge-TTS synthesis OK: %d bytes", len(data))
            return data
        except Exception as exc:
            logger.error("Edge-TTS synthesis error: %s", exc, exc_info=True)
            return None

    # ── Playback ────────────────────────────────────────────────────────────────

    async def _play_audio(self, audio_bytes: bytes, ext: str = "mp3") -> None:
        """Play audio bytes using Windows MCI (non-blocking via executor)."""
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, self._blocking_mci_play, audio_bytes, ext
            )
        except Exception as exc:
            logger.error("TTS playback error: %s", exc, exc_info=True)

    def _blocking_mci_play(self, audio_bytes: bytes, ext: str = "mp3") -> None:
        """Synchronous playback via Windows MCI API (runs in thread executor)."""
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=f".{ext}")
            with os.fdopen(fd, "wb") as f:
                f.write(audio_bytes)

            ctypes.windll.winmm.mciSendStringW("close jarvis_speech", None, 0, None)

            cmd_open = f'open "{path}" type mpegvideo alias jarvis_speech'
            if ctypes.windll.winmm.mciSendStringW(cmd_open, None, 0, None) != 0:
                logger.error("MCI Open failed for %s", path)
                return

            ctypes.windll.winmm.mciSendStringW("play jarvis_speech wait", None, 0, None)
        except Exception as exc:
            logger.error("MCI playback failed: %s", exc, exc_info=True)
        finally:
            ctypes.windll.winmm.mciSendStringW("close jarvis_speech", None, 0, None)
            if path:
                try:
                    os.remove(path)
                except Exception:
                    pass

    # ── Utilities ───────────────────────────────────────────────────────────────

    async def set_voice(self, voice: str) -> None:
        """Change the Edge-TTS voice at runtime."""
        self._edge_voice = voice
        logger.info("Edge-TTS voice changed to: %s", voice)

    @property
    def engine(self) -> str:
        """Return the name of the active TTS engine."""
        return "ElevenLabs" if self._use_elevenlabs else "Edge-TTS"

    @staticmethod
    async def list_edge_voices(language_filter: str = "pt-BR") -> list[dict]:
        """List available Edge-TTS voices."""
        voices = await edge_tts.list_voices()
        if language_filter:
            voices = [v for v in voices if v.get("Locale", "").startswith(language_filter)]
        return voices


def _clean_for_speech(text: str) -> str:
    """
    Remove markdown symbols that sound awkward when spoken aloud.
    Keeps punctuation and natural structure.
    """
    import re
    # Remove markdown headers, bold, italic, backticks
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", text)
    # Remove markdown links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove bullet points but keep content
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    # Collapse multiple newlines into one pause
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    return text.strip()
