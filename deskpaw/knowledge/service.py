"""Optional retrieval with bounded, source-attributed context construction."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from itertools import islice

from .models import KnowledgeChunk, KnowledgeContext, KnowledgeQuery
from .ports import KnowledgeRetriever


class KnowledgeService:
    def __init__(
        self,
        retriever: KnowledgeRetriever | None = None,
        *,
        limit: int = 4,
        max_context_chars: int = 6000,
        collection_ids: tuple[str, ...] = (),
    ) -> None:
        if not 1 <= limit <= 20:
            raise ValueError("Knowledge result limit must be between 1 and 20")
        if not 256 <= max_context_chars <= 32000:
            raise ValueError("Knowledge context budget must be between 256 and 32000 characters")
        self.retriever = retriever
        self.limit = limit
        self.max_context_chars = max_context_chars
        self.collection_ids = tuple(collection_ids)

    def context_for(self, text: str) -> KnowledgeContext:
        """Retrieve only when explicitly configured and the query is nonempty."""
        if self.retriever is None or not text.strip():
            return KnowledgeContext()
        query = KnowledgeQuery(text.strip(), self.limit, self.collection_ids)
        chunks: list[KnowledgeChunk] = []
        seen: set[tuple[str, str]] = set()
        for hit in islice(self.retriever.retrieve(query), self.limit):
            key = (hit.source, hit.chunk_id)
            if key in seen or not hit.content.strip():
                continue
            seen.add(key)
            candidate = replace(
                hit,
                chunk_id=hit.chunk_id[:200],
                source=hit.source[:500],
                title=hit.title[:200],
                content=hit.content.strip()[: self.max_context_chars],
            )
            # Use the serialized size, including JSON escaping and source metadata.
            low, high = 0, len(candidate.content)
            while low < high:
                middle = (low + high + 1) // 2
                trial = replace(candidate, content=candidate.content[:middle])
                if len(_serialize([*chunks, trial])) <= self.max_context_chars:
                    low = middle
                else:
                    high = middle - 1
            if low:
                chunks.append(replace(candidate, content=candidate.content[:low]))
        return KnowledgeContext(_serialize(chunks), tuple(chunks)) if chunks else KnowledgeContext()


def _serialize(chunks: list[KnowledgeChunk]) -> str:
    return json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False)
