"""CLI entry point for business-consistent synthetic data generation.

Usage:
    python scripts/generate_synthetic_data.py --scale small [--seed 42]
    python scripts/generate_synthetic_data.py --scale full --reset

The database schema must already exist (run `alembic upgrade head` first).
`--reset` truncates all business tables before seeding.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings

from scripts.synthetic_data.config import SCALE_PROFILES
from scripts.synthetic_data.seed import generate_all, reset_database


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate business-consistent CloudDesk synthetic data.")
    parser.add_argument(
        "--scale",
        choices=sorted(SCALE_PROFILES),
        default="small",
        help="small = quick validation profile; full = spec-scale profile",
    )
    parser.add_argument("--seed", type=int, default=42, help="deterministic RNG seed")
    parser.add_argument("--tenant-prefix", default="synthetic", help="tenant slug prefix")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    parser.add_argument("--reset", action="store_true", help="truncate all business tables first")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    profile = SCALE_PROFILES[args.scale]

    async def _run() -> None:
        if args.reset:
            print("resetting business tables...")
            await reset_database(args.database_url)
        counters = await generate_all(
            database_url=args.database_url,
            profile=profile,
            seed=args.seed,
            tenant_prefix=args.tenant_prefix,
        )
        print("synthetic data generated:")
        for key, value in counters.items():
            print(f"  {key}: {value}")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
