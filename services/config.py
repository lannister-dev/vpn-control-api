from dataclasses import dataclass
from functools import lru_cache
from environs import Env


@dataclass
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    ssl: str
    url: str
    poolSize: int
    poolOverflowSize: int


@dataclass
class RedisConfig:
    broker_url: str
    assignments_cache_ttl: int
    assignment_lock_ttl: int


@dataclass
class DocsConfig:
    username: str
    password_hash: str


@dataclass
class AdminConfig:
    api_key_hash: str
    bootstrap_token_hash: str


@dataclass
class ProfilesVpnConfig:
    allow_empty_registry_on_startup: bool = False


@dataclass
class SubscriptionsConfig:
    require_hwid_default: bool = False
    max_devices_default: int = 5
    hwid_header: str = "x-hwid"


@dataclass
class Settings:
    database: DbConfig
    redis: RedisConfig
    admin: AdminConfig
    docs: DocsConfig
    profiles_vpn: ProfilesVpnConfig
    subscriptions: SubscriptionsConfig


@lru_cache
def get_settings() -> Settings:
    env = Env()
    env.read_env('.env')

    database = DbConfig(
        host=env.str("DB_HOST"),
        port=env.int("DB_PORT"),
        name=env.str("DB_NAME"),
        user=env.str("DB_USER"),
        password=env.str("DB_PASSWORD"),
        ssl=env.str("SSL_PATH"),
        url=f"postgresql+asyncpg://{env.str('DB_USER')}:{env.str('DB_PASSWORD')}@{env.str('DB_HOST')}:{env.str('DB_PORT')}/{env.str('DB_NAME')}",
        poolSize=env.int('DB_POOL_SIZE', default=50),
        poolOverflowSize=env.int('DB_POOL_OVERFLOW_SIZE', default=25)
    )

    redis = RedisConfig(
        broker_url=env.str("REDIS_BROKER_URL"),
        assignments_cache_ttl=env.int("REDIS_ASSIGNMENTS_CACHE_TTL", default=10),
        assignment_lock_ttl=env.int("REDIS_ASSIGNMENT_LOCK_TTL", default=30)
    )

    admin = AdminConfig(
        api_key_hash=env.str("ADMIN_API_KEY_HASH"),
        bootstrap_token_hash=env.str("BOOTSTRAP_TOKEN_HASH"),
    )

    docs = DocsConfig(
        username=env.str("DOCS_USERNAME", default="admin"),
        password_hash=env.str("DOCS_PASSWORD_HASH"),
    )

    profiles_vpn = ProfilesVpnConfig(
        allow_empty_registry_on_startup=env.bool("PROFILES_ALLOW_EMPTY_REGISTRY_ON_STARTUP")
    )

    subscriptions = SubscriptionsConfig(
        require_hwid_default=env.bool("SUBSCRIPTIONS_REQUIRE_HWID_DEFAULT", default=False),
        max_devices_default=env.int("SUBSCRIPTIONS_MAX_DEVICES_DEFAULT", default=5),
        hwid_header=env.str("SUBSCRIPTIONS_HWID_HEADER", default="x-hwid").lower(),
    )

    return Settings(
        database=database,
        redis=redis,
        admin=admin,
        docs=docs,
        profiles_vpn=profiles_vpn,
        subscriptions=subscriptions,
    )
