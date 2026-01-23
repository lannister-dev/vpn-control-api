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
    host: str
    port: int
    password: str
    broker_url: str


@dataclass
class Settings:
    database: DbConfig
    redis: RedisConfig


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
        host=env.str("REDIS_HOST"),
        port=env.int("REDIS_PORT"),
        password=env.str("REDIS_PASSWORD"),
        broker_url=env.str("REDIS_BROKER_URL"),
    )

    return Settings(database=database, redis=redis)
