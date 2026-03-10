"""
JARVIS - Windows OS Control Module - Brightness
"""

import logging
from typing import Any

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.brightness")


async def set_brightness(level: int) -> dict[str, Any]:
    """
    Set screen brightness (0–100).
    Works only for built-in displays (laptops, monitors with WMI support).

    Args:
        level: Integer 0–100.
    """
    level = max(0, min(100, int(level)))
    script = f"""
$ErrorActionPreference = "Continue"
try {{
    $monitors = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction Stop
    if ($monitors) {{
        $monitors | ForEach-Object {{ $_.WmiSetBrightness(1, {level}) }}
        Write-Output "[OK] Brightness set to {level}%"
    }} else {{
        Write-Output "[WARN] No WMI-compatible monitors found for brightness control"
    }}
}} catch {{
    Write-Output "[!] Error: $_"
}}
"""
    result = await run_powershell(script)
    logger.info("set_brightness(%d): %s", level, result)
    return {**result, "level": level}


async def get_brightness() -> dict[str, Any]:
    """Return current screen brightness (0–100)."""
    script = """
$ErrorActionPreference = "Continue"
try {
    $brightness = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness -ErrorAction Stop).CurrentBrightness
    Write-Output $brightness
} catch {
    Write-Output "N/A"
}
"""
    result = await run_powershell(script)
    level = None
    if result["success"]:
        try:
            val = result["output"].strip()
            if val != "N/A":
                level = int(val)
        except ValueError:
            pass
    return {**result, "level": level}
