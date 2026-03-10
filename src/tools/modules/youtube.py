"""
JARVIS - YouTube Toolkit
"""

import urllib.parse
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.youtube")

async def read_youtube_transcript(url: str) -> dict[str, Any]:
    """
    Reads the transcript/subtitles of a YouTube video given its URL.
    Returns the full text so the LLM can summarize it.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"success": False, "error": "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"}

    logger.info("Reading YouTube transcript from %s", url)
    try:
        # Extract video ID
        parsed = urllib.parse.urlparse(url)
        video_id = None
        
        if parsed.hostname == 'youtu.be':
            video_id = parsed.path[1:]
        elif parsed.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch':
                p = urllib.parse.parse_qs(parsed.query)
                video_id = p.get('v', [None])[0]
        
        if not video_id:
            return {"success": False, "error": "URL do YouTube inválida ou não suportada."}
            
        # Download transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try getting Portuguese first, then English
        try:
            transcript = transcript_list.find_transcript(['pt', 'pt-BR'])
        except Exception:
            try:
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                # If neither is available, try to fallback to whatever auto-generated language exists
                transcript = transcript_list.find_generated_transcript(['pt', 'en'])
                
        data = transcript.fetch()
        text = " ".join([t['text'] for t in data])
        
        # Cap text to ~20000 characters to prevent overloading the LLM context window
        return {
            "success": True,
            "transcript": text[:20000]
        }
    except Exception as exc:
        logger.error("YouTube transcript failed: %s", exc)
        return {"success": False, "error": f"Não foi possível obter a legenda: {exc}"}
