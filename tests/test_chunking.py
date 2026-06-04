from edu_curator.chunking import word_chunks
from edu_curator.schemas import NormalizedDocument


def test_word_chunks_basic():
    text = " ".join([f"word{i}" for i in range(100)])
    doc = NormalizedDocument(
        source_id="src_1",
        title="Test Doc",
        content=text,
        metadata={"char_count": len(text), "word_count": 100},
    )

    # Chunk size 40, overlap 10
    chunks = word_chunks(doc, chunk_size=40, overlap=10)

    assert len(chunks) == 3
    assert chunks[0].metadata["word_start"] == 0
    assert chunks[0].metadata["word_end"] == 40

    assert chunks[1].metadata["word_start"] == 30  # overlap of 10
    assert chunks[1].metadata["word_end"] == 70

    assert chunks[2].metadata["word_start"] == 60  # overlap of 10
    assert chunks[2].metadata["word_end"] == 100


def test_word_chunks_smaller_than_chunk_size():
    text = " ".join([f"word{i}" for i in range(20)])
    doc = NormalizedDocument(
        source_id="src_1",
        title="Test Doc",
        content=text,
        metadata={"char_count": len(text), "word_count": 20},
    )

    chunks = word_chunks(doc, chunk_size=40, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].metadata["word_start"] == 0
    assert chunks[0].metadata["word_end"] == 20
