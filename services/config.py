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
    nodes_traffic_subject: str = "nodes.traffic"
    nodes_traffic_queue: str = "vpn-control-api-nodes-traffic"
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
    force_reconnect_after_s: float = 30.0
    js_traffic_stream: str = "vpn_control_api_traffic"
    js_traffic_max_msgs_per_subject: int = 100_000
    js_traffic_max_age_s: int = 3600
    js_traffic_duplicate_window_s: int = 120
    js_traffic_ack_wait_s: float = 30.0
    js_traffic_max_deliver: int = 10
    js_support_stream: str = "vpn_support"
    support_inbound_subject: str = "support.message.in"
    support_outbound_subject: str = "support.message.out"
    support_sent_subject: str = "support.message.sent"
    support_inbound_queue: str = "vpn-control-api-support-inbound"
    support_sent_queue: str = "vpn-control-api-support-sent"
    js_support_max_msgs_per_subject: int = 100_000
    js_support_max_age_s: int = 86400
    js_support_duplicate_window_s: int = 600
    js_support_ack_wait_s: float = 30.0
    js_support_max_deliver: int = 5


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
    relay_token: str
    relay_token_hash: str


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
    happ_profile_update_interval_hours: int = 1
    happ_support_url: str = ""
    happ_profile_web_page_url: str = ""
    happ_provider_id: str = ""
    happ_routing: str = ""
    happ_hide_settings: bool = False
    happ_always_hwid_enable: bool = False
    happ_color_profile: str = DEFAULT_HAPP_COLOR_PROFILE
    happ_autoconnect: bool = True
    happ_autoconnect_type: str = "lowestdelay"
    happ_ping_onopen: bool = True


@dataclass
class SubscriptionsExpirationConfig:
    enabled: bool = True
    tick_sec: int = 60
    batch_size: int = 200


@dataclass
class EntryRelayConfig:
    listen_port: int = 443
    api_poll_sec: int = 300
    user_entry_bucket_seconds: int = 0


@dataclass
class WgMeshConfig:
    enabled: bool = False
    mesh_cidr: str = "10.10.0.0/24"
    listen_port: int = 51820


@dataclass
class EntryRoutingConfig:
    enabled: bool = False
    publisher_tick_sec: int = 30
    listen_port: int = 8443
    reality_private_key: str = ""
    reality_short_id: str = ""
    reality_server_name: str = "www.cloudflare.com"
    reality_handshake_server: str = "www.cloudflare.com"
    reality_handshake_port: int = 443
    backend_service_uuid: str = ""
    backend_reality_public_key: str = ""
    backend_reality_fingerprint: str = "chrome"
    backend_port: int = 443
    backend_flow: str = "xtls-rprx-vision"
    backend_use_wg: bool = False
    backend_wg_port: int = 10100
    per_user_outbound_uuid: bool = False

@dataclass
class K3sConfig:
    server_url: str = ""
    node_token: str = ""
    version: str = ""
    bootstrap_token_ttl_sec: int = 86400
    public_base_url: str = ""
    channel: str = ""  # "dev" | "prod" — used as nodeSelector channel= label by installer


@dataclass
class NodeAgentConfig:
    # bootstrap/protocol — remain in env
    sync_report_debounce_sec: int = 10
    auth_token_rotation_grace_sec: int = 300
    bootstrap_allow_create: bool = True
    # operational tunables moved to DB (node_policy)


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
class SupportConfig:
    bot_token: str = ""
    media_proxy_timeout_sec: int = 10


@dataclass
class ProbeConfig:
    target_port: int = 443
    synthetic_reality_client_id: str | None = None
    synthetic_ws_client_id: str | None = None
    synthetic_user_telegram_id: int = 0
    synthetic_user_username: str = "probe-synthetic"


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
    reset_enabled: bool = False
    reset_tick_sec: int = 300


