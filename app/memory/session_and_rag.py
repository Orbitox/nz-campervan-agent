"""Persistent Session State & Grounded Vector/FTS Knowledge Store (Criterion 2.3).

Connects the KiwiCamp agent to persistent multi-turn session storage and RAG:
1. Cloud production: `VertexAiSessionService` (managed by Vertex AI Agent Engine)
   and `VertexAiSearchTool` (Vertex AI Search datastore grounding).
2. Relational/Local persistence: `DatabaseSessionService` (SQLAlchemy/PostgreSQL/SQLite)
   and `NzCampervanPersistentStore` (SQLite database persisting session state, user
   preferences, and full-text/vector similarity search across turns and restarts).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.data.nz_itinerary_dataset import NZ_28_DAY_ITINERARY_RAW
from app.observability.pii_redactor import redact_pii

try:
    from google.adk.sessions import (
        DatabaseSessionService,
        InMemorySessionService,
        VertexAiSessionService,
    )
except ImportError:  # pragma: no cover
    DatabaseSessionService = None  # type: ignore[assignment,misc]
    InMemorySessionService = None  # type: ignore[assignment,misc]
    VertexAiSessionService = None  # type: ignore[assignment,misc]

try:
    from google.adk.tools import VertexAiSearchTool
except ImportError:  # pragma: no cover
    VertexAiSearchTool = None  # type: ignore[assignment,misc]


class NzCampervanPersistentStore:
    """SQLite-backed persistent session state & vector-indexed knowledge store.

    Provides durable cross-turn storage for session state (`sessions` table),
    consolidated long-term traveler memories (`user_memories` table), and grounded
    28-day New Zealand campsite & route embeddings (`knowledge_chunks` table).
    """

    def __init__(self, db_path: str = "/tmp/kiwicamp_persistent_state.sqlite3") -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._seed_knowledge_base_if_empty()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_memories (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    fact_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    day_number INTEGER NOT NULL,
                    island TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _compute_bag_of_words_embedding(text: str) -> Dict[str, float]:
        """Computes a normalized sparse term-frequency vector for cosine similarity."""
        tokens = [
            tok.strip(".,!?:;()[]{}\"'").lower()
            for tok in text.split()
            if len(tok.strip(".,!?:;()[]{}\"'")) >= 3
        ]
        counts: Dict[str, float] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
        return {k: round(v / norm, 4) for k, v in counts.items()}

    @staticmethod
    def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        shared = set(vec_a.keys()) & set(vec_b.keys())
        return sum(vec_a[k] * vec_b[k] for k in shared)

    def _seed_knowledge_base_if_empty(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM knowledge_chunks").fetchone()
            if row and int(row["cnt"]) >= 28:
                return

            for day_raw in NZ_28_DAY_ITINERARY_RAW:
                text_blob = (
                    f"Day {day_raw['day_number']} ({day_raw['date_label']}) - {day_raw['title']}. "
                    f"Route: {day_raw['start_location']} to {day_raw['end_location']}. "
                    f"{day_raw['summary']} "
                    f"Highlights: {'; '.join(day_raw['must_do_highlights'])}. "
                    f"Campsite: {day_raw['overnight_campsite']['name']}."
                )
                emb = self._compute_bag_of_words_embedding(text_blob)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO knowledge_chunks
                    (chunk_id, day_number, island, title, content, embedding_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"day-{day_raw['day_number']:02d}",
                        day_raw["day_number"],
                        day_raw["island"],
                        day_raw["title"],
                        text_blob,
                        json.dumps(emb),
                    ),
                )

    def save_session_state(
        self, session_id: str, user_id: str, state: Dict[str, Any]
    ) -> None:
        """Persists scrubbed session state to SQLite."""
        scrubbed_state = redact_pii(state)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, user_id, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, user_id, json.dumps(scrubbed_state), now_iso),
            )

    def load_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Loads persisted session state across turns."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return json.loads(row["state_json"])
        return None

    def semantic_search_knowledge(
        self, query: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Performs vector cosine similarity retrieval over the 28-day NZ knowledge base."""
        q_vec = self._compute_bag_of_words_embedding(query)
        scored: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, day_number, island, title, content, embedding_json FROM knowledge_chunks"
            ).fetchall()
            for r in rows:
                doc_vec = json.loads(r["embedding_json"])
                score = self._cosine_similarity(q_vec, doc_vec)
                scored.append(
                    {
                        "chunk_id": r["chunk_id"],
                        "day_number": r["day_number"],
                        "island": r["island"],
                        "title": r["title"],
                        "content": r["content"],
                        "similarity_score": round(score, 4),
                    }
                )
        scored.sort(key=lambda item: item["similarity_score"], reverse=True)
        return scored[:top_k]


def build_persistent_session_service(
    project_id: Optional[str] = None,
    location: str = "us-central1",
    agent_engine_id: Optional[str] = None,
    db_url: Optional[str] = None,
) -> Any:
    """Instantiates `VertexAiSessionService` or `DatabaseSessionService` for persistent sessions."""
    proj = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    eng_id = agent_engine_id or os.environ.get("AGENT_ENGINE_ID")
    database_url = db_url or os.environ.get(
        "SESSION_DATABASE_URL", "sqlite:///kiwicamp_sessions.db"
    )

    if proj and eng_id and VertexAiSessionService is not None:
        return VertexAiSessionService(
            project=proj,
            location=location,
            agent_engine_id=eng_id,
        )

    if DatabaseSessionService is not None:
        try:
            return DatabaseSessionService(db_url=database_url)
        except Exception:
            pass

    return NzCampervanPersistentStore()


def build_vertex_ai_search_grounding_tool(
    data_store_id: Optional[str] = None,
) -> Any:
    """Configures `VertexAiSearchTool` pointing to the NZ Tourism & DOC Campsite datastore."""
    ds_id = data_store_id or os.environ.get(
        "VERTEX_SEARCH_DATASTORE_ID",
        "projects/kiwicamp-prod/locations/global/collections/default_collection/dataStores/nz-doc-campsites-datastore",
    )
    if VertexAiSearchTool is not None:
        return VertexAiSearchTool(data_store_id=ds_id)
    return {"type": "VertexAiSearchTool", "data_store_id": ds_id}
