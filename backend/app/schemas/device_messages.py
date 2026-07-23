"""Messaggi validati al confine Node-RED -> FastAPI.

The physical gateway and simulator may emit different raw packets. Node-RED is
responsible for mapping them to these stable normalized messages.
"""

from typing import Literal

from pydantic import BaseModel, Field


class NormalizedPostureSample(BaseModel):
    schema_version: Literal[1] = 1
    device_id: str = Field(min_length=1, max_length=128)
    patient_id: str = Field(min_length=1, max_length=128)
    timestamp: int = Field(gt=0)
    sequence: int = Field(default=0, ge=0)
    type: Literal["accgyro"] = "accgyro"
    sampling_frequency: float = Field(default=0, ge=0)
    x: float
    y: float
    z: float
    quality: str = Field(default="unknown", max_length=32)
    source_topic: str | None = None
    simulation_state: str | None = None
    source_timestamp: int | None = None
    sample_count: int | None = Field(default=None, ge=1)
    orientation: int | None = None


class NormalizedDeviceStatus(BaseModel):
    schema_version: Literal[1] = 1
    device_id: str = Field(min_length=1, max_length=128)
    patient_id: str = Field(min_length=1, max_length=128)
    timestamp: int = Field(gt=0)
    type: Literal["battery"] = "battery"
    state_of_charge: float = Field(ge=0, le=100)
    charging: bool = False
    quality: str = Field(default="unknown", max_length=32)
    source_topic: str | None = None
    source_timestamp: int | None = None
    voltage: float | None = None
    temperature: float | None = None
