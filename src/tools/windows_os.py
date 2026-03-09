"""
JARVIS - Windows OS Control Module
Provides async Python wrappers around PowerShell commands for deep OS integration.
All functions run PowerShell via subprocess — never block the event loop.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any

import psutil

# Injected by JarvisApp at startup (loaded from .env)
_OPENWEATHERMAP_API_KEY: str = ""
# VisionSystem instance injected by JarvisApp for the analyze_screen tool
_VISION_SYSTEM: Any = None

logger = logging.getLogger("jarvis.tools.windows_os")

# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

async def _run_powershell(script: str) -> dict[str, Any]:
    """
    Run a PowerShell script asynchronously and return structured result.

    Returns:
        {"success": bool, "output": str, "error": str}
    """
    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", script,
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


# ─────────────────────────────────────────────
# Volume Control
# ─────────────────────────────────────────────

async def set_volume(level: int) -> dict[str, Any]:
    """
    Set master volume level (0–100).

    Args:
        level: Integer from 0 to 100.

    Returns:
        Result dict with success flag and message.
    """
    level = max(0, min(100, int(level)))
    script = f"""
$volume = {level} / 100.0
$obj = New-Object -ComObject WScript.Shell
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
    int _reserved1();
    int _reserved2();
    int SetMasterVolumeLevelScalar(float fLevel, ref System.Guid pguidEventContext);
    int GetMasterVolumeLevelScalar(out float pfLevel);
}}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumeratorCOM {{}}
'@

$MMDevice = [System.Runtime.InteropServices.Marshal]::GetActiveObject("MMDeviceEnumerator") 2>$null
if (-not $MMDevice) {{
    $nircmd = Join-Path $env:SystemRoot "system32\\nircmd.exe"
    $wsh = New-Object -ComObject WScript.Shell
    # Fallback: use nircmd if available, otherwise SoundMixer via COM
}}

# Primary method: PowerShell Audio API via COM
$code = @"
using System.Runtime.InteropServices;
public class Audio {{
    [DllImport("user32.dll")] static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    public static void SetVolume(float vol) {{
        var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        var device = enumerator.GetDefaultAudioEndpoint(0, 1);
        var vol_ep = (IAudioEndpointVolume)device.Activate(typeof(IAudioEndpointVolume).GUID, 0, 0);
        var guid = System.Guid.Empty;
        vol_ep.SetMasterVolumeLevelScalar(vol, ref guid);
    }}
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    [CoClass(typeof(MMDeviceEnumerator))]
    interface IMMDeviceEnumerator {{ IMMDevice GetDefaultAudioEndpoint(int dataFlow, int role); }}
    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    interface IMMDevice {{ object Activate(System.Guid iid, int dwClsCtx, System.IntPtr pActivationParams); }}
    [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A")]
    interface IAudioEndpointVolume {{
        int _r1(); int _r2();
        void SetMasterVolumeLevelScalar(float fLevel, ref System.Guid pguidEventContext);
    }}
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    class MMDeviceEnumerator {{}}
}}
"@

try {{
    Add-Type -TypeDefinition $code -ErrorAction Stop
    [Audio]::SetVolume({level / 100.0:.2f})
    Write-Output "[OK] Volume set to {level}%"
}} catch {{
    # Simple fallback using Windows Shell
    $wsh = New-Object -ComObject WScript.Shell
    for ($i = 0; $i -lt 50; $i++) {{ $wsh.SendKeys([char]174) }}
    $steps = [math]::Round({level} / 2)
    for ($i = 0; $i -lt $steps; $i++) {{ $wsh.SendKeys([char]175) }}
    Write-Output "[OK] Volume approximately set to {level}% via fallback"
}}
"""
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
    result = await _run_powershell(script_simple)
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
    result = await _run_powershell(script)
    level = None
    if result["success"]:
        try:
            level = int(result["output"].strip())
        except ValueError:
            pass
    return {**result, "level": level}


# ─────────────────────────────────────────────
# Brightness Control
# ─────────────────────────────────────────────

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
    result = await _run_powershell(script)
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
    result = await _run_powershell(script)
    level = None
    if result["success"]:
        try:
            val = result["output"].strip()
            if val != "N/A":
                level = int(val)
        except ValueError:
            pass
    return {**result, "level": level}


# ─────────────────────────────────────────────
# Process Management
# ─────────────────────────────────────────────

async def open_application(app_name: str) -> dict[str, Any]:
    """
    Launch an application by name or path.

