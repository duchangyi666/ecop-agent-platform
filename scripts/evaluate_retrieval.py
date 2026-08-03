"""Offline retrieval evaluation with rerank-before/after comparison.

Loads one tenant's knowledge documents into an isolated Milvus collection,
runs its retrieval evaluation cases, then reports Recall@K, Precision@K,
MRR and NDCG for:

  * dense-only retrieval
  * dense + sparse hybrid fusion (RRF)
  * hybrid fused candidates re-ranked by a real BGE Cross-Encoder

Usage:
    python scripts/evaluate_retrieval.py --tenant-slug synthetic-1
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import get_settings
from backend.database.models.governance import Document, EvaluationCase, EvaluationDataset
from backend.database.models.knowledge import KnowledgeChunk
from backend.rag.bge_hybrid import BgeM3HybridEmbedder
from backend.rag.vector_store import MilvusKnowledgeVectorStore


# ---------------------------------------------------------------------------
# Ranking metrics
# ---------------------------------------------------------------------------


def recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(relevant.intersection(retrieved[:k])) / len(relevant)


def precision_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if k == 0:
        return 0.0
    return len(relevant.intersection(retrieved[:k])) / k


def mrr(relevant: set[str], retrieved: list[str]) -> float:
    for rank, document_id in enumerate(retrieved, start=1):
        if document_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    import math

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, document_id in enumerate(retrieved[:k], start=1)
        if document_id in relevant
    )
    idcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, min(len(relevant), k) + 1)
    )
    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def load_tenant_documents(database_url: str, tenant_id: UUID) -> tuple[list[Document], list[KnowledgeChunk]]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            documents = list(
                (
                    await session.scalars(
                        select(Document).where(
                            Document.tenant_id == tenant_id,
                            Document.deleted_at.is_(None),
                        )
                    )
                ).all()
            )
            chunks = list(
                (
                    await session.scalars(
                        select(KnowledgeChunk).where(KnowledgeChunk.tenant_id == tenant_id)
                    )
                ).all()
            )
            return documents, chunks
    finally:
        await engine.dispose()


async def load_retrieval_cases(database_url: str, tenant_id: UUID, limit: int) -> list[dict]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(EvaluationCase.input_summary, EvaluationCase.expected_summary)
                    .join(
                        EvaluationDataset,
                        EvaluationDataset.id == EvaluationCase.dataset_id,
                    )
                    .where(
                        EvaluationDataset.dataset_code == "retrieval",
                        EvaluationDataset.tenant_id == tenant_id,
                        EvaluationCase.tenant_id == tenant_id,
                    )
                    .limit(limit)
                )
            ).all()
            cases: list[dict] = []
            for row in rows:
                input_summary, expected_summary = row
                expected = expected_summary or {}
                cases.append(
                    {
                        "query": input_summary,
                        "relevant": set(expected.get("document_ids", [])),
                    }
                )
            return cases
    finally:
        await engine.dispose()


def _as_document_ids(hits: list) -> list[str]:
    """Return document ids in first-appearance order (dedupe chunk hits)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for hit in hits:
        document_id = str(hit.document_id)
        if document_id not in seen:
            seen.add(document_id)
            ordered.append(document_id)
    return ordered


def _aggregate(scores: list[dict]) -> dict[str, float]:
    combined: dict[str, list[float]] = defaultdict(list)
    for score in scores:
        for key, value in score.items():
            combined[key].append(value)
    return {key: sum(values) / len(values) for key, values in combined.items()}


