from datetime import timedelta

from services.traffic.nodes.schemas import TrafficPeriod


PERIOD_WINDOW: dict[TrafficPeriod, tuple[timedelta, int]] = {
    TrafficPeriod.HOUR: (timedelta(hours=1), 60),
    TrafficPeriod.DAY: (timedelta(days=1), 300),
    TrafficPeriod.WEEK: (timedelta(days=7), 3600),
    TrafficPeriod.MONTH: (timedelta(days=30), 6 * 3600),
}
