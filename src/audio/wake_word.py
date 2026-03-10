"""
JARVIS - Wake Word Detection
Uses Picovoice Porcupine for ultra-low-latency, CPU-efficient wake word detection.
Runs in a background thread and signals the main event loop via asyncio.Event.
"""

import asyncio
import logging
import threading
from typing import Callable, Coroutine, Any

import pvporcupine
import pvrecorder

logger = logging.getLogger("jarvis.audio.wake_word")


class WakeWordDetector:
    """
    Listens continuously for the configured wake word using Porcupine.
    When detected, fires an asyncio callback in the main event loop.

    Usage:
        detector = WakeWordDetector(
            access_key="...",
            keywords=["jarvis"],           # built-in keyword
            loop=asyncio.get_event_loop(),
            on_detected=handle_wake_word,
        )
        detector.start()
        # ... later:
        detector.stop()
    """

    def __init__(
        self,
        access_key: str,
        loop: asyncio.AbstractEventLoop,
        on_detected: Callable[[], Coroutine[Any, Any, None]],
        keywords: list[str] | None = None,
        keyword_paths: list[str] | None = None,
        sensitivities: list[float] | None = None,
    ) -> None:
        self._access_key = access_key
        self._loop = loop
        self._on_detected = on_detected
        self._keywords = keywords or ["jarvis"]
        self._keyword_paths = keyword_paths
        self._sensitivities = sensitivities

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the wake word detection in a background daemon thread."""
        if self._running:
            logger.warning("WakeWordDetector already running.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="wake-word-thread",
        )
        self._thread.start()
        logger.info("WakeWordDetector started. Listening for: %s", self._keywords)

    def stop(self) -> None:
        """Signal the detection loop to stop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("WakeWordDetector stopped.")

    def _detection_loop(self) -> None:
        """Main detection loop — runs in a background thread."""
        porcupine = None
        recorder = None

        try:
            # Build Porcupine with either built-in keywords or custom .ppn paths
            if self._keyword_paths:
                porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keyword_paths=self._keyword_paths,
                    sensitivities=self._sensitivities
                    or [0.7] * len(self._keyword_paths),
                )
            else:
                porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keywords=self._keywords,
                    sensitivities=self._sensitivities or [0.7] * len(self._keywords),
                )

            devices = pvrecorder.PvRecorder.get_available_devices()
            indices_to_try = [-1] + list(range(len(devices)))

            for idx in indices_to_try:
                try:
                    recorder = pvrecorder.PvRecorder(
                        frame_length=porcupine.frame_length,
                        device_index=idx,
                    )
                    logger.info("Initialized PvRecorder with device_index=%d", idx)
                    break
                except RuntimeError:
                    pass
            else:
                logger.critical(
                    "All microphone attempts failed. Available mics: %s", devices
                )
                raise RuntimeError("Failed to initialize PvRecorder on any device.")
            recorder.start()
            logger.info(
                "Wake word engine ready. Frame length: %d, Sample rate: %d Hz",
                porcupine.frame_length,
                porcupine.sample_rate,
            )

            while self._running:
                pcm = recorder.read()
                result = porcupine.process(pcm)
                if result >= 0:
                    keyword_detected = (
                        self._keywords[result]
                        if result < len(self._keywords)
                        else "custom"
                    )
                    logger.info(
                        "Wake word detected: '%s' (index=%d)", keyword_detected, result
                    )
                    # Fire the async callback from the main event loop thread-safely
                    asyncio.run_coroutine_threadsafe(self._on_detected(), self._loop)

        except pvporcupine.PorcupineActivationError as exc:
            logger.critical("Porcupine activation error (invalid key?): %s", exc)
        except pvporcupine.PorcupineError as exc:
            logger.error("Porcupine error: %s", exc, exc_info=True)
        except Exception as exc:
            logger.error("Wake word detection loop crashed: %s", exc, exc_info=True)
        finally:
            if recorder:
                recorder.delete()
            if porcupine:
                porcupine.delete()
            logger.info("Wake word resources released.")
