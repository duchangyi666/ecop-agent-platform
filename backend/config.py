from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str = Field(
        default="postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations",
    )


@lru_cache(maxsize=1)
def get_settings() -> DatabaseSettings:
    return DatabaseSettings(database_url=os.getenv("DATABASE_URL", DatabaseSettings.model_fields["database_url"].default))
