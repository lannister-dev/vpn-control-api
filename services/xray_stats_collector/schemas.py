"""Schemas for XRay traffic statistics API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TrafficStats(BaseModel):
    """Traffic statistics for a user or inbound."""

    uplink: int = Field(..., description="Upload traffic in bytes")
    downlink: int = Field(..., description="Download traffic in bytes")
    total: int = Field(..., description="Total traffic in bytes")


class UserTrafficResponse(BaseModel):
    """Response containing traffic data for a user."""

    user_id: str = Field(..., description="User identifier/UUID")
    node_id: Optional[str] = Field(None, description="Node identifier")
    inbound: str = Field(..., description="Inbound name (e.g., 'vless-ws')")
    stats: TrafficStats
    updated_at: Optional[datetime] = Field(None, description="Timestamp of last update")


class InboundTrafficResponse(BaseModel):
    """Response containing traffic data for an inbound."""

    inbound: str = Field(..., description="Inbound name")
    node_id: Optional[str] = Field(None, description="Node identifier")
    stats: TrafficStats
    updated_at: Optional[datetime] = Field(None, description="Timestamp of last update")


class AllTrafficResponse(BaseModel):
    """Response containing all traffic data."""

    inbounds: list[InboundTrafficResponse]
    total: TrafficStats


class UserTrafficRequest(BaseModel):
    """Request model for querying user traffic."""

    user_id: str = Field(..., description="User identifier/UUID", min_length=1)
    node_id: str = Field(..., description="Node identifier", min_length=1)
    inbound: Optional[str] = Field(None, description="Optional inbound filter")


class NodeTrafficResponse(BaseModel):
    """Response containing traffic data for a specific node."""

    node_id: str = Field(..., description="Node identifier")
    user_id: str = Field(..., description="User identifier")
    inbound: str = Field(..., description="Inbound name")
    stats: TrafficStats
    updated_at: Optional[datetime] = Field(None, description="Timestamp of last update")
