from __future__ import annotations

import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from scripts import evaluate_retrieval


@pytest.mark.asyncio
async def test_evaluation_does_not_drop_an_existing_collection(monkeypatch):
    class ExistingCollectionClient:
        def __init__(self, **kwargs):
            self.dropped = []
            self.closed = False
            clients.append(self)

        def has_collection(self, name):
            return True

        def drop_collection(self, name):
            self.dropped.append(name)

        def close(self):
            self.closed = True

    async def documents(*args):
        return [object()], []

    async def cases(*args):
        return [{"query": "test", "relevant": set()}]

    clients = []
    monkeypatch.setitem(sys.modules, "pymilvus", SimpleNamespace(MilvusClient=ExistingCollectionClient))
    monkeypatch.setattr(evaluate_retrieval, "load_tenant_documents", documents)
    monkeypatch.setattr(evaluate_retrieval, "load_retrieval_cases", cases)
    monkeypatch.setattr(evaluate_retrieval, "MilvusKnowledgeVectorStore", lambda **kwargs: object())
    with pytest.raises(RuntimeError, match="already exists"):
        await evaluate_retrieval.evaluate(
            database_url="unused", tenant_id=UUID(int=1), model_path="unused",
            reranker_path=None, milvus_uri="unused", limit_cases=1, embedder=object(),
        )
    assert clients[0].dropped == []
    assert clients[0].closed
