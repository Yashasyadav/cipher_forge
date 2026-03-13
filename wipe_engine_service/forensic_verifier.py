from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import logging


class ForensicVerifier:
    """Post-wipe forensic validation using PhotoRec and TestDisk."""

    def __init__(self, timeout_seconds: int = 180, working_dir: str | Path | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger("wipe_engine_service.forensic_verifier")
        self.working_dir = (
            Path(working_dir)
            if working_dir
            else Path(__file__).resolve().parents[1] / "certificates" / "forensic_tmp"
        )
        self.working_dir.mkdir(parents=True, exist_ok=True)

    def verify(self, device: str) -> dict[str, object]:
        target = self._normalize_target(device)
        recovered_files = 0
        details: list[dict[str, object]] = []

        recovery_dir = self.working_dir / f"recovery_{uuid.uuid4().hex}"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        try:
            recovered_files += self._run_photorec(target, recovery_dir, details)
            recovered_files += self._run_testdisk(target, recovery_dir, details)
        finally:
            shutil.rmtree(recovery_dir, ignore_errors=True)

        verification = "PASSED" if recovered_files == 0 else "FAILED"
        result = {
            "recovered_files": recovered_files,
            "verification": verification,
            "details": details,
        }
        self.logger.info(
            "Forensic verification finished",
            extra={
                "event": "forensic_verification_finished",
                "device": target,
                "recovered_files": recovered_files,
                "verification": verification,
            },
        )
        return result

    def _run_photorec(self, target: str, recovery_dir: Path, details: list[dict[str, object]]) -> int:
        binary = self._resolve_binary(["photorec", "photorec_win.exe"])
        if not binary:
            details.append({"tool": "photorec", "status": "not_found", "recovered_files": 0})
            return 0

        command = [binary, "/log", "/d", str(recovery_dir), "/cmd", target, "search"]
        return self._execute_recovery("photorec", command, recovery_dir, details)

    def _run_testdisk(self, target: str, recovery_dir: Path, details: list[dict[str, object]]) -> int:
        binary = self._resolve_binary(["testdisk", "testdisk_win.exe"])
        if not binary:
            details.append({"tool": "testdisk", "status": "not_found", "recovered_files": 0})
            return 0

        log_file = recovery_dir / "testdisk.log"
        command = [binary, "/log", "/logname", str(log_file), "/cmd", target, "analyze,quicksearch,quit"]
        return self._execute_recovery("testdisk", command, recovery_dir, details)

    def _execute_recovery(
        self,
        tool_name: str,
        command: list[str],
        recovery_dir: Path,
        details: list[dict[str, object]],
    ) -> int:
        before_count = self._count_recovered_files(recovery_dir)
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            output = f"{process.stdout}\n{process.stderr}"
            parsed_count = self._parse_recovered_files(output)
            after_count = self._count_recovered_files(recovery_dir)
            recovered_files = max(parsed_count, max(0, after_count - before_count))

            details.append(
                {
                    "tool": tool_name,
                    "status": "completed" if process.returncode == 0 else "non_zero_exit",
                    "returncode": process.returncode,
                    "recovered_files": recovered_files,
                }
            )
            if process.returncode != 0:
                self.logger.warning(
                    "Recovery tool returned non-zero exit",
                    extra={"tool": tool_name, "returncode": process.returncode},
                )
            return recovered_files
        except subprocess.TimeoutExpired:
            details.append({"tool": tool_name, "status": "timeout", "recovered_files": 0})
            self.logger.warning(
                "Recovery tool timed out",
                extra={"tool": tool_name, "timeout_seconds": self.timeout_seconds},
            )
            return 0
        except Exception:
            details.append({"tool": tool_name, "status": "error", "recovered_files": 0})
            self.logger.exception("Recovery tool execution failed", extra={"tool": tool_name})
            return 0

    @staticmethod
    def _parse_recovered_files(output_text: str) -> int:
        patterns = [
            r"(\d+)\s+files?\s+recovered",
            r"recovered\s+files?\s*[:=]\s*(\d+)",
            r"(\d+)\s+file\(s\)",
        ]
        best = 0
        for pattern in patterns:
            for match in re.finditer(pattern, output_text, flags=re.IGNORECASE):
                try:
                    best = max(best, int(match.group(1)))
                except (TypeError, ValueError):
                    continue
        return best

    @staticmethod
    def _count_recovered_files(path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        try:
            for _, _, files in os.walk(path, onerror=lambda _: None):
                total += len([name for name in files if not name.lower().endswith(".log")])
        except Exception:
            return total
        return total

    @staticmethod
    def _resolve_binary(candidates: list[str]) -> str | None:
        for name in candidates:
            found = shutil.which(name)
            if found:
                return found
        return None

    @staticmethod
    def _normalize_target(device: str) -> str:
        normalized = device.strip()
        os_name = platform.system().lower()
        if os_name == "linux":
            return normalized if normalized.startswith("/dev/") else f"/dev/{normalized}"
        if os_name == "windows":
            upper = normalized.upper()
            if upper.startswith("\\\\.\\PHYSICALDRIVE"):
                return normalized
            if upper.startswith("PHYSICALDRIVE"):
                return f"\\\\.\\{normalized}"
        return normalized

