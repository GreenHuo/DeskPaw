"""Optional, backend-neutral knowledge retrieval."""

from .models import KnowledgeChunk, KnowledgeContext, KnowledgeQuery
from .ports import KnowledgeRetriever
from .service import KnowledgeService

__all__ = [
    "KnowledgeChunk",
    "KnowledgeContext",
    "KnowledgeQuery",
    "KnowledgeRetriever",
    "KnowledgeService",
]
