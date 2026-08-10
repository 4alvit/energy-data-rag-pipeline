"""Cross-encoder reranking for improved retrieval."""

import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker for document reordering."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy load the cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name, max_length=512)
                logger.info("Loaded reranker model: %s", self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed, reranking disabled")
                self._model = False

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int | None = None,
    ) -> list[Document]:
        """Rerank documents by relevance to query."""
        self._load_model()

        if not self._model:
            return documents[:top_k] if top_k else documents

        if not documents:
            return []

        # Prepare pairs for cross-encoder
        pairs = [(query, doc.page_content) for doc in documents]

        # Get scores
        scores = self._model.predict(pairs, show_progress_bar=False)

        # Sort by score descending
        scored_docs = list(zip(documents, scores, strict=False))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        reranked = [doc for doc, _ in scored_docs]
        return reranked[:top_k] if top_k else reranked


def create_reranker(model_name: str | None = None) -> Reranker | None:
    """Create reranker if enabled."""
    if model_name is None:
        return None
    return Reranker(model_name)
