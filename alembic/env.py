"""Alembic environment configuration for testmcpy."""

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context
from testmcpy.models import Base

# Alembic Config object
config = context.config

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate support
target_metadata = Base.metadata

# Dynamically set the database URL if not already configured
# Resolution order: existing config > TESTMCPY_DB_PATH env var > default (.testmcpy/storage.db)
if not config.get_main_option("sqlalchemy.url"):
    db_path_env = os.environ.get("TESTMCPY_DB_PATH")
    if db_path_env:
        db_path = Path(db_path_env)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        db_dir = Path.cwd() / ".testmcpy"
        db_dir.mkdir(exist_ok=True)
        db_path = db_dir / "storage.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
