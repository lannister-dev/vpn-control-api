from pydantic import BaseModel, ConfigDict


class DripTriggerEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    telegram_id: int
