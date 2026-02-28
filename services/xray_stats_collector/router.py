"""FastAPI router for XRay traffic statistics API."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from services.xray_stats_collector.schemas import (
    AllTrafficResponse,
    InboundTrafficResponse,
    NodeTrafficResponse,
    TrafficStats,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xray", tags=["XRay Traffic Statistics"])

# Global client instances - should be initialized from config
# This will be set up during app startup
_single_node_client: Optional[XRayStatsClient] = None
_multi_node_client: Optional[MultiNodeXRayClient] = None


def init_xray_clients(
    nodes: dict[str, tuple[str, int]],
    timeout_s: int = 5,
) -> None:
    """Initialize XRay clients.

    Args:
        nodes: Dictionary mapping node_id to (host, port) tuples
        timeout_s: Connection timeout in seconds

    Example:
        nodes = {
            "us-1": ("192.168.1.1", 10085),
            "eu-1": ("192.168.1.2", 10085),
        }
        init_xray_clients(nodes)
    """
    global _single_node_client, _multi_node_client

    if not nodes:
        logger.warning("No XRay nodes configured")
        return

    _multi_node_client = MultiNodeXRayClient(nodes, timeout_s)

    # Use first node as default single-node client for backward compatibility
    first_node_id = next(iter(nodes))
    host, port = nodes[first_node_id]
    _single_node_client = XRayStatsClient(host, port, timeout_s)

    logger.info(f"XRay clients initialized with {len(nodes)} nodes")


def get_multi_node_client() -> MultiNodeXRayClient:
    """Get multi-node client instance.

    Returns:
        MultiNodeXRayClient instance

    Raises:
        HTTPException: If client not initialized
    """
    if _multi_node_client is None:
        raise HTTPException(
            status_code=503,
            detail="XRay clients not initialized. Check configuration.",
        )
    return _multi_node_client


def get_single_node_client() -> XRayStatsClient:
    """Get single-node client instance.

    Returns:
        XRayStatsClient instance

    Raises:
        HTTPException: If client not initialized
    """
    if _single_node_client is None:
        raise HTTPException(
            status_code=503,
            detail="XRay client not initialized. Check configuration.",
        )
    return _single_node_client


# ============================================================================
# Health Check Endpoints
# ============================================================================


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check for XRay API connectivity.

    Returns:
        Health status for all configured nodes
    """
    try:
        client = get_multi_node_client()
        nodes = client.get_available_nodes()

        if not nodes:
            raise HTTPException(status_code=503, detail="No XRay nodes configured")

        health_status = {}
        for node_id in nodes:
            try:
                client_instance = client.clients[node_id]
                client_instance.query_stats()
                health_status[node_id] = {"status": "healthy"}
            except Exception as e:
                health_status[node_id] = {"status": "unhealthy", "error": str(e)}

        all_healthy = all(h["status"] == "healthy" for h in health_status.values())

        return {
            "status": "healthy" if all_healthy else "degraded",
            "nodes": health_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="XRay service unavailable")


# ============================================================================
# User Traffic Endpoints
# ============================================================================


@router.post(
    "/traffic/user",
    response_model=UserTrafficResponse,
    # responses={
    #    404: {"model": HTTPException, "description": "User traffic not found"},
    #    503: {"model": HTTPException, "description": "XRay service unavailable"},
    #    504: {"model": HTTPException, "description": "XRay API timeout"},
    # },
)
async def get_user_traffic(
    request: UserTrafficRequest = Body(...),
) -> UserTrafficResponse:
    """Get traffic statistics for a user on a specific node.

    This endpoint allows you to query the traffic usage of a user on any configured node.
    You need to provide the user_id and node_id, with an optional inbound filter.

    Args:
        request: Request containing user_id, node_id, and optional inbound

    Returns:
        UserTrafficResponse with uplink, downlink, and total traffic in bytes

    Raises:
        HTTPException 404: User has no traffic data
        HTTPException 503: XRay service unavailable
        HTTPException 504: XRay API timeout
    """
    try:
        client = get_multi_node_client()
        data = client.get_user_traffic(
            user_id=request.user_id,
            node_id=request.node_id,
            inbound=request.inbound,
        )

        return UserTrafficResponse(
            user_id=data["user_id"],
            node_id=data["node_id"],
            inbound=data["inbound"],
            stats=TrafficStats(
                uplink=data["uplink"],
                downlink=data["downlink"],
                total=data["total"],
            ),
            updated_at=data.get("timestamp"),
        )
    except XRayNotFoundError as e:
        logger.warning(f"Traffic data not found: {e}")
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )
    except XRayTimeoutError as e:
        logger.error(f"XRay API timeout: {e}")
        raise HTTPException(
            status_code=504,
            detail="XRay API timeout",
        )
    except XRayConnectionError as e:
        logger.error(f"Cannot connect to XRay: {e}")
        raise HTTPException(
            status_code=503,
            detail="XRay service unavailable",
        )
    except XRayStatsClientError as e:
        logger.error(f"XRay client error: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting user traffic: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


@router.get(
    "/traffic/user/{user_id}/node/{node_id}",
    response_model=UserTrafficResponse,
)
async def get_user_traffic_by_path(
    user_id: str = Path(..., description="User ID or UUID"),
    node_id: str = Path(..., description="Node identifier"),
    inbound: Optional[str] = Query(None, description="Optional inbound name filter"),
) -> UserTrafficResponse:
    """Get traffic statistics for a user on a specific node (using path parameters).

    Args:
        user_id: User identifier or UUID
        node_id: Node identifier
        inbound: Optional inbound name to filter by

    Returns:
        UserTrafficResponse with traffic statistics
    """
    request = UserTrafficRequest(
        user_id=user_id,
        node_id=node_id,
        inbound=inbound,
    )
    return await get_user_traffic(request)


@router.get(
    "/traffic/user/{user_id}",
    response_model=dict[str, UserTrafficResponse],
)
async def get_user_traffic_all_nodes(
    user_id: str,
    inbound: Optional[str] = Query(None, description="Optional inbound filter"),
) -> dict[str, UserTrafficResponse]:
    """Get traffic statistics for a user across all configured nodes.

    Args:
        user_id: User identifier or UUID
        inbound: Optional inbound name to filter by

    Returns:
        Dictionary mapping node_id to UserTrafficResponse
    """
    try:
        client = get_multi_node_client()
        results = client.get_user_traffic_from_all_nodes(user_id, inbound)

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No traffic data found for user {user_id} on any node",
            )

        response = {}
        for node_id, data in results.items():
            response[node_id] = UserTrafficResponse(
                user_id=data["user_id"],
                node_id=data["node_id"],
                inbound=data["inbound"],
                stats=TrafficStats(
                    uplink=data["uplink"],
                    downlink=data["downlink"],
                    total=data["total"],
                ),
                updated_at=data.get("timestamp"),
            )

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user traffic from all nodes: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


