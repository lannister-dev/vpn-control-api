class AlertTexts:
    TELEGRAM_MESSAGE = """{level_prefix} {title}
    
{body}"""

    PROBE_STATUS_TITLE = "VPN Probe Status"
    PROBE_STATUS_BODY = """
Node: {node_name} ({node_id})
Region: {region}
Source: {source}
Route: {route_id}
Transport: {transport_kind}
Probe kind: {probe_kind}
Target: {target}
State: {state}
Checked at: {checked_at}
Error phase: {error_phase}
Error: {error}
"""
