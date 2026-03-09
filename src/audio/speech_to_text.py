"""
JARVIS - Speech to Text Module
Records audio after wake word detection and transcribes it via Gemini's multimodal API.
Optionally supports local Whisper as a fallback (lower latency, no API cost).
"""

import asyncio
import io
import logging
import struct
import time
import wave
from typing import Callable

import pvrecorder

logger = logging.getLogger("jarvis.audio.speech_to_text")

# Default recording settings
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 500       # RMS amplitude below this = silence
SILENCE_TIMEOUT = 2.5         # Seconds of silence before stopping
MAX_RECORD_SECONDS = 30       # Hard cap on recording duration
FRAME_LENGTH = 512            # Samples per frame for recorder


class SpeechToText:
    """
    Records audio from the microphone until silence is detected,
    then transcribes using Gemini's multimodal API.

    Dependencies:
        - pvrecorder for mic access
        - GeminiClient for transcription
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        silence_timeout: float = SILENCE_TIMEOUT,
        max_seconds: float = MAX_RECORD_SECONDS,
        silence_threshold: int = SILENCE_THRESHOLD,
    ) -> None:
        self._sample_rate = sample_rate
        self._silence_timeout = silence_timeout
        self._max_seconds = max_seconds
        self._silence_threshold = silence_threshold

    def _compute_rms(self, frame: list[int]) -> float:
        """Return RMS amplitude of a PCM int16 frame."""
        if not frame:
            return 0.0
        squared_sum = sum(s * s for s in frame)
        return (squared_sum / len(frame)) ** 0.5

    async def record(self) -> bytes | None:
        """
        Record audio from the microphone until silence is detected or max duration is reached.

        Returns:
            WAV-encoded bytes of the recorded speech, or None if nothing was captured.
        """
        logger.info("Recording started — speak now...")

        frames: list[list[int]] = []
        recorder = None

        try:
            devices = pvrecorder.PvRecorder.get_available_devices()
            indices_to_try = [-1] + list(range(len(devices)))
            
            for idx in indices_to_try:
                try:
                    recorder = pvrecorder.PvRecorder(
                        frame_length=FRAME_LENGTH,
                        device_index=idx,
                    )
                    logger.info("STT Initialized PvRecorder with device_index=%d", idx)
                    break
                except RuntimeError:
                    pass
            else:
                logger.critical("All STT microphone attempts failed. Available mics: %s", devices)
                raise RuntimeError("Failed to initialize PvRecorder for STT on any device.")
            recorder.start()

            last_speech_time = time.monotonic()
            start_time = time.monotonic()
            has_speech = False

            while True:
                # Yield control so the event loop stays responsive
                await asyncio.sleep(0)

                # Read a frame (blocking — runs in executor as workaround)
                frame = await asyncio.get_event_loop().run_in_executor(
                    None, recorder.read
                )
                frames.append(frame)

                rms = self._compute_rms(frame)

                if rms > self._silence_threshold:
                    has_speech = True
                    last_speech_time = time.monotonic()

                elapsed = time.monotonic() - start_time
                silence_duration = time.monotonic() - last_speech_time

                # Stop conditions
                if has_speech and silence_duration >= self._silence_timeout:
                    logger.info("Silence detected after %.1fs. Stopping.", silence_duration)
                    break
                if elapsed >= self._max_seconds:
                    logger.info("Max recording duration reached (%.1fs).", elapsed)
                    break

            if not has_speech:
                logger.info("No speech detected in recording.")
                return None

        except Exception as exc:
            logger.error("Recording error: %s", exc, exc_info=True)
            return None
        finally:
            if recorder:
                recorder.delete()

        # Convert to WAV bytes
        return self._to_wav_bytes(frames)

    def _to_wav_bytes(self, frames: list[list[int]]) -> bytes:
        """Convert a list of PCM int16 frames to WAV bytes."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self._sample_rate)
            for frame in frames:
                packed = struct.pack(f"{len(frame)}h", *frame)
                wf.writeframes(packed)
        buffer.seek(0)
        return buffer.read()


class WhisperSTT:
    """
    Optional local Whisper-based transcription for offline/low-latency scenarios.
    Requires `openai-whisper` package and a model download.
    """

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    def _load_model(self) -> None:
        """Lazy-load Whisper model to avoid startup delay."""
        if self._model is None:
            try:
                import whisper  # type: ignore
                logger.info("Loading Whisper model '%s'...", self._model_size)
                self._model = whisper.load_model(self._model_size)
                logger.info("Whisper model loaded.")
            except ImportError:
                logger.error("openai-whisper is not installed. Run: pip install openai-whisper")
                raise

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes using Whisper locally.

        Args:
            audio_bytes: WAV audio bytes.

        Returns:
            Transcribed text string.
        """
        try:
            import whisper
            import numpy as np
            import tempfile, os

            await asyncio.get_event_loop().run_in_executor(None, self._load_model)

            # Write to temp file (Whisper expects a file path or numpy array)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._model.transcribe(tmp_path, language="pt", fp16=False),
                )
                text = result.get("text", "").strip()
                logger.info("Whisper transcribed: '%s'", text)
                return text
            finally:
                os.unlink(tmp_path)

        except Exception as exc:
            logger.error("Whisper transcription failed: %s", exc, exc_info=True)
            return ""
