"""
JARVIS - Gemini API Client
Handles all communication with the Gemini AI, including function calling
and multi-turn conversation management.
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from src.core.memory_manager import MemoryManager

logger = logging.getLogger("jarvis.gemini_client")


class GeminiClient:
    """
    Async wrapper around the Google GenAI SDK.
    Manages system prompt, function tools, and conversation chaining.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        memory_manager: MemoryManager,
        tools: list[types.Tool] | None = None,
    ) -> None:
        self._model = model
        self._memory = memory_manager
        self._tools = tools or []

        self._client = genai.Client(api_key=api_key)

        # Load system prompt
        prompt_path = Path(__file__).parent / "system_prompt.txt"
        self._system_instruction = prompt_path.read_text(encoding="utf-8")
        logger.info("GeminiClient initialized. Model: %s", model)

    async def send_message(
        self,
        user_input: str,
        tool_executor: Any | None = None,
    ) -> str:
        """
        Send a message to Gemini and handle the full agentic loop:
        1. Send user message + conversation history
        2. If model returns tool calls, execute them and loop back
        3. Return the final text response

        Args:
            user_input:    The raw text from the user.
            tool_executor: An object with an async `execute(name, args)` method.

        Returns:
            The final assistant text response.
        """
        # Add user turn to memory
        self._memory.add_turn(role="user", content=user_input)

        # Build the contents list from memory
        contents = self._memory.get_history_as_contents()

        config = types.GenerateContentConfig(
            system_instruction=self._system_instruction,
            tools=self._tools if self._tools else None,
            tool_config=(
                types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="AUTO")
                )
                if self._tools
                else None
            ),
        )

        response_text = ""
        max_iterations = 10  # Safety cap for agentic loop
        # Models to try in order: preferred → stable fallback
        models_to_try = [self._model, "gemini-2.0-flash", "gemini-1.5-flash"]

        for iteration in range(max_iterations):
            logger.debug("Gemini call iteration %d", iteration + 1)

            response = None
            last_error = None

            # ── Retry with model fallback on 503/429 ──────────────────────
            for attempt, model in enumerate(models_to_try):
                retry_delays = [5, 15, 35]  # respect server's ~30s retry-after for 429
                for retry in range(len(retry_delays) + 1):
                    try:
                        response = await asyncio.to_thread(
                            self._client.models.generate_content,
                            model=model,
                            contents=contents,
                            config=config,
                        )
                        if model != self._model:
                            logger.warning("Using fallback model: %s", model)
                        last_error = None
                        break  # success
                    except Exception as exc:
                        last_error = exc
                        err_str = str(exc)
                        is_retryable = (
                            "503" in err_str
                            or "429" in err_str
                            or "UNAVAILABLE" in err_str
                            or "RESOURCE_EXHAUSTED" in err_str
                        )
                        if is_retryable and retry < len(retry_delays):
                            wait = retry_delays[retry]
                            logger.warning(
                                "Retryable error (attempt %d/%d, model=%s): %s — waiting %ds",
                                retry + 1,
                                len(retry_delays) + 1,
                                model,
                                exc,
                                wait,
                            )
                            await asyncio.sleep(wait)
                        else:
                            break  # non-retryable or exhausted retries for this model

                if response is not None:
                    break  # got a response, stop trying models

            if response is None:
                logger.error("All models failed: %s", last_error, exc_info=True)
                error_msg = "Desculpe, o servidor de IA está congestionado agora. Tente novamente em instantes, Mikael."
                self._memory.add_turn(role="model", content=error_msg)
                return error_msg

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                logger.warning("Gemini returned no candidates.")
                break

            # Check for function calls
            function_calls = [
                part.function_call
                for part in (candidate.content.parts or [])
                if hasattr(part, "function_call") and part.function_call
            ]

            if not function_calls:
                # Final text response
                response_text = response.text or ""
                logger.debug(
                    "Final text response received (%d chars).", len(response_text)
                )
                break

            # ── Agentic loop: execute tool calls ──────────────────────────
            if not tool_executor:
                logger.warning("Model requested tool calls but no executor provided.")
                break

            # Append model's turn (with function calls) to contents
            contents.append(candidate.content)

            # Build function response parts
            function_response_parts: list[types.Part] = []
            for fc in function_calls:
                logger.info("Executing tool: %s(%s)", fc.name, fc.args)
                try:
                    result = await tool_executor.execute(fc.name, dict(fc.args))
                    result_json = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.error(
                        "Tool '%s' execution failed: %s", fc.name, exc, exc_info=True
                    )
                    result_json = json.dumps({"error": str(exc)})

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result_json},
                    )
                )

            # Append tool results as a "user" turn (tool role)
            contents.append(types.Content(role="user", parts=function_response_parts))

        # Save final model response to memory
        if response_text:
            self._memory.add_turn(role="model", content=response_text)

        return response_text

    async def send_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        tool_executor: Any | None = None,
    ) -> str:
        """
        Send raw audio bytes to Gemini for multimodal transcription + response.
        Useful for STT directly via the Gemini model.
        """
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        prompt_part = types.Part(
            text="Transcreva o áudio e responda ao pedido do usuário."
        )

        user_content = types.Content(role="user", parts=[prompt_part, audio_part])

        config = types.GenerateContentConfig(
            system_instruction=self._system_instruction,
            tools=self._tools if self._tools else None,
        )

        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=[user_content],
                config=config,
            )
            return response.text or ""
        except Exception as exc:
            logger.error("Gemini audio call failed: %s", exc, exc_info=True)
            return "Não consegui processar o áudio. Por favor, tente novamente."
