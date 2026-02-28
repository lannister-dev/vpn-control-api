"""
Integration Examples for XRay Traffic Statistics Service

This file demonstrates how to integrate and use the XRay stats collector service
in your VPN Control API application.
"""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from services.xray_stats_collector import (
    get_multi_node_client,
    init_xray_clients,
)
from services.xray_stats_collector import (
    router as xray_router,
)

# ============================================================================
# Example 1: Basic Integration in app.py
# ============================================================================


def example_basic_integration():
    """
    Minimal integration example for the XRay stats service.

    This shows how to add XRay stats querying to your FastAPI app.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        print("Starting up XRay stats service...")

        # Configure your X-ray nodes
        xray_nodes = {
            "us-1": ("xray-us-1.example.com", 10085),
            "us-2": ("xray-us-2.example.com", 10085),
            "eu-1": ("xray-eu-1.example.com", 10085),
        }

        # Initialize the XRay clients
        init_xray_clients(xray_nodes, timeout_s=5)
        print(f"Initialized XRay clients for {len(xray_nodes)} nodes")

        yield

        # Shutdown
        print("Shutting down XRay stats service...")

    app = FastAPI(
        title="VPN Control API",
        lifespan=lifespan,
    )

    # Create API router and include XRay router
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(xray_router)
    app.include_router(api_router)

    return app


# ============================================================================
# Example 2: Custom Endpoints Using XRay Stats
# ============================================================================


def create_user_stats_router():
    """
    Example of creating custom endpoints that use XRay stats client.

    This demonstrates how to build application-specific features
    on top of the XRay stats service.
    """
    from fastapi import HTTPException, Query
    from pydantic import BaseModel

    router = APIRouter(prefix="/users", tags=["User Management"])

    class UserTrafficQuota(BaseModel):
        """User traffic quota model."""

        user_id: str
        total_quota_bytes: int
        used_bytes: int
        remaining_bytes: int
        used_percentage: float

    @router.get("/{user_id}/traffic-quota", response_model=UserTrafficQuota)
    async def get_user_traffic_quota(
        user_id: str,
        node_id: str = Query(..., description="Node ID to query"),
    ):
        """
        Get user traffic quota status.

        Combines XRay traffic data with user quota settings.
        """
        try:
            client = get_multi_node_client()

            # Query traffic from XRay
            traffic_data = client.get_user_traffic(user_id, node_id)
            used_bytes = traffic_data["total"]

            # Example: Assume 100GB quota per user
            quota_bytes = 100 * 1024 * 1024 * 1024  # 100GB
            remaining = max(0, quota_bytes - used_bytes)
            used_percentage = (used_bytes / quota_bytes) * 100

            return UserTrafficQuota(
                user_id=user_id,
                total_quota_bytes=quota_bytes,
                used_bytes=used_bytes,
                remaining_bytes=remaining,
                used_percentage=used_percentage,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{user_id}/traffic-summary")
    async def get_user_traffic_summary(user_id: str):
        """
        Get user traffic summary across all nodes.

        Aggregates traffic data from multiple nodes.
        """
        try:
            client = get_multi_node_client()

            # Get traffic from all nodes
            all_traffic = client.get_user_traffic_from_all_nodes(user_id)

            if not all_traffic:
                raise HTTPException(
                    status_code=404, detail=f"No traffic data found for user {user_id}"
                )

            # Aggregate totals
            total_uplink = sum(d["uplink"] for d in all_traffic.values())
            total_downlink = sum(d["downlink"] for d in all_traffic.values())
            total_traffic = total_uplink + total_downlink

            return {
                "user_id": user_id,
                "total_uplink_bytes": total_uplink,
                "total_downlink_bytes": total_downlink,
                "total_bytes": total_traffic,
                "nodes": len(all_traffic),
                "details": {
                    node_id: {
                        "uplink": data["uplink"],
                        "downlink": data["downlink"],
                        "total": data["total"],
                        "inbound": data["inbound"],
                    }
                    for node_id, data in all_traffic.items()
                },
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router


# ============================================================================
# Example 3: Monitoring and Alerting
# ============================================================================


def create_monitoring_router():
    """
    Example of using XRay stats for monitoring and alerting.

    This demonstrates how to build monitoring features on top of XRay stats.
    """
    from fastapi import Query

    router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

    @router.get("/nodes/status")
    async def get_nodes_status():
        """
        Check status of all XRay nodes.

        Useful for monitoring dashboards and alerting systems.
        """
        try:
            client = get_multi_node_client()
            nodes = client.get_available_nodes()

            status = {}
            for node_id in nodes:
                try:
                    # Try to query stats from the node
                    node_client = client.clients[node_id]
                    node_client.query_stats()
                    status[node_id] = {
                        "healthy": True,
                        "error": None,
                    }
                except Exception as e:
                    status[node_id] = {
                        "healthy": False,
                        "error": str(e),
                    }

            all_healthy = all(s["healthy"] for s in status.values())

            return {
                "overall_status": "healthy" if all_healthy else "degraded",
                "nodes": status,
            }
        except Exception as e:
            return {
                "overall_status": "down",
                "error": str(e),
            }

    @router.get("/inbounds/top-traffic")
    async def get_top_traffic_inbounds(
        node_id: str = Query(...),
        limit: int = Query(5, ge=1, le=50),
    ):
        """
        Get top inbounds by traffic usage.

        Useful for identifying heavily used inbounds.
        """
        try:
            client = get_multi_node_client()
            data = client.get_all_traffic(node_id)

            # Sort by total traffic
            inbounds = [
                {
                    "inbound": name,
                    "uplink": traffic["uplink"],
                    "downlink": traffic["downlink"],
                    "total": traffic["uplink"] + traffic["downlink"],
                }
                for name, traffic in data["inbounds"].items()
            ]

            inbounds.sort(key=lambda x: x["total"], reverse=True)

            return {
                "node_id": node_id,
                "top_inbounds": inbounds[:limit],
            }
        except Exception as e:
            return {"error": str(e)}

    return router


# ============================================================================
# Example 4: Complete App Setup
# ============================================================================


def create_complete_app():
    """
    Complete example of a VPN Control API with XRay stats integration.

    This shows how to combine multiple routers and services.
    """
    from datetime import datetime

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        print(f"[{datetime.now().isoformat()}] Starting VPN Control API...")

        # Initialize XRay stats service
        xray_nodes = {
            "us-east": ("192.168.1.10", 10085),
            "us-west": ("192.168.1.11", 10085),
            "eu-central": ("192.168.1.20", 10085),
            "asia-sg": ("192.168.1.30", 10085),
        }

        try:
            init_xray_clients(xray_nodes, timeout_s=5)
            print(
                f"[{datetime.now().isoformat()}] XRay clients initialized for {len(xray_nodes)} nodes"
            )
        except Exception as e:
            print(
                f"[{datetime.now().isoformat()}] Error initializing XRay clients: {e}"
            )

        yield

        # Shutdown
        print(f"[{datetime.now().isoformat()}] Shutting down VPN Control API...")

    app = FastAPI(
        title="VPN Control API",
        description="Complete VPN management API with traffic monitoring",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Main API router
    api_router = APIRouter(prefix="/api/v1")

    # Include XRay stats router
    api_router.include_router(xray_router, prefix="/xray")

    # Include custom routers
    api_router.include_router(create_user_stats_router())
    api_router.include_router(create_monitoring_router())

    app.include_router(api_router)

    # Health check endpoint
    @app.get("/health")
    async def health():
        """Simple health check endpoint."""
        return {"status": "ok"}

    return app


# ============================================================================
# Example 5: Usage Examples in Client Code
# ============================================================================


async def example_client_usage():
    """
    Example of how to use the XRay stats API from client code.

    This demonstrates various ways to interact with the API.
    """
    import httpx

    BASE_URL = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # Example 1: Check health
        print("Checking XRay health...")
        response = await client.get(f"{BASE_URL}/xray/health")
        print(response.json())

        # Example 2: Get user traffic from specific node
        print("\nGetting user traffic...")
        response = await client.post(
            f"{BASE_URL}/xray/traffic/user",
            json={
                "user_id": "user123@example.com",
                "node_id": "us-east",
                "inbound": "vless-ws",
            },
        )
        traffic = response.json()
        print(f"User traffic: {traffic['stats']['total']} bytes")

        # Example 3: Get user traffic from all nodes
        print("\nGetting user traffic from all nodes...")
        response = await client.get(f"{BASE_URL}/xray/traffic/user/user123@example.com")
        all_nodes = response.json()
        for node_id, data in all_nodes.items():
            print(f"{node_id}: {data['stats']['total']} bytes")

        # Example 4: Get inbound traffic
        print("\nGetting inbound traffic...")
        response = await client.get(
            f"{BASE_URL}/xray/traffic/inbound/vless-ws/node/us-east"
        )
        inbound = response.json()
        print(f"Inbound total: {inbound['stats']['total']} bytes")

        # Example 5: List available nodes
        print("\nListing available nodes...")
        response = await client.get(f"{BASE_URL}/xray/nodes")
        nodes = response.json()
        print(f"Available nodes: {nodes['nodes']}")


# ============================================================================
# Example 6: Environment Configuration
# ============================================================================


def example_configuration_from_env():
    """
    Example of loading XRay node configuration from environment variables.

    Useful for containerized deployments and multi-environment setups.
    """
    import json
    import os
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load XRay nodes from environment
        xray_nodes_json = os.getenv("XRAY_NODES", '{"default": ["localhost", 10085]}')

        try:
            xray_nodes_raw = json.loads(xray_nodes_json)
            xray_nodes = {
                node_id: (host, int(port))
                for node_id, (host, port) in xray_nodes_raw.items()
            }
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing XRAY_NODES: {e}")
            xray_nodes = {"default": ("localhost", 10085)}

        # Get timeout from environment
        timeout_s = int(os.getenv("XRAY_TIMEOUT_S", "5"))

        # Initialize
        init_xray_clients(xray_nodes, timeout_s=timeout_s)
        print(f"Initialized XRay with {len(xray_nodes)} nodes")

        yield

    app = FastAPI(lifespan=lifespan)
    return app


# ============================================================================
# Example 7: Caching Results
# ============================================================================


def example_with_caching():
    """
    Example of adding caching layer on top of XRay stats.

    This reduces load on XRay nodes by caching frequently requested data.
    """
    from datetime import datetime, timedelta
    from functools import lru_cache
    from typing import Optional

    class CachedTrafficResult:
        """Simple cache entry for traffic results."""

        def __init__(self, data, ttl_seconds=60):
            self.data = data
            self.cached_at = datetime.now()
            self.ttl_seconds = ttl_seconds

        def is_expired(self) -> bool:
            """Check if cache entry has expired."""
            age = (datetime.now() - self.cached_at).total_seconds()
            return age > self.ttl_seconds

    class CachedXRayClient:
        """Wrapper around XRay client with caching."""

        def __init__(self, ttl_seconds=60):
            self.ttl_seconds = ttl_seconds
            self.cache: dict[str, CachedTrafficResult] = {}

        async def get_user_traffic(self, user_id: str, node_id: str):
            """Get user traffic with caching."""
            cache_key = f"{user_id}:{node_id}"

            # Check cache
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if not cached.is_expired():
                    print(f"Cache hit for {cache_key}")
                    return cached.data

            # Cache miss - query XRay
            print(f"Cache miss for {cache_key} - querying XRay")
            client = get_multi_node_client()
            data = client.get_user_traffic(user_id, node_id)

            # Store in cache
            self.cache[cache_key] = CachedTrafficResult(data, self.ttl_seconds)

            return data

        def clear_cache(self, user_id: Optional[str] = None):
            """Clear cache entries."""
            if user_id:
                # Clear specific user
                to_delete = [k for k in self.cache if k.startswith(user_id)]
                for k in to_delete:
                    del self.cache[k]
            else:
                # Clear all
                self.cache.clear()

    return CachedXRayClient(ttl_seconds=60)


# ============================================================================
# If running this file directly, create and run the complete app
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Create the complete app
    app = create_complete_app()

    # Run the app
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
