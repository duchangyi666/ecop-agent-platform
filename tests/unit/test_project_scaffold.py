from __future__ import annotations

from pathlib import Path
import tomllib


def test_pyproject_declares_valid_pytest_options() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    pytest_options = data["tool"]["pytest"]["ini_options"]

    assert pytest_options["pythonpath"] == ["."]
    assert pytest_options["asyncio_mode"] == "auto"
    assert pytest_options["asyncio_default_fixture_loop_scope"] == "function"


def test_pyproject_declares_authoritative_database_dependencies() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dependencies = set(data["project"]["dependencies"])

    assert "SQLAlchemy==2.0.36" in dependencies
    assert "asyncpg==0.30.0" in dependencies
    assert "pydantic==2.11.4" in dependencies
    assert "pytest==8.3.4" in dependencies
    assert "pytest-asyncio==0.24.0" in dependencies
    assert "alembic==1.18.5" in dependencies
