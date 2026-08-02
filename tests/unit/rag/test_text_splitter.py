from __future__ import annotations

from backend.rag.text_splitter import split_knowledge_text


def test_split_knowledge_text_produces_overlapping_chunks() -> None:
    content = "第一段退款政策内容。" + "重复扣费可以在二十四小时内申请退款。" * 8

    chunks = split_knowledge_text(content, chunk_size=60, chunk_overlap=10)

    assert len(chunks) > 1
    assert all(chunks)


def test_split_knowledge_text_keeps_short_content_as_single_chunk() -> None:
    chunks = split_knowledge_text("短政策", chunk_size=800, chunk_overlap=80)

    assert chunks == ["短政策"]


def test_split_knowledge_text_rejects_invalid_overlap() -> None:
    try:
        split_knowledge_text("内容", chunk_size=10, chunk_overlap=10)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for invalid overlap")
