from services.config import RoutesConfig
from services.connect.schemas import ConnectRefreshPolicy


def build_connect_refresh_policy(routes: RoutesConfig) -> ConnectRefreshPolicy:
    refresh_interval_sec = max(10, int(routes.connect_refresh_interval_sec))
    max_cache_age_sec = max(refresh_interval_sec, int(routes.connect_max_cache_age_sec))

    backoff_steps_sec = [int(step) for step in routes.connect_backoff_steps_sec if int(step) > 0]
    if not backoff_steps_sec:
        backoff_steps_sec = [2, 5, 10, 30, 60]

    return ConnectRefreshPolicy(
        refresh_interval_sec=refresh_interval_sec,
        max_cache_age_sec=max_cache_age_sec,
        backoff_steps_sec=backoff_steps_sec,
    )
