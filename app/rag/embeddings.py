"""
rag/embeddings.py
-----------------
Local embeddings via fastembed (ONNX runtime, no PyTorch).

Model: BAAI/bge-small-en-v1.5
  - 384-dimensional vectors
  - ~130MB on disk, ~300MB RAM when loaded
  - Loaded lazily on first use; cached for the process lifetime.
"""

from threading import Lock
from fastembed import TextEmbedding

from ..config import settings

_model: TextEmbedding | None = None
_lock = Lock()


def _get_model() -> TextEmbedding:
    """Lazy-load + cache the embedding model (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = TextEmbedding(model_name=settings.embedding_model)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of chunks for storage. One vector per text."""
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_query(query: str) -> list[float]:
    """Embed a single recruiter query for similarity search."""
    model = _get_model()
    vectors = list(model.query_embed([query]))
    return vectors[0].tolist()