"""Immutable knowledge retrieval values, independent of Qt and storage engines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeQuery:
    text: str
    limit: int = 4
    collection_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeChunk:
    """A retrievable passage with a stable ID and human-readable source."""

    chunk_id: str
    content: str
    source: str
    title: str = ""


@dataclass(frozen=True)
class KnowledgeContext:
    """Bounded JSON passages and the exact source chunks included in them."""

    payload: str = ""
    chunks: tuple[KnowledgeChunk, ...] = ()
