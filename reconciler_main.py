import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from services.admin_transport.models import NatsProcessedMsgLog  # noqa: F401
from services.admin_transport.reconcilers.cleanup import AdminTransportCleanupReconciler
from services.artifacts.models import ProfileArtifact  # noqa: F401
from services.auth.admin.models import AdminAuditEvent, AdminSession, AdminUser  # noqa: F401
from services.billing.models import BalanceTransaction, PaymentOrder  # noqa: F401
from services.billing.reconcilers.expiration import BillingOrderExpirationReconciler
from services.config import get_settings
from services.entry.models import EntryBackendAssignment  # noqa: F401
from services.entry.reconcilers.auto_drain import EntryAutoDrainReconciler
from services.nodes.agent.model import (  # noqa: F401
    NodeTransportEventLog,
    NodeTransportOutbox,
    NodeTransportState,
)
from services.nodes.agent.runtime import NodeAgentRuntime
from services.nodes.models import NodeAgentIdentity, NodeAgentState, VpnNode  # noqa: F401
from services.nodes.reconcilers.placement import NodePlacementReconciler
from services.nodes.reconcilers.upstream_failover import UpstreamFailoverReconciler
from services.placements.model import UserPlacement  # noqa: F401
from services.placements.reconcilers.error_retry import PlacementErrorRetryReconciler
from services.placements.reconcilers.rebalance import PlacementRebalanceReconciler
from services.plans.models import Plan  # noqa: F401
from services.probe.model import ProbeSignal  # noqa: F401
from services.probe.reconcilers.auto_drain import ProbeAutoDrainReconciler
from services.probe.reconcilers.cleanup import ProbeSignalCleanupReconciler
from services.probe.reconcilers.synthetic import ProbeSyntheticCredentialReconciler
from services.routes.model import Route, TransportProfile  # noqa: F401
from services.routes.reconcilers.warmup import RouteWarmupReconciler
from services.routing.entry.publisher import EntryRoutingPublisher
from services.support.consumer import SupportInboundConsumer, SupportSentConsumer
from services.support.models import SupportTicket  # noqa: F401
from services.traffic.nodes.consumer import NodeTrafficNatsConsumer
from services.traffic.nodes.model import NodeTrafficUsage  # noqa: F401
from services.traffic.nodes.reconcilers.cleanup import NodeTrafficHistoryCleanupReconciler
from services.traffic.policy.model import TrafficPolicy  # noqa: F401
from services.traffic.users.consumer import UserTrafficNatsConsumer
from services.traffic.users.model import TrafficUsage  # noqa: F401
from services.traffic.users.reconcilers.cleanup import TrafficHistoryCleanupReconciler
from services.traffic.users.reconcilers.reset import TrafficResetReconciler

# Register all SQLAlchemy models (no routers to pull them in)
from services.users.models import User  # noqa: F401
from services.vpn.keys.models import KeyAssignment, VpnKey  # noqa: F401
from services.vpn.keys.reconcilers.backend_rebalance import BackendRebalanceReconciler
from services.vpn.keys.reconcilers.expiration import VpnKeyExpirationReconciler
from services.vpn.subscriptions.model import Subscription, SubscriptionDevice, SubscriptionDeviceKey  # noqa: F401
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
from shared.reconciler.watchdog import watchdog
from shared.utils.logger import StructuredLogger

configure_root_logging()
logger = StructuredLogger(logging.getLogger("reconciler-worker"))

_METRICS_EXPORT_INTERVAL_SEC = 10


def _build_reconcilers() -> list:
    return [
        RouteWarmupReconciler(),
        ProbeSignalCleanupReconciler(),
        ProbeAutoDrainReconciler(),
        ProbeSyntheticCredentialReconciler(),
        NodePlacementReconciler(),
        TrafficHistoryCleanupReconciler(),
        NodeTrafficHistoryCleanupReconciler(),
        AdminTransportCleanupReconciler(),
        TrafficResetReconciler(),
        PlacementErrorRetryReconciler(),
        PlacementRebalanceReconciler(),
        VpnKeyExpirationReconciler(),
        SubscriptionExpirationReconciler(),
        BillingOrderExpirationReconciler(),
        EntryAutoDrainReconciler(),
        UpstreamFailoverReconciler(),
        EntryRoutingPublisher(),
        BackendRebalanceReconciler(),
        WgMeshPeerPublisher(),
    ]


def _build_nats_runtimes(nats_settings) -> list:
    return [
        NodeAgentRuntime(nats_settings),
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
    reconcilers = _build_reconcilers()
    runtimes = _build_nats_runtimes(settings.nats)

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
        logger.info("reconciler_worker_stopped")


app = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

add_healthz(app)
add_reconciler_healthz(app)


if __name__ == "__main__":
    uvicorn.run("reconciler_main:app", host="0.0.0.0", port=8081)