    Args:
        app_name: e.g. "chrome", "notepad", "code" (VS Code), or a full path.
    """
    # Map common friendly names to executables
    app_map: dict[str, str] = {
        "chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "vscode": "code",
        "vs code": "code",
        "notepad": "notepad",
        "explorer": "explorer",
        "calculator": "calc",
        "terminal": "wt",
        "powershell": "powershell",
        "paint": "mspaint",
        "spotify": "spotify",
        "discord": "discord",
        "steam": "steam",
    }

    exe = app_map.get(app_name.lower().strip(), app_name)
    script = f'Start-Process "{exe}" -ErrorAction Continue; Write-Output "[OK] Started: {exe}"'
    result = await _run_powershell(script)
    logger.info("open_application('%s' -> '%s'): %s", app_name, exe, result)
    return result


async def click_mouse(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict[str, Any]:
    """
    Click the mouse at specific coordinates or current position.

    Args:
        x: X coordinate (optional, defaults to current).
        y: Y coordinate (optional, defaults to current).
        button: "left", "right", or "middle".
        clicks: Number of clicks.
    """
    try:
        import pyautogui
        
        button = button.lower()
        if button not in ["left", "right", "middle"]:
            button = "left"
            
        def _do_click():
            if x is not None and y is not None:
                pyautogui.click(x=int(x), y=int(y), button=button, clicks=int(clicks))
            else:
                pyautogui.click(button=button, clicks=int(clicks))

        await asyncio.to_thread(_do_click)
        pos = f"({x}, {y})" if x is not None else "current position"
        return {"success": True, "output": f"Clicked {button} button {clicks} time(s) at {pos}.", "error": ""}
    except Exception as exc:
        logger.error("click_mouse error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def type_text(text: str, press_enter: bool = False) -> dict[str, Any]:
    """
    Type text on the keyboard sequentially, as if a human was typing.
    
    Args:
        text: The string to type.
        press_enter: Whether to press Enter after typing.
    """
    try:
        import pyautogui
        
        def _do_type():
            pyautogui.write(text, interval=0.01)
            if press_enter:
                pyautogui.press('enter')

        await asyncio.to_thread(_do_type)
        return {"success": True, "output": f"Typed text successfully. Enter pressed: {press_enter}", "error": ""}
    except Exception as exc:
        logger.error("type_text error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
        
        
async def press_key(key_sequence: str) -> dict[str, Any]:
    """
    Press a single key or a combination of keys (e.g. 'win', 'ctrl+c', 'enter', 'tab', 'down').
    
    Args:
        key_sequence: '+' separated keys, e.g. "ctrl+shift+esc", "win+d" or just "enter"
    """
    try:
        import pyautogui
        
        keys = [k.strip().lower() for k in key_sequence.split('+')]
        
        def _do_hotkey():
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)

        await asyncio.to_thread(_do_hotkey)
        return {"success": True, "output": f"Pressed hotkey: {key_sequence}", "error": ""}
    except Exception as exc:
        logger.error("press_key error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


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
    result = await _run_powershell(script)
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
        for proc in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info.get("cpu_percent", 0) or 0,
                           reverse=True)[:top_n]:
            info = proc.info
            processes.append({
                "pid": info.get("pid"),
                "name": info.get("name"),
                "cpu": round(info.get("cpu_percent") or 0, 1),
                "mem": round(info.get("memory_percent") or 0, 1),
            })
        return {"success": True, "output": json.dumps(processes), "error": "", "processes": processes}
    except Exception as exc:
        logger.error("list_running_processes error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc), "processes": []}


# ─────────────────────────────────────────────
# System Resource Monitoring
# ─────────────────────────────────────────────

async def get_system_stats() -> dict[str, Any]:
    """
    Return real-time CPU, RAM, and disk stats using psutil.

    Returns:
        Dict with cpu_percent, ram_percent, ram_gb_used, ram_gb_total, disk_percent.
    """
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

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


# ─────────────────────────────────────────────
# Lock Screen
# ─────────────────────────────────────────────

async def lock_screen() -> dict[str, Any]:
    """Lock the Windows workstation immediately."""
    script = "rundll32.exe user32.dll,LockWorkStation; Write-Output '[OK] Screen locked'"
    result = await _run_powershell(script)
    logger.info("lock_screen: %s", result)
    return result


# ─────────────────────────────────────────────
# Clipboard
# ─────────────────────────────────────────────

async def get_clipboard() -> dict[str, Any]:
    """Return the current clipboard text content."""
    script = "Get-Clipboard | Out-String"
    result = await _run_powershell(script)
    return result


async def set_clipboard(text: str) -> dict[str, Any]:
    """Set the clipboard to the given text."""
    escaped = text.replace('"', '`"')
    script = f'Set-Clipboard -Value "{escaped}"; Write-Output "[OK] Clipboard updated"'
    result = await _run_powershell(script)
    logger.info("set_clipboard: %s", result)
    return result


# ─────────────────────────────────────────────
# System Power
# ─────────────────────────────────────────────

async def sleep_system() -> dict[str, Any]:
    """Put the system to sleep."""
    script = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0; Write-Output '[OK] System sleeping'"
    return await _run_powershell(script)


async def shutdown_system(delay_seconds: int = 30) -> dict[str, Any]:
    """
    Schedule a system shutdown.

