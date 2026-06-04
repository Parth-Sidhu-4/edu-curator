from __future__ import annotations

import re
from datetime import UTC, datetime

from edu_curator.ids import new_id
from edu_curator.schemas import ContentChunk, NormalizedDocument


def word_chunks(
    document: NormalizedDocument,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[ContentChunk]:
    words = re.findall(r"\S+", document.content)
    if not words:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[ContentChunk] = []
    start = 0
    chunk_number = 1
    now = datetime.now(UTC)
    while start < len(words):
        end = min(start + chunk_size, len(words))
        text = " ".join(words[start:end])
        chunks.append(
            ContentChunk(
                id=new_id(),
                source_id=document.source_id,
                chunk_text=text,
                chunk_number=chunk_number,
                created_at=now,
                metadata={
                    "title": document.title,
                    "word_start": start,
                    "word_end": end,
                    "chunk_size_words": chunk_size,
                    "overlap_words": overlap,
                },
            )
        )
        if end == len(words):
            break
        start = end - overlap
        chunk_number += 1

    return chunks