async def evaluate(
    *,
    database_url: str,
    tenant_id: UUID,
    model_path: str,
    reranker_path: str | None,
    milvus_uri: str,
    limit_cases: int,
    embedder: BgeM3HybridEmbedder | None = None,
    reranker=None,
) -> dict:
    documents, chunks = await load_tenant_documents(database_url, tenant_id)
    cases = await load_retrieval_cases(database_url, tenant_id, limit_cases)
    if not documents:
        raise RuntimeError("no documents found for tenant")
    if not cases:
        raise RuntimeError("no retrieval evaluation cases found for tenant")

    from pymilvus import MilvusClient

    collection = f"ecop_eval_retrieval_{str(tenant_id)[:8]}"
    client = MilvusClient(uri=milvus_uri, timeout=30)
    if client.has_collection(collection):
        client.drop_collection(collection)

    hybrid_embedder = embedder or BgeM3HybridEmbedder(model_path)
    hybrid_store = MilvusKnowledgeVectorStore(
        uri=milvus_uri,
        collection_name=collection,
        embedder=hybrid_embedder,
        sparse_embedder=hybrid_embedder,
    )
    dense_store = MilvusKnowledgeVectorStore(
        uri=milvus_uri,
        collection_name=collection,
        embedder=hybrid_embedder,
        sparse_embedder=None,
    )

    # Cross-Encoder reranker for the rerank pass (shared across tenants).
    if reranker is None and reranker_path:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(reranker_path)
        print(f"loaded CrossEncoder reranker from {reranker_path}")

    try:
        document_by_id = {str(document.id): document for document in documents}
        for document in documents:
            document_chunks = [
                chunk
                for chunk in chunks
                if chunk.document_id == document.id and chunk.content.strip()
            ]
            await hybrid_store.upsert_document_chunks(
                tenant_id=tenant_id,
                document=document,
                chunks=document_chunks,
            )
        print(f"indexed {len(documents)} documents / {len(chunks)} chunks")

        per_case: list[dict] = []
        for index, case in enumerate(cases, start=1):
            relevant = case["relevant"]
            query = case["query"]
            dense_hits = await dense_store.search(tenant_id=tenant_id, query=query, limit=30)
            hybrid_hits = await hybrid_store.search(tenant_id=tenant_id, query=query, limit=30)

            hybrid_ranked = _as_document_ids(hybrid_hits)
            dense_ranked = _as_document_ids(dense_hits)

            reranked_order: list[str] = hybrid_ranked
            if reranker is not None:
                pairs = [
                    (query, hit.content_snippet or hit.title)
                    for hit in hybrid_hits
                ]
                scores = reranker.predict(pairs)
                scored = sorted(
                    zip(hybrid_hits, [float(score) for score in scores]),
                    key=lambda pair: pair[1],
                    reverse=True,
                )
                reranked_order = _as_document_ids([hit for hit, _ in scored])

            per_case.append(
                {
                    "dense": {
                        "recall@5": recall_at_k(relevant, dense_ranked, 5),
                        "recall@10": recall_at_k(relevant, dense_ranked, 10),
                        "precision@5": precision_at_k(relevant, dense_ranked, 5),
                        "mrr": mrr(relevant, dense_ranked),
                        "ndcg@10": ndcg_at_k(relevant, dense_ranked, 10),
                    },
                    "hybrid": {
                        "recall@5": recall_at_k(relevant, hybrid_ranked, 5),
                        "recall@10": recall_at_k(relevant, hybrid_ranked, 10),
                        "precision@5": precision_at_k(relevant, hybrid_ranked, 5),
                        "mrr": mrr(relevant, hybrid_ranked),
                        "ndcg@10": ndcg_at_k(relevant, hybrid_ranked, 10),
                    },
                    "reranked": {
                        "recall@5": recall_at_k(relevant, reranked_order, 5),
                        "recall@10": recall_at_k(relevant, reranked_order, 10),
                        "precision@5": precision_at_k(relevant, reranked_order, 5),
                        "mrr": mrr(relevant, reranked_order),
                        "ndcg@10": ndcg_at_k(relevant, reranked_order, 10),
                    },
                }
            )
            if index % 10 == 0:
                print(f"  evaluated {index}/{len(cases)} cases")

        return {
            "cases": len(cases),
            "dense": _aggregate([case["dense"] for case in per_case]),
            "hybrid": _aggregate([case["hybrid"] for case in per_case]),
            "reranked": _aggregate([case["reranked"] for case in per_case]),
            "reranker_enabled": reranker is not None,
            "_per_case": per_case,
        }
    finally:
        await hybrid_store.close()
        await dense_store.close()
        client.drop_collection(collection)


