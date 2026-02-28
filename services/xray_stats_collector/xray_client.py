"""XRay Stats Client for querying traffic statistics from XRay nodes."""

import json
import logging
import socket
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class XRayStatsClientError(Exception):
    """Base exception for XRay stats client errors."""

    pass


class XRayConnectionError(XRayStatsClientError):
    """Exception raised when connection to XRay fails."""

    pass


class XRayTimeoutError(XRayStatsClientError):
    """Exception raised when XRay API request times out."""

    pass


class XRayNotFoundError(XRayStatsClientError):
    """Exception raised when requested data is not found."""

    pass


class XRayStatsClient:
    """Client for querying XRay statistics API.

    Supports both single-node and multi-node configurations.
    """

    def __init__(self, host: str = "localhost", port: int = 10085, timeout_s: int = 5):
        """Initialize XRay stats client.

        Args:
            host: XRay API host
            port: XRay API port
            timeout_s: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        logger.info(f"XRayStatsClient initialized: {host}:{port}")

    def _send_command(self, command: dict) -> dict:
        """Send command to XRay stats API and get response.

        Args:
            command: Command dictionary to send

        Returns:
            Response dictionary from XRay

        Raises:
            XRayConnectionError: When connection fails
            XRayTimeoutError: When request times out
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_s)
            sock.connect((self.host, self.port))

            # Send command as JSON
            sock.sendall(json.dumps(command).encode() + b"\n")

            # Receive response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            sock.close()

            data = json.loads(response.decode().strip())
            return data
        except socket.timeout:
            logger.error(f"Timeout connecting to XRay API at {self.host}:{self.port}")
            raise XRayTimeoutError(f"XRay API timeout at {self.host}:{self.port}")
        except ConnectionRefusedError:
            logger.error(f"Cannot connect to XRay API at {self.host}:{self.port}")
            raise XRayConnectionError(
                f"Cannot connect to XRay at {self.host}:{self.port}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from XRay: {e}")
            raise XRayStatsClientError(f"Invalid JSON response from XRay: {e}")
        except Exception as e:
            logger.error(f"Error communicating with XRay: {e}")
            raise XRayStatsClientError(f"Error communicating with XRay: {e}")

    def query_stats(self, pattern: str = "") -> dict:
        """Query XRay statistics.

        Args:
            pattern: Optional pattern to filter stats

        Returns:
            Dictionary containing stat entries
        """
        command = {"command": "QueryStats"}
        if pattern:
            command["pattern"] = pattern

        response = self._send_command(command)
        return response

    def get_user_traffic(self, user_id: str, inbound: Optional[str] = None) -> dict:
        """Get traffic statistics for a specific user.

        Args:
            user_id: User identifier (UUID or email)
            inbound: Optional inbound name to filter by

        Returns:
            Dictionary containing:
                - user_id: User identifier
                - inbound: Inbound name
                - uplink: Upload bytes
                - downlink: Download bytes
                - total: Total bytes

        Raises:
            XRayNotFoundError: When user has no traffic data
        """
        try:
            stats = self.query_stats()

            user_uplink = 0
            user_downlink = 0
            inbound_name = inbound or ""

            # Parse stats to find user data
            # Format: inbound>>>inbound_name>>>user>>>user_id>>>uplink/downlink
            for stat in stats.get("stat", []):
                name = stat.get("name", "")
                value = stat.get("value", 0)

                if "user" in name and user_id in name:
                    # Skip if inbound filter is set and doesn't match
                    if inbound and inbound not in name:
                        continue

                    if "uplink" in name:
                        user_uplink += value
                        if not inbound_name:
                            # Extract inbound name from stat name
                            parts = name.split(">>>")
                            if len(parts) >= 2:
                                inbound_name = parts[1]
                    elif "downlink" in name:
                        user_downlink += value
                        if not inbound_name:
                            parts = name.split(">>>")
                            if len(parts) >= 2:
                                inbound_name = parts[1]

            if user_uplink == 0 and user_downlink == 0:
                logger.warning(f"No traffic data found for user {user_id}")
                raise XRayNotFoundError(f"No traffic data found for user {user_id}")

            return {
                "user_id": user_id,
                "inbound": inbound_name,
                "uplink": user_uplink,
                "downlink": user_downlink,
                "total": user_uplink + user_downlink,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        except XRayStatsClientError:
            raise
        except Exception as e:
            logger.error(f"Error getting user traffic: {e}")
            raise XRayStatsClientError(f"Error getting user traffic: {e}")

    def get_inbound_traffic(self, inbound: str) -> dict:
        """Get traffic statistics for a specific inbound.

        Args:
            inbound: Inbound name (e.g., 'vless-ws', 'vless-xhttp')

        Returns:
            Dictionary containing:
                - inbound: Inbound name
                - uplink: Upload bytes
                - downlink: Download bytes
                - total: Total bytes

        Raises:
            XRayNotFoundError: When inbound has no traffic data
        """
        try:
            stats = self.query_stats()

            inbound_uplink = 0
            inbound_downlink = 0

            # Parse stats to find inbound data
            # Format: inbound>>>inbound_name>>>uplink/downlink
            for stat in stats.get("stat", []):
                name = stat.get("name", "")
                value = stat.get("value", 0)

                # Match inbound stats but exclude user-specific stats
                if "inbound" in name and inbound in name and "user" not in name:
                    if "uplink" in name:
                        inbound_uplink += value
                    elif "downlink" in name:
                        inbound_downlink += value

            if inbound_uplink == 0 and inbound_downlink == 0:
                logger.warning(f"No traffic data found for inbound {inbound}")
                raise XRayNotFoundError(f"No traffic data found for inbound {inbound}")

            return {
                "inbound": inbound,
                "uplink": inbound_uplink,
                "downlink": inbound_downlink,
                "total": inbound_uplink + inbound_downlink,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        except XRayStatsClientError:
            raise
        except Exception as e:
            logger.error(f"Error getting inbound traffic: {e}")
            raise XRayStatsClientError(f"Error getting inbound traffic: {e}")

    def get_all_traffic(self) -> dict:
        """Get all traffic statistics aggregated by inbound.

        Returns:
            Dictionary containing:
                - inbounds: Dict of inbound names to traffic data
                - total_uplink: Total upload bytes
                - total_downlink: Total download bytes
                - total_traffic: Total bytes
        """
        try:
            stats = self.query_stats()

            inbounds_data: dict = {}

            # Parse stats to aggregate by inbound
            for stat in stats.get("stat", []):
                name = stat.get("name", "")
                value = stat.get("value", 0)

                if "inbound" in name and "user" not in name:
                    # Extract inbound name
                    parts = name.split(">>>")
                    if len(parts) >= 2:
                        inbound_name = parts[1]

                        if inbound_name not in inbounds_data:
                            inbounds_data[inbound_name] = {"uplink": 0, "downlink": 0}

                        if "uplink" in name:
                            inbounds_data[inbound_name]["uplink"] += value
                        elif "downlink" in name:
                            inbounds_data[inbound_name]["downlink"] += value

            # Calculate totals
            total_uplink = sum(data["uplink"] for data in inbounds_data.values())
            total_downlink = sum(data["downlink"] for data in inbounds_data.values())

            return {
                "inbounds": inbounds_data,
                "total_uplink": total_uplink,
                "total_downlink": total_downlink,
                "total_traffic": total_uplink + total_downlink,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            logger.error(f"Error getting all traffic: {e}")
            raise XRayStatsClientError(f"Error getting all traffic: {e}")

    def get_user_traffic_all_inbounds(self, user_id: str) -> Dict[str, dict]:
        """Get traffic statistics for a user across all inbounds.

        Args:
            user_id: User identifier

        Returns:
            Dictionary mapping inbound names to traffic data
        """
        try:
            stats = self.query_stats()
            inbounds_data: Dict[str, dict] = {}

            # Parse stats to find all inbounds for this user
            for stat in stats.get("stat", []):
                name = stat.get("name", "")
                value = stat.get("value", 0)

                if "user" in name and user_id in name:
                    # Extract inbound name
                    parts = name.split(">>>")
                    if len(parts) >= 2:
                        inbound_name = parts[1]

                        if inbound_name not in inbounds_data:
                            inbounds_data[inbound_name] = {"uplink": 0, "downlink": 0}

                        if "uplink" in name:
                            inbounds_data[inbound_name]["uplink"] += value
                        elif "downlink" in name:
                            inbounds_data[inbound_name]["downlink"] += value

            return inbounds_data
        except Exception as e:
            logger.error(f"Error getting user traffic for all inbounds: {e}")
            raise XRayStatsClientError(f"Error getting user traffic: {e}")


class MultiNodeXRayClient:
    """Client for querying stats from multiple XRay nodes.

    Maps node IDs to their respective XRay API endpoints.
    """

    def __init__(self, nodes: Dict[str, Tuple[str, int]], timeout_s: int = 5):
        """Initialize multi-node client.

        Args:
            nodes: Dictionary mapping node_id to (host, port) tuples
            timeout_s: Connection timeout in seconds

        Example:
            nodes = {
                "us-1": ("xray-us-1.example.com", 10085),
                "eu-1": ("xray-eu-1.example.com", 10085),
            }
        """
        self.clients: Dict[str, XRayStatsClient] = {}
        self.timeout_s = timeout_s

        for node_id, (host, port) in nodes.items():
            self.clients[node_id] = XRayStatsClient(host, port, timeout_s)

        logger.info(f"MultiNodeXRayClient initialized with {len(nodes)} nodes")

    def get_user_traffic(
        self, user_id: str, node_id: str, inbound: Optional[str] = None
    ) -> dict:
        """Get user traffic from a specific node.

        Args:
            user_id: User identifier
            node_id: Node identifier
            inbound: Optional inbound filter

        Returns:
            Dictionary with traffic data including node_id

        Raises:
            XRayStatsClientError: When node_id is invalid or request fails
        """
        if node_id not in self.clients:
            raise XRayStatsClientError(f"Unknown node_id: {node_id}")

        try:
            client = self.clients[node_id]
            data = client.get_user_traffic(user_id, inbound)
            data["node_id"] = node_id
            return data
        except XRayStatsClientError:
            raise
        except Exception as e:
            logger.error(f"Error getting traffic from node {node_id}: {e}")
            raise XRayStatsClientError(f"Error querying node {node_id}: {e}")

    def get_inbound_traffic(self, inbound: str, node_id: str) -> dict:
        """Get inbound traffic from a specific node.

        Args:
            inbound: Inbound name
            node_id: Node identifier

        Returns:
            Dictionary with traffic data including node_id
        """
        if node_id not in self.clients:
            raise XRayStatsClientError(f"Unknown node_id: {node_id}")

        try:
            client = self.clients[node_id]
            data = client.get_inbound_traffic(inbound)
            data["node_id"] = node_id
            return data
        except XRayStatsClientError:
            raise
        except Exception as e:
            logger.error(f"Error getting traffic from node {node_id}: {e}")
            raise XRayStatsClientError(f"Error querying node {node_id}: {e}")

    def get_all_traffic(self, node_id: str) -> dict:
        """Get all traffic from a specific node.

        Args:
            node_id: Node identifier

        Returns:
            Dictionary with all traffic data including node_id
        """
        if node_id not in self.clients:
            raise XRayStatsClientError(f"Unknown node_id: {node_id}")

        try:
            client = self.clients[node_id]
            data = client.get_all_traffic()
            data["node_id"] = node_id
            return data
        except Exception as e:
            logger.error(f"Error getting traffic from node {node_id}: {e}")
            raise XRayStatsClientError(f"Error querying node {node_id}: {e}")

    def get_user_traffic_from_all_nodes(
        self, user_id: str, inbound: Optional[str] = None
    ) -> Dict[str, dict]:
        """Get user traffic from all available nodes.

        Args:
            user_id: User identifier
            inbound: Optional inbound filter

        Returns:
            Dictionary mapping node_id to traffic data
        """
        results: Dict[str, dict] = {}

        for node_id, client in self.clients.items():
            try:
                data = client.get_user_traffic(user_id, inbound)
                data["node_id"] = node_id
                results[node_id] = data
            except XRayNotFoundError:
                logger.debug(f"No traffic for user {user_id} on node {node_id}")
            except Exception as e:
                logger.warning(f"Error querying node {node_id}: {e}")

        return results

    def add_node(self, node_id: str, host: str, port: int) -> None:
        """Add or update a node in the client.

        Args:
            node_id: Node identifier
            host: XRay API host
            port: XRay API port
        """
        self.clients[node_id] = XRayStatsClient(host, port, self.timeout_s)
        logger.info(f"Added node {node_id}: {host}:{port}")

    def remove_node(self, node_id: str) -> None:
        """Remove a node from the client.

        Args:
            node_id: Node identifier to remove
        """
        if node_id in self.clients:
            del self.clients[node_id]
            logger.info(f"Removed node {node_id}")

    def get_available_nodes(self) -> List[str]:
        """Get list of available node IDs.

        Returns:
            List of node identifiers
        """
        return list(self.clients.keys())
