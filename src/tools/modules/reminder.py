"""
JARVIS - Windows OS Control Module - Reminder
"""

import asyncio
import logging
from typing import Any

from .utils import run_powershell

logger = logging.getLogger("jarvis.tools.windows_os.reminder")


import time
import json
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.reminder")

REMINDERS_FILE = Path("data") / "reminders.json"


def _load_reminders() -> list[dict]:
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_reminders(reminders: list[dict]) -> None:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(reminders, ensure_ascii=False), encoding="utf-8")


async def set_reminder(message: str, delay_minutes: int) -> dict[str, Any]:
    """
    Schedule a reminder to be spoken aloud after a certain number of minutes.

    Args:
        message: The text of the reminder.
        delay_minutes: Wait time in minutes before alarming.
    """
    trigger_time = time.time() + (delay_minutes * 60)
    
    reminders = _load_reminders()
    reminders.append({
        "message": message,
        "trigger_time": trigger_time,
        "id": int(time.time() * 1000)
    })
    _save_reminders(reminders)
    
    logger.info("Reminder scheduled: '%s' in %d minutes.", message, delay_minutes)
    
    return {
        "success": True,
        "output": f"[OK] Lembrete programado para daqui a {delay_minutes} minutos.",
        "error": "",
    }
