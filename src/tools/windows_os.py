"""
JARVIS - Windows OS Control Module
Provides async Python wrappers around PowerShell commands for deep OS integration.
All functions run PowerShell via subprocess — never block the event loop.
"""

import logging
from typing import Any

from .modules import (
    volume,
    brightness,
    process,
    input,
    system,
    clipboard,
    media,
    vision,
    web,
    reminder,
)
from .modules.utils import run_powershell

# VisionSystem instance injected by JarvisApp for the analyze_screen tool
_VISION_SYSTEM: Any = None

logger = logging.getLogger("jarvis.tools.windows_os")


# Re-export functions from modules
set_volume = volume.set_volume
get_volume = volume.get_volume
set_brightness = brightness.set_brightness
get_brightness = brightness.get_brightness
open_application = process.open_application
kill_application = process.kill_application
list_running_processes = process.list_running_processes
click_mouse = input.click_mouse
type_text = input.type_text
press_key = input.press_key
get_system_stats = system.get_system_stats
lock_screen = system.lock_screen
sleep_system = system.sleep_system
shutdown_system = system.shutdown_system
restart_system = system.restart_system
get_clipboard = clipboard.get_clipboard
set_clipboard = clipboard.set_clipboard
control_media = media.control_media
analyze_screen = vision.analyze_screen
search_web = web.search_web
read_website = web.read_website
execute_powershell = run_powershell
set_reminder = reminder.set_reminder