@dataclass
class BillingConfig:
    crypto_api_url: str = "https://api.cryptocloud.plus/v2"
    crypto_api_key: str = ""
    crypto_shop_id: str = ""
    crypto_webhook_secret: str = ""
    freekassa_api_url: str = "https://pay.fk.money/"
    freekassa_shop_id: str = ""
    freekassa_secret_word_1: str = ""
    freekassa_secret_word_2: str = ""
    freekassa_currency: str = "RUB"
    freekassa_success_redirect_url: str = ""
    freekassa_fail_redirect_url: str = ""
    stars_bot_token: str = ""
    platega_api_url: str = "https://app.platega.io"
    platega_shop_id: str = ""
    platega_api_key: str = ""
    platega_success_redirect_url: str = ""
    platega_fail_redirect_url: str = ""
    order_ttl_minutes: int = 30
    expiration_reconciler_enabled: bool = True
    expiration_tick_sec: int = 60
    expiration_batch_size: int = 500


@dataclass
class MigrationConfig:
    enabled: bool = False
    gift_plan_name: str = ""


@dataclass
class ReferralConfig:
    enabled: bool = True
    reward_rub: int = 50
    referred_reward_rub: int = 0
    bot_username: str = ""


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
    telegram_oidc_proxy: str = ""


@dataclass
class S3Config:
    endpoint_url: str = ""
    region: str = ""
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    public_base_url: str = ""
    addressing_style: str = "virtual"
    presigned_ttl_sec: int = 3600

    @property
    def enabled(self) -> bool:
        return bool(self.bucket and self.access_key and self.secret_key)


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
    support: SupportConfig
    probe: ProbeConfig
    routes: RoutesConfig
    edge: EdgeConfig
    traffic: TrafficConfig
    admin_auth: AdminAuthConfig
    vpn_key: VpnKeyConfig
    billing: BillingConfig
    migration: MigrationConfig
    referral: ReferralConfig
    k3s: K3sConfig
    entry_relay: EntryRelayConfig
    entry_routing: EntryRoutingConfig
    subscriptions_expiration: SubscriptionsExpirationConfig
    wg_mesh: WgMeshConfig
    s3: S3Config


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
        nodes_traffic_subject=env.str("NATS_NODES_TRAFFIC_SUBJECT", default="nodes.traffic"),
        nodes_traffic_queue=env.str("NATS_NODES_TRAFFIC_QUEUE", default="vpn-control-api-nodes-traffic"),
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
        js_traffic_stream=env.str("NATS_JS_TRAFFIC_STREAM", default="vpn_control_api_traffic"),
        js_traffic_max_msgs_per_subject=max(1, env.int("NATS_JS_TRAFFIC_MAX_MSGS_PER_SUBJECT", default=100_000)),
        js_traffic_max_age_s=max(60, env.int("NATS_JS_TRAFFIC_MAX_AGE_S", default=3600)),
        js_traffic_duplicate_window_s=max(0, env.int("NATS_JS_TRAFFIC_DUPLICATE_WINDOW_S", default=120)),
        js_traffic_ack_wait_s=max(1.0, env.float("NATS_JS_TRAFFIC_ACK_WAIT_S", default=30.0)),
        js_traffic_max_deliver=max(1, env.int("NATS_JS_TRAFFIC_MAX_DELIVER", default=10)),
        js_support_stream=env.str("NATS_JS_SUPPORT_STREAM", default="vpn_support"),
        support_inbound_subject=env.str("NATS_SUPPORT_INBOUND_SUBJECT", default="support.message.in"),
        support_outbound_subject=env.str("NATS_SUPPORT_OUTBOUND_SUBJECT", default="support.message.out"),
        support_sent_subject=env.str("NATS_SUPPORT_SENT_SUBJECT", default="support.message.sent"),
        support_inbound_queue=env.str("NATS_SUPPORT_INBOUND_QUEUE", default="vpn-control-api-support-inbound"),
        support_sent_queue=env.str("NATS_SUPPORT_SENT_QUEUE", default="vpn-control-api-support-sent"),
        js_support_max_msgs_per_subject=max(1, env.int("NATS_JS_SUPPORT_MAX_MSGS_PER_SUBJECT", default=100_000)),
        js_support_max_age_s=max(60, env.int("NATS_JS_SUPPORT_MAX_AGE_S", default=86400)),
        js_support_duplicate_window_s=max(0, env.int("NATS_JS_SUPPORT_DUPLICATE_WINDOW_S", default=600)),
        js_support_ack_wait_s=max(1.0, env.float("NATS_JS_SUPPORT_ACK_WAIT_S", default=30.0)),
        js_support_max_deliver=max(1, env.int("NATS_JS_SUPPORT_MAX_DELIVER", default=5)),
    )

    admin = AdminConfig(
        api_key_hash=env.str("ADMIN_API_KEY_HASH"),
        connect_api_key_hash=env.str("CONNECT_API_KEY_HASH", default=env.str("ADMIN_API_KEY_HASH")),
        bootstrap_token_hash=env.str("BOOTSTRAP_TOKEN_HASH"),
        probe_token_hash= env.str("PROBE_TOKEN_HASH"),
        relay_token=env.str("RELAY_TOKEN", default=""),
        relay_token_hash=env.str("RELAY_TOKEN_HASH", default=""),
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
        happ_profile_update_interval_hours=env.int("SUBSCRIPTIONS_HAPP_PROFILE_UPDATE_INTERVAL_HOURS", default=1),
        happ_support_url=env.str("SUBSCRIPTIONS_HAPP_SUPPORT_URL", default=""),
        happ_profile_web_page_url=env.str("SUBSCRIPTIONS_HAPP_PROFILE_WEB_PAGE_URL", default=""),
        happ_provider_id=env.str("SUBSCRIPTIONS_HAPP_PROVIDER_ID", default=""),
        happ_routing=env.str("SUBSCRIPTIONS_HAPP_ROUTING", default=""),
        happ_hide_settings=env.bool("SUBSCRIPTIONS_HAPP_HIDE_SETTINGS", default=False),
        happ_always_hwid_enable=env.bool("SUBSCRIPTIONS_HAPP_ALWAYS_HWID_ENABLE", default=False),
        happ_color_profile=env.str("SUBSCRIPTIONS_HAPP_COLOR_PROFILE", default="").strip() or DEFAULT_HAPP_COLOR_PROFILE,
        happ_autoconnect=env.bool("SUBSCRIPTIONS_HAPP_AUTOCONNECT", default=True),
        happ_autoconnect_type=env.str("SUBSCRIPTIONS_HAPP_AUTOCONNECT_TYPE", default="lowestdelay"),
        happ_ping_onopen=env.bool("SUBSCRIPTIONS_HAPP_PING_ONOPEN", default=True),
    )

    node_agent = NodeAgentConfig(
        sync_report_debounce_sec=env.int("NODE_SYNC_REPORT_DEBOUNCE_SEC", default=10),
        auth_token_rotation_grace_sec=max(
            0,
            env.int("NODE_AUTH_TOKEN_ROTATION_GRACE_SEC", default=300),
        ),
        bootstrap_allow_create=env.bool("NODE_BOOTSTRAP_ALLOW_CREATE", default=True),
    )

    alerts = AlertsConfig(
        telegram_enabled=env.bool("ALERTS_TELEGRAM_ENABLED", default=False),
        telegram_bot_token=env.str("ALERTS_TELEGRAM_BOT_TOKEN", default=""),
        telegram_chat_id=env.str("ALERTS_TELEGRAM_CHAT_ID", default=""),
        telegram_timeout_sec=env.int("ALERTS_TELEGRAM_TIMEOUT_SEC", default=5),
    )

    bot_notifications_token = env.str("BOT_NOTIFICATIONS_TOKEN", default="")
    if not bot_notifications_token:
        bot_notifications_token = env.str("BILLING_STARS_BOT_TOKEN", default="")
    bot_notifications = BotNotificationsConfig(
        enabled=env.bool("BOT_NOTIFICATIONS_ENABLED", default=bool(bot_notifications_token)),
        bot_token=bot_notifications_token,
        timeout_sec=env.int("BOT_NOTIFICATIONS_TIMEOUT_SEC", default=5),
    )

    support = SupportConfig(
        bot_token=env.str("SUPPORT_BOT_TOKEN", default=""),
        media_proxy_timeout_sec=env.int("SUPPORT_MEDIA_PROXY_TIMEOUT_SEC", default=10),
    )

    probe = ProbeConfig(
        target_port=env.int("PROBE_TARGET_PORT", default=443),
        synthetic_reality_client_id=env.str("PROBE_SYNTHETIC_REALITY_CLIENT_ID", default=""),
        synthetic_ws_client_id=env.str("PROBE_SYNTHETIC_WS_CLIENT_ID", default=""),
        synthetic_user_telegram_id=env.int("PROBE_SYNTHETIC_USER_TELEGRAM_ID", default=0),
        synthetic_user_username=env.str("PROBE_SYNTHETIC_USER_USERNAME", default="probe-synthetic"),
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
        reset_enabled=env.bool("TRAFFIC_RESET_ENABLED", default=False),
        reset_tick_sec=max(60, env.int("TRAFFIC_RESET_TICK_SEC", default=300)),
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
        freekassa_api_url=env.str("BILLING_FREEKASSA_API_URL", default="https://pay.fk.money/"),
        freekassa_shop_id=env.str("BILLING_FREEKASSA_SHOP_ID", default=""),
        freekassa_secret_word_1=env.str("BILLING_FREEKASSA_SECRET_WORD_1", default=""),
        freekassa_secret_word_2=env.str("BILLING_FREEKASSA_SECRET_WORD_2", default=""),
        freekassa_currency=env.str("BILLING_FREEKASSA_CURRENCY", default="RUB"),
        freekassa_success_redirect_url=env.str("BILLING_FREEKASSA_SUCCESS_REDIRECT_URL", default=""),
        freekassa_fail_redirect_url=env.str("BILLING_FREEKASSA_FAIL_REDIRECT_URL", default=""),
        stars_bot_token=env.str("BILLING_STARS_BOT_TOKEN", default=""),
        platega_api_url=env.str("BILLING_PLATEGA_API_URL", default="https://app.platega.io"),
        platega_shop_id=env.str("BILLING_PLATEGA_SHOP_ID", default=""),
        platega_api_key=env.str("BILLING_PLATEGA_API_KEY", default=""),
        platega_success_redirect_url=env.str("BILLING_PLATEGA_SUCCESS_REDIRECT_URL", default=""),
        platega_fail_redirect_url=env.str("BILLING_PLATEGA_FAIL_REDIRECT_URL", default=""),
        order_ttl_minutes=max(1, env.int("BILLING_ORDER_TTL_MINUTES", default=30)),
        expiration_reconciler_enabled=env.bool("BILLING_ORDER_EXPIRATION_ENABLED", default=True),
        expiration_tick_sec=max(30, env.int("BILLING_ORDER_EXPIRATION_TICK_SEC", default=60)),
        expiration_batch_size=max(1, env.int("BILLING_ORDER_EXPIRATION_BATCH_SIZE", default=500)),
    )

    migration = MigrationConfig(
        enabled=env.bool("MIGRATION_ENABLED", default=False),
        gift_plan_name=env.str("MIGRATION_GIFT_PLAN_NAME", default="").strip(),
    )

    referral = ReferralConfig(
        enabled=env.bool("REFERRAL_ENABLED", default=True),
        reward_rub=env.int("REFERRAL_REWARD_RUB", default=50),
        referred_reward_rub=env.int("REFERRAL_REFERRED_REWARD_RUB", default=0),
        bot_username=env.str("REFERRAL_BOT_USERNAME", default="").strip(),
    )

    k3s = K3sConfig(
        server_url=env.str("K3S_URL", default=""),
        node_token=env.str("K3S_NODE_TOKEN", default=""),
        version=env.str("K3S_VERSION", default=""),
        bootstrap_token_ttl_sec=max(300, env.int("NODE_BOOTSTRAP_TOKEN_TTL_SEC", default=86400)),
        public_base_url=env.str("CONTROL_API_PUBLIC_URL", default="").strip().rstrip("/"),
        channel=env.str("CHANNEL", default="").strip().lower(),
    )

    entry_relay = EntryRelayConfig(
        listen_port=env.int("ENTRY_RELAY_LISTEN_PORT", default=443),
        api_poll_sec=env.int("ENTRY_RELAY_API_POLL_SEC", default=300),
        user_entry_bucket_seconds=max(0, env.int("ENTRY_RELAY_USER_BUCKET_SECONDS", default=0)),
    )

    entry_routing = EntryRoutingConfig(
        enabled=env.bool("ENTRY_ROUTING_ENABLED", default=False),
        publisher_tick_sec=max(5, env.int("ENTRY_ROUTING_PUBLISHER_TICK_SEC", default=30)),
        listen_port=env.int("ENTRY_ROUTING_LISTEN_PORT", default=8443),
        reality_private_key=env.str("ENTRY_ROUTING_REALITY_PRIVATE_KEY", default=""),
        reality_short_id=env.str("ENTRY_ROUTING_REALITY_SHORT_ID", default=""),
        reality_server_name=env.str("ENTRY_ROUTING_REALITY_SERVER_NAME", default="www.cloudflare.com"),
        reality_handshake_server=env.str("ENTRY_ROUTING_REALITY_HANDSHAKE_SERVER", default="www.cloudflare.com"),
        reality_handshake_port=env.int("ENTRY_ROUTING_REALITY_HANDSHAKE_PORT", default=443),
        backend_service_uuid=env.str("ENTRY_ROUTING_BACKEND_SERVICE_UUID", default=""),
        backend_reality_public_key=env.str("ENTRY_ROUTING_BACKEND_REALITY_PUBLIC_KEY", default=""),
        backend_reality_fingerprint=env.str("ENTRY_ROUTING_BACKEND_REALITY_FINGERPRINT", default="chrome"),
        backend_port=env.int("ENTRY_ROUTING_BACKEND_PORT", default=443),
        backend_flow=env.str("ENTRY_ROUTING_BACKEND_FLOW", default="xtls-rprx-vision"),
        backend_use_wg=env.bool("ENTRY_ROUTING_BACKEND_USE_WG", default=False),
        backend_wg_port=env.int("ENTRY_ROUTING_BACKEND_WG_PORT", default=10100),
        per_user_outbound_uuid=env.bool("ENTRY_ROUTING_PER_USER_OUTBOUND_UUID", default=False),
    )

    subscriptions_expiration = SubscriptionsExpirationConfig(
        enabled=env.bool("SUBSCRIPTIONS_EXPIRATION_ENABLED", default=True),
        tick_sec=max(30, env.int("SUBSCRIPTIONS_EXPIRATION_TICK_SEC", default=60)),
        batch_size=max(1, env.int("SUBSCRIPTIONS_EXPIRATION_BATCH_SIZE", default=200)),
    )

    wg_mesh = WgMeshConfig(
        enabled=env.bool("WG_MESH_ENABLED", default=False),
        mesh_cidr=env.str("WG_MESH_CIDR", default="10.10.0.0/24"),
        listen_port=env.int("WG_MESH_LISTEN_PORT", default=51820),
    )

    _tg_allowed_raw = env.str("ADMIN_TELEGRAM_ALLOWED_IDS", default="")
    _tg_allowed = tuple(
        int(x.strip()) for x in _tg_allowed_raw.split(",") if x.strip().isdigit()
    )
    s3 = S3Config(
        endpoint_url=env.str("S3_ENDPOINT_URL", default=""),
        region=env.str("S3_REGION", default=""),
        bucket=env.str("S3_BUCKET", default=""),
        access_key=env.str("S3_ACCESS_KEY", default=""),
        secret_key=env.str("S3_SECRET_KEY", default=""),
        public_base_url=env.str("S3_PUBLIC_BASE_URL", default=""),
        addressing_style=env.str("S3_ADDRESSING_STYLE", default="virtual"),
        presigned_ttl_sec=env.int("S3_PRESIGNED_TTL_SEC", default=3600),
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
        telegram_oidc_proxy=env.str("ADMIN_TELEGRAM_OIDC_PROXY", default=""),
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
        support=support,
        probe=probe,
        routes=routes,
        edge=edge,
        traffic=traffic,
        admin_auth=admin_auth,
        vpn_key=vpn_key,
        billing=billing,
        migration=migration,
        referral=referral,
        k3s=k3s,
        entry_relay=entry_relay,
        entry_routing=entry_routing,
        subscriptions_expiration=subscriptions_expiration,
        wg_mesh=wg_mesh,
        s3=s3,
    )
