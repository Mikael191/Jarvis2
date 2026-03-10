"""
JARVIS - Windows OS Control Module - Vision
"""

import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.vision")

# VisionSystem instance injected by JarvisApp for the analyze_screen tool
_VISION_SYSTEM: Any = None


async def analyze_screen(prompt: str) -> dict[str, Any]:
    """
    Take a screenshot of the main monitor and ask Gemini 1.5 Flash Vision model a question about it.

    Args:
        prompt: The question to ask the vision model about the screenshot.
    """
    global _VISION_SYSTEM

    if not _VISION_SYSTEM or not _VISION_SYSTEM.enabled:
        return {
            "success": False,
            "error": "Vision system is disabled or GEMINI_API_KEY is not set in .env.",
        }

    try:
        logger.info("analyze_screen: delegating to VisionSystem...")
        vision_text = await _VISION_SYSTEM.analyze_screen(prompt)
        logger.info("analyze_screen: success.")
        return {"success": True, "output": vision_text, "error": ""}
    except Exception as exc:
        logger.error("analyze_screen error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
