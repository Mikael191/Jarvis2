"""
JARVIS - Local Files Module
"""

import os
import logging
from typing import Any
from pathlib import Path

logger = logging.getLogger("jarvis.tools.files")

async def search_local_files(query: str, start_dir: str = "", max_results: int = 15) -> dict[str, Any]:
    """
    Search recursively for files whose names match the query.
    Returns absolute paths of the matched files.
    """
    if not start_dir:
        # Default to the user's home directory (e.g. C:\Users\Mikael)
        start_dir = str(Path.home())
        
    logger.info("Searching for '%s' in '%s'", query, start_dir)
    results = []
    query_lower = query.lower()
    
    try:
        if not os.path.exists(start_dir):
            return {"success": False, "error": f"Directory not found: {start_dir}"}
            
        for root, dirs, files in os.walk(start_dir):
            # Prevent traversing deep hidden folders or development environments
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'venv', 'env', '__pycache__', 'AppData')]
            
            for file in files:
                if query_lower in file.lower():
                    results.append(os.path.join(root, file))
                    if len(results) >= max_results:
                        return {"success": True, "files": results}
                        
        return {"success": True, "files": results}
    except Exception as exc:
        logger.error("Error searching files: %s", exc)
        return {"success": False, "error": str(exc)}
