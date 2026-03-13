from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WipeMethod(str, Enum):
    NIST = "NIST"
    DOD = "DoD"
    GUTMANN = "Gutmann"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceInfo(BaseModel):
    device: str
    type: str
    size: str
    serial: str = "UNKNOWN"
    size_bytes: int = Field(default=0, ge=0, exclude=True, repr=False)


class LogicalDriveInfo(BaseModel):
    drive: str
    type: str
    size: str
    label: str | None = None
    size_bytes: int = Field(default=0, ge=0, exclude=True, repr=False)


class FileMetadata(BaseModel):
    name: str
    size: str
    size_bytes: int = Field(..., ge=0)


class FilesystemBrowseResponse(BaseModel):
    path: str
    folders: list[str]
    files: list[FileMetadata]


class FolderWipeRequest(BaseModel):
    path: str = Field(..., min_length=1)
    method: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("path must not be empty")
        return normalized

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("method must not be blank when provided")
        return normalized


class FolderWipeResponse(BaseModel):
    deleted_files: int = Field(..., ge=0)
    status: str
    total_files: int = Field(default=0, ge=0)
    failed_files: int = Field(default=0, ge=0)
    processed_files: int = Field(default=0, ge=0)
    last_message: str | None = None


class FolderWipeJobStatusResponse(BaseModel):
    job_id: str
    path: str
    method: str
    status: str
    progress: float = Field(..., ge=0, le=100)
    total_files: int = Field(default=0, ge=0)
    processed_files: int = Field(default=0, ge=0)
    deleted_files: int = Field(default=0, ge=0)
    failed_files: int = Field(default=0, ge=0)
    current_file: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    last_message: str | None = None
    error: str | None = None


class FileWipeRequest(BaseModel):
    path: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)

    @field_validator("path", "method")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("path and method must not be empty")
        return normalized


class FileWipeResponse(BaseModel):
    status: str
    deleted_files: int = Field(default=1, ge=0)
    passes: int | None = None
    verified: bool | None = None
    last_message: str | None = None
    stage_logs: list[str] = Field(default_factory=list)
    free_space_cleanup: str | None = None


class WipeRequest(BaseModel):
    device: str = Field(..., min_length=1)
    method: WipeMethod

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("device must not be empty")
        return normalized

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        mapping = {
            "nist": WipeMethod.NIST.value,
            "nist clear": WipeMethod.NIST.value,
            "dod": WipeMethod.DOD.value,
            "dod 5220.22-m": WipeMethod.DOD.value,
            "gutmann": WipeMethod.GUTMANN.value,
            "gutmann method": WipeMethod.GUTMANN.value,
        }
        key = value.strip().lower()
        if key not in mapping:
            raise ValueError("method must be one of: NIST, DoD, Gutmann")
        return mapping[key]


class WipeJobResponse(BaseModel):
    job_id: str
    device: str
    wipe_method: WipeMethod
    method: WipeMethod
    status: JobStatus
    progress: float = Field(..., ge=0, le=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    certificate_id: str | None = None
    last_message: str | None = None
    error: str | None = None


class CertificateMetadata(BaseModel):
    id: str
    job_id: str
    device: str
    device_serial_number: str
    device_type: str
    wipe_method: WipeMethod
    overwrite_passes: int
    timestamp: datetime
    verification_status: str
    recovered_files: int
    sha256_hash: str
    bytes_wiped: int
    execution_seconds: float
    verification_url: str
    qr_code_path: str
    json_path: str
    pdf_path: str


class VerificationResponse(BaseModel):
    device: str
    wipe_method: WipeMethod
    timestamp: datetime
    verification_status: str
