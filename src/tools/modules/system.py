"""
JARVIS - Windows OS Control Module - System
"""

import json
import logging
from typing import Any

import psutil

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.system")


async def get_system_stats() -> dict[str, Any]:
    """
    Return real-time CPU, RAM, and disk stats using psutil.

    Returns:
        Dict with cpu_percent, ram_percent, ram_gb_used, ram_gb_total, disk_percent.
    """
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:")

        stats = {
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(ram.percent, 1),
            "ram_gb_used": round(ram.used / (1024**3), 2),
            "ram_gb_total": round(ram.total / (1024**3), 2),
            "disk_percent": round(disk.percent, 1),
            "disk_gb_free": round(disk.free / (1024**3), 2),
        }
        logger.debug("System stats: %s", stats)
        return {"success": True, "output": json.dumps(stats), "error": "", **stats}
    except Exception as exc:
        logger.error("get_system_stats error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def lock_screen() -> dict[str, Any]:
    """Lock the Windows workstation immediately."""
    script = (
        "rundll32.exe user32.dll,LockWorkStation; Write-Output '[OK] Screen locked'"
    )
    result = await run_powershell(script)
    logger.info("lock_screen: %s", result)
    return result


async def sleep_system() -> dict[str, Any]:
    """Put the system to sleep."""
    script = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0; Write-Output '[OK] System sleeping'"
    return await run_powershell(script)


async def shutdown_system(delay_seconds: int = 30) -> dict[str, Any]:
    """
    Schedule a system shutdown.

    Args:
        delay_seconds: Seconds before shutdown (default 30). Pass 0 for immediate.
    """
    script = f"shutdown /s /t {delay_seconds}; Write-Output '[OK] Shutdown scheduled in {delay_seconds}s'"
    result = await run_powershell(script)
    logger.warning("shutdown_system(%ds): %s", delay_seconds, result)
    return result


async def restart_system(delay_seconds: int = 30) -> dict[str, Any]:
    """
    Schedule a system restart.

    Args:
        delay_seconds: Seconds before restart (default 30).
    """
    script = f"shutdown /r /t {delay_seconds}; Write-Output '[OK] Restart scheduled in {delay_seconds}s'"
    result = await run_powershell(script)
    logger.warning("restart_system(%ds): %s", delay_seconds, result)
    return result