# ============================================================================
# Inbound Traffic Endpoints
# ============================================================================


@router.get(
    "/traffic/inbound/{inbound}/node/{node_id}",
    response_model=InboundTrafficResponse,
)
async def get_inbound_traffic(
    inbound: str = Path(..., description="Inbound name"),
    node_id: str = Path(..., description="Node identifier"),
) -> InboundTrafficResponse:
    """Get traffic statistics for a specific inbound on a node.

    Args:
        inbound: Inbound name (e.g., 'vless-ws', 'vless-xhttp', 'vless-tcp')
        node_id: Node identifier

    Returns:
        InboundTrafficResponse with traffic statistics
    """
    try:
        client = get_multi_node_client()
        data = client.get_inbound_traffic(inbound=inbound, node_id=node_id)

        return InboundTrafficResponse(
            inbound=data["inbound"],
            node_id=data["node_id"],
            stats=TrafficStats(
                uplink=data["uplink"],
                downlink=data["downlink"],
                total=data["total"],
            ),
            updated_at=data.get("timestamp"),
        )
    except XRayNotFoundError as e:
        logger.warning(f"Inbound traffic not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except XRayStatsClientError as e:
        logger.error(f"Error getting inbound traffic: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting inbound traffic: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Aggregate Traffic Endpoints
# ============================================================================


@router.get(
    "/traffic/node/{node_id}",
    response_model=AllTrafficResponse,
)
async def get_node_all_traffic(
    node_id: str,
) -> AllTrafficResponse:
    """Get all traffic statistics aggregated by inbound for a node.

    Args:
        node_id: Node identifier

    Returns:
        AllTrafficResponse with all inbounds and totals
    """
    try:
        client = get_multi_node_client()
        data = client.get_all_traffic(node_id)

        inbounds_response = [
            InboundTrafficResponse(
                inbound=name,
                node_id=node_id,
                stats=TrafficStats(
                    uplink=traffic["uplink"],
                    downlink=traffic["downlink"],
                    total=traffic["uplink"] + traffic["downlink"],
                ),
            )
            for name, traffic in data["inbounds"].items()
        ]

        return AllTrafficResponse(
            inbounds=inbounds_response,
            total=TrafficStats(
                uplink=data["total_uplink"],
                downlink=data["total_downlink"],
                total=data["total_traffic"],
            ),
        )
    except XRayStatsClientError as e:
        logger.error(f"Error getting node traffic: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting node traffic: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Node Management Endpoints
# ============================================================================


@router.get(
    "/nodes",
    response_model=dict,
)
async def list_nodes() -> dict:
    """Get list of all configured XRay nodes.

    Returns:
        Dictionary with list of node identifiers
    """
    try:
        client = get_multi_node_client()
        nodes = client.get_available_nodes()
        return {
            "nodes": nodes,
            "count": len(nodes),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing nodes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Legacy Single-Node Endpoints (for backward compatibility)
# ============================================================================


@router.get(
    "/stats/user/{user_id}",
    response_model=UserTrafficResponse,
    deprecated=True,
)
async def get_user_traffic_legacy(
    user_id: str,
    inbound: Optional[str] = Query(None),
) -> UserTrafficResponse:
    """Get traffic statistics for a user (legacy endpoint).

    This endpoint is deprecated. Use POST /xray/traffic/user instead.

    Args:
        user_id: User identifier
        inbound: Optional inbound filter

    Returns:
        UserTrafficResponse with traffic statistics
    """
    try:
        if _multi_node_client and _multi_node_client.get_available_nodes():
            # Use first available node
            node_id = _multi_node_client.get_available_nodes()[0]
            data = _multi_node_client.get_user_traffic(user_id, node_id, inbound)
        else:
            # Fallback to single node client
            client = get_single_node_client()
            data = client.get_user_traffic(user_id, inbound)
            data["node_id"] = "default"

        return UserTrafficResponse(
            user_id=data["user_id"],
            node_id=data.get("node_id", "default"),
            inbound=data["inbound"],
            stats=TrafficStats(
                uplink=data["uplink"],
                downlink=data["downlink"],
                total=data["total"],
            ),
            updated_at=data.get("timestamp"),
        )
    except XRayNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except XRayStatsClientError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in legacy endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
