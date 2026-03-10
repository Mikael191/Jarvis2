"""
JARVIS - Groq AI Client
Handles all communication with Groq's LPU-accelerated API.
Uses the OpenAI-compatible interface with native function calling.
Supports models: llama-3.3-70b-versatile, llama-3.1-8b-instant
"""

import asyncio
import json
import logging
import platform
from datetime import datetime
from pathlib import Path
from typing import Any
import re

import psutil
from groq import Groq

from src.core.memory_manager import MemoryManager

logger = logging.getLogger("jarvis.groq_client")


def _get_runtime_context(memory: MemoryManager) -> dict[str, str]:
    """Build dynamic context strings to inject into the system prompt at runtime."""
    # Date/time with Brazil timezone awareness
    now = datetime.now()
    datetime_str = now.strftime("%A, %d de %B de %Y, %H:%M")

    # OS info
    os_info = (
        f"Windows {platform.version()}"
        if platform.system() == "Windows"
        else platform.system()
    )

    # System stats (lightweight — no interval delay)
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        stats = f"CPU {cpu:.0f}%, RAM {ram.percent:.0f}% ({ram.used//(1024**3)}GB/{ram.total//(1024**3)}GB)"
    except Exception:
        stats = "N/A"

    # Long-term memory context
    ltm = memory.get_long_term_context()

    return {
        "DATETIME": datetime_str,
        "OS_INFO": os_info,
        "SYSTEM_STATS": stats,
        "LONG_TERM_MEMORY": (
            ltm if ltm else "Nenhuma memória de longo prazo registrada ainda."
        ),
    }


