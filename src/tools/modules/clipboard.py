"""
JARVIS - Windows OS Control Module - Clipboard
"""

import logging
from typing import Any

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.clipboard")


async def get_clipboard() -> dict[str, Any]:
    """Return the current clipboard text content."""
    script = "Get-Clipboard | Out-String"
    result = await run_powershell(script)
    return result


async def set_clipboard(text: str) -> dict[str, Any]:
    """Set the clipboard to the given text."""
    escaped = text.replace('"', '`"')
    script = f'Set-Clipboard -Value "{escaped}"; Write-Output "[OK] Clipboard updated"'
    result = await run_powershell(script)
    logger.info("set_clipboard: %s", result)
    return result
