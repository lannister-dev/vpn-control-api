import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from services.admin.transport.models import NatsProcessedMsgLog  # noqa: F401
from services.admin.transport.reconcilers.cleanup import AdminTransportCleanupReconciler
from services.alerts.reconcilers.cleanup import AlertsCleanupReconciler
from services.artifacts.models import ProfileArtifact  # noqa: F401
from services.auth.admin.models import AdminAuditEvent, AdminSession, AdminUser  # noqa: F401
from services.billing.models import BalanceTransaction, PaymentOrder  # noqa: F401
from services.billing.reconcilers.expiration import BillingOrderExpirationReconciler
from services.config import get_settings
from services.entry.models import EntryBackendAssignment  # noqa: F401
from services.entry.reconcilers.auto_drain import EntryAutoDrainReconciler
from services.nodes.agent.models import (  # noqa: F401
    NodeTransportEventLog,
    NodeTransportOutbox,
    NodeTransportState,
)
from services.nodes.agent.runtime import NodeAgentRuntime
from services.nodes.models import NodeAgentIdentity, NodeAgentState, VpnNode  # noqa: F401
from services.nodes.reconcilers.placement import NodePlacementReconciler
from services.nodes.reconcilers.upstream_failover import UpstreamFailoverReconciler
from services.notifications.reconciller.digest import NotificationsDigestReconciler
from services.notifications.service import NotificationService
from services.placements.models import UserPlacement  # noqa: F401
from services.placements.reconcilers.error_retry import PlacementErrorRetryReconciler
from services.placements.reconcilers.rebalance import PlacementRebalanceReconciler
from services.placements.reconcilers.role_invalidator import PlacementNodeRoleInvalidator
from services.plans.models import Plan  # noqa: F401
from services.probe.models import ProbeSignal  # noqa: F401
from services.probe.reconcilers.auto_drain import ProbeAutoDrainReconciler
from services.probe.reconcilers.cleanup import ProbeSignalCleanupReconciler
from services.probe.reconcilers.synthetic import ProbeSyntheticCredentialReconciler
from services.routes.models import Route, TransportProfile  # noqa: F401
from services.routes.reconcilers.auto_create import RouteAutoCreateReconciler
from services.routes.reconcilers.warmup import RouteWarmupReconciler
from services.routing.entry.publisher import EntryRoutingPublisher
from services.support.consumer import SupportInboundConsumer, SupportSentConsumer
from services.support.models import SupportTicket  # noqa: F401
from services.support.reconcilers.broadcast_scheduler import BroadcastSchedulerReconciler
from services.traffic.nodes.consumer import NodeTrafficNatsConsumer
from services.traffic.nodes.models import NodeTrafficUsage  # noqa: F401
from services.traffic.nodes.reconcilers.cleanup import NodeTrafficHistoryCleanupReconciler
from services.traffic.policy.models import TrafficPolicy  # noqa: F401
from services.traffic.users.consumer import UserTrafficNatsConsumer
from services.traffic.users.models import TrafficUsage  # noqa: F401
from services.traffic.users.reconcilers.cleanup import TrafficHistoryCleanupReconciler
from services.traffic.users.reconcilers.reset import TrafficResetReconciler

# Register all SQLAlchemy models (no routers to pull them in)
from services.users.models import User  # noqa: F401
from services.vpn.keys.models import KeyAssignment, VpnKey  # noqa: F401
from services.vpn.keys.reconcilers.backend_rebalance import BackendRebalanceReconciler
from services.vpn.keys.reconcilers.expiration import VpnKeyExpirationReconciler
from services.vpn.subscriptions.models import Subscription, SubscriptionDevice, SubscriptionDeviceKey  # noqa: F401
from services.vpn.subscriptions.reconcilers.assignment_invalidator import SubscriptionAssignmentInvalidator
from services.vpn.subscriptions.reconcilers.expiration import SubscriptionExpirationReconciler
from services.wg.publisher import WgMeshPeerPublisher
from shared.app.bootstrap import (
    bootstrap_profiles,
    configure_root_logging,
    connect_redis,
)
from shared.app.healthz import add_healthz, add_reconciler_healthz
from shared.monitoring.metrics import (
    RECONCILER_ALIVE,
    RECONCILER_MAX_SILENCE_SECONDS,
    RECONCILER_SILENCE_SECONDS,
)
from shared.nats.client import NatsClient
from shared.reconciler.watchdog import watchdog
from shared.utils.logger import StructuredLogger

