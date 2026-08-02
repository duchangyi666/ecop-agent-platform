from __future__ import annotations

from pathlib import Path


def test_readme_documents_api_entrypoint_and_dev_context() -> None:
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "backend.main:app" in readme
    assert "X-Tenant-Id" in readme
    assert "POST /api/v1/customer-consultations" in readme
    assert "customer.consult" in readme
    assert "本地退款申请" in readme
    assert "input_security_guard" in readme
    assert "业务范围 Guard" in readme


def test_readme_documents_model_gateway_secret_and_offline_boundaries() -> None:
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY" in readme
    assert "只允许从运行时环境变量读取" in readme
    assert "create_model_gateway()" in readme
    assert "FakeModelGateway" in readme
    assert "自动回归不执行真实 API 冒烟请求" in readme
    assert "不保存 Key、完整 Prompt 或模型响应原文" in readme
    assert "RAG 向量知识库" in readme
    assert "MILVUS_URI" in readme
    assert "knowledge.ingest" in readme
    assert "knowledge_evidence_count" in readme
    assert "customer-consultations/stream" in readme
    assert "JWT_SECRET" in readme
    assert "正式 OAuth/SSO" in readme
    assert "本地前端控制台" in readme
    assert "evaluations/run" in readme
    assert "Recall@K" in readme
    assert "RERANKER_MODEL_PATH" in readme
    assert "memory_candidate_count" in readme
    assert "长期记忆" in readme
    assert "MODEL_ROUTE_MODEL" in readme
    assert "PromptRegistry" in readme
