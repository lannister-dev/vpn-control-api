"""XRay Statistics Collector Service

This module provides APIs for querying traffic statistics from X-ray VPN nodes.

Typical usage example:

    # Initialize during app startup
    from services.xray_stats_collector.router import init_xray_clients

    nodes = {
        "us-1": ("xray-us-1.example.com", 10085),
        "eu-1": ("xray-eu-1.example.com", 10085),
    }
    init_xray_clients(nodes)

    # Then use the router in your FastAPI app
    from services.xray_stats_collector.router import router
    app.include_router(router)

    # Make requests to the API
    # POST /xray/traffic/user
    # GET /xray/traffic/user/{user_id}/node/{node_id}
    # GET /xray/health
"""

from services.xray_stats_collector.router import (
    get_multi_node_client,
    get_single_node_client,
    init_xray_clients,
    router,
)
from services.xray_stats_collector.schemas import (
    AllTrafficResponse,
    InboundTrafficResponse,
    NodeTrafficResponse,
    TrafficStats,
    #   UserTrafficError,
    UserTrafficRequest,
    UserTrafficResponse,
)
from services.xray_stats_collector.xray_client import (
    MultiNodeXRayClient,
    XRayConnectionError,
    XRayNotFoundError,
    XRayStatsClient,
    XRayStatsClientError,
    XRayTimeoutError,
)

__all__ = [
    # Router
    "router",
    "init_xray_clients",
    "get_multi_node_client",
    "get_single_node_client",
    # Client classes
    "XRayStatsClient",
    "MultiNodeXRayClient",
    # Exceptions
    "XRayStatsClientError",
    "XRayNotFoundError",
    "XRayConnectionError",
    "XRayTimeoutError",
    # Schemas
    "TrafficStats",
    "UserTrafficResponse",
    "UserTrafficRequest",
    "InboundTrafficResponse",
    "AllTrafficResponse",
    "NodeTrafficResponse",
    "UserTrafficError",
]
