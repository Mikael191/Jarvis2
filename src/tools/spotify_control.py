"""
JARVIS - Spotify Control Module
Provides deep integration with Spotify API for search and playback,
with a fallback to Windows URI protocols if API keys are missing.
"""

import logging
import subprocess
import asyncio
from typing import Any, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger("jarvis.tools.spotify")

# Injected by JarvisApp at startup
_CLIENT_ID: str = ""
_CLIENT_SECRET: str = ""
_REDIRECT_URI: str = "http://localhost:8888/callback"

_spotify_client: Optional[spotipy.Spotify] = None

def _get_client() -> Optional[spotipy.Spotify]:
    """Get or initialize the Spotify API client."""
    global _spotify_client
    if _spotify_client:
        return _spotify_client
        
    if not _CLIENT_ID or not _CLIENT_SECRET:
        logger.warning("Spotify API credentials missing. API mode disabled.")
        return None
        
    try:
        auth_manager = SpotifyOAuth(
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
            redirect_uri=_REDIRECT_URI,
            scope="user-modify-playback-state user-read-playback-state",
            open_browser=True # This will open a browser for the first-time login
        )
        _spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        return _spotify_client
    except Exception as exc:
        logger.error("Failed to initialize Spotify client: %s", exc)
        return None

async def play_spotify(query: str, type: str = "track") -> dict[str, Any]:
    """
    Search and play music on Spotify.
    
    Args:
        query: The song, album, or artist name.
        type: 'track', 'album', or 'playlist'.
    """
    client = _get_client()
    
    if client:
        try:
            # 1. Search for the item
            results = client.search(q=query, limit=1, type=type)
            items = results.get(type + 's', {}).get('items', [])
            
            if not items:
                return {"success": False, "error": f"No {type} found for '{query}'."}
                
            item = items[0]
            uri = item['uri']
            name = item['name']
            
            # 2. Try to play
            devices = client.devices()
            active_devices = [d for d in devices.get('devices', []) if d.get('is_active')]
            
            if not active_devices:
                # If no active device, we still try to start playback, 
                # but Spotify often requires an active session.
                # Fallback: Open the URI which should wake up the desktop app.
                subprocess.run(["powershell", "-Command", f"Start-Process '{uri}'"], check=False)
                return {"success": True, "output": f"Opening {name} on Spotify (no active device found).", "error": ""}

            if type == "track":
                client.start_playback(uris=[uri])
            else:
                client.start_playback(context_uri=uri)
                
            return {"success": True, "output": f"Now playing {type}: {name}", "error": ""}
            
        except Exception as exc:
            logger.error("Spotify API play error: %s", exc)
            # Fallback to URI method on API error
            return await _play_via_uri(query)
    else:
        # Simple mode: Just use Windows URI
        return await _play_via_uri(query)

async def _play_via_uri(query: str) -> dict[str, Any]:
    """Fallback: Opens Spotify and searches for the query."""
    logger.info("Using Spotify URI fallback for: %s", query)
    # Spotify URI for search: spotify:search:QUERY
    encoded_query = query.replace(" ", "%20")
    script = f"Start-Process 'spotify:search:{encoded_query}'"
    
    # We use the existing powershell runner logic from windows_os if we had it, 
    # but for simplicity since this is a new module:
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)
        return {
            "success": True, 
            "output": f"Spotify opened and searching for '{query}'. (Simplified Mode)", 
            "error": ""
        }
    except Exception as exc:
        return {"success": False, "error": f"Failed to open Spotify: {exc}"}
