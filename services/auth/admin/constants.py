from __future__ import annotations

import enum


class AdminRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_


ROLE_HIERARCHY: dict[str, int] = {
    AdminRole.viewer.value: 0,
    AdminRole.operator.value: 1,
    AdminRole.admin.value: 2,
}

SESSION_COOKIE_NAME = "admin_sid"
CSRF_COOKIE_NAME = "admin_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
TG_OIDC_STATE_COOKIE_NAME = "admin_tg_oidc_state"
TG_OIDC_NONCE_COOKIE_NAME = "admin_tg_oidc_nonce"
TG_OIDC_VERIFIER_COOKIE_NAME = "admin_tg_oidc_verifier"
SESSION_ID_BYTES = 32
SALT_BYTES = 16
