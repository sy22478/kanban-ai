"""Insert the single development user.

Deliberately not part of migration 0001: migrations are schema history and run in
every environment, so a development row baked into them would follow us to
deployment. This script is idempotent and is dropped in phase 2, when real
registration replaces it.
"""

import asyncio

from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal, engine
from app.models import User

SEED_EMAIL = "sonu@example.com"


async def main() -> None:
    async with SessionLocal() as session:
        await session.execute(
            insert(User).values(email=SEED_EMAIL).on_conflict_do_nothing(
                index_elements=["email"]
            )
        )
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
