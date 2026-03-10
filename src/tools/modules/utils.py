"""
JARVIS - Windows OS Control Module - Utilities
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.utils")


async def run_powershell(script: str) -> dict[str, Any]:
    """
    Run a PowerShell script asynchronously and return structured result.

    Returns:
        {"success": bool, "output": str, "error": str}
    """
    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.warning("PowerShell non-zero exit (%d): %s", proc.returncode, error)
            return {"success": False, "output": output, "error": error}

        return {"success": True, "output": output, "error": ""}
    except Exception as exc:
        logger.error("PowerShell execution error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
