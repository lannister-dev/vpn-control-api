from services.routes.schemas import RouteWarmupStage

DEFAULT_WARMUP_STAGES: tuple[RouteWarmupStage, ...] = (
    RouteWarmupStage(target_weight=10, hold_minutes=30),
    RouteWarmupStage(target_weight=25, hold_minutes=60),
)
