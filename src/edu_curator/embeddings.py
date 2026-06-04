from __future__ import annotations

_embeddings_model = None


def get_embeddings_model():
    """Lazy load the sentence transformer model on CPU."""
    global _embeddings_model
    if _embeddings_model is None:
        print("Loading local sentence-transformers model (all-MiniLM-L6-v2) on CPU...")
        from sentence_transformers import SentenceTransformer

        _embeddings_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embeddings_model


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    """Compute embeddings for a list of texts using the local model."""
    if not texts:
        return []
    model = get_embeddings_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


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
