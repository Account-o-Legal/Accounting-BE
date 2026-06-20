"""Alembic migration environment.

ponytail: every model module must be imported here (even though nothing
in this file uses them directly) so SQLModel.metadata is populated before
autogenerate runs. This is the single place that import list lives —
don't duplicate it elsewhere.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from app.core.config import settings

# Import every module's models so their tables register on SQLModel.metadata
import app.modules.auth.models  # noqa: F401
import app.modules.accounting_core.models  # noqa: F401
import app.modules.sales.models  # noqa: F401
import app.modules.purchases.models  # noqa: F401
import app.modules.banking.models  # noqa: F401
import app.modules.tax.models  # noqa: F401
import app.core.audit  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(config.get_section(config.config_ini_section, {}))
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
