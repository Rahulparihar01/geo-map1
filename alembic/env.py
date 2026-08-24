from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load app settings
from app.core.config import settings

# Import all models so Alembic detects them
from app.database.base import Base
from app.models import user 
from app.models import user_location  # noqa: F401
from app.models import location_history  # noqa: F401
from app.models import search_query  # noqa: F401
from app.models import search_result  # noqa: F401
from app.models import place_detail  # noqa: F401
from app.models import place_knowledge_sync  # noqa: F401
from app.models import place_question  # noqa: F401
from app.models import place_answer_log  # noqa: F401
from app.models import ai_chat_session  # noqa: F401
from app.models import ai_chat_message  # noqa: F401
from app.models import place_qa_session  # noqa: F401
from app.models import place_qa_message  # noqa: F401
from app.models import place_unlock  # noqa: F401
from app.models import place_category_price  # noqa: F401
from app.models import user_saved_place  # noqa: F401
from app.models import place_visit_log  # noqa: F401
from app.models import payment_transaction  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DATABASE_URL from .env
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
