"""
JARVIS - Windows OS Control Module - Input Control
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.input")


async def click_mouse(
    x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1
) -> dict[str, Any]:
    """
    Click the mouse at specific coordinates or current position.

    Args:
        x: X coordinate (optional, defaults to current).
        y: Y coordinate (optional, defaults to current).
        button: "left", "right", or "middle".
        clicks: Number of clicks.
    """
    try:
        import pyautogui

        button = button.lower()
        if button not in ["left", "right", "middle"]:
            button = "left"

        def _do_click():
            if x is not None and y is not None:
                pyautogui.click(x=int(x), y=int(y), button=button, clicks=int(clicks))
            else:
                pyautogui.click(button=button, clicks=int(clicks))

        await asyncio.to_thread(_do_click)
        pos = f"({x}, {y})" if x is not None else "current position"
        return {
            "success": True,
            "output": f"Clicked {button} button {clicks} time(s) at {pos}.",
            "error": "",
        }
    except Exception as exc:
        logger.error("click_mouse error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def type_text(text: str, press_enter: bool = False) -> dict[str, Any]:
    """
    Type text on the keyboard sequentially, as if a human was typing.

    Args:
        text: The string to type.
        press_enter: Whether to press Enter after typing.
    """
    try:
        import pyautogui

        def _do_type():
            pyautogui.write(text, interval=0.01)
            if press_enter:
                pyautogui.press("enter")

        await asyncio.to_thread(_do_type)
        return {
            "success": True,
            "output": f"Typed text successfully. Enter pressed: {press_enter}",
            "error": "",
        }
    except Exception as exc:
        logger.error("type_text error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def press_key(key_sequence: str) -> dict[str, Any]:
    """
    Press a single key or a combination of keys (e.g. 'win', 'ctrl+c', 'enter', 'tab', 'down').

    Args:
        key_sequence: '+' separated keys, e.g. "ctrl+shift+esc", "win+d" or just "enter"
    """
    try:
        import pyautogui

        keys = [k.strip().lower() for k in key_sequence.split("+")]

        def _do_hotkey():
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)

        await asyncio.to_thread(_do_hotkey)
        return {
            "success": True,
            "output": f"Pressed hotkey: {key_sequence}",
            "error": "",
        }
    except Exception as exc:
        logger.error("press_key error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
