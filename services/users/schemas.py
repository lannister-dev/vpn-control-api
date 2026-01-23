from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    telegram_id: int

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    balance: float

    model_config = ConfigDict(from_attributes=True)
