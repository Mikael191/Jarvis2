"""
JARVIS - Windows OS Control Module - Volume
"""

import logging
from typing import Any

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.volume")


async def set_volume(level: int) -> dict[str, Any]:
    """
    Set master volume level (0–100).

    Args:
        level: Integer from 0 to 100.

    Returns:
        Result dict with success flag and message.
    """
    level = max(0, min(100, int(level)))
    # Simpler and more reliable approach using nircmd or the audio API
    script_simple = f"""
$ErrorActionPreference = "Stop"
try {{
    $wshell = New-Object -ComObject wscript.shell
    # Mute then unmute to reset volume position
    $SoundMixer = [System.Runtime.InteropServices.Marshal]::GetActiveObject("WMPlayer.OCX") 2>$null
}} catch {{}}

# Use the reliable Windows API via Add-Type
$code = @"
using System.Runtime.InteropServices;
public class VolumeControl {{
    [DllImport("winmm.dll")] public static extern int waveOutSetVolume(IntPtr h, uint v);
}}
"@
Add-Type -TypeDefinition $code
$vol = [uint32](({level} / 100.0) * 65535)
$volumeValue = ($vol -bor ($vol -shl 16))
[VolumeControl]::waveOutSetVolume([System.IntPtr]::Zero, $volumeValue) | Out-Null
Write-Output "[OK] Volume set to {level}%"
"""
    result = await run_powershell(script_simple)
    logger.info("set_volume(%d): %s", level, result)
    return {**result, "level": level}


async def get_volume() -> dict[str, Any]:
    """Return the current master volume level (0–100)."""
    script = """
$code = @"
using System.Runtime.InteropServices;
public class VolumeQuery {
    [DllImport("winmm.dll")] public static extern int waveOutGetVolume(IntPtr h, out uint v);
}
"@
Add-Type -TypeDefinition $code
$vol = 0
[VolumeQuery]::waveOutGetVolume([System.IntPtr]::Zero, [ref]$vol) | Out-Null
$left = ($vol -band 0xFFFF)
$level = [math]::Round(($left / 65535.0) * 100)
Write-Output $level
"""
    result = await run_powershell(script)
    level = None
    if result["success"]:
        try:
            level = int(result["output"].strip())
        except ValueError:
            pass
    return {**result, "level": level}
