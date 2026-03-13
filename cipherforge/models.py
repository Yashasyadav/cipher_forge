from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DeviceType(str, Enum):
    HDD = "HDD"
    SSD = "SSD"
    NVME = "NVMe"
    USB = "USB"
    ANDROID = "ANDROID"
    UNKNOWN = "UNKNOWN"


class WipeMethod(str, Enum):
    NIST = "NIST"
    DOD = "DoD"
    GUTMANN = "Gutmann"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceInfo(BaseModel):
    device: str = Field(..., description="System device identifier")
    type: DeviceType = Field(..., description="Detected storage type")
    size: str = Field(..., description="Human-readable device size, e.g. 512GB")
    serial: str = Field(default="UNKNOWN", description="Hardware serial number where available")
    size_bytes: int = Field(default=0, ge=0, exclude=True, repr=False)


class WipeRequest(BaseModel):
    device: str = Field(..., min_length=1, description="Device name or path")
    method: WipeMethod = Field(..., description="Sanitization method")

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("device must not be empty")
        return candidate

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        mapping = {
            "nist": WipeMethod.NIST.value,
            "nist clear": WipeMethod.NIST.value,
            "dod": WipeMethod.DOD.value,
            "dod 5220.22-m": WipeMethod.DOD.value,
            "gutmann": WipeMethod.GUTMANN.value,
            "gutmann method": WipeMethod.GUTMANN.value,
        }
        if normalized in mapping:
            return mapping[normalized]
        raise ValueError("method must be one of: NIST, DoD, Gutmann")


class WipeJobResponse(BaseModel):
    job_id: str
    device: str
    wipe_method: WipeMethod
    method: WipeMethod
    status: JobState
    progress: float = Field(..., ge=0, le=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    submitted_at: datetime
    certificate_id: str | None = None
    last_message: str | None = None
    error: str | None = None


class CertificateResponse(BaseModel):
    id: str
    job_id: str
    device: str
    device_serial: str
    device_type: DeviceType
    wipe_method: WipeMethod
    overwrite_passes: int = Field(..., ge=0)
    timestamp: datetime
    verification_status: str
    recovered_files: int = Field(..., ge=0)
    sha256_hash: str
    pdf_path: str
    json_path: str
    bytes_wiped: int = Field(..., ge=0)
    execution_seconds: float = Field(..., ge=0)
