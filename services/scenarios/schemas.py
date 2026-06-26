from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.scenarios.constants import SCENARIO_CONDITIONS, SCENARIO_TRIGGERS


class ScenarioTriggerEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    telegram_id: int


class ScenarioNodeIn(BaseModel):
    key: str
    type: str
    pos_cx: int = 0
    pos_top: int = 0
    delay_seconds: int = 0
    condition: str = "always"
    repeat_count: int = 1
    repeat_interval_sec: int = 0
    text_body: str | None = None
    inline_buttons: list[dict] | None = None
    media_kind: str | None = None
    media_url: str | None = None
    check: str | None = None
    conversion: bool = False
    label: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("message", "condition", "end"):
            raise ValueError("type must be one of message|condition|end")
        return v

    @field_validator("condition")
    @classmethod
    def _check_condition(cls, v: str) -> str:
        if v not in SCENARIO_CONDITIONS:
            raise ValueError(f"condition must be one of {SCENARIO_CONDITIONS}")
        return v

    @field_validator("check")
    @classmethod
    def _check_check(cls, v: str | None) -> str | None:
        if v is not None and v not in SCENARIO_CONDITIONS:
            raise ValueError(f"check must be null or one of {SCENARIO_CONDITIONS}")
        return v


class ScenarioEdgeIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    branch: str | None = None


class ScenarioNodeOut(BaseModel):
    id: UUID
    key: str
    type: str
    pos_cx: int = 0
    pos_top: int = 0
    delay_seconds: int = 0
    condition: str = "always"
    repeat_count: int = 1
    repeat_interval_sec: int = 0
    text_body: str | None = None
    inline_buttons: list[dict] | None = None
    media_kind: str | None = None
    media_url: str | None = None
    check: str | None = None
    conversion: bool = False
    label: str | None = None


class ScenarioEdgeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    from_node: str = Field(serialization_alias="from")
    to_node: str = Field(serialization_alias="to")
    branch: str | None = None


class ScenarioCampaignIn(BaseModel):
    key: str
    name: str
    trigger_event: str | None = None
    is_active: bool = True
    entry_node_key: str | None = None
    nodes: list[ScenarioNodeIn] = Field(default_factory=list)
    edges: list[ScenarioEdgeIn] = Field(default_factory=list)

    @field_validator("trigger_event")
    @classmethod
    def _check_trigger(cls, v: str | None) -> str | None:
        if v is not None and v not in SCENARIO_TRIGGERS:
            raise ValueError(f"trigger_event must be null or one of {SCENARIO_TRIGGERS}")
        return v


class ScenarioCampaignPatch(BaseModel):
    is_active: bool


class ScenarioCampaignOut(BaseModel):
    id: UUID
    key: str
    name: str
    trigger_event: str | None
    is_active: bool
    entry_node_key: str | None = None
    nodes: list[ScenarioNodeOut] = Field(default_factory=list)
    edges: list[ScenarioEdgeOut] = Field(default_factory=list)


class ScenarioCampaignListOut(BaseModel):
    items: list[ScenarioCampaignOut]


class ScenarioCampaignStat(BaseModel):
    campaign_id: UUID
    enrolled: int = 0
    active: int = 0
    completed: int = 0
    abandoned: int = 0
    stopped: int = 0


class ScenarioStatsOut(BaseModel):
    items: list[ScenarioCampaignStat]
