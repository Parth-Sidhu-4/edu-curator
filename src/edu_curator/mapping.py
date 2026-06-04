"""Topic mapping: assign content chunks to syllabus topics.

MVP Strategy
------------
Each Source carries a `topic_ids` list that declares which topic(s) its
content covers.  During mapping we create one SourceToTopicMapping row per
(chunk, topic_id) pair so that every topic's extraction step can find its
relevant chunks without scanning across all sources.

For sources that have no topic_ids set (legacy / pre-migration data) we fall
back to mapping their chunks to ALL provided topics — matching the original
single-topic behaviour so that existing data is never silently dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime

from edu_curator.ids import new_id
from edu_curator.schemas import (
    ContentChunk,
    Source,
    SourceToTopicMapping,
    SyllabusTopic,
)
from edu_curator.embeddings import compute_embeddings, cosine_similarity


def map_chunks_to_topics(
    topics: list[SyllabusTopic],
    chunks: list[ContentChunk],
    sources: list[Source],
    topic_filter_ids: set[str] | None = None,
) -> list[SourceToTopicMapping]:
    """Create SourceToTopicMapping rows for every (chunk, topic) pair.

    Parameters
    ----------
    topics:
        All registered syllabus topics.
    chunks:
        Content chunks to map (typically ALL chunks from documents.json).
    sources:
        All registered sources (used to look up topic_ids).
    topic_filter_ids:
        If provided, only create mappings for topics whose id is in this set.
        Use this when you want to (re)map a single topic without touching others.
    """
    source_by_id = {s.id: s for s in sources}
    all_topic_ids = {t.id for t in topics}

    # Determine which topic IDs we are mapping to
    target_topic_ids = topic_filter_ids if topic_filter_ids else all_topic_ids

    now = datetime.now(UTC)
    mappings: list[SourceToTopicMapping] = []

    for chunk in chunks:
        source = source_by_id.get(chunk.source_id)
        if source is None:
            continue

        # Determine which topics this chunk's source covers
        if source.topic_ids:
            covered = set(source.topic_ids) & target_topic_ids
        else:
            # Legacy source with no topic_ids: map to all target topics
            covered = target_topic_ids

        for topic_id in sorted(covered):
            mappings.append(
                SourceToTopicMapping(
                    id=new_id(),
                    source_id=chunk.source_id,
                    chunk_id=chunk.id,
                    topic_id=topic_id,
                    vector_score=None,
                    reranker_score=None,
                    is_active=True,
                    created_at=now,
                )
            )

    return mappings


# ---------------------------------------------------------------------------
# Backward-compat alias used by the old single-topic CLI command
# ---------------------------------------------------------------------------


def map_chunks_to_single_topic(
    topic: SyllabusTopic,
    chunks: list[ContentChunk],
) -> list[SourceToTopicMapping]:
    """Legacy helper kept for CLI backward compat.

    Maps ALL chunks to a single topic regardless of source.topic_ids.
    Only used internally; prefer map_chunks_to_topics for new code.
    """
    now = datetime.now(UTC)
    return [
        SourceToTopicMapping(
            id=new_id(),
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            topic_id=topic.id,
            vector_score=None,
            reranker_score=None,
            is_active=True,
            created_at=now,
        )
        for chunk in chunks
    ]


# ---------------------------------------------------------------------------
# Semantic Vector Mapping (PGVector Support)
# ---------------------------------------------------------------------------

# Mappings logic continues using imports from embeddings module


def map_chunks_semantically(
    topics: list[SyllabusTopic],
    chunks: list[ContentChunk],
    sources: list[Source],
    topic_filter_ids: set[str] | None = None,
    similarity_threshold: float = 0.30,
) -> tuple[list[SourceToTopicMapping], list[ContentChunk]]:
    """Compute embeddings for un-embedded chunks, and map chunks to topics using cosine similarity.

    Returns:
        (mappings, updated_chunks)
    """
    import datetime

    # 1. First, compute embeddings for any chunks that don't have them
    unembedded_chunks = [ck for ck in chunks if not ck.embedding or len(ck.embedding) == 0]
    updated_chunks = []
    if unembedded_chunks:
        print(f"Generating local embeddings for {len(unembedded_chunks)} new chunk(s)...")
        texts = [ck.chunk_text for ck in unembedded_chunks]
        embeddings = compute_embeddings(texts)
        for ck, emb in zip(unembedded_chunks, embeddings):
            ck.embedding = emb
            updated_chunks.append(ck)

    # 2. Filter topics if a filter is active
    target_topics = [t for t in topics if t.id in topic_filter_ids] if topic_filter_ids else topics

    if not target_topics:
        return [], updated_chunks

    # 3. Compute embeddings for target topics search representations
    topic_texts = []
    for t in target_topics:
        repr_text = t.topic_name
        if t.keywords:
            repr_text += " " + " ".join(t.keywords)
        topic_texts.append(repr_text)

    print(f"Computing embeddings for {len(target_topics)} topic representations...")
    topic_embeddings = compute_embeddings(topic_texts)
    topic_emb_by_id = {t.id: emb for t, emb in zip(target_topics, topic_embeddings)}

    # 4. Perform cosine similarity search and map chunks
    now = datetime.datetime.now(datetime.UTC)
    mappings: list[SourceToTopicMapping] = []

    source_by_id = {s.id: s for s in sources}

    for ck in chunks:
        source = source_by_id.get(ck.source_id)
        if not source:
            continue

        # Scope matching by source topic links if defined
        allowed_topics = target_topics
        if source.topic_ids:
            allowed_ids = set(source.topic_ids)
            allowed_topics = [t for t in target_topics if t.id in allowed_ids]

        if not allowed_topics:
            continue

        for topic in allowed_topics:
            t_emb = topic_emb_by_id[topic.id]
            if ck.embedding:
                score = cosine_similarity(ck.embedding, t_emb)
                if score >= similarity_threshold:
                    mappings.append(
                        SourceToTopicMapping(
                            id=new_id(),
                            source_id=ck.source_id,
                            chunk_id=ck.id,
                            topic_id=topic.id,
                            vector_score=score,
                            reranker_score=None,
                            is_active=True,
                            created_at=now,
                        )
                    )

    return mappings, updated_chunks
