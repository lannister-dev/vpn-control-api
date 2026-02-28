"""
XRay Stats Exporter for Prometheus
Exposes xray client traffic statistics as Prometheus metrics
"""

import json
import logging
import os
import socket
import time
from typing import Dict, List, Tuple

from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
inbound_uplink = Gauge(
    "xray_inbound_uplink_bytes", "Inbound upload traffic", ["inbound"]
)
inbound_downlink = Gauge(
    "xray_inbound_downlink_bytes", "Inbound download traffic", ["inbound"]
)
user_uplink = Gauge(
    "xray_user_uplink_bytes", "User upload traffic", ["user", "inbound"]
)
user_downlink = Gauge(
    "xray_user_downlink_bytes", "User download traffic", ["user", "inbound"]
)
user_connections = Gauge(
    "xray_user_connections", "Active user connections", ["user", "inbound"]
)
total_requests = Counter("xray_stats_updates_total", "Total statistics updates")


class XRayStatsCollector:
    def __init__(self, xray_host: str = "localhost", xray_port: int = 10085):
        self.xray_host = xray_host
        self.xray_port = xray_port

    def _send_command(self, command: List[str]) -> str:
        """Send command to XRay stats API"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.xray_host, self.xray_port))

            # Build XRay API command
            request = {
                "command": command[0],
                **({"pattern": command[1]} if len(command) > 1 else {}),
            }

            sock.send(json.dumps(request).encode() + b"\n")

            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            sock.close()
            return response.decode().strip()
        except Exception as e:
            logger.error(f"Error communicating with XRay: {e}")
            return ""

    def query_stats(self, pattern: str = "") -> Dict:
        """Query XRay statistics"""
        try:
            command = ["QueryStats"]
            if pattern:
                command.append(pattern)

            response = self._send_command(command)
            if response:
                stats = json.loads(response)
                return stats
        except Exception as e:
            logger.error(f"Error parsing stats: {e}")
        return {}

    def update_metrics(self):
        """Update Prometheus metrics from XRay stats"""
        try:
            stats = self.query_stats()

            # Parse inbound stats
            for stat in stats.get("stat", []):
                name = stat.get("name", "")
                value = stat.get("value", 0)

                if "inbound" in name:
                    if "uplink" in name:
                        inbound_name = name.split(">>>")[0].replace("inbound>>>", "")
                        inbound_uplink.labels(inbound=inbound_name).set(value)
                    elif "downlink" in name:
                        inbound_name = name.split(">>>")[0].replace("inbound>>>", "")
                        inbound_downlink.labels(inbound=inbound_name).set(value)

                elif "user" in name:
                    if "uplink" in name:
                        parts = name.split(">>>")
                        user = parts[1] if len(parts) > 1 else "unknown"
                        inbound = (
                            parts[0].replace("inbound>>>", "")
                            if "inbound" in parts[0]
                            else "unknown"
                        )
                        user_uplink.labels(user=user, inbound=inbound).set(value)
                    elif "downlink" in name:
                        parts = name.split(">>>")
                        user = parts[1] if len(parts) > 1 else "unknown"
                        inbound = (
                            parts[0].replace("inbound>>>", "")
                            if "inbound" in parts[0]
                            else "unknown"
                        )
                        user_downlink.labels(user=user, inbound=inbound).set(value)

            total_requests.inc()
            logger.debug("Metrics updated successfully")
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")


def main():
    # Configuration
    xray_host = os.getenv("XRAY_HOST", "xray")
    xray_port = int(os.getenv("XRAY_PORT", 10085))
    exporter_port = int(os.getenv("EXPORTER_PORT", 9091))
    update_interval = int(os.getenv("UPDATE_INTERVAL", 15))

    # Start Prometheus HTTP server
    start_http_server(exporter_port)
    logger.info(f"XRay Stats Exporter started on port {exporter_port}")

    # Create collector
    collector = XRayStatsCollector(xray_host, xray_port)

    # Update loop
    while True:
        try:
            collector.update_metrics()
            time.sleep(update_interval)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
