import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from services.config import get_settings
from shared.database.base_model import Base

db = get_settings().database
sys.path.append(os.path.join(sys.path[0], 'src'))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
section = config.config_ini_section

config.set_section_option(section, "DB_HOST", db.host)
config.set_section_option(section, "DB_PORT", str(db.port))
config.set_section_option(section, "DB_NAME", db.name)
config.set_section_option(section, "DB_USER", db.user)
config.set_section_option(section, "DB_PASSWORD", db.password)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support

from services.artifacts.models import ProfileArtifact
from services.auth.admin.models import AdminAuditEvent, AdminSession, AdminUser
from services.billing.models import BalanceTransaction, PaymentOrder
from services.nodes.agent.model import (
    NodeTransportEventLog,
    NodeTransportOutbox,
    NodeTransportState,
)
from services.nodes.models import NodeAgentIdentity, NodeAgentState, VpnNode
from services.placements.model import UserPlacement
from services.probe.model import ProbeSignal
from services.routes.model import Route, TransportProfile
from services.traffic.nodes.model import NodeTrafficUsage
from services.traffic.users.model import TrafficUsage
from services.users.models import User
from services.vpn.keys.models import KeyAssignment, VpnKey
from services.vpn.subscriptions.model import Subscription
from services.zones.models import Zone

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
