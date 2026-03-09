"""
JARVIS - Memory Manager
Persists and retrieves conversation context using TinyDB (JSON-backed).
Provides windowed history for the LLM (last N turns or last N minutes).
Also manages long-term persistent memory between sessions.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tinydb import TinyDB, Query

logger = logging.getLogger("jarvis.memory_manager")


class MemoryManager:
    """
    Manages short-term conversation memory using TinyDB.
    Each turn is stored with a UTC timestamp for time-based windowing.
    Also handles long-term persistent facts about the user.
    """

    def __init__(
        self,
        db_path: Path,
        max_turns: int = 20,
        max_minutes: int = 60,
    ) -> None:
        self._db_path = db_path
        self._max_turns = max_turns
        self._max_minutes = max_minutes

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(str(db_path))
        self._table = self._db.table("conversations")

        # Long-term memory: persistent facts about Mikael/preferences
        self._ltm_path = db_path.parent / "long_term_memory.json"
        self._long_term: dict[str, Any] = self._load_long_term_memory()

        logger.info("MemoryManager initialized. DB: %s", db_path)
        
        # Vector Database for Semantic Memory
        self._chroma_collection = None
        try:
            import chromadb
            # Disable posthog telemetry
            chromadb.api.client.SharedSystemClient._identifier = "jarvis" 
            chroma_dir = db_path.parent / "chroma"
            self._chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
            self._chroma_collection = self._chroma_client.get_or_create_collection(name="jarvis_memory")
            logger.info("ChromaDB Vector Memory initialized.")
        except Exception as exc:
            logger.error("Failed to initialize ChromaDB: %s", exc)

    # ── Short-term memory (session-based) ──────────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        """
        Append a conversation turn to the DB.

        Args:
            role:    "user" or "assistant"
            content: Text content of the turn
        """
        now = datetime.now(timezone.utc).isoformat()
        self._table.insert({"role": role, "content": content, "timestamp": now})
        logger.debug("Memory: added turn [%s] at %s", role, now)
        
        if self._chroma_collection:
            try:
                # Add to Vector DB for long-term semantic retrieval
                doc_id = f"msg_{datetime.now().timestamp()}"
                self._chroma_collection.add(
                    documents=[content],
                    metadatas=[{"role": role, "timestamp": now}],
                    ids=[doc_id]
                )
            except Exception as exc:
                logger.error("Failed to add memory to ChromaDB: %s", exc)

        self._prune()

    def _prune(self) -> None:
        """Remove turns older than max_minutes to keep DB lean."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._max_minutes)
        cutoff_iso = cutoff.isoformat()
        Turn = Query()
        removed = self._table.remove(Turn.timestamp < cutoff_iso)
        if removed:
            logger.debug("Memory: pruned %d old turns.", len(removed))

    def get_recent_turns(self) -> list[dict[str, str]]:
        """
        Retrieve the most recent turns within the time window,
        capped at max_turns.

        Returns:
            List of {'role': ..., 'content': ...} dicts, oldest first.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._max_minutes)
        cutoff_iso = cutoff.isoformat()

        Turn = Query()
        recent = self._table.search(Turn.timestamp >= cutoff_iso)

        # Sort by timestamp, take last max_turns
        recent.sort(key=lambda t: t["timestamp"])
        if len(recent) > self._max_turns:
            recent = recent[-self._max_turns:]

        return [{"role": t["role"], "content": t["content"]} for t in recent]

    def search_memory(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Search the vector database for semantically similar past turns.
        """
        if not self._chroma_collection:
            return []
            
        try:
            results = self._chroma_collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            docs = []
            if results and results.get("documents") and results["documents"][0]:
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    docs.append({
                        "content": doc, 
                        "role": meta.get("role", "unknown"), 
                        "timestamp": meta.get("timestamp", "")
                    })
            return docs
        except Exception as exc:
            logger.error("Failed to query ChromaDB: %s", exc)
            return []

    def clear(self) -> None:
        """Wipe all stored conversation history."""
        self._table.truncate()
        logger.info("Memory: conversation history cleared.")

    # ── Long-term memory (persistent between sessions) ──────────────────────────

    def _load_long_term_memory(self) -> dict[str, Any]:
        """Load persistent long-term memory from disk. Creates defaults if not found."""
        if self._ltm_path.exists():
            try:
                data = json.loads(self._ltm_path.read_text(encoding="utf-8"))
                logger.info("Long-term memory loaded: %d keys", len(data))
                return data
            except Exception as exc:
                logger.warning("Failed to load long-term memory: %s", exc)

        # Default structure for new installations
        default = {
            "owner": "Mikael",
            "preferences": [],
            "projects": [],
            "facts": [],
            "last_seen": None,
        }
        self._save_long_term_memory(default)
        return default

    def _save_long_term_memory(self, data: dict | None = None) -> None:
        """Persist long-term memory to disk."""
        target = data or self._long_term
        try:
            self._ltm_path.write_text(
                json.dumps(target, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to save long-term memory: %s", exc)

    def get_long_term_context(self) -> str:
        """
        Return long-term memory as a formatted string to inject in the system prompt.
        """
        ltm = self._long_term
        lines = []

        if ltm.get("preferences"):
            lines.append(f"Preferências do Mikael: {', '.join(ltm['preferences'])}")
        if ltm.get("projects"):
            lines.append(f"Projetos ativos: {', '.join(ltm['projects'])}")
        if ltm.get("facts"):
            lines.append(f"Fatos relevantes: {', '.join(ltm['facts'])}")
        if ltm.get("last_seen"):
            lines.append(f"Última sessão: {ltm['last_seen']}")

        return "\n".join(lines) if lines else ""

    def update_long_term(self, key: str, value: Any) -> None:
        """Update a single key in long-term memory and persist."""
        self._long_term[key] = value
        self._save_long_term_memory()
        logger.info("Long-term memory updated: %s = %s", key, value)

    def add_to_long_term_list(self, key: str, item: str) -> None:
        """Append an item to a list in long-term memory (no duplicates)."""
        lst = self._long_term.setdefault(key, [])
        if item not in lst:
            lst.append(item)
            self._save_long_term_memory()
            logger.info("Long-term memory: added '%s' to '%s'", item, key)

    def record_session_start(self) -> None:
        """Record the timestamp of the current session start."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.update_long_term("last_seen", now)

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the TinyDB connection gracefully."""
        self._db.close()
        logger.info("MemoryManager closed.")
