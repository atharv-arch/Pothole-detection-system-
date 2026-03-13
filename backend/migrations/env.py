"""APIS v5.0 — Alembic migration env"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Load alembic config
config = context.config

if config.config_file_name is not None:
    # Use python-dotenv to load environment variables explicitly
    from dotenv import load_dotenv
    import os
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8")
    # Load alembic config explicitly with utf-8 to avoid charmap errors on Windows
    import configparser
    fileConfig(config.config_file_name, defaults={'here': os.path.dirname(config.config_file_name)}, disable_existing_loggers=False, encoding='utf-8')

# Import all models so Alembic can see them
from app.models import Base
target_metadata = Base.metadata

# Override URL from env if available
db_url = os.getenv("DATABASE_SYNC_URL") or os.getenv("SYNC_DATABASE_URL")
if not db_url:
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("+aiosqlite", "")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline():
    """Run migrations in 'offline' mode — generates SQL without DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode — connects to DB and applies."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
