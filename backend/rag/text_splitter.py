from __future__ import annotations


def split_knowledge_text(
    content: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 80,
) -> list[str]:
    """Split plain text into deterministic, non-empty chunks for vector indexing."""
    cleaned = content.strip()
    if not cleaned:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between 0 and chunk_size - 1")

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        next_start = end - chunk_overlap
        if next_start <= start:
            next_start = start + 1
        if next_start >= len(cleaned):
            break
        start = next_start
    return chunks


__all__ = ["split_knowledge_text"]
