"""Persistent memory: SQLite for raw transcripts + Chroma for semantic recall.

The companion remembers every conversation, idea, and piece of context. The
SQLite store is the immutable journal; Chroma provides "what did the user say
about X six weeks ago" semantic search.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ..config import get_settings


class Base(DeclarativeBase):
    pass


class MemoryRow(Base):
    __tablename__ = "memories"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)  # message|idea|fact|task
    role: Mapped[str] = mapped_column(String)              # user|assistant|system
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[Any] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


@dataclass
class MemoryItem:
    id: str
    user_id: str
    kind: str
    role: str
    content: str
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class MemoryStore:
    """SQLite-backed journal + optional Chroma semantic index."""

    def __init__(self, db_path: Optional[str] = None, chroma_path: Optional[str] = None):
        s = get_settings()
        self.db_path = db_path or s.memory_db_path
        self.chroma_path = chroma_path or s.chroma_path

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)

        self._chroma = None
        self._collection = None
        try:
            import chromadb
            self._chroma = chromadb.PersistentClient(path=self.chroma_path)
            self._collection = self._chroma.get_or_create_collection(
                name="companion_memory",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            # Chroma is optional; raw SQL still works.
            self._chroma = None
            self._collection = None

    # -------------------------------------------------------------------- write
    def add(
        self,
        user_id: str,
        content: str,
        *,
        role: str = "user",
        kind: str = "message",
        meta: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            kind=kind,
            role=role,
            content=content,
            meta=meta or {},
        )
        with Session(self.engine) as session:
            session.add(
                MemoryRow(
                    id=item.id,
                    user_id=user_id,
                    kind=kind,
                    role=role,
                    content=content,
                    meta=json.dumps(item.meta),
                )
            )
            session.commit()

        if self._collection is not None:
            try:
                self._collection.add(
                    ids=[item.id],
                    documents=[content],
                    metadatas=[{"user_id": user_id, "kind": kind, "role": role}],
                )
            except Exception:
                pass
        return item

    # -------------------------------------------------------------------- reads
    def recent(self, user_id: str, limit: int = 20) -> List[MemoryItem]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(MemoryRow)
                .where(MemoryRow.user_id == user_id)
                .order_by(MemoryRow.seq.desc())
                .limit(limit)
            ).scalars().all()
        return [self._row_to_item(r) for r in reversed(rows)]

    def search(self, user_id: str, query: str, k: int = 5) -> List[MemoryItem]:
        """Semantic search via Chroma; falls back to LIKE if Chroma is missing."""
        if self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=k,
                    where={"user_id": user_id},
                )
                ids = results.get("ids", [[]])[0]
                if ids:
                    with Session(self.engine) as session:
                        rows = session.execute(
                            select(MemoryRow).where(MemoryRow.id.in_(ids))
                        ).scalars().all()
                    return [self._row_to_item(r) for r in rows]
            except Exception:
                pass

        # Fallback: substring match
        with Session(self.engine) as session:
            rows = session.execute(
                select(MemoryRow)
                .where(MemoryRow.user_id == user_id)
                .where(MemoryRow.content.like(f"%{query}%"))
                .order_by(MemoryRow.seq.desc())
                .limit(k)
            ).scalars().all()
        return [self._row_to_item(r) for r in rows]

    def context_block(self, user_id: str, query: str) -> str:
        """Build a compact 'what we know' string to inject into a prompt."""
        recent = self.recent(user_id, limit=8)
        relevant = self.search(user_id, query, k=5)

        seen: set[str] = set()
        lines: List[str] = []

        if relevant:
            lines.append("Relevant prior memories:")
            for m in relevant:
                if m.id in seen:
                    continue
                seen.add(m.id)
                lines.append(f"  - [{m.kind}] {m.content}")

        if recent:
            lines.append("\nRecent conversation:")
            for m in recent:
                if m.id in seen:
                    continue
                seen.add(m.id)
                lines.append(f"  {m.role}: {m.content}")

        return "\n".join(lines) if lines else "(no prior memory)"

    # -------------------------------------------------------------------- utils
    @staticmethod
    def _row_to_item(r: MemoryRow) -> MemoryItem:
        return MemoryItem(
            id=r.id,
            user_id=r.user_id,
            kind=r.kind,
            role=r.role,
            content=r.content,
            meta=json.loads(r.meta or "{}"),
            created_at=r.created_at.timestamp() if r.created_at else time.time(),
        )
