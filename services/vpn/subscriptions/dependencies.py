from services.config import get_settings
from services.vpn.subscriptions.adapter import SubscriptionPublicAdapter


def get_subscription_public_adapter() -> SubscriptionPublicAdapter:
    settings = get_settings()
    return SubscriptionPublicAdapter(
        hwid_header=settings.subscriptions.hwid_header,
        happ_profile_title=settings.subscriptions.happ_profile_title,
        happ_profile_update_interval_hours=settings.subscriptions.happ_profile_update_interval_hours,
        happ_support_url=settings.subscriptions.happ_support_url,
        happ_profile_web_page_url=settings.subscriptions.happ_profile_web_page_url,
        happ_provider_id=settings.subscriptions.happ_provider_id,
        happ_routing=settings.subscriptions.happ_routing,
    )
