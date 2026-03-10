"""
JARVIS - Windows OS Control Module - Web
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.web")


async def search_web(query: str) -> dict[str, Any]:
    """
    Search the internet using DuckDuckGo to answer real-time questions.

    Args:
        query: The search query string.
    """
    try:
        from duckduckgo_search import DDGS

        logger.info("search_web query: '%s'", query)

        # We must run synchronous DDGS inside a thread to not block the event loop
        def _do_search():
            ddgs = DDGS()
            # return top 5 text results
            return list(ddgs.text(query, max_results=5))

        results = await asyncio.to_thread(_do_search)

        if not results:
            return {"success": True, "output": "No results found.", "error": ""}

        formatted_results = "

".join(
            [
                f"Title: {r.get('title')}
URL: {r.get('href')}
Snippet: {r.get('body')}"
                for r in results
            ]
        )
        return {
            "success": True,
            "output": f"Top {len(results)} results:
" + formatted_results,
            "error": "",
        }
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
            response = requests.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove scripts, styles, embedded CSS
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.extract()

            text = soup.get_text(separator="
", strip=True)

            # Collapse multiple newlines
            import re

            text = re.sub(r"
{2,}", "

", text)

            # Limit the output length to avoid blowing up the context window
            max_chars = 15000
            if len(text) > max_chars:
                text = text[:max_chars] + "... [TRUNCATED]"

            return text

        content = await asyncio.to_thread(_fetch_and_parse)

        if not content:
            return {
                "success": True,
                "output": "Website is empty or could not be parsed.",
                "error": "",
            }

        return {"success": True, "output": content, "error": ""}
    except Exception as exc:
        logger.error("read_website error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}
