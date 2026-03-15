from __future__ import annotations

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
    ):
        self._hwid_header = hwid_header.strip()
        self._happ_profile_title = happ_profile_title.strip() or "VPN"
        self._happ_profile_update_interval_hours = max(1, int(happ_profile_update_interval_hours))
        self._happ_support_url = happ_support_url.strip()
        self._happ_profile_web_page_url = happ_profile_web_page_url.strip()
        self._happ_provider_id = happ_provider_id.strip()
        self._happ_routing = happ_routing.strip()

    @property
    def hwid_header(self) -> str:
        return self._hwid_header

    def build_success_response(
            self,
            *,
            payload: str,
            etag: str,
            not_modified: bool,
    ) -> SubscriptionPublicSuccessResponse:
        headers = self._build_headers(etag=etag)
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
            payload=payload,
            headers=headers,
        )

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
    ) -> dict[str, str]:
        vary_parts = ["If-None-Match", "User-Agent"]
        if self._hwid_header:
            vary_parts.append(self._hwid_header)

        headers = {
            "ETag": etag,
            "Cache-Control": "private, no-cache, must-revalidate",
            "profile-title": self._happ_profile_title,
            "profile-update-interval": str(self._happ_profile_update_interval_hours),
            "Vary": ", ".join(vary_parts),
        }
        if self._happ_support_url:
            headers["support-url"] = self._happ_support_url
        if self._happ_profile_web_page_url:
            headers["profile-web-page-url"] = self._happ_profile_web_page_url
        if self._happ_provider_id:
            headers["providerid"] = self._happ_provider_id
        if self._happ_routing:
            headers["routing"] = self._happ_routing
        return headers