    Args:
        delay_seconds: Seconds before shutdown (default 30). Pass 0 for immediate.
    """
    script = f"shutdown /s /t {delay_seconds}; Write-Output '[OK] Shutdown scheduled in {delay_seconds}s'"
    result = await _run_powershell(script)
    logger.warning("shutdown_system(%ds): %s", delay_seconds, result)
    return result


async def restart_system(delay_seconds: int = 30) -> dict[str, Any]:
    """
    Schedule a system restart.

    Args:
        delay_seconds: Seconds before restart (default 30).
    """
    script = f"shutdown /r /t {delay_seconds}; Write-Output '[OK] Restart scheduled in {delay_seconds}s'"
    result = await _run_powershell(script)
    logger.warning("restart_system(%ds): %s", delay_seconds, result)
    return result


# ─────────────────────────────────────────────
# Phase 2: Iron Man Upgrades (Vision & Web)
# ─────────────────────────────────────────────

async def analyze_screen(prompt: str) -> dict[str, Any]:
    """
    Take a screenshot of the main monitor and ask Gemini 1.5 Flash Vision model a question about it.

    Args:
        prompt: The question to ask the vision model about the screenshot.
    """
    global _VISION_SYSTEM
    
    if not _VISION_SYSTEM or not _VISION_SYSTEM.enabled:
        return {"success": False, "error": "Vision system is disabled or GEMINI_API_KEY is not set in .env."}
        
    try:
        logger.info("analyze_screen: delegating to VisionSystem...")
        vision_text = await _VISION_SYSTEM.analyze_screen(prompt)
        logger.info("analyze_screen: success.")
        return {"success": True, "output": vision_text, "error": ""}
    except Exception as exc:
        logger.error("analyze_screen error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def search_web(query: str) -> dict[str, Any]:
    """
    Search the internet using DuckDuckGo to answer real-time questions.

    Args:
        query: The search query string.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
            
        import json

        logger.info("search_web query: '%s'", query)
        
        # We must run synchronous DDGS inside a thread to not block the event loop
        def _do_search():
            with DDGS() as ddgs:
                # return top 5 text results
                return list(ddgs.text(query, max_results=5))

        results = await asyncio.to_thread(_do_search)
        
        if not results:
            return {"success": True, "output": "No results found.", "error": ""}
            
