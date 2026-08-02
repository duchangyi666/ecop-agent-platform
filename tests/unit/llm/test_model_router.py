from __future__ import annotations

import pytest

from backend.llm.router import ModelRoute, ModelRouter, ModelTask


def test_model_router_resolves_configured_route() -> None:
    router = ModelRouter(
        {
            ModelTask.CUSTOMER_SERVICE: ModelRoute(
                task=ModelTask.CUSTOMER_SERVICE,
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        }
    )

    route = router.resolve(ModelTask.CUSTOMER_SERVICE)

    assert route.provider == "deepseek"
    assert route.model == "deepseek-v4-flash"


def test_model_router_rejects_missing_task() -> None:
    router = ModelRouter({})

    with pytest.raises(ValueError):
        router.resolve(ModelTask.BILLING)
