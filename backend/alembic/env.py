"""Alembic environment.

The connection URL comes from app.config (i.e. from DATABASE_URL) rather than
from alembic.ini, so migrations always target the same database the application
does — including Neon in production, where the URL is only ever an env var.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection, create_engine

from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares against this. Every model module must be imported by
# app/models/__init__.py or Alembic will not see its table and will happily
# generate a migration that drops it.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — used to review a migration."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # catch a column type change, not just added/dropped columns
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        _run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
