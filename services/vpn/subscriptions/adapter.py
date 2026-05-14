from __future__ import annotations

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
    SubscriptionTokenExpired,
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

    def should_disable_not_modified(self, *, user_agent: str | None) -> bool:
        if not self._is_happ_user_agent(user_agent):
            return False
        return (
            self._happ_hide_settings
            or self._happ_always_hwid_enable
            or bool(self._happ_color_profile)
            or bool(self._happ_provider_id)
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
        if isinstance(exc, SubscriptionTokenExpired):
            return SubscriptionPublicErrorResponse(
                metric_result="token_expired",
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
            "profile-title": self._happ_profile_title,
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
            headers["color-profile"] = self._happ_color_profile
        if self._happ_autoconnect:
            headers["subscription-autoconnect"] = "true"
            headers["subscription-autoconnect-type"] = self._happ_autoconnect_type
        if self._happ_ping_onopen:
            headers["subscription-ping-onopen-enabled"] = "true"
        return headers

    def _build_payload_body(self, *, payload: str, user_agent: str | None, is_json: bool = False) -> str:
        if is_json:
            return payload
        if not self._is_happ_user_agent(user_agent):
            return payload
        directives = self._happ_body_directives()
        if not directives:
            return payload
        if not payload:
            return "\n".join(directives)
        return "\n".join([*directives, payload])

    def _happ_body_directives(self) -> list[str]:
        directives: list[str] = []
        if self._happ_profile_title:
            directives.append(f"#profile-title: {self._happ_profile_title}")
        if self._happ_profile_update_interval_hours:
            directives.append(f"#profile-update-interval: {self._happ_profile_update_interval_hours}")
        if self._happ_support_url:
            directives.append(f"#support-url: {self._happ_support_url}")
        if self._happ_profile_web_page_url:
            directives.append(f"#profile-web-page-url: {self._happ_profile_web_page_url}")
        if self._happ_provider_id:
            directives.append(f"#providerid: {self._happ_provider_id}")
        if self._happ_routing:
            directives.append(f"#routing: {self._happ_routing}")
        if self._happ_hide_settings:
            directives.append("#hide-settings: 1")
        if self._happ_always_hwid_enable:
            directives.append("#subscription-always-hwid-enable: 1")
        if self._happ_color_profile:
            directives.append(f"#color-profile: {self._happ_color_profile}")
        if self._happ_autoconnect:
            directives.append("#subscription-autoconnect: true")
            directives.append(f"#subscription-autoconnect-type: {self._happ_autoconnect_type}")
        if self._happ_ping_onopen:
            directives.append("#subscription-ping-onopen-enabled: true")
        return directives

    @staticmethod
    def _is_happ_user_agent(user_agent: str | None) -> bool:
        if not user_agent:
            return False
        return user_agent.strip().lower().startswith("happ/")
