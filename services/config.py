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
    poolTimeoutSec: int


@dataclass
class RedisConfig:
    broker_url: str
    assignments_cache_ttl: int
    assignment_lock_ttl: int


@dataclass
class NatsConfig:
    enabled: bool = False
    server: str = "nats://localhost:4222"
    name: str = "vpn-control-api"
    users_traffic_subject: str = "users.traffic"
    users_traffic_queue: str = "vpn-control-api-users-traffic"
    reconnect_time_wait: int = 2
    max_reconnect_attempts: int = -1


@dataclass
class DocsConfig:
    username: str
    password_hash: str


@dataclass
class AdminConfig:
    api_key_hash: str
    connect_api_key_hash: str
    bootstrap_token_hash: str
    probe_token_hash: str


@dataclass
class ProfilesVpnConfig:
    allow_empty_registry_on_startup: bool = False


@dataclass
class SubscriptionsConfig:
    require_hwid_default: bool = False
    max_devices_default: int = 5
    hwid_header: str = "x-hwid"
    smart_route_max_count: int = 6
    response_cache_ttl_sec: int = 15
    response_max_payload_bytes: int = 32768
    public_base_url: str = ""
    happ_profile_title: str = "VPN"
    happ_profile_update_interval_hours: int = 24
    happ_support_url: str = ""
    happ_profile_web_page_url: str = ""
    happ_provider_id: str = ""
    happ_routing: str = ""


@dataclass
class NodeAgentConfig:
    sync_report_debounce_sec: int = 10
    auth_token_rotation_grace_sec: int = 300
    bootstrap_allow_create: bool = True
    heartbeat_unhealthy_drain_threshold: int = 2
    heartbeat_healthy_undrain_threshold: int = 3
    stale_after_sec: int = 90
    auto_heal_enabled: bool = False
    auto_heal_tick_sec: int = 60
    auto_heal_max_nodes: int = 20
    auto_undrain_enabled: bool = False


@dataclass
class AlertsConfig:
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_sec: int = 5


@dataclass
class ProbeConfig:
    target_port: int = 443
    retention_days: int = 30
    auto_route_health_enabled: bool = True
    route_block_cooldown_hours: int = 6
    auto_drain_migrate_enabled: bool = False
    auto_drain_tick_sec: int = 120
    auto_drain_source: str | None = None
    auto_drain_require_recent_failure: bool = True
    auto_drain_max_probe_age_sec: int = 600
    auto_drain_min_consecutive_failures: int = 2
    auto_drain_include_already_draining: bool = False
    auto_drain_max_nodes: int = 20
    auto_drain_target_backend_id: str | None = None
    auto_drain_last_migration_reason: str = "probe_auto_failure"


@dataclass
class RoutesConfig:
    warmup_tick_sec: int = 300
    connect_refresh_interval_sec: int = 60
    connect_max_cache_age_sec: int = 300
    connect_backoff_steps_sec: tuple[int, ...] = (2, 5, 10, 30, 60)
    connect_telemetry_debounce_sec: int = 10
    connect_telemetry_failure_window_sec: int = 300
    connect_telemetry_degraded_threshold: int = 2
    connect_telemetry_block_threshold: int = 3
    connect_telemetry_block_cooldown_hours: int = 6


@dataclass
class EdgeConfig:
    public_domain: str = ""


@dataclass
class TrafficConfig:
    cleanup_enabled: bool = False
    cleanup_tick_sec: int = 3600
    history_retention_days: int = 14


@dataclass
class Settings:
    database: DbConfig
    redis: RedisConfig
    nats: NatsConfig
    admin: AdminConfig
    docs: DocsConfig
    profiles_vpn: ProfilesVpnConfig
    subscriptions: SubscriptionsConfig
    node_agent: NodeAgentConfig
    alerts: AlertsConfig
    probe: ProbeConfig
    routes: RoutesConfig
    edge: EdgeConfig
    traffic: TrafficConfig


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
        poolSize=env.int('DB_POOL_SIZE', default=20),
        poolOverflowSize=env.int('DB_POOL_OVERFLOW_SIZE', default=10),
        poolTimeoutSec=env.int('DB_POOL_TIMEOUT_SEC', default=30),
    )

    redis = RedisConfig(
        broker_url=env.str("REDIS_BROKER_URL"),
        assignments_cache_ttl=env.int("REDIS_ASSIGNMENTS_CACHE_TTL", default=10),
        assignment_lock_ttl=env.int("REDIS_ASSIGNMENT_LOCK_TTL", default=30)
    )
    nats = NatsConfig(
        enabled=env.bool("NATS_ENABLED", default=False),
        server=env.str("NATS_SERVER", default="nats://localhost:4222"),
        name=env.str("NATS_NAME", default="vpn-control-api"),
        users_traffic_subject=env.str("NATS_USERS_TRAFFIC_SUBJECT", default="users.traffic"),
        users_traffic_queue=env.str("NATS_USERS_TRAFFIC_QUEUE", default="vpn-control-api-users-traffic"),
        reconnect_time_wait=env.int("NATS_RECONNECT_TIME_WAIT", default=2),
        max_reconnect_attempts=env.int("NATS_RECONNECT_ATTEMPTS", default=-1),
    )

    admin = AdminConfig(
        api_key_hash=env.str("ADMIN_API_KEY_HASH"),
        connect_api_key_hash=env.str("CONNECT_API_KEY_HASH", default=env.str("ADMIN_API_KEY_HASH")),
        bootstrap_token_hash=env.str("BOOTSTRAP_TOKEN_HASH"),
        probe_token_hash= env.str("PROBE_TOKEN_HASH"),
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
        hwid_header=env.str("SUBSCRIPTIONS_HWID_HEADER", default="x-hwid"),
        smart_route_max_count=env.int("SUBSCRIPTIONS_SMART_ROUTE_MAX_COUNT", default=6),
        response_cache_ttl_sec=env.int("SUBSCRIPTIONS_RESPONSE_CACHE_TTL_SEC", default=15),
        response_max_payload_bytes=env.int("SUBSCRIPTIONS_RESPONSE_MAX_PAYLOAD_BYTES", default=32768),
        public_base_url=env.str("SUBSCRIPTIONS_PUBLIC_BASE_URL", default=""),
        happ_profile_title=env.str("SUBSCRIPTIONS_HAPP_PROFILE_TITLE", default="VPN"),
        happ_profile_update_interval_hours=env.int("SUBSCRIPTIONS_HAPP_PROFILE_UPDATE_INTERVAL_HOURS", default=24),
        happ_support_url=env.str("SUBSCRIPTIONS_HAPP_SUPPORT_URL", default=""),
        happ_profile_web_page_url=env.str("SUBSCRIPTIONS_HAPP_PROFILE_WEB_PAGE_URL", default=""),
        happ_provider_id=env.str("SUBSCRIPTIONS_HAPP_PROVIDER_ID", default=""),
        happ_routing=env.str("SUBSCRIPTIONS_HAPP_ROUTING", default=""),
    )

    node_agent = NodeAgentConfig(
        sync_report_debounce_sec=env.int("NODE_SYNC_REPORT_DEBOUNCE_SEC", default=10),
        auth_token_rotation_grace_sec=max(
            0,
            env.int("NODE_AUTH_TOKEN_ROTATION_GRACE_SEC", default=300),
        ),
        bootstrap_allow_create=env.bool("NODE_BOOTSTRAP_ALLOW_CREATE", default=True),
        heartbeat_unhealthy_drain_threshold=max(
            1,
            env.int("NODE_HEARTBEAT_UNHEALTHY_DRAIN_THRESHOLD", default=2),
        ),
        heartbeat_healthy_undrain_threshold=max(
            1,
            env.int("NODE_HEARTBEAT_HEALTHY_UNDRAIN_THRESHOLD", default=3),
        ),
        stale_after_sec=max(30, env.int("NODE_STALE_AFTER_SEC", default=90)),
        auto_heal_enabled=env.bool("NODE_AUTO_HEAL_ENABLED", default=False),
        auto_heal_tick_sec=max(30, env.int("NODE_AUTO_HEAL_TICK_SEC", default=60)),
        auto_heal_max_nodes=min(500, max(1, env.int("NODE_AUTO_HEAL_MAX_NODES", default=20))),
        auto_undrain_enabled=env.bool("NODE_AUTO_UNDRAIN_ENABLED", default=False),
    )

    alerts = AlertsConfig(
        telegram_enabled=env.bool("ALERTS_TELEGRAM_ENABLED", default=False),
        telegram_bot_token=env.str("ALERTS_TELEGRAM_BOT_TOKEN", default=""),
        telegram_chat_id=env.str("ALERTS_TELEGRAM_CHAT_ID", default=""),
        telegram_timeout_sec=env.int("ALERTS_TELEGRAM_TIMEOUT_SEC", default=5),
    )

    probe = ProbeConfig(
        target_port=env.int("PROBE_TARGET_PORT", default=443),
        retention_days= env.int("PROBE_RETENTION_DAYS", default=30),
        auto_route_health_enabled=env.bool("PROBE_AUTO_ROUTE_HEALTH_ENABLED", default=True),
        route_block_cooldown_hours=env.int("PROBE_ROUTE_BLOCK_COOLDOWN_HOURS", default=6),
        auto_drain_migrate_enabled=env.bool("PROBE_AUTO_DRAIN_MIGRATE_ENABLED", default=False),
        auto_drain_tick_sec=env.int("PROBE_AUTO_DRAIN_TICK_SEC", default=120),
        auto_drain_source=env.str("PROBE_AUTO_DRAIN_SOURCE", default=""),
        auto_drain_require_recent_failure=env.bool("PROBE_AUTO_DRAIN_REQUIRE_RECENT_FAILURE", default=True),
        auto_drain_max_probe_age_sec=env.int("PROBE_AUTO_DRAIN_MAX_PROBE_AGE_SEC", default=600),
        auto_drain_min_consecutive_failures=env.int("PROBE_AUTO_DRAIN_MIN_CONSECUTIVE_FAILURES", default=2),
        auto_drain_include_already_draining=env.bool("PROBE_AUTO_DRAIN_INCLUDE_ALREADY_DRAINING", default=False),
        auto_drain_max_nodes=env.int("PROBE_AUTO_DRAIN_MAX_NODES", default=20),
        auto_drain_target_backend_id=env.str("PROBE_AUTO_DRAIN_TARGET_BACKEND_ID", default=""),
        auto_drain_last_migration_reason=env.str("PROBE_AUTO_DRAIN_LAST_MIGRATION_REASON",default="probe_auto_failure"),
    )

    routes = RoutesConfig(
        warmup_tick_sec=env.int("ROUTES_WARMUP_TICK_SEC", default=300),
        connect_refresh_interval_sec=env.int("ROUTES_CONNECT_REFRESH_INTERVAL_SEC", default=60),
        connect_max_cache_age_sec=env.int("ROUTES_CONNECT_MAX_CACHE_AGE_SEC", default=300),
        connect_backoff_steps_sec=tuple(
            env.list(
                "ROUTES_CONNECT_BACKOFF_STEPS_SEC",
                subcast=int,
                default=[2, 5, 10, 30, 60],
            )
        ),
        connect_telemetry_debounce_sec=env.int("ROUTES_CONNECT_TELEMETRY_DEBOUNCE_SEC", default=10),
        connect_telemetry_failure_window_sec=env.int("ROUTES_CONNECT_TELEMETRY_FAILURE_WINDOW_SEC", default=300),
        connect_telemetry_degraded_threshold=env.int("ROUTES_CONNECT_TELEMETRY_DEGRADED_THRESHOLD", default=2),
        connect_telemetry_block_threshold=env.int("ROUTES_CONNECT_TELEMETRY_BLOCK_THRESHOLD", default=3),
        connect_telemetry_block_cooldown_hours=env.int("ROUTES_CONNECT_TELEMETRY_BLOCK_COOLDOWN_HOURS", default=6),
    )

    edge = EdgeConfig(
        public_domain=env.str("VPN_PUBLIC_DOMAIN", default=""),
    )
    traffic = TrafficConfig(
        cleanup_enabled=env.bool("TRAFFIC_CLEANUP_ENABLED", default=False),
        cleanup_tick_sec=max(300, env.int("TRAFFIC_CLEANUP_TICK_SEC", default=3600)),
        history_retention_days=max(1, env.int("TRAFFIC_HISTORY_RETENTION_DAYS", default=14)),
    )

    return Settings(
        database=database,
        redis=redis,
        nats=nats,
        admin=admin,
        docs=docs,
        profiles_vpn=profiles_vpn,
        subscriptions=subscriptions,
        node_agent=node_agent,
        alerts=alerts,
        probe=probe,
        routes=routes,
        edge=edge,
        traffic=traffic,
    )
