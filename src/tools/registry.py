"""
JARVIS - Tool Registry
Maps Python OS-control functions to Groq/OpenAI function calling schemas.
"""

import asyncio
import logging
from typing import Any

from src.tools import windows_os
from src.tools import smart_home
from src.tools import spotify_control

logger = logging.getLogger("jarvis.tools.registry")


# ─────────────────────────────────────────────────────────────
# Groq / OpenAI-compatible Tool Schema
# ─────────────────────────────────────────────────────────────

def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    """Helper to build an OpenAI-style function tool dict."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


GROQ_TOOLS: list[dict] = [
    _fn("set_volume", "Adjust the master volume of the Windows system (0-100).",
        {"level": {"type": "integer", "description": "Volume level 0-100"}}, ["level"]),

    _fn("get_volume", "Get the current master volume level.",
        {}),

    _fn("set_brightness", "Adjust screen brightness (0-100). Only compatible displays.",
        {"level": {"type": "integer", "description": "Brightness 0-100"}}, ["level"]),

    _fn("get_brightness", "Get the current screen brightness level.",
        {}),

    _fn("open_application",
        "Launch an app by friendly name: 'chrome','vscode','spotify','discord','steam','notepad','calculator','terminal', or full path.",
        {"app_name": {"type": "string", "description": "App name or executable path"}}, ["app_name"]),

    _fn("kill_application", "Kill all running instances of an app by process name.",
        {"process_name": {"type": "string", "description": "Process name, e.g. 'chrome'"}}, ["process_name"]),

    _fn("list_running_processes", "List top processes sorted by CPU usage.",
        {"top_n": {"type": "integer", "description": "How many to return (default 15)"}}),

    _fn("get_system_stats", "Get real-time CPU%, RAM usage, and disk usage.",
        {}),

    _fn("lock_screen", "Lock the Windows workstation immediately.",
        {}),

    _fn("click_mouse", "Click the mouse at specific coordinates or current position.",
        {"x": {"type": "integer", "description": "X coordinate (optional)."},
         "y": {"type": "integer", "description": "Y coordinate (optional)."},
         "button": {"type": "string", "description": "'left', 'right', or 'middle'"},
         "clicks": {"type": "integer", "description": "Number of clicks"}}),

    _fn("type_text", "Type text on the keyboard securely.",
        {"text": {"type": "string", "description": "The string to type."},
         "press_enter": {"type": "boolean", "description": "Whether to press Enter after typing."}}, ["text"]),

    _fn("press_key", "Press a single key or a combination of keys (e.g. 'win', 'ctrl+c', 'enter', 'down').",
        {"key_sequence": {"type": "string", "description": "The key or keys to press."}}, ["key_sequence"]),

    _fn("get_clipboard", "Read text from the Windows clipboard.",
        {}),

    _fn("set_clipboard", "Write text to the Windows clipboard.",
        {"text": {"type": "string", "description": "Text to write"}}, ["text"]),

    _fn("sleep_system", "Put the computer into sleep mode.",
        {}),

    _fn("shutdown_system", "Schedule a system shutdown. Use delay_seconds=30 by default.",
        {"delay_seconds": {"type": "integer", "description": "Seconds before shutdown, default 30"}}),

    _fn("restart_system", "Schedule a system restart.",
        {"delay_seconds": {"type": "integer", "description": "Seconds before restart, default 30"}}),

    _fn("analyze_screen", "Take a screenshot of the computer screen and ask a visual question about it.",
        {"prompt": {"type": "string", "description": "Question to ask the AI vision model about the screen."}}, ["prompt"]),

    _fn("search_web", "Search the internet for real-time information, news, or documents. Returns URLs that you can read using read_website.",
        {"query": {"type": "string", "description": "The internet search query."}}, ["query"]),

    _fn("read_website", "Read the text content of a specific webpage URL. Use this to read articles returned from search_web.",
        {"url": {"type": "string", "description": "The full URL of the website to read."}}, ["url"]),

    _fn("execute_powershell", "Execute an arbitrary PowerShell script to manipulate the OS or automate complex tasks. ALWAYS use this if the user asks you to do something that your pre-mapped tools cannot solve.",
        {"script": {"type": "string", "description": "The raw PowerShell code to run."}}, ["script"]),

    _fn("set_reminder", "Schedule an audio reminder or alarm that will fire after a given number of minutes.",
        {"message": {"type": "string", "description": "The message to speak when the reminder triggers."},
         "delay_minutes": {"type": "integer", "description": "Wait time in minutes before triggering (e.g., 5)."}}, ["message", "delay_minutes"]),

    _fn("control_media", "Control system media playback (e.g., Spotify, Chrome).",
        {"action": {"type": "string", "description": "Action to perform: 'play_pause', 'next', or 'previous'."}}, ["action"]),

    _fn("get_weather", "Get the current weather and forecast for a city.",
        {"city": {"type": "string", "description": "City name, e.g. 'São Paulo' or 'Curitiba'"}}, ["city"]),

    _fn("control_smart_home", "Control a smart home device or IoT service via local Webhook/Home Assistant.",
        {"device_name": {"type": "string", "description": "Name of the device, e.g., 'luz_quarto'."},
         "action": {"type": "string", "description": "Action to execute, e.g., 'turn_on', 'turn_off'."},
         "parameters": {"type": "object", "description": "Optional parameters like temperature or brightness."}}, ["device_name", "action"]),

    _fn("play_spotify", "Search and play music, albums, or playlists on Spotify.",
        {"query": {"type": "string", "description": "Song name, artist, or album."},
         "type": {"type": "string", "description": "'track', 'album', or 'playlist' (default 'track')"}}, ["query"]),
]


# ─────────────────────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────────────────────

class ToolExecutor:
    """
    Dispatches function calls to their Python implementations.
    """

    # Map: function name → python coroutine
    _DISPATCH: dict[str, Any] = {
        "set_volume": windows_os.set_volume,
        "get_volume": windows_os.get_volume,
        "set_brightness": windows_os.set_brightness,
        "get_brightness": windows_os.get_brightness,
        "open_application": windows_os.open_application,
        "kill_application": windows_os.kill_application,
        "list_running_processes": windows_os.list_running_processes,
        "get_system_stats": windows_os.get_system_stats,
        "lock_screen": windows_os.lock_screen,
        "click_mouse": windows_os.click_mouse,
        "type_text": windows_os.type_text,
        "press_key": windows_os.press_key,
        "get_clipboard": windows_os.get_clipboard,
        "set_clipboard": windows_os.set_clipboard,
        "sleep_system": windows_os.sleep_system,
        "shutdown_system": windows_os.shutdown_system,
        "restart_system": windows_os.restart_system,
        "analyze_screen": windows_os.analyze_screen,
        "search_web": windows_os.search_web,
        "read_website": windows_os.read_website,
        "execute_powershell": windows_os.execute_powershell,
        "set_reminder": windows_os.set_reminder,
        "control_media": windows_os.control_media,
        "get_weather": windows_os.get_weather,
        "control_smart_home": smart_home.control_smart_home,
        "play_spotify": spotify_control.play_spotify,
    }

    # Tools that require explicit user confirmation before running
    _DANGEROUS_TOOLS: frozenset[str] = frozenset({
        "shutdown_system",
        "restart_system",
        "sleep_system",
        "execute_powershell",
    })

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a registered tool by name.

        Args:
            name: Function name as declared in GROQ_TOOLS.
            args: Arguments dict from the model's function call.

        Returns:
            A dict result (always JSON-serializable).
        """
        fn = self._DISPATCH.get(name)
        if not fn:
            logger.warning("Tool '%s' not found in registry.", name)
            return {"success": False, "error": f"Tool '{name}' is not registered."}

        logger.info("Executing tool '%s' with args: %s", name, args)
        try:
            result = await fn(**args)
            return result
        except TypeError as exc:
            logger.error("Tool '%s' bad arguments %s: %s", name, args, exc, exc_info=True)
            return {"success": False, "error": f"Invalid arguments for '{name}': {exc}"}
        except Exception as exc:
            logger.error("Tool '%s' execution exception: %s", name, exc, exc_info=True)
            return {"success": False, "error": str(exc)}
