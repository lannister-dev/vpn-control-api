# XRay Traffic Statistics Service

A comprehensive Python API service for querying traffic statistics from X-ray VPN nodes. This service provides real-time insights into user and inbound traffic usage across multiple X-ray instances.

## Features

- **Multi-node Support**: Query traffic statistics from multiple X-ray instances simultaneously
- **User Traffic Tracking**: Get uplink, downlink, and total traffic for specific users
- **Inbound Statistics**: Monitor traffic on specific inbounds (VLESS-WS, VLESS-XHTTP, etc.)
- **Aggregate Metrics**: View total traffic across all inbounds on a node
- **Error Handling**: Comprehensive error handling with meaningful HTTP status codes
- **Health Checks**: Monitor connectivity to X-ray API endpoints
- **Type Safety**: Full Pydantic model validation
- **Async/Await**: Fully async API using FastAPI

## Installation

The service is part of the VPN Control API. Ensure you have the required dependencies:

```bash
pip install fastapi pydantic prometheus-client
```

## Configuration

### Initialize During App Startup

In your main `app.py`:

```python
from fastapi import FastAPI
from services.xray_stats_collector import router, init_xray_clients

app = FastAPI()

# Configure your X-ray nodes
nodes = {
    "us-1": ("192.168.1.100", 10085),
    "us-2": ("192.168.1.101", 10085),
    "eu-1": ("192.168.1.200", 10085),
    "eu-2": ("192.168.1.201", 10085),
}

# Initialize the XRay clients
init_xray_clients(nodes, timeout_s=5)

# Include the router
app.include_router(router, prefix="/api/v1")
```

## API Endpoints

### Health Check

Check connectivity to X-ray nodes.

**GET** `/xray/health`

```bash
curl -X GET http://localhost:8000/api/v1/xray/health
```

**Response (200 OK)**:
```json
{
  "status": "healthy",
  "nodes": {
    "us-1": {"status": "healthy"},
    "us-2": {"status": "healthy"},
    "eu-1": {"status": "healthy"}
  }
}
```

### Get User Traffic (Recommended)

Query traffic for a specific user on a specific node.

**POST** `/xray/traffic/user`

**Request Body**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_id": "us-1",
  "inbound": "vless-ws"
}
```

**Example with Python requests**:
```python
import requests

url = "http://localhost:8000/api/v1/xray/traffic/user"
payload = {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "node_id": "us-1",
    "inbound": "vless-ws"
}

response = requests.post(url, json=payload)
data = response.json()

print(f"Upload: {data['stats']['uplink']} bytes")
print(f"Download: {data['stats']['downlink']} bytes")
print(f"Total: {data['stats']['total']} bytes")
```

**Response (200 OK)**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_id": "us-1",
  "inbound": "vless-ws",
  "stats": {
    "uplink": 1024000,
    "downlink": 2048000,
    "total": 3072000
  },
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Response (404 Not Found)**:
```json
{
  "detail": "No traffic data found for user 550e8400-e29b-41d4-a716-446655440000"
}
```

### Get User Traffic by Path

Alternative endpoint using path parameters.

**GET** `/xray/traffic/user/{user_id}/node/{node_id}`

**Parameters**:
- `user_id` (string, required): User ID or UUID
- `node_id` (string, required): Node identifier
- `inbound` (string, optional): Inbound name filter

**Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/xray/traffic/user/550e8400-e29b-41d4-a716-446655440000/node/us-1?inbound=vless-ws"
```

### Get User Traffic from All Nodes

Query traffic for a user across all configured nodes.

**GET** `/xray/traffic/user/{user_id}`

**Parameters**:
- `user_id` (string, required): User ID or UUID
- `inbound` (string, optional): Inbound name filter

**Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/xray/traffic/user/550e8400-e29b-41d4-a716-446655440000"
```

**Response (200 OK)**:
```json
{
  "us-1": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "node_id": "us-1",
    "inbound": "vless-ws",
    "stats": {
      "uplink": 1024000,
      "downlink": 2048000,
      "total": 3072000
    },
    "updated_at": "2024-01-15T10:30:00Z"
  },
  "eu-1": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "node_id": "eu-1",
    "inbound": "vless-tcp",
    "stats": {
      "uplink": 512000,
      "downlink": 1024000,
      "total": 1536000
    },
    "updated_at": "2024-01-15T10:30:00Z"
  }
}
```

### Get Inbound Traffic

Query traffic statistics for a specific inbound on a node.

**GET** `/xray/traffic/inbound/{inbound}/node/{node_id}`

**Parameters**:
- `inbound` (string, required): Inbound name (e.g., 'vless-ws', 'vless-xhttp', 'vless-tcp')
- `node_id` (string, required): Node identifier

**Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/xray/traffic/inbound/vless-ws/node/us-1"
```

**Response (200 OK)**:
```json
{
  "inbound": "vless-ws",
  "node_id": "us-1",
  "stats": {
    "uplink": 10240000,
    "downlink": 20480000,
    "total": 30720000
  },
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### Get All Traffic from Node

Get aggregated traffic statistics for all inbounds on a node.

**GET** `/xray/traffic/node/{node_id}`

**Parameters**:
- `node_id` (string, required): Node identifier

**Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/xray/traffic/node/us-1"
```

**Response (200 OK)**:
```json
{
  "inbounds": [
    {
      "inbound": "vless-ws",
      "node_id": "us-1",
      "stats": {
        "uplink": 10240000,
        "downlink": 20480000,
        "total": 30720000
      }
    },
    {
      "inbound": "vless-xhttp",
      "node_id": "us-1",
      "stats": {
        "uplink": 5120000,
        "downlink": 10240000,
        "total": 15360000
      }
    }
  ],
  "total": {
    "uplink": 15360000,
    "downlink": 30720000,
    "total": 46080000
  }
}
```