class GroqClient:
    """
    Async wrapper around the Groq SDK.
    Uses OpenAI-style function calling (tools as list of dicts).
    Injects dynamic context (date/time, system stats) into every request.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        memory_manager: MemoryManager,
        tools: list[dict] | None = None,
    ) -> None:
        self._model = model
        self._memory = memory_manager
        self._tools = tools or []

        self._client = Groq(api_key=api_key)

        # Load system prompt template
        prompt_path = Path(__file__).parent / "system_prompt.txt"
        self._system_prompt_template = prompt_path.read_text(encoding="utf-8")
        logger.info("GroqClient initialized. Model: %s", model)

    def _build_system_prompt(self) -> str:
        """Build the system prompt with fresh runtime context injected."""
        ctx = _get_runtime_context(self._memory)
        prompt = self._system_prompt_template
        for key, value in ctx.items():
            prompt = prompt.replace(f"{{{key}}}", value)
        return prompt

    def _build_messages(self) -> list[dict]:
        """Build the messages list for the API: system prompt + conversation history."""
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        recent_turns = self._memory.get_recent_turns()

        for turn in recent_turns:
            role = turn["role"]
            if role == "model":
                role = "assistant"
            messages.append({"role": role, "content": turn["content"]})

        # If there's at least one user message, inject vector memory into the last one
        if messages and messages[-1]["role"] == "user":
            last_query = messages[-1]["content"]
            past_memories = self._memory.search_memory(last_query, n_results=3)

            if past_memories:
                # Filter out memories that are exactly the same as the current query to avoid duplicate echo
                valid_memories = [
                    m
                    for m in past_memories
                    if m["content"].strip() != last_query.strip()
                ]

                if valid_memories:
                    memory_context = "Contexto oculto recuperado da memória de longo prazo (Base de Dados Vetorial):\\n"
                    for m in valid_memories:
                        timestamp = m.get("timestamp", "")[:16].replace("T", " ")
                        memory_context += (
                            f"[{timestamp}] {m['role'].capitalize()}: {m['content']}\\n"
                        )

                    # Inject without saving to TinyDB history
                    messages[-1][
                        "content"
                    ] = f"{memory_context}\\n\\n[Fala de Agora]:\\n{last_query}"
                    logger.debug(
                        "Injected %d memories into prompt.", len(valid_memories)
                    )

        return messages

    async def send_message(
        self,
        user_input: str,
        tool_executor: Any | None = None,
    ) -> str:
        """
        Send a message to Groq and handle the full agentic tool-call loop.

        Args:
            user_input:    The raw text from the user.
            tool_executor: Object with async execute(name, args) method.

        Returns:
            The final assistant text response.
        """
        self._memory.add_turn(role="user", content=user_input)

        messages = self._build_messages()
        max_iterations = 10
        response_text = ""
        consecutive_tool_failures = 0

        for iteration in range(max_iterations):
            logger.debug("Groq call iteration %d", iteration + 1)

            try:
                kwargs: dict[str, Any] = dict(
                    model=self._model,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=1024,
                )
                if self._tools and tool_executor:
                    kwargs["tools"] = self._tools
                    kwargs["tool_choice"] = "auto"

                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    **kwargs,
                )

            except Exception as exc:
                err_str = str(exc)
                if (
                    "401" in err_str
                    or "invalid_api_key" in err_str
                    or "AuthenticationError" in type(exc).__name__
                ):
                    logger.critical(
                        "Groq API key inválida! Verifique GROQ_API_KEY no .env."
                    )
                    error_msg = "Mikael, a chave da API do Groq é inválida. Por favor, corrija no arquivo .env."
                    self._memory.add_turn(role="assistant", content=error_msg)
                    return error_msg

                if (
                    "tool_use_failed" in err_str
                    or "tool call validation failed" in err_str
                ):
                    consecutive_tool_failures += 1
                    if consecutive_tool_failures >= 3:
                        logger.error("Groq tool validation failed 3 times. Aborting.")
                        error_msg = "Desculpe, ocorreu um erro de formatação lógica interno contínuo."
                        self._memory.add_turn(role="assistant", content=error_msg)
                        return error_msg

                    logger.warning(
                        "Groq tool syntax error: %s — retrying with a hint.", exc
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "System Error: Chamada de ferramenta inválida. Por favor, use o nome exato e argumentos JSON válidos.",
                        }
                    )
                    continue

                # Reset counter if error is something else
                consecutive_tool_failures = 0

                is_retryable = any(
                    code in err_str
                    for code in ("503", "429", "UNAVAILABLE", "rate_limit")
                )
                if is_retryable:
                    logger.warning("Groq rate limit/error: %s — retrying in 5s", exc)
                    await asyncio.sleep(5)
                    continue

                logger.error("Groq API call failed: %s", exc, exc_info=True)
                error_msg = "Desculpe, ocorreu um erro ao me comunicar com o servidor de IA, Mikael."
                self._memory.add_turn(role="assistant", content=error_msg)
                return error_msg

            choice = response.choices[0]
            msg = choice.message

            # ── Check for tool calls ──────────────────────────────────────────
            if msg.tool_calls and tool_executor:
                # Append assistant's response with tool calls to messages
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )

                # Execute each tool call
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        args_str = tc.function.arguments
                        if not args_str:
                            fn_args = {}
                        else:
                            # Tenta arrumar se o groq mandou quebras de linha ou aspas ruins em json
                            import ast
                            try:
                                fn_args = json.loads(args_str)
                            except json.JSONDecodeError:
                                # Fallback perigoso mas as vezes salva LLM malformados
                                try:
                                    fn_args = ast.literal_eval(args_str)
                                except Exception:
                                    logger.warning("AST literal eval falhou para args: %s", args_str)
                                    fn_args = {}
                            
                        if not isinstance(fn_args, dict):
                            fn_args = {}
                    except Exception as exc:
                        logger.error("Falha fatal no parse dos args do tool %s: %s", fn_name, exc)
                        fn_args = {}

                    logger.info("Executing tool: %s(%s)", fn_name, fn_args)
                    try:
                        result = await tool_executor.execute(fn_name, fn_args)
                        result_str = json.dumps(result, ensure_ascii=False, default=str)
                    except Exception as exc:
                        logger.error(
                            "Tool '%s' failed: %s", fn_name, exc, exc_info=True
                        )
                        result_str = json.dumps({"error": str(exc)})

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        }
                    )

                # Loop back to let the model compose a final answer
                continue

            # ── Check for inline text tool calls (<function=name>{args}</function>) ──
            text_content = msg.content or ""
            inline_tool_match = re.search(r"<function=([^>]+)>(.*?)</function>", text_content, re.DOTALL)
            
            if inline_tool_match and tool_executor:
                fn_name = inline_tool_match.group(1).strip()
                args_str = inline_tool_match.group(2).strip()
                
                logger.info("Detected inline tool call in text: %s(%s)", fn_name, args_str)
                
                try:
                    import ast
                    if not args_str:
                        fn_args = {}
                    else:
                        try:
                            fn_args = json.loads(args_str)
                        except json.JSONDecodeError:
                            fn_args = ast.literal_eval(args_str)
                    if not isinstance(fn_args, dict):
                        fn_args = {}
                except Exception as exc:
                    logger.error("Failed to parse inline tool args: %s", exc)
                    fn_args = {}
                    
                try:
                    result = await tool_executor.execute(fn_name, fn_args)
                    result_str = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.error("Inline tool '%s' failed: %s", fn_name, exc, exc_info=True)
                    result_str = json.dumps({"error": str(exc)})
                    
                # Clean the text to be spoken (remove the tool tag)
                clean_text = re.sub(r"<function=[^>]+>.*?</function>", "", text_content, flags=re.DOTALL).strip()
                
                # If there's content before/after the tool, we save it
                if clean_text:
                    response_text = clean_text
                    
                # Append a fake tool flow to messages for context
                messages.append({
                    "role": "assistant",
                    "content": text_content
                })
                
                messages.append({
                    "role": "user",  # Groq text only mode doesn't support 'tool' role easily without passing back IDs
                    "content": f"System Notice - A função '{fn_name}' foi executada e retornou: {result_str}. Confirme brevemente o que aconteceu se necessário, ou ignore se já avisou."
                })
                
                if clean_text:
                    # Se ele falou algo antes de chamar, já consideramos q respondeu e retornamos
                    logger.debug("Returning early after inline tool because text was spoken.")
                    break
                else:
                    # Se não falou nada, deixa dar loop pra gerar resposta conversacional
                    continue

            # ── Final text response ───────────────────────────────────────────
            response_text = text_content
            logger.debug("Final Groq response (%d chars).", len(response_text))
            break

        if response_text:
            self._memory.add_turn(role="assistant", content=response_text)

        return response_text

    async def summarize_text(self, system_instruction: str, user_text: str) -> str:
        """
        Pure generation method without touching conversation history. 
        Useful for background jobs like circular summarization.
        """
        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.2,
                max_tokens=300,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("groq_client summarize_text failed: %s", exc)
            return ""

    async def send_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        tool_executor: Any | None = None,
    ) -> str:
        """
        Transcribe audio using Groq's Whisper endpoint, then send as text message.

        Args:
            audio_bytes: Raw WAV audio bytes.
            mime_type:   Audio MIME type (informational; Groq Whisper accepts wav).
            tool_executor: Tool executor for function calling.

        Returns:
            The final JARVIS response text.
        """
        import io

        logger.info("Transcribing audio via Groq Whisper...")
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = "audio.wav"  # Groq requires a name attribute

        try:
            transcription = await asyncio.to_thread(
                self._client.audio.transcriptions.create,
                file=audio_buffer,
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text",
            )
            transcribed_text = str(transcription).strip()
            logger.info("Whisper transcribed: '%s'", transcribed_text[:80])
        except Exception as exc:
            logger.error("Groq Whisper transcription failed: %s", exc, exc_info=True)
            return "Não consegui transcrever o áudio. Pode repetir, Mikael?"

        if not transcribed_text:
            return ""

        # Pass the transcription through the normal message pipeline
        return await self.send_message(transcribed_text, tool_executor)
