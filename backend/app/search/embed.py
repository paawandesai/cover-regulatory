"""Local text embeddings (nomic-embed-text-v1.5 through fastembed, ONNX on CPU).

The model runs in-process, so regulation text and queries never leave the machine for embedding.
nomic models expect a task prefix on every input."""

from collections.abc import Iterable
from functools import lru_cache

from app.config import get_settings

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


@lru_cache
def _model():
    from fastembed import TextEmbedding  # imported lazily: loading the model takes seconds

    return TextEmbedding(get_settings().embedding_model)


def embed_documents(texts: Iterable[str], batch_size: int = 32) -> list[list[float]]:
    return [v.tolist() for v in _model().embed([DOC_PREFIX + t for t in texts], batch_size=batch_size)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().embed([QUERY_PREFIX + text]))).tolist()


def model_name() -> str:
    return get_settings().embedding_model
