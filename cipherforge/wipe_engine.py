from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable

from .logger import get_logger
from .models import WipeMethod

ProgressCallback = Callable[[float, str], None]


class WipeEngine:
    """
    Performs software-based overwrite sanitization against a file or raw device.
    """

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
            else os.getenv("CIPHERFORGE_DRY_RUN", "false").strip().lower() == "true"
        )
        self.logger = get_logger("cipherforge.wipe_engine")

    def wipe(
        self,
        target: str,
        method: WipeMethod,
        size_hint: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, object]:
        target_path = self._resolve_target(target)
        total_size = size_hint or self._get_target_size(target_path)
        start_ts = datetime.now(timezone.utc)
        start_monotonic = time.monotonic()
        pass_patterns = self._patterns_for(method)
        total_steps = len(pass_patterns) + (1 if method == WipeMethod.NIST else 0)
        bytes_wiped = 0

        self.logger.info(
            "Starting wipe operation",
            extra={
                "event": "wipe_started",
                "target": target_path,
                "method": method.value,
                "size_bytes": total_size,
                "dry_run": self.dry_run,
            },
        )

        if progress_callback:
            progress_callback(0.0, "Wipe job accepted.")

        if self.dry_run:
            bytes_wiped = self._simulate_wipe(total_size, pass_patterns, method, progress_callback)
        else:
            bytes_wiped = self._execute_wipe(
                target_path=target_path,
                target_size=total_size,
                pass_patterns=pass_patterns,
                method=method,
                total_steps=total_steps,
                progress_callback=progress_callback,
            )

        finished_ts = datetime.now(timezone.utc)
        duration = time.monotonic() - start_monotonic
        audit_digest = hashlib.sha256(
            f"{target_path}|{method.value}|{start_ts.isoformat()}|{finished_ts.isoformat()}|{bytes_wiped}".encode(
                "utf-8"
            )
        ).hexdigest()

        self.logger.info(
            "Wipe operation completed",
            extra={
                "event": "wipe_completed",
                "target": target_path,
                "method": method.value,
                "duration_seconds": round(duration, 3),
                "bytes_wiped": bytes_wiped,
            },
        )

        return {
            "target_path": target_path,
            "bytes_wiped": bytes_wiped,
            "passes_completed": len(pass_patterns),
            "execution_seconds": duration,
            "started_at": start_ts,
            "finished_at": finished_ts,
            "audit_digest": audit_digest,
        }

    def _execute_wipe(
        self,
        target_path: str,
        target_size: int,
        pass_patterns: list[bytes | None],
        method: WipeMethod,
        total_steps: int,
        progress_callback: ProgressCallback | None,
    ) -> int:
        bytes_wiped = 0
        with open(target_path, "r+b", buffering=0) as handle:
            for pass_index, pattern in enumerate(pass_patterns, start=1):
                label = self._pattern_label(pattern)
                self.logger.info(
                    "Running overwrite pass",
                    extra={
                        "event": "wipe_pass",
                        "target": target_path,
                        "pass_index": pass_index,
                        "pass_total": len(pass_patterns),
                        "pattern": label,
                    },
                )
                self._run_pass(
                    handle=handle,
                    total_size=target_size,
                    pattern=pattern,
                )
                bytes_wiped += target_size
                if progress_callback:
                    progress_callback(
                        round((pass_index / total_steps) * 100, 2),
                        f"Pass {pass_index}/{len(pass_patterns)} complete ({label}).",
                    )

        if method == WipeMethod.NIST:
            self._verify_zeroes(target_path, target_size)
            if progress_callback:
                progress_callback(100.0, "NIST verification complete.")
        elif progress_callback:
            progress_callback(100.0, "Overwrite complete.")

        return bytes_wiped

    def _simulate_wipe(
        self,
        target_size: int,
        pass_patterns: list[bytes | None],
        method: WipeMethod,
        progress_callback: ProgressCallback | None,
    ) -> int:
        total_steps = len(pass_patterns) + (1 if method == WipeMethod.NIST else 0)
        bytes_wiped = 0
        for pass_index, pattern in enumerate(pass_patterns, start=1):
            time.sleep(0.15)
            bytes_wiped += target_size
            if progress_callback:
                progress_callback(
                    round((pass_index / total_steps) * 100, 2),
                    f"Simulated pass {pass_index}/{len(pass_patterns)} ({self._pattern_label(pattern)}).",
                )
        if method == WipeMethod.NIST and progress_callback:
            time.sleep(0.15)
            progress_callback(100.0, "Simulated NIST verification complete.")
        elif progress_callback:
            progress_callback(100.0, "Simulated wipe complete.")
        return bytes_wiped

    def _run_pass(self, handle, total_size: int, pattern: bytes | None) -> None:
        handle.seek(0)
        remaining = total_size
        while remaining > 0:
            chunk_len = min(self.chunk_size, remaining)
            if pattern is None:
                payload = os.urandom(chunk_len)
            else:
                payload = (pattern * ((chunk_len // len(pattern)) + 1))[:chunk_len]
            handle.write(payload)
            remaining -= chunk_len
        handle.flush()
        os.fsync(handle.fileno())

    def _verify_zeroes(self, target_path: str, total_size: int) -> None:
        checked = 0
        with open(target_path, "rb", buffering=0) as handle:
            while checked < total_size:
                chunk = handle.read(min(self.chunk_size, total_size - checked))
                if not chunk:
                    break
                if any(byte != 0 for byte in chunk):
                    raise RuntimeError("NIST verification failed: non-zero data found after overwrite.")
                checked += len(chunk)

    def _patterns_for(self, method: WipeMethod) -> list[bytes | None]:
        if method == WipeMethod.NIST:
            return [b"\x00"]
        if method == WipeMethod.DOD:
            return [b"\x00", b"\xFF", None]
        if method == WipeMethod.GUTMANN:
            return [None, None, None, None, *self.GUTMANN_PATTERNS, None, None, None, None]
        raise ValueError(f"Unsupported wipe method: {method}")

    def _resolve_target(self, device: str) -> str:
        if os.path.exists(device):
            return device

        system_name = platform.system().lower()
        normalized = device.strip()

        if system_name == "linux":
            return normalized if normalized.startswith("/dev/") else f"/dev/{normalized}"

        if system_name == "windows":
            upper = normalized.upper()
            if upper.startswith("\\\\.\\PHYSICALDRIVE"):
                return normalized
            if upper.startswith("PHYSICALDRIVE"):
                return f"\\\\.\\{normalized}"
            if normalized.isdigit():
                return f"\\\\.\\PhysicalDrive{normalized}"
            return normalized

        return normalized

    def _get_target_size(self, target_path: str) -> int:
        try:
            size = os.path.getsize(target_path)
            if size > 0:
                return size
        except OSError:
            pass

        if platform.system().lower() == "linux" and target_path.startswith("/dev/"):
            result = subprocess.run(
                ["blockdev", "--getsize64", target_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return int(result.stdout.strip())

        raise RuntimeError(
            f"Unable to determine target size for '{target_path}'. Provide a valid device path or size hint."
        )

    @staticmethod
    def _pattern_label(pattern: bytes | None) -> str:
        if pattern is None:
            return "RANDOM"
        if len(pattern) == 1:
            return f"0x{pattern.hex().upper()}"
        return f"PATTERN({pattern.hex().upper()})"

