from __future__ import annotations

import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable

from .models import WipeMethod

ProgressCallback = Callable[[float, str], None]


class WipeExecutor:
    """Secure overwrite executor for files or raw storage devices."""

    GUTMANN_PATTERNS = [
        b"\x55",
        b"\xAA",
        b"\x92\x49\x24",
        b"\x49\x24\x92",
        b"\x24\x92\x49",
        b"\x00",
        b"\x11",
        b"\x22",
        b"\x33",
        b"\x44",
        b"\x55",
        b"\x66",
        b"\x77",
        b"\x88",
        b"\x99",
        b"\xAA",
        b"\xBB",
        b"\xCC",
        b"\xDD",
        b"\xEE",
        b"\xFF",
        b"\x92\x49\x24",
        b"\x49\x24\x92",
        b"\x24\x92\x49",
        b"\x6D\xB6\xDB",
        b"\xB6\xDB\x6D",
        b"\xDB\x6D\xB6",
    ]

    def __init__(self, chunk_size: int = 4 * 1024 * 1024, dry_run: bool | None = None) -> None:
        self.chunk_size = chunk_size
        self.dry_run = (
            dry_run
            if dry_run is not None
            else os.getenv("WIPE_ENGINE_DRY_RUN", "true").strip().lower() == "true"
        )

    def wipe(
        self,
        target: str,
        method: WipeMethod,
        size_hint: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, object]:
        target_path = self._resolve_target(target)
        total_size = size_hint or self._get_size(target_path)
        start_time = datetime.now(timezone.utc)
        start_monotonic = time.monotonic()
        patterns = self._patterns(method)
        total_steps = len(patterns) + (1 if method == WipeMethod.NIST else 0)
        bytes_wiped = 0

        if progress_callback:
            progress_callback(0.0, "Wipe job started.")

        if self.dry_run:
            for idx, pattern in enumerate(patterns, start=1):
                time.sleep(0.1)
                bytes_wiped += total_size
                if progress_callback:
                    progress_callback(
                        round((idx / total_steps) * 100, 2),
                        f"Simulated pass {idx}/{len(patterns)} ({self._pattern_label(pattern)}).",
                    )
            if progress_callback:
                progress_callback(100.0, "Simulated wipe complete.")
        else:
            with open(target_path, "r+b", buffering=0) as handle:
                for idx, pattern in enumerate(patterns, start=1):
                    self._run_pass(handle, total_size, pattern)
                    bytes_wiped += total_size
                    if progress_callback:
                        progress_callback(
                            round((idx / total_steps) * 100, 2),
                            f"Pass {idx}/{len(patterns)} complete ({self._pattern_label(pattern)}).",
                        )
            if method == WipeMethod.NIST:
                self._verify_zeros(target_path, total_size)
                if progress_callback:
                    progress_callback(100.0, "NIST verification complete.")
            elif progress_callback:
                progress_callback(100.0, "Overwrite complete.")

        end_time = datetime.now(timezone.utc)
        return {
            "target_path": target_path,
            "bytes_wiped": bytes_wiped,
            "passes_completed": len(patterns),
            "execution_seconds": time.monotonic() - start_monotonic,
            "start_time": start_time,
            "end_time": end_time,
        }

    def _run_pass(self, handle, total_size: int, pattern: bytes | None) -> None:
        handle.seek(0)
        remaining = total_size
        while remaining > 0:
            chunk_len = min(self.chunk_size, remaining)
            if pattern is None:
                data = os.urandom(chunk_len)
            else:
                data = (pattern * ((chunk_len // len(pattern)) + 1))[:chunk_len]
            handle.write(data)
            remaining -= chunk_len
        handle.flush()
        os.fsync(handle.fileno())

    def _verify_zeros(self, target_path: str, total_size: int) -> None:
        checked = 0
        with open(target_path, "rb", buffering=0) as handle:
            while checked < total_size:
                chunk = handle.read(min(self.chunk_size, total_size - checked))
                if not chunk:
                    break
                if any(byte != 0 for byte in chunk):
                    raise RuntimeError("NIST verification failed: non-zero content detected.")
                checked += len(chunk)

    @staticmethod
    def _patterns(method: WipeMethod) -> list[bytes | None]:
        if method == WipeMethod.NIST:
            return [b"\x00"]
        if method == WipeMethod.DOD:
            return [b"\x00", b"\xFF", None]
        if method == WipeMethod.GUTMANN:
            return [None, None, None, None, *WipeExecutor.GUTMANN_PATTERNS, None, None, None, None]
        raise ValueError(f"Unsupported wipe method: {method}")

    @staticmethod
    def _pattern_label(pattern: bytes | None) -> str:
        if pattern is None:
            return "RANDOM"
        if len(pattern) == 1:
            return f"0x{pattern.hex().upper()}"
        return "MULTI_BYTE_PATTERN"

    @staticmethod
    def _resolve_target(device: str) -> str:
        if os.path.exists(device):
            return device
        os_name = platform.system().lower()
        normalized = device.strip()
        if os_name == "linux":
            return normalized if normalized.startswith("/dev/") else f"/dev/{normalized}"
        if os_name == "windows":
            upper = normalized.upper()
            if upper.startswith("\\\\.\\PHYSICALDRIVE"):
                return normalized
            if upper.startswith("PHYSICALDRIVE"):
                return f"\\\\.\\{normalized}"
            if normalized.isdigit():
                return f"\\\\.\\PhysicalDrive{normalized}"
        return normalized

    @staticmethod
    def _get_size(target_path: str) -> int:
        try:
            size = os.path.getsize(target_path)
            if size > 0:
                return size
        except OSError:
            pass

        if platform.system().lower() == "linux" and target_path.startswith("/dev/"):
            result = subprocess.run(["blockdev", "--getsize64", target_path], capture_output=True, text=True, check=True)
            return int(result.stdout.strip())
        raise RuntimeError(f"Unable to determine target size for '{target_path}'.")


# Backward compatibility for existing imports.
WipeEngine = WipeExecutor