        formatted_results = "\\n\\n".join([
            f"Title: {r.get('title')}\\nURL: {r.get('href')}\\nSnippet: {r.get('body')}"
            for r in results
        ])
        return {"success": True, "output": f"Top {len(results)} results:\\n" + formatted_results, "error": ""}
    except Exception as exc:
        logger.error("search_web error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def read_website(url: str) -> dict[str, Any]:
    """
    Read a website's content and extract its main text.

    Args:
        url: The URL of the website to read.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        
        logger.info("read_website url: '%s'", url)
        
        def _fetch_and_parse():
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            # Ignore SSL verification errors to allow reading broader endpoints
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, timeout=10.0, verify=False)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts, styles, embedded CSS
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.extract()
                
            text = soup.get_text(separator="\\n", strip=True)
            
            # Collapse multiple newlines
            import re
            text = re.sub(r"\\n{2,}", "\\n\\n", text)
            
            # Limit the output length to avoid blowing up the context window
            max_chars = 15000
            if len(text) > max_chars:
                text = text[:max_chars] + "... [TRUNCATED]"
                
            return text

        content = await asyncio.to_thread(_fetch_and_parse)
        
        if not content:
            return {"success": True, "output": "Website is empty or could not be parsed.", "error": ""}
            
        return {"success": True, "output": content, "error": ""}
    except Exception as exc:
        logger.error("read_website error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}


async def execute_powershell(script: str) -> dict[str, Any]:
    """
    Execute arbitrary PowerShell code.
    EXTREMELY DANGEROUS. Placed behind a strict manual terminal confirmation.
    
    Args:
        script: The raw PowerShell script to execute.
    """
    import builtins
    
    logger.warning("JARVIS ATTEMPTING TO RUN ARBITRARY POWERSHELL.")
    print("\n" + "="*60)
    print("⚠️ JARVIS wants to execute the following PowerShell script ⚠️")
    print("="*60)
    print(script)
    print("="*60)
    
    try:
        # Prompt user in terminal without blocking the event loop
        ans = await asyncio.to_thread(builtins.input, "Allow execution? (y/N): ")
    except Exception:
        ans = "n"
        
    if ans.lower().strip() != "y":
        logger.info("User denied execution of execute_powershell.")
        return {"success": False, "error": "Operation aborted by user. I am not allowed to run this code."}

    logger.info("User approved execution. Running script...")
    return await _run_powershell(script)


# ─────────────────────────────────────────────
# Reminders & Temporal Awareness
# ─────────────────────────────────────────────

async def _reminder_worker(message: str, delay_minutes: int):
    """Background worker that waits and then plays an audio notification."""
    await asyncio.sleep(delay_minutes * 60)
    logger.info("Reminder triggered: %s", message)
    # Use PowerShell's built-in TTS for the alarm
    script = f"""
Add-Type -AssemblyName System.speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoiceByHints('Female')
$synth.Speak("Lembrete importante: {message.replace('"', '`"')}")
"""
    await _run_powershell(script)

async def set_reminder(message: str, delay_minutes: int) -> dict[str, Any]:
    """
    Schedule a reminder to be spoken aloud after a certain number of minutes.
    
    Args:
        message: The text of the reminder.
        delay_minutes: Wait time in minutes before alarming.
    """
    # Fire and forget
    loop = asyncio.get_running_loop()
    loop.create_task(_reminder_worker(message, delay_minutes))
    return {"success": True, "output": f"[OK] Lembrete programado para daqui a {delay_minutes} minutos.", "error": ""}


# ─────────────────────────────────────────────
# Media Controls
# ─────────────────────────────────────────────

async def control_media(action: str) -> dict[str, Any]:
    """
    Control system media playback (Play/Pause, Next, Previous).
    
    Args:
        action: "play_pause", "next", or "previous".
    """
    keys = {
        "play_pause": 179,
        "next": 176,
        "previous": 177
    }
    
    act_key = keys.get(action.lower().strip())
    if not act_key:
        return {"success": False, "error": f"Invalid action '{action}'. Use play_pause, next, or previous."}
        
    script = f"""
$wshell = New-Object -ComObject wscript.shell
$wshell.SendKeys([char]{act_key})
"""
    result = await _run_powershell(script)
    if result["success"]:
        return {"success": True, "output": f"[OK] Media action '{action}' sent.", "error": ""}
    return result


# ─────────────────────────────────────────────
# Weather (OpenWeatherMap)
# ─────────────────────────────────────────────

async def get_weather(city: str) -> dict[str, Any]:
    """
    Fetch current weather for a city using OpenWeatherMap API.
    Falls back to a DuckDuckGo search if no API key is configured.

    Args:
        city: City name, e.g. "São Paulo", "Curitiba", "Brasília".
    """
    import urllib.parse

    api_key = _OPENWEATHERMAP_API_KEY

    if api_key:
        # Primary: OpenWeatherMap free tier
        try:
            import httpx

            encoded_city = urllib.parse.quote(city)
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={encoded_city}&appid={api_key}&units=metric&lang=pt_br"
            )

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            description = data["weather"][0]["description"].capitalize()
            wind_speed = data["wind"]["speed"]
            city_name = data["name"]

            summary = (
                f"{city_name}: {description}, {temp:.0f}°C "
                f"(sensação {feels_like:.0f}°C), "
                f"umidade {humidity}%, vento {wind_speed:.1f} m/s"
            )
            logger.info("get_weather('%s'): %s", city, summary)
            return {"success": True, "output": summary, "error": "", "data": data}

        except Exception as exc:
            logger.warning("OpenWeatherMap failed: %s — falling back to search", exc)

    # Fallback: DuckDuckGo search
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        def _search():
            with DDGS() as ddgs:
                # Perguntar explicitamente pelo clima atual
                return list(ddgs.text(f"tempo agora em {city} previsao", max_results=3))

        results = await asyncio.to_thread(_search)
        if results:
            snippets = " | ".join(r.get("body", "") for r in results[:2])
            return {"success": True, "output": f"Resultados de busca para clima em {city}: {snippets}", "error": ""}
        return {"success": False, "output": "", "error": "Não foi possível obter o clima."}
    except Exception as exc:
        logger.error("get_weather fallback error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