configure_root_logging()
logger = StructuredLogger(logging.getLogger("reconciler-worker"))

_METRICS_EXPORT_INTERVAL_SEC = 10


def _build_reconcilers(notifications: NotificationService, nats_client: NatsClient | None) -> list:
    return [
        RouteWarmupReconciler(),
        RouteAutoCreateReconciler(),
        ProbeSignalCleanupReconciler(),
        ProbeAutoDrainReconciler(),
        ProbeSyntheticCredentialReconciler(),
        NodePlacementReconciler(notifications=notifications),
        TrafficHistoryCleanupReconciler(),
        NodeTrafficHistoryCleanupReconciler(),
        AdminTransportCleanupReconciler(),
        AlertsCleanupReconciler(),
        TrafficResetReconciler(),
        PlacementErrorRetryReconciler(),
        PlacementRebalanceReconciler(),
        VpnKeyExpirationReconciler(),
        SubscriptionExpirationReconciler(),
        SubscriptionAssignmentInvalidator(),
        PlacementNodeRoleInvalidator(),
        BillingOrderExpirationReconciler(),
        EntryAutoDrainReconciler(),
        UpstreamFailoverReconciler(),
        EntryRoutingPublisher(),
        BackendRebalanceReconciler(),
        WgMeshPeerPublisher(),
        NotificationsDigestReconciler(notifications=notifications),
        BroadcastSchedulerReconciler(nats_client=nats_client),
    ]


def _build_nats_runtimes(nats_settings, notifications: NotificationService) -> list:
    return [
        NodeAgentRuntime(nats_settings, notifications=notifications),
        UserTrafficNatsConsumer(nats_settings),
        NodeTrafficNatsConsumer(nats_settings),
        SupportInboundConsumer(nats_settings),
        SupportSentConsumer(nats_settings),
    ]


async def _export_watchdog_metrics(stop: asyncio.Event):
    while not stop.is_set():
        for s in watchdog.statuses():
            RECONCILER_SILENCE_SECONDS.labels(name=s.name).set(s.silence_sec)
            RECONCILER_MAX_SILENCE_SECONDS.labels(name=s.name).set(s.max_silence_sec)
            RECONCILER_ALIVE.labels(name=s.name).set(1 if s.alive else 0)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_METRICS_EXPORT_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_redis(logger)
    await bootstrap_profiles(logger)

    settings = get_settings()
    notifications_nats: NatsClient | None = None
    try:
        notifications_nats = NatsClient(settings.nats)
        await notifications_nats.connect()
    except Exception:
        logger.exception("notifications_nats_connect_failed")
        notifications_nats = None
    notifications = NotificationService(notifications_nats)
    app.state.notifications = notifications

    reconcilers = _build_reconcilers(notifications, notifications_nats)
    runtimes = _build_nats_runtimes(settings.nats, notifications)

    for r in reconcilers:
        watchdog.register(r.__class__.__name__)
        await r.start()
    for r in runtimes:
        await r.start()

    logger.info("reconciler_worker_ready", count=len(reconcilers) + len(runtimes))

    metrics_stop = asyncio.Event()
    metrics_task = asyncio.create_task(_export_watchdog_metrics(metrics_stop))

    try:
        yield
    finally:
        metrics_stop.set()
        await metrics_task
        for r in reversed(runtimes):
            await r.stop()
        for r in reversed(reconcilers):
            await r.stop()
        if notifications_nats is not None:
            try:
                await notifications_nats.close()
            except Exception:
                logger.exception("notifications_nats_close_failed")
        logger.info("reconciler_worker_stopped")


app = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

add_healthz(app)
add_reconciler_healthz(app)


if __name__ == "__main__":
    uvicorn.run("reconciler_main:app", host="0.0.0.0", port=8081)
