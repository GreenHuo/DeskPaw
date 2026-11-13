"""Contracts implemented by future local, vector or remote knowledge adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .models import KnowledgeChunk, KnowledgeQuery


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: KnowledgeQuery) -> Iterable[KnowledgeChunk]:
        """Return best matches first, scoped to query.collection_ids.

        Called on a chat worker thread. Implementations own timeouts, access
        controls and thread safety; yield at most query.limit results.
        """
        ...
