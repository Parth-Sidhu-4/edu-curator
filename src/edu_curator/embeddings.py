from __future__ import annotations

import hashlib
import threading
from functools import lru_cache

_embeddings_model = None
_model_lock = threading.Lock()

# ── Embedding cache ────────────────────────────────────────────────────────────
# Keyed by SHA-256 of the input text. Bounded to 4096 entries (~150MB worst-case
# for 384-dim float32 vectors). Thread-safe via a dedicated lock.
_embed_cache: dict[str, list[float]] = {}
_embed_cache_lock = threading.Lock()
_EMBED_CACHE_MAX = 4096


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def get_embeddings_model():
    """Lazy load the sentence transformer model on CPU (thread-safe)."""
    global _embeddings_model
    if _embeddings_model is None:
        with _model_lock:
            if _embeddings_model is None:
                print("Loading local sentence-transformers model (all-MiniLM-L6-v2) on CPU...")
                from sentence_transformers import SentenceTransformer
                _embeddings_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embeddings_model


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    """Compute embeddings for a list of texts, using the per-process cache.

    Texts that were already embedded in this process are returned instantly
    from the cache without touching the model — eliminates redundant inference
    on pipeline re-runs and subtopic matching calls.
    """
    if not texts:
        return []

    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    with _embed_cache_lock:
        for i, text in enumerate(texts):
            key = _cache_key(text)
            if key in _embed_cache:
                results[i] = _embed_cache[key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

    if uncached_texts:
        model = get_embeddings_model()
        new_embeddings = model.encode(uncached_texts, show_progress_bar=False)
        with _embed_cache_lock:
            for idx, emb in zip(uncached_indices, new_embeddings):
                key = _cache_key(texts[idx])
                # Evict oldest entries if cache is full (simple FIFO eviction)
                if len(_embed_cache) >= _EMBED_CACHE_MAX:
                    oldest_key = next(iter(_embed_cache))
                    del _embed_cache[oldest_key]
                _embed_cache[key] = emb.tolist()
                results[idx] = _embed_cache[key]

    return [r for r in results if r is not None]


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity between two float lists using NumPy."""
    import numpy as np

    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

