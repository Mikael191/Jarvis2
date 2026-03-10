"""
JARVIS - Windows OS Control Module - Web
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.windows_os.web")


import httpx

# OpenWeatherMap API key injected by JarvisApp for the get_weather tool
_OPENWEATHERMAP_API_KEY: str = ""

async def get_weather(city: str) -> dict[str, Any]:
    """
    Get the current weather and forecast for a city using OpenWeatherMap.

    Args:
        city: City name, e.g. 'São Paulo' or 'Curitiba'
    """
    if not _OPENWEATHERMAP_API_KEY:
        return {"success": False, "output": "Erro: OPENWEATHERMAP_API_KEY não configurada.", "error": "Missing API key"}

    logger.info("get_weather for: '%s'", city)

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": _OPENWEATHERMAP_API_KEY,
        "units": "metric",
        "lang": "pt_br"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            desc = data["weather"][0]["description"]
            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]

            output = f"Clima em {city}: {desc}. Temperatura: {temp}°C (sensação de {feels_like}°C). Umidade: {humidity}%."
            return {"success": True, "output": output, "error": ""}

    except Exception as exc:
        logger.error("get_weather error: %s", exc, exc_info=True)
        return {"success": False, "output": "", "error": str(exc)}

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

        formatted_results = "\n\n".join(
            [
                f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}"
                for r in results
            ]
        )
        return {
            "success": True,
            "output": f"Top {len(results)} results:\n" + formatted_results,
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
        from bs4 import BeautifulSoup

        logger.info("read_website url: '%s'", url)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            html_content = response.text

        def _parse():
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove scripts, styles, embedded CSS
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.extract()

            text = soup.get_text(separator="\n", strip=True)

            # Collapse multiple newlines
            import re

            text = re.sub(r"\n{2,}", "\n\n", text)

            # Limit the output length to avoid blowing up the context window
            max_chars = 15000
            if len(text) > max_chars:
                text = text[:max_chars] + "... [TRUNCATED]"

            return text

        content = await asyncio.to_thread(_parse)

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