def _print_report(result: dict) -> None:
    labels = ("dense", "hybrid", "reranked")
    metrics = ("recall@5", "recall@10", "precision@5", "mrr", "ndcg@10")
    header = "metric        | " + " | ".join(f"{label:>12}" for label in labels)
    print("\nretrieval evaluation summary")
    print(f"cases: {result['cases']}  reranker_enabled: {result['reranker_enabled']}")
    if result.get("tenants"):
        print("per-tenant (hybrid mrr / reranked mrr):")
        for summary in result["tenants"]:
            print(
                f"  {summary['tenant_id'][:8]}  cases={summary['cases']}  "
                f"hybrid={summary['hybrid_mrr']:.3f}  reranked={summary['reranked_mrr']:.3f}"
            )
    print(header)
    print("-" * len(header))
    for metric in metrics:
        values = [f"{result[label][metric]:>12.4f}" for label in labels]
        print(f"{metric:<13} | " + " | ".join(values))
    print()
    if result["reranker_enabled"]:
        for metric in ("recall@10", "mrr", "ndcg@10"):
            delta = result["reranked"][metric] - result["hybrid"][metric]
            print(f"rerank delta {metric}: {delta:+.4f}")


def _parse_args() -> argparse.Namespace:
    default_model = PROJECT_ROOT / "models" / "bge-m3"
    default_reranker = PROJECT_ROOT / "models" / "bge-reranker-base"
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation with rerank comparison.")
    parser.add_argument(
        "--tenant-ids",
        nargs="+",
        type=UUID,
        required=True,
        help="one or more tenant UUIDs to evaluate (results are aggregated)",
    )
    parser.add_argument("--limit-cases", type=int, default=40)
    parser.add_argument("--model-path", default=os.getenv("BGE_M3_MODEL_PATH", str(default_model)))
    parser.add_argument(
        "--reranker-path",
        default=os.getenv("RERANKER_MODEL_PATH", str(default_reranker)),
        help="BGE cross-encoder model directory; omit to skip rerank pass",
    )
    parser.add_argument("--milvus-uri", default=os.getenv("MILVUS_URI", "http://localhost:19531"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    return parser.parse_args()


async def _evaluate_tenants(
    *,
    database_url: str,
    tenant_ids: list[UUID],
    model_path: str,
    reranker_path: str | None,
    milvus_uri: str,
    limit_cases: int,
) -> dict:
    # Models are expensive to load: create once and reuse for every tenant.
    embedder = BgeM3HybridEmbedder(model_path)
    reranker = None
    if reranker_path:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(reranker_path)
        print(f"loaded CrossEncoder reranker from {reranker_path}")

    all_per_case: list[dict] = []
    tenant_summaries: list[dict] = []
    for tenant_id in tenant_ids:
        result = await evaluate(
            database_url=database_url,
            tenant_id=tenant_id,
            model_path=model_path,
            reranker_path=reranker_path,
            milvus_uri=milvus_uri,
            limit_cases=limit_cases,
            embedder=embedder,
            reranker=reranker,
        )
        tenant_summaries.append(
            {
                "tenant_id": str(tenant_id),
                "cases": result["cases"],
                "hybrid_mrr": result["hybrid"]["mrr"],
                "reranked_mrr": result["reranked"]["mrr"],
            }
        )
        all_per_case.extend(
            [
                {"dense": case["dense"], "hybrid": case["hybrid"], "reranked": case["reranked"]}
                for case in result["_per_case"]
            ]
        )
    return {
        "cases": len(all_per_case),
        "dense": _aggregate([case["dense"] for case in all_per_case]),
        "hybrid": _aggregate([case["hybrid"] for case in all_per_case]),
        "reranked": _aggregate([case["reranked"] for case in all_per_case]),
        "reranker_enabled": reranker_path is not None,
        "tenants": tenant_summaries,
    }


if __name__ == "__main__":
    args = _parse_args()
    result = asyncio.run(
        _evaluate_tenants(
            database_url=args.database_url,
            tenant_ids=args.tenant_ids,
            model_path=args.model_path,
            reranker_path=args.reranker_path,
            milvus_uri=args.milvus_uri,
            limit_cases=args.limit_cases,
        )
    )
    _print_report(result)
