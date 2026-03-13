from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .device_detector import DeviceDetector
from .logger import configure_logging, get_logger
from .models import (
    CertificateResponse,
    DeviceInfo,
    WipeJobResponse,
    WipeRequest,
)
from .wipe_engine import WipeEngine
from .wipe_manager import WipeManager


configure_logging()
logger = get_logger("cipherforge.api")

app = FastAPI(
    title="CipherForge Wipe Service",
    version="1.0.0",
    description="Secure data wiping orchestration API for storage devices.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CIPHERFORGE_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

detector = DeviceDetector()
engine = WipeEngine()
manager = WipeManager(detector=detector, engine=engine)


@app.get("/devices", response_model=list[DeviceInfo], tags=["devices"])
async def get_devices() -> list[DeviceInfo]:
    """Detect and return available storage devices."""
    try:
        return detector.list_devices()
    except Exception as exc:
        logger.exception("Device listing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device detection failed: {exc}",
        ) from exc


@app.post("/wipe", response_model=WipeJobResponse, status_code=status.HTTP_202_ACCEPTED, tags=["wipe"])
async def start_wipe(request: WipeRequest) -> WipeJobResponse:
    """Queue a wipe job for the selected device and algorithm."""
    try:
        return manager.start_wipe(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to queue wipe job")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue wipe job: {exc}",
        ) from exc


@app.get("/wipe/status/{job_id}", response_model=WipeJobResponse, tags=["wipe"])
async def get_wipe_status(job_id: str) -> WipeJobResponse:
    """Fetch progress and current state for a wipe job."""
    status_payload = manager.get_status(job_id)
    if not status_payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return status_payload


@app.get("/certificate/{id}", response_model=CertificateResponse, tags=["certificate"])
async def get_certificate(id: str) -> CertificateResponse:
    """Return wipe certificate metadata by certificate ID."""
    certificate = manager.get_certificate(id)
    if not certificate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Certificate '{id}' not found.")
    return certificate


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
