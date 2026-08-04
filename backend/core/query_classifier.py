"""Local intent classifier (process-in-memory, no extra download).

Mirrors EduAgent's MiniLM intent layer but reuses the already-loaded BGE-M3
embedder: each domain is represented by labeled prototype sentences and a query
is routed to the nearest prototype by cosine similarity. When the local embedder
is unavailable (offline deterministic embedder) the confidence is low so callers
fall back to the LLM router.
"""

from __future__ import annotations

import math
from functools import lru_cache

from backend.rag.config import get_rag_settings

# Domain -> prototype utterances. Keep short and discriminative.
_INTENT_PROTOTYPES: dict[str, list[str]] = {
    "route_billing": [
        "我被重复扣费了要退款",
        "申请退款",
        "账单金额不对",
        "支付失败",
        "查询我的扣费记录",
    ],
    "route_ticket": [
        "帮我建一个工单",
        "我的工单处理到哪了",
        "提交一个故障工单",
    ],
    "route_approval": [
        "我的审批通过了吗",
        "退款审批进度",
    ],
    "route_knowledge": [
        "退款政策是什么",
        "SLA 支持等级怎么规定",
        "如何修改发票信息",
    ],
    "route_customer": [
        "你好",
        "谢谢",
        "你能做什么",
    ],
}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class QueryClassifier:
    """Embedding-prototype intent classifier over the local BGE-M3 embedder."""

    def __init__(self) -> None:
        self._embedder = None
        self._proto_vectors: list[tuple[str, list[float]]] = []
        self._real = bool(get_rag_settings().bge_m3_model_path)

    def _ensure(self) -> None:
        if self._embedder is not None:
            return
        from backend.rag.embedder import create_embedder

        self._embedder = create_embedder(get_rag_settings())
        texts = [t for protos in _INTENT_PROTOTYPES.values() for t in protos]
        vectors = self._embedder.embed(texts)
        idx = 0
        for domain, protos in _INTENT_PROTOTYPES.items():
            for _ in protos:
                self._proto_vectors.append((domain, vectors[idx]))
                idx += 1

    def classify(self, text: str) -> tuple[str, float]:
        """Return (domain, confidence). Low confidence -> caller uses LLM route."""
        if not self._real:
            return "route_customer", 0.0
        try:
            self._ensure()
            query_vec = self._embedder.embed([text])[0]
        except Exception:  # noqa: BLE001 - degrade to low confidence
            return "route_customer", 0.0
        best_domain = "route_customer"
        best_score = -1.0
        for domain, vec in self._proto_vectors:
            score = _cosine(query_vec, vec)
            if score > best_score:
                best_score = score
                best_domain = domain
        return best_domain, best_score


@lru_cache(maxsize=1)
def get_query_classifier() -> QueryClassifier:
    return QueryClassifier()


# Only trust the local classifier above this similarity; below -> LLM router.
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.6


__all__ = [
    "CLASSIFIER_CONFIDENCE_THRESHOLD",
    "QueryClassifier",
    "get_query_classifier",
]
