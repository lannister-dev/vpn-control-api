class AlertTexts:
    TELEGRAM_MESSAGE = """{level_prefix} {title}
    
{body}"""

    PROBE_STATUS_TITLE = "VPN Probe Status"
    PROBE_STATUS_BODY = """
Node: {node_name} ({node_id})
Region: {region}
Source: {source}
State: {state}
Checked at: {checked_at}
Error: {error}
"""
