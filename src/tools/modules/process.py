"""
JARVIS - Windows OS Control Module - Process Management
"""

import asyncio
import json
import logging
from typing import Any

import psutil

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.process")


async def open_application(app_name: str) -> dict[str, Any]:
    """
    Launch an application by name or path.

    Args:
        app_name: e.g. "chrome", "notepad", "code" (VS Code), or a full path.
    """
    # Map common friendly names to executables
    app_map: dict[str, str] = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "notepad": "notepad",
        "bloco de notas": "notepad",
        "explorer": "explorer",
        "arquivos": "explorer",
        "calculator": "calc",
        "calculadora": "calc",
        "terminal": "wt",
        "powershell": "powershell",
        "paint": "mspaint",
        "spotify": "spotify",
        "discord": "discord",
        "steam": "steam",
    }

    exe = app_map.get(app_name.lower().strip(), app_name)
    script = f'Start-Process "{exe}" -ErrorAction Continue; Write-Output "[OK] Started: {exe}"'
    result = await run_powershell(script)
    logger.info("open_application('%s' -> '%s'): %s", app_name, exe, result)
    return result


async def kill_application(process_name: str) -> dict[str, Any]:
    """
    Kill all processes matching a name.

    Args:
        process_name: e.g. "chrome", "notepad", "code"

    Returns:
        Result dict.
    """
    # Strip .exe suffix if user includes it
    name_clean = process_name.lower().replace(".exe", "").strip()
    script = f"""
$ErrorActionPreference = "Continue"
$procs = Get-Process -Name "{name_clean}" -ErrorAction SilentlyContinue
if ($procs -and $procs.Count -gt 0) {{
    $procs | Stop-Process -Force -ErrorAction Continue
    Write-Output "[OK] Killed $($procs.Count) instance(s) of '{name_clean}'"
}} else {{
    Write-Output "[WARN] No running process found with name '{name_clean}'"
}}
"""
    result = await run_powershell(script)
    logger.info("kill_application('%s'): %s", process_name, result)
    return result


async def list_running_processes(top_n: int = 15) -> dict[str, Any]:
    """
    List top processes by CPU usage.

    Args:
        top_n: How many processes to return (default 15).

    Returns:
        Result dict with "processes" list.
    """
    processes = []
    try:
        for proc in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent", 0) or 0,
            reverse=True,
        )[:top_n]:
            info = proc.info
            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "cpu": round(info.get("cpu_percent") or 0, 1),
                    "mem": round(info.get("memory_percent") or 0, 1),
                }
            )
        return {
            "success": True,
            "output": json.dumps(processes),
            "error": "",
            "processes": processes,
        }
    except Exception as exc:
        logger.error("list_running_processes error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc), "processes": []}
