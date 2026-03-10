"""
JARVIS - Windows OS Control Module - Media
"""

import logging
from typing import Any

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.media")


async def control_media(action: str) -> dict[str, Any]:
    """
    Control system media playback (Play/Pause, Next, Previous).

    Args:
        action: "play_pause", "next", or "previous".
    """
    keys = {"play_pause": 179, "next": 176, "previous": 177}

    act_key = keys.get(action.lower().strip())
    if not act_key:
        return {
            "success": False,
            "error": f"Invalid action '{action}'. Use play_pause, next, or previous.",
        }

    script = f"""
$wshell = New-Object -ComObject wscript.shell
$wshell.SendKeys([char]{act_key})
"""
    result = await run_powershell(script)
    if result["success"]:
        return {
            "success": True,
            "output": f"[OK] Media action '{action}' sent.",
            "error": "",
        }
    return result
