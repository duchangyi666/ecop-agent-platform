from __future__ import annotations

from pathlib import Path


def test_readme_documents_api_entrypoint_and_dev_context() -> None:
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "backend.main:app" in readme
    assert "X-Tenant-Id" in readme
    assert "本地退款申请" in readme
    assert "input_security_guard" in readme
    assert "业务范围 Guard" in readme
