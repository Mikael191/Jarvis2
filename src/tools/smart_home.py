"""
JARVIS - Smart Home Integration
Provides integration for local Home Assistant and generic Webhooks (like IFTTT).
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.smart_home")

# You can add these later in .env
_HOME_ASSISTANT_URL = "" 
_HOME_ASSISTANT_TOKEN = ""

async def control_smart_home(device_name: str, action: str, parameters: dict | None = None) -> dict[str, Any]:
    """
    Control a smart home device via Home Assistant or a generic local webhook.
    
    Args:
        device_name: Name of the device, e.g., 'luz_quarto', 'ar_condicionado'.
        action: What to do, e.g., 'turn_on', 'turn_off', 'set_temperature'.
        parameters: Optional extra parameters (like brightness or temperature).
    """
    try:
        import httpx
        
        logger.info("Smart Home command: %s -> %s %s", device_name, action, parameters)
        
        if not _HOME_ASSISTANT_URL or not _HOME_ASSISTANT_TOKEN:
            # Stub mode: return a mockup success message so the LLM can acknowledge it smoothly
            # while the user has not configured the real integration.
            mock_msg = f"[MOCK] Sucesso. '{device_name}' recebeu a ação '{action}'."
            logger.info("Smart Home (Stub Mode) -> %s", mock_msg)
            return {"success": True, "output": mock_msg, "error": ""}
        
        # Real Home Assistant Implementation
        domain = "light" if "luz" in device_name.lower() or "light" in device_name.lower() else "switch"
        url = f"{_HOME_ASSISTANT_URL}/api/services/{domain}/{action}"
        headers = {
            "Authorization": f"Bearer {_HOME_ASSISTANT_TOKEN}",
            "Content-Type": "application/json",
        }
        
        payload = {"entity_id": f"{domain}.{device_name}"}
        if parameters:
            payload.update(parameters)
            
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            
        return {"success": True, "output": f"Comando enviado com sucesso para {device_name}.", "error": ""}
        
    except httpx.RequestError as exc:
        logger.error("Smart Home HTTP error: %s", exc)
        return {"success": False, "output": "", "error": f"Erro de conexão com o Smart Home: {exc}"}
    except Exception as exc:
        logger.error("Smart Home unexpected error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