### List Available Nodes

Get the list of configured X-ray nodes.

**GET** `/xray/nodes`

**Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/xray/nodes"
```

**Response (200 OK)**:
```json
{
  "nodes": ["us-1", "us-2", "eu-1", "eu-2"],
  "count": 4
}
```

## Error Responses

The API returns standardized error responses:

### 404 Not Found
```json
{
  "detail": "No traffic data found for user {user_id}"
}
```

### 503 Service Unavailable
```json
{
  "detail": "XRay service unavailable"
}
```

### 504 Gateway Timeout
```json
{
  "detail": "XRay API timeout"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

## X-ray Stats Query Format

The service queries X-ray's statistics API using the `QueryStats` command. The stats are returned in a format like:

```
inbound>>>vless-ws>>>uplink: 1024000
inbound>>>vless-ws>>>downlink: 2048000
inbound>>>vless-ws>>>user>>>email@example.com>>>uplink: 512000
inbound>>>vless-ws>>>user>>>email@example.com>>>downlink: 1024000
```

The service automatically parses this format to provide structured JSON responses.

## Using the Client Directly

For advanced use cases, you can use the client classes directly:

### Single Node Client

```python
from services.xray_stats_collector import XRayStatsClient

# Create a client for a specific node
client = XRayStatsClient(host="192.168.1.100", port=10085, timeout_s=5)

# Get user traffic
try:
    traffic = client.get_user_traffic(
        user_id="550e8400-e29b-41d4-a716-446655440000",
        inbound="vless-ws"
    )
    print(f"User traffic: {traffic}")
except Exception as e:
    print(f"Error: {e}")
```

### Multi-Node Client

```python
from services.xray_stats_collector import MultiNodeXRayClient

# Create a client for multiple nodes
nodes = {
    "us-1": ("192.168.1.100", 10085),
    "eu-1": ("192.168.1.200", 10085),
}

client = MultiNodeXRayClient(nodes, timeout_s=5)

# Get traffic from specific node
try:
    traffic = client.get_user_traffic(
        user_id="550e8400-e29b-41d4-a716-446655440000",
        node_id="us-1"
    )
    print(f"Traffic: {traffic}")
except Exception as e:
    print(f"Error: {e}")

# Get traffic from all nodes
try:
    all_traffic = client.get_user_traffic_from_all_nodes(
        user_id="550e8400-e29b-41d4-a716-446655440000"
    )
    for node_id, traffic in all_traffic.items():
        print(f"{node_id}: {traffic}")
except Exception as e:
    print(f"Error: {e}")
```

## Exception Handling

The service provides specific exception types for different error scenarios:

```python
from services.xray_stats_collector import (
    XRayStatsClientError,
    XRayNotFoundError,
    XRayConnectionError,
    XRayTimeoutError,
)

try:
    traffic = client.get_user_traffic("user-id")
except XRayNotFoundError:
    print("User has no traffic data")
except XRayConnectionError:
    print("Cannot connect to XRay API")
except XRayTimeoutError:
    print("XRay API request timed out")
except XRayStatsClientError as e:
    print(f"Other error: {e}")
```

## Performance Considerations

- **Caching**: Consider implementing caching for frequently queried statistics to reduce load on X-ray nodes
- **Batch Queries**: Use the "get from all nodes" endpoints when possible instead of making multiple requests
- **Timeouts**: Default timeout is 5 seconds. Adjust based on your network conditions
- **Connection Pooling**: The client creates new connections for each request. For production, consider implementing connection pooling

## Monitoring

The service logs all operations. Enable debug logging to see detailed information:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

Log messages include:
- Node registration and initialization
- Successful queries
- Connection errors
- Timeouts
- Parse errors

## Testing

Example test cases:

```python
import pytest
from services.xray_stats_collector import XRayStatsClient

def test_get_user_traffic():
    client = XRayStatsClient("localhost", 10085)
    traffic = client.get_user_traffic("test-user-id")
    
    assert traffic["user_id"] == "test-user-id"
    assert traffic["uplink"] > 0
    assert traffic["downlink"] > 0
    assert traffic["total"] == traffic["uplink"] + traffic["downlink"]

def test_user_not_found():
    client = XRayStatsClient("localhost", 10085)
    
    with pytest.raises(XRayNotFoundError):
        client.get_user_traffic("non-existent-user")
```

## Architecture

```
┌─────────────────────────────────────┐
│        FastAPI Application          │
└──────────────────┬──────────────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │  Router (endpoints)  │
         └──────────┬───────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
         ▼                     ▼
    ┌──────────────┐   ┌──────────────────────┐
    │ Single Node  │   │  Multi-Node Client   │
    │  XRayClient  │   │  (coordinates nodes) │
    └──────┬───────┘   └──────────┬───────────┘
           │                      │
           │              ┌───────┴───────┐
           │              │               │
           ▼              ▼               ▼
         ┌──────────────────────────────────────┐
         │   X-ray API Nodes (gRPC/JSON)       │
         │   - us-1, us-2, eu-1, eu-2, ...     │
         └──────────────────────────────────────┘
```

## Contributing

When contributing to this service:

1. Add type hints to all functions
2. Include docstrings with parameters and return types
3. Add error handling for all network operations
4. Include logging statements for debugging
5. Add tests for new functionality

## License

Part of the Pasha Dev VPN Control API project.