from __future__ import with_statement

import os

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

from src.backend.infra.db.models import Base
import src.backend.infra.db.models_notes_jobs  # register mapped tables
import src.backend.infra.db.models_ehr  # register EHR outbox tables

config = context.config
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section),
                                    prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if (
            connection.dialect.name == "postgresql"
            and "alembic_version" not in inspect(connection).get_table_names()
        ):
            connection.execute(text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(64) NOT NULL PRIMARY KEY)"
            ))
            connection.commit()
        elif (
            connection.dialect.name == "postgresql"
            and "alembic_version" in inspect(connection).get_table_names()
        ):
            # Several historical revision identifiers exceed Alembic's old
            # VARCHAR(32) default. Widen metadata before Alembic updates it.
            connection.execute(text(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE VARCHAR(64)"
            ))
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()