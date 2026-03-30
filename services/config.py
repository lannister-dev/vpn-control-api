from dataclasses import dataclass
from functools import lru_cache
from environs import Env
from services.vpn.subscriptions.constants import DEFAULT_HAPP_COLOR_PROFILE


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
    js_command_stream: str = "agent_placement_commands"
    js_result_stream: str = "agent_placement_results"
    js_control_stream: str = "agent_control_events"
    js_command_subject_prefix: str = "agent.placements"
    js_result_subject_prefix: str = "agent.placement_results"
    js_snapshot_subject_prefix: str = "agent.snapshots"
    js_heartbeat_subject_prefix: str = "agent.heartbeats"
    js_sync_report_subject_prefix: str = "agent.sync_reports"
    js_consumer_prefix: str = "vpn-control-api"
    js_ack_wait_s: float = 30.0
    js_max_deliver: int = 30
    js_fetch_timeout_s: float = 1.0
    js_outbox_batch_size: int = 200
    js_outbox_poll_interval_s: float = 1.0


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
class BotApiConfig:
    api_key_hash: str


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
    happ_hide_settings: bool = False
    happ_always_hwid_enable: bool = False
    happ_color_profile: str = DEFAULT_HAPP_COLOR_PROFILE


@dataclass
class NodeAgentConfig:
    sync_report_debounce_sec: int = 10
    auth_token_rotation_grace_sec: int = 300
    bootstrap_allow_create: bool = True
    heartbeat_unhealthy_drain_threshold: int = 5
    heartbeat_healthy_undrain_threshold: int = 3
    stale_after_sec: int = 90
    auto_heal_enabled: bool = False
    auto_heal_tick_sec: int = 60
    auto_heal_max_nodes: int = 20
    auto_heal_drain_cooldown_sec: int = 180
    auto_undrain_enabled: bool = False
    placement_error_retry_enabled: bool = True
    placement_error_retry_tick_sec: int = 120
    placement_error_retry_after_sec: int = 120


@dataclass
class AlertsConfig:
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_sec: int = 5


@dataclass
class BotNotificationsConfig:
    enabled: bool = False
    bot_token: str = ""
    timeout_sec: int = 5


@dataclass
class ProbeConfig:
    target_port: int = 443
    synthetic_reality_client_id: str | None = None
    synthetic_ws_client_id: str | None = None
    synthetic_reconcile_enabled: bool = False
    synthetic_reconcile_tick_sec: int = 300
    synthetic_user_telegram_id: int = 0
    synthetic_user_username: str = "probe-synthetic"
    synthetic_key_valid_days: int = 3650
    synthetic_key_traffic_limit_mb: int = 102400
    retention_days: int = 3
    cleanup_enabled: bool = True
    cleanup_tick_sec: int = 3600
    auto_route_health_enabled: bool = True
    route_block_cooldown_hours: int = 6
    route_suspected_after_failures: int = 2
    route_degraded_after_failures: int = 3
    route_block_after_failures: int = 4
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
class VpnKeyConfig:
    expiration_enabled: bool = True
    expiration_tick_sec: int = 60
    expiration_batch_size: int = 500


@dataclass
class TrafficConfig:
    cleanup_enabled: bool = False
    cleanup_tick_sec: int = 3600
    history_retention_days: int = 14
    reset_enabled: bool = False
    reset_tick_sec: int = 300


@dataclass
class TransportConfig:
    cleanup_enabled: bool = True
    cleanup_tick_sec: int = 3600
    retention_days: int = 30


@dataclass
class BillingConfig:
    crypto_api_url: str = "https://api.cryptocloud.plus/v2"
    crypto_api_key: str = ""
    crypto_shop_id: str = ""
    crypto_webhook_secret: str = ""
    stars_bot_token: str = ""
    platega_api_url: str = ""
    platega_shop_id: str = ""
    platega_api_key: str = ""
    platega_webhook_secret: str = ""
    order_ttl_minutes: int = 30


@dataclass
class AdminAuthConfig:
    enabled: bool = False
    session_secret: str = ""
    session_ttl_sec: int = 86400
    session_cookie_secure: bool = True
    telegram_login_enabled: bool = False
    telegram_client_id: str = ""
    telegram_client_secret: str = ""
    telegram_redirect_uri: str = ""
    telegram_authorize_url: str = "https://oauth.telegram.org/auth"
    telegram_token_url: str = "https://oauth.telegram.org/token"
    telegram_jwks_url: str = "https://oauth.telegram.org/.well-known/jwks.json"
    telegram_issuer: str = "https://oauth.telegram.org"
    telegram_allowed_ids: tuple[int, ...] = ()


@dataclass
class Settings:
    database: DbConfig
    redis: RedisConfig
    nats: NatsConfig
    admin: AdminConfig
    bot_api: BotApiConfig
    docs: DocsConfig
    profiles_vpn: ProfilesVpnConfig
    subscriptions: SubscriptionsConfig
    node_agent: NodeAgentConfig
    alerts: AlertsConfig
    bot_notifications: BotNotificationsConfig
    probe: ProbeConfig
    routes: RoutesConfig
    edge: EdgeConfig
    traffic: TrafficConfig
    transport: TransportConfig
    admin_auth: AdminAuthConfig
    vpn_key: VpnKeyConfig
    billing: BillingConfig


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
        js_command_stream=env.str("NATS_JS_COMMAND_STREAM", default="agent_placement_commands"),
        js_result_stream=env.str("NATS_JS_RESULT_STREAM", default="agent_placement_results"),
        js_control_stream=env.str("NATS_JS_CONTROL_STREAM", default="agent_control_events"),
        js_command_subject_prefix=env.str("NATS_JS_COMMAND_SUBJECT_PREFIX", default="agent.placements"),
        js_result_subject_prefix=env.str("NATS_JS_RESULT_SUBJECT_PREFIX", default="agent.placement_results"),
        js_snapshot_subject_prefix=env.str("NATS_JS_SNAPSHOT_SUBJECT_PREFIX", default="agent.snapshots"),
        js_heartbeat_subject_prefix=env.str("NATS_JS_HEARTBEAT_SUBJECT_PREFIX", default="agent.heartbeats"),
        js_sync_report_subject_prefix=env.str("NATS_JS_SYNC_REPORT_SUBJECT_PREFIX", default="agent.sync_reports"),
        js_consumer_prefix=env.str("NATS_JS_CONSUMER_PREFIX", default="vpn-control-api"),
        js_ack_wait_s=env.float("NATS_JS_ACK_WAIT_S", default=30.0),
        js_max_deliver=env.int("NATS_JS_MAX_DELIVER", default=30),
        js_fetch_timeout_s=env.float("NATS_JS_FETCH_TIMEOUT_S", default=1.0),
        js_outbox_batch_size=max(1, env.int("NATS_JS_OUTBOX_BATCH_SIZE", default=200)),
        js_outbox_poll_interval_s=max(0.1, env.float("NATS_JS_OUTBOX_POLL_INTERVAL_S", default=1.0)),
    )

    admin = AdminConfig(
        api_key_hash=env.str("ADMIN_API_KEY_HASH"),
        connect_api_key_hash=env.str("CONNECT_API_KEY_HASH", default=env.str("ADMIN_API_KEY_HASH")),
        bootstrap_token_hash=env.str("BOOTSTRAP_TOKEN_HASH"),
        probe_token_hash= env.str("PROBE_TOKEN_HASH"),
    )

    bot_api = BotApiConfig(api_key_hash=env.str("BOT_API_KEY_HASH", default=""))

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
        happ_hide_settings=env.bool("SUBSCRIPTIONS_HAPP_HIDE_SETTINGS", default=False),
        happ_always_hwid_enable=env.bool("SUBSCRIPTIONS_HAPP_ALWAYS_HWID_ENABLE", default=False),
        happ_color_profile=env.str("SUBSCRIPTIONS_HAPP_COLOR_PROFILE", default="").strip() or DEFAULT_HAPP_COLOR_PROFILE,
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
            env.int("NODE_HEARTBEAT_UNHEALTHY_DRAIN_THRESHOLD", default=5),
        ),
        heartbeat_healthy_undrain_threshold=max(
            1,
            env.int("NODE_HEARTBEAT_HEALTHY_UNDRAIN_THRESHOLD", default=3),
        ),
        stale_after_sec=max(30, env.int("NODE_STALE_AFTER_SEC", default=90)),
        auto_heal_enabled=env.bool("NODE_AUTO_HEAL_ENABLED", default=False),
        auto_heal_tick_sec=max(30, env.int("NODE_AUTO_HEAL_TICK_SEC", default=60)),
        auto_heal_max_nodes=min(500, max(1, env.int("NODE_AUTO_HEAL_MAX_NODES", default=20))),
        auto_heal_drain_cooldown_sec=max(0, env.int("NODE_AUTO_HEAL_DRAIN_COOLDOWN_SEC", default=180)),
        auto_undrain_enabled=env.bool("NODE_AUTO_UNDRAIN_ENABLED", default=False),
        placement_error_retry_enabled=env.bool("NODE_PLACEMENT_ERROR_RETRY_ENABLED", default=True),
        placement_error_retry_tick_sec=max(30, env.int("NODE_PLACEMENT_ERROR_RETRY_TICK_SEC", default=120)),
        placement_error_retry_after_sec=max(30, env.int("NODE_PLACEMENT_ERROR_RETRY_AFTER_SEC", default=120)),
    )

    alerts = AlertsConfig(
        telegram_enabled=env.bool("ALERTS_TELEGRAM_ENABLED", default=False),
        telegram_bot_token=env.str("ALERTS_TELEGRAM_BOT_TOKEN", default="").strip(),
        telegram_chat_id=env.str("ALERTS_TELEGRAM_CHAT_ID", default="").strip(),
        telegram_timeout_sec=env.int("ALERTS_TELEGRAM_TIMEOUT_SEC", default=5),
    )

    bot_notifications_token = env.str("BOT_NOTIFICATIONS_TOKEN", default="").strip()
    if not bot_notifications_token:
        bot_notifications_token = env.str("BILLING_STARS_BOT_TOKEN", default="").strip()
    bot_notifications = BotNotificationsConfig(
        enabled=env.bool("BOT_NOTIFICATIONS_ENABLED", default=bool(bot_notifications_token)),
        bot_token=bot_notifications_token,
        timeout_sec=env.int("BOT_NOTIFICATIONS_TIMEOUT_SEC", default=5),
    )

    probe = ProbeConfig(
        target_port=env.int("PROBE_TARGET_PORT", default=443),
        synthetic_reality_client_id=env.str("PROBE_SYNTHETIC_REALITY_CLIENT_ID", default=""),
        synthetic_ws_client_id=env.str("PROBE_SYNTHETIC_WS_CLIENT_ID", default=""),
        synthetic_reconcile_enabled=env.bool("PROBE_SYNTHETIC_RECONCILE_ENABLED", default=False),
        synthetic_reconcile_tick_sec=max(30, env.int("PROBE_SYNTHETIC_RECONCILE_TICK_SEC", default=300)),
        synthetic_user_telegram_id=env.int("PROBE_SYNTHETIC_USER_TELEGRAM_ID", default=0),
        synthetic_user_username=env.str("PROBE_SYNTHETIC_USER_USERNAME", default="probe-synthetic"),
        synthetic_key_valid_days=max(1, env.int("PROBE_SYNTHETIC_KEY_VALID_DAYS", default=3650)),
        synthetic_key_traffic_limit_mb=max(1, env.int("PROBE_SYNTHETIC_KEY_TRAFFIC_LIMIT_MB", default=102400)),
        retention_days= env.int("PROBE_RETENTION_DAYS", default=3),
        cleanup_enabled=env.bool("PROBE_CLEANUP_ENABLED", default=True),
        cleanup_tick_sec=max(300, env.int("PROBE_CLEANUP_TICK_SEC", default=3600)),
        auto_route_health_enabled=env.bool("PROBE_AUTO_ROUTE_HEALTH_ENABLED", default=True),
        route_block_cooldown_hours=env.int("PROBE_ROUTE_BLOCK_COOLDOWN_HOURS", default=6),
        route_suspected_after_failures=max(1, env.int("PROBE_ROUTE_SUSPECTED_AFTER_FAILURES", default=2)),
        route_degraded_after_failures=max(2, env.int("PROBE_ROUTE_DEGRADED_AFTER_FAILURES", default=3)),
        route_block_after_failures=max(3, env.int("PROBE_ROUTE_BLOCK_AFTER_FAILURES", default=4)),
        auto_drain_migrate_enabled=env.bool("PROBE_AUTO_DRAIN_MIGRATE_ENABLED", default=False),
        auto_drain_tick_sec=env.int("PROBE_AUTO_DRAIN_TICK_SEC", default=120),
        auto_drain_source=env.str("PROBE_AUTO_DRAIN_SOURCE", default=""),
        auto_drain_require_recent_failure=env.bool("PROBE_AUTO_DRAIN_REQUIRE_RECENT_FAILURE", default=True),
        auto_drain_max_probe_age_sec=env.int("PROBE_AUTO_DRAIN_MAX_PROBE_AGE_SEC", default=600),
        auto_drain_min_consecutive_failures=env.int("PROBE_AUTO_DRAIN_MIN_CONSECUTIVE_FAILURES", default=2),
        auto_drain_include_already_draining=env.bool("PROBE_AUTO_DRAIN_INCLUDE_ALREADY_DRAINING", default=False),
        auto_drain_max_nodes=env.int("PROBE_AUTO_DRAIN_MAX_NODES", default=20),
        auto_drain_target_backend_id=env.str("PROBE_AUTO_DRAIN_TARGET_BACKEND_ID", default="").strip() or None,
        auto_drain_last_migration_reason=env.str("PROBE_AUTO_DRAIN_LAST_MIGRATION_REASON", default="probe_auto_failure"),
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
        public_domain=env.str("VPN_PUBLIC_DOMAIN", default="").strip(),
    )
    traffic = TrafficConfig(
        cleanup_enabled=env.bool("TRAFFIC_CLEANUP_ENABLED", default=False),
        cleanup_tick_sec=max(300, env.int("TRAFFIC_CLEANUP_TICK_SEC", default=3600)),
        history_retention_days=max(1, env.int("TRAFFIC_HISTORY_RETENTION_DAYS", default=14)),
        reset_enabled=env.bool("TRAFFIC_RESET_ENABLED", default=False),
        reset_tick_sec=max(60, env.int("TRAFFIC_RESET_TICK_SEC", default=300)),
    )
    transport = TransportConfig(
        cleanup_enabled=env.bool("TRANSPORT_CLEANUP_ENABLED", default=True),
        cleanup_tick_sec=max(300, env.int("TRANSPORT_CLEANUP_TICK_SEC", default=3600)),
        retention_days=max(1, env.int("TRANSPORT_RETENTION_DAYS", default=30)),
    )

    vpn_key = VpnKeyConfig(
        expiration_enabled=env.bool("VPN_KEY_EXPIRATION_ENABLED", default=True),
        expiration_tick_sec=max(30, env.int("VPN_KEY_EXPIRATION_TICK_SEC", default=60)),
        expiration_batch_size=max(1, env.int("VPN_KEY_EXPIRATION_BATCH_SIZE", default=500)),
    )

    billing = BillingConfig(
        crypto_api_url=env.str("BILLING_CRYPTO_API_URL", default="https://api.cryptocloud.plus/v2"),
        crypto_api_key=env.str("BILLING_CRYPTO_API_KEY", default=""),
        crypto_shop_id=env.str("BILLING_CRYPTO_SHOP_ID", default=""),
        crypto_webhook_secret=env.str("BILLING_CRYPTO_WEBHOOK_SECRET", default=""),
        stars_bot_token=env.str("BILLING_STARS_BOT_TOKEN", default=""),
        platega_api_url=env.str("BILLING_PLATEGA_API_URL", default=""),
        platega_shop_id=env.str("BILLING_PLATEGA_SHOP_ID", default=""),
        platega_api_key=env.str("BILLING_PLATEGA_API_KEY", default=""),
        platega_webhook_secret=env.str("BILLING_PLATEGA_WEBHOOK_SECRET", default=""),
        order_ttl_minutes=max(1, env.int("BILLING_ORDER_TTL_MINUTES", default=30)),
    )

    _tg_allowed_raw = env.str("ADMIN_TELEGRAM_ALLOWED_IDS", default="")
    _tg_allowed = tuple(
        int(x.strip()) for x in _tg_allowed_raw.split(",") if x.strip().isdigit()
    )
    admin_auth = AdminAuthConfig(
        enabled=env.bool("ADMIN_AUTH_ENABLED", default=False),
        session_secret=env.str("ADMIN_SESSION_SECRET", default=""),
        session_ttl_sec=env.int("ADMIN_SESSION_TTL_SEC", default=86400),
        session_cookie_secure=env.bool("ADMIN_SESSION_COOKIE_SECURE", default=True),
        telegram_login_enabled=env.bool("ADMIN_TELEGRAM_LOGIN_ENABLED", default=False),
        telegram_client_id=env.str("ADMIN_TELEGRAM_CLIENT_ID", default=""),
        telegram_client_secret=env.str("ADMIN_TELEGRAM_CLIENT_SECRET", default=""),
        telegram_redirect_uri=env.str("ADMIN_TELEGRAM_REDIRECT_URI", default=""),
        telegram_authorize_url=env.str("ADMIN_TELEGRAM_AUTHORIZE_URL", default="https://oauth.telegram.org/auth"),
        telegram_token_url=env.str("ADMIN_TELEGRAM_TOKEN_URL", default="https://oauth.telegram.org/token"),
        telegram_jwks_url=env.str("ADMIN_TELEGRAM_JWKS_URL", default="https://oauth.telegram.org/.well-known/jwks.json"),
        telegram_issuer=env.str("ADMIN_TELEGRAM_ISSUER", default="https://oauth.telegram.org"),
        telegram_allowed_ids=_tg_allowed,
    )

    return Settings(
        database=database,
        redis=redis,
        nats=nats,
        admin=admin,
        bot_api=bot_api,
        docs=docs,
        profiles_vpn=profiles_vpn,
        subscriptions=subscriptions,
        node_agent=node_agent,
        alerts=alerts,
        bot_notifications=bot_notifications,
        probe=probe,
        routes=routes,
        edge=edge,
        traffic=traffic,
        transport=transport,
        admin_auth=admin_auth,
        vpn_key=vpn_key,
        billing=billing,
    )
