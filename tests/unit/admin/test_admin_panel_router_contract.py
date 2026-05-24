import pytest
from starlette.requests import Request

from services.admin.ui.router import admin_control_panel


@pytest.mark.asyncio
async def test_admin_control_panel_returns_html():
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/admin/panel", "headers": []})
    response = await admin_control_panel(request)
    assert response.status_code == 307
