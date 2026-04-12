"""Memory store smoke tests using a temporary SQLite db.

We don't import Chroma here, so the test exercises the SQLite + LIKE-fallback
search path.
"""
from __future__ import annotations

import pytest

from backend.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(
        db_path=str(tmp_path / "test.db"),
        chroma_path=str(tmp_path / "chroma"),
    )


def test_add_and_recent(store):
    store.add("u1", "first idea")
    store.add("u1", "second idea")
    items = store.recent("u1", limit=10)
    assert [i.content for i in items] == ["first idea", "second idea"]


def test_search_substring_fallback(store):
    store._collection = None  # force the LIKE fallback
    store.add("u1", "I love sushi in San Francisco")
    store.add("u1", "Reminder to call Alice")
    hits = store.search("u1", "sushi", k=5)
    assert any("sushi" in h.content for h in hits)


def test_context_block_includes_recent(store):
    store._collection = None
    store.add("u1", "Hello there", role="user")
    store.add("u1", "General Kenobi", role="assistant")
    block = store.context_block("u1", "kenobi")
    assert "General Kenobi" in block
