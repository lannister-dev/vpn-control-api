import pytest

from services.admin_ui.router import admin_control_panel


@pytest.mark.asyncio
async def test_admin_control_panel_returns_html():
    response = await admin_control_panel()

    assert response.status_code == 200
    assert response.media_type == "text/html"
    body = response.body.decode("utf-8")
    assert "VPN Control Plane" in body
    assert "/api/v1/admin/status" in body
    assert "/api/v1/agent/nodes/" in body
