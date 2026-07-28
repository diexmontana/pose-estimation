"""Entorno de Alembic. Toma la URL de POSE_DB_URL y el metadata de los
modelos, de modo que --autogenerate detecte los cambios de esquema."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permitir importar el paquete backend
RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

from backend.db.models import Base  # noqa: E402

load_dotenv()

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    os.getenv("POSE_DB_URL", "postgresql+psycopg://pose:pose@localhost:5432/pose_estimation"),
)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
