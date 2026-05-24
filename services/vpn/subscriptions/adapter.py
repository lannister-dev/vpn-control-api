from __future__ import annotations

import base64
import hashlib
import json

from fastapi import status

from services.vpn.subscriptions.exceptions import (
    SubscriptionBuild,
    SubscriptionDeviceLimitReached,
    SubscriptionExpired,
    SubscriptionHwidRequired,
    SubscriptionInactive,
    SubscriptionNotFound,
    SubscriptionRateLimited,
)
from services.vpn.subscriptions.schemas import (
    SubscriptionPublicErrorResponse,
    SubscriptionPublicSuccessResponse,
    SubscriptionUserInfo,
)


class SubscriptionPublicAdapter:
    def __init__(
            self,
            *,
            hwid_header: str,
            happ_profile_title: str,
            happ_profile_update_interval_hours: int,
            happ_support_url: str,
            happ_profile_web_page_url: str,
            happ_provider_id: str,
            happ_routing: str,
            happ_hide_settings: bool = False,
            happ_always_hwid_enable: bool = False,
            happ_color_profile: str = "",
            happ_autoconnect: bool = True,
            happ_autoconnect_type: str = "lowestdelay",
            happ_ping_onopen: bool = True,
    ):
        self._hwid_header = hwid_header.strip()
        self._happ_profile_title = happ_profile_title.strip() or "VPN"
        self._happ_profile_update_interval_hours = max(1, int(happ_profile_update_interval_hours))
        self._happ_support_url = happ_support_url.strip()
        self._happ_profile_web_page_url = happ_profile_web_page_url.strip()
        self._happ_provider_id = happ_provider_id.strip()
        self._happ_routing = happ_routing.strip()
        self._happ_hide_settings = bool(happ_hide_settings)
        self._happ_always_hwid_enable = bool(happ_always_hwid_enable)
        self._happ_autoconnect = bool(happ_autoconnect)
        self._happ_autoconnect_type = happ_autoconnect_type.strip() or "lowestdelay"
        self._happ_ping_onopen = bool(happ_ping_onopen)
        color_profile = happ_color_profile.strip()
        self._happ_color_profile = (
            json.dumps(json.loads(color_profile), separators=(",", ":"))
            if color_profile
            else ""
        )

    @property
    def hwid_header(self) -> str:
        return self._hwid_header

    @property
    def directives_signature(self) -> str:
        parts = [
            self._happ_profile_title,
            str(self._happ_profile_update_interval_hours),
            self._happ_support_url,
            self._happ_profile_web_page_url,
            self._happ_provider_id,
            self._happ_routing,
            "1" if self._happ_hide_settings else "0",
            "1" if self._happ_always_hwid_enable else "0",
            self._happ_color_profile,
            "1" if self._happ_autoconnect else "0",
            self._happ_autoconnect_type,
            "1" if self._happ_ping_onopen else "0",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]

    def should_disable_not_modified(self, *, user_agent: str | None) -> bool:
        # Independent of UA — many Happ builds (notably macOS) report unexpected
        # user-agent strings; gating on it caused stale cached profiles to stick.
        del user_agent
        return (
            self._happ_hide_settings
            or self._happ_always_hwid_enable
            or bool(self._happ_color_profile)
            or bool(self._happ_provider_id)
            or bool(self._happ_routing)
        )

    def build_success_response(
            self,
            *,
            payload: str,
            etag: str,
            not_modified: bool,
            user_info: SubscriptionUserInfo | None = None,
            user_agent: str | None = None,
    ) -> SubscriptionPublicSuccessResponse:
        is_json = self._is_json_payload(payload)
        headers = self._build_headers(etag=etag, user_info=user_info, is_json=is_json)
        if not_modified:
            return SubscriptionPublicSuccessResponse(
                metric_result="not_modified",
                status_code=status.HTTP_304_NOT_MODIFIED,
                payload=None,
                headers=headers,
            )
        return SubscriptionPublicSuccessResponse(
            metric_result="success",
            status_code=status.HTTP_200_OK,
            payload=self._build_payload_body(payload=payload, user_agent=user_agent, is_json=is_json),
            headers=headers,
        )

    @staticmethod
    def _is_json_payload(payload: str) -> bool:
        if not payload:
            return False
        stripped = payload.lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    def map_error(self, exc: Exception) -> SubscriptionPublicErrorResponse:
        if isinstance(exc, SubscriptionNotFound):
            return SubscriptionPublicErrorResponse(
                metric_result="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )
        if isinstance(exc, SubscriptionHwidRequired):
            # Keep opaque behavior for public endpoint: do not leak token validity.
            return SubscriptionPublicErrorResponse(
                metric_result="hwid_required",
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )
        if isinstance(exc, SubscriptionDeviceLimitReached):
            return SubscriptionPublicErrorResponse(
                metric_result="device_limit",
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device limit reached",
            )
        if isinstance(exc, SubscriptionInactive):
            return SubscriptionPublicErrorResponse(
                metric_result="inactive",
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subscription is not active",
            )
        if isinstance(exc, SubscriptionExpired):
            return SubscriptionPublicErrorResponse(
                metric_result="expired",
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subscription is not active",
            )
        if isinstance(exc, SubscriptionRateLimited):
            return SubscriptionPublicErrorResponse(
                metric_result="rate_limited",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        if isinstance(exc, SubscriptionBuild):
            message = str(exc)
            if self._is_service_unavailable_build_error(message):
                return SubscriptionPublicErrorResponse(
                    metric_result="build_error",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to build subscription: {exc}",
                )
            return SubscriptionPublicErrorResponse(
                metric_result="build_error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to build subscription: {exc}",
            )
        return SubscriptionPublicErrorResponse(
            metric_result="build_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build subscription",
        )

    @staticmethod
    def _is_service_unavailable_build_error(message: str) -> bool:
        if message.startswith("No available "):
            return True
        return message in {"Node placement sync pending", "Backend placement sync pending"}

    def _build_headers(
            self,
            *,
            etag: str,
            user_info: SubscriptionUserInfo | None = None,
            is_json: bool = False,
    ) -> dict[str, str]:
        vary_parts = ["If-None-Match", "User-Agent"]
        if self._hwid_header:
            vary_parts.append(self._hwid_header)

        headers = {
            "ETag": etag,
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Type": "application/json; charset=utf-8" if is_json else "text/plain; charset=utf-8",
            "profile-title": self._b64_header_value(self._happ_profile_title),
            "profile-update-interval": str(self._happ_profile_update_interval_hours),
            "Vary": ", ".join(vary_parts),
        }
        if user_info is not None:
            headers["subscription-userinfo"] = user_info.to_header()
        if self._happ_support_url:
            headers["support-url"] = self._happ_support_url
        if self._happ_profile_web_page_url:
            headers["profile-web-page-url"] = self._happ_profile_web_page_url
        if self._happ_provider_id:
            headers["providerid"] = self._happ_provider_id
        if self._happ_routing:
            headers["routing"] = self._happ_routing
        if self._happ_hide_settings:
            headers["hide-settings"] = "1"
        if self._happ_always_hwid_enable:
            headers["subscription-always-hwid-enable"] = "1"
        if self._happ_color_profile:
            headers["color-profile"] = self._b64_header_value(self._happ_color_profile)
        if self._happ_autoconnect:
            headers["subscription-autoconnect"] = "true"
            headers["subscription-autoconnect-type"] = self._happ_autoconnect_type
        if self._happ_ping_onopen:
            headers["subscription-ping-onopen-enabled"] = "true"
        return headers

    def _build_payload_body(self, *, payload: str, user_agent: str | None, is_json: bool = False) -> str:
        # Happ reads all directives (color-profile, hide-settings, etc.) from HTTP
        # response headers only. Body-prefixed "#..." lines confuse some Happ
        # parsers (each "#" line is treated as a VLESS fragment), so we keep the
        # body strictly to vless:// lines — matches the Remnawave panel convention.
        del user_agent, is_json
        return payload

    @staticmethod
    def _b64_header_value(value: str) -> str:
        """Wrap a UTF-8 value in `base64:<base64>` so it survives non-ASCII chars
        in HTTP headers (Cloudflare/proxies may strip non-latin-1)."""
        if not value:
            return ""
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"base64:{encoded}"

