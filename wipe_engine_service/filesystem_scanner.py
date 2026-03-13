from __future__ import annotations

import json
import logging
import platform
import re
import subprocess

from .models import LogicalDriveInfo


class FilesystemScanner:
    """Detects logical drives for file-level shredding workflows."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("wipe_engine_service.filesystem_scanner")

    def list_logical_drives(self) -> list[LogicalDriveInfo]:
        if platform.system().lower() != "windows":
            self.logger.info("Logical drive scan is only supported on Windows hosts.")
            return []

        wmic_drives = self._scan_with_wmic()
        if wmic_drives:
            return sorted(wmic_drives, key=lambda drive: drive.drive.upper())

        powershell_drives = self._scan_with_powershell_driveinfo()
        if powershell_drives:
            self.logger.info("Logical drives loaded via PowerShell fallback.")
            return sorted(powershell_drives, key=lambda drive: drive.drive.upper())

        self.logger.warning("Logical drive detection failed with all available strategies.")
        return []

    def _scan_with_wmic(self) -> list[LogicalDriveInfo]:
        command = ["wmic", "logicaldisk", "get", "name,size,description,volumename"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        except FileNotFoundError:
            self.logger.warning("wmic command not found on this system. Falling back to PowerShell.")
            return []
        except subprocess.CalledProcessError as exc:
            self.logger.warning(
                "WMIC logical drive detection failed",
                extra={
                    "command": command,
                    "returncode": exc.returncode,
                    "stderr": (exc.stderr or "").strip(),
                    "stdout": (exc.stdout or "").strip(),
                },
            )
            return []

        return self._parse_wmic_output(result.stdout)

    def _scan_with_powershell_driveinfo(self) -> list[LogicalDriveInfo]:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "[System.IO.DriveInfo]::GetDrives() | Select-Object Name,DriveType,TotalSize,VolumeLabel | ConvertTo-Json -Compress",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        except FileNotFoundError:
            self.logger.warning("PowerShell executable not found on this system.")
            return []
        except subprocess.CalledProcessError as exc:
            self.logger.error(
                "PowerShell logical drive detection failed",
                extra={
                    "command": command,
                    "returncode": exc.returncode,
                    "stderr": (exc.stderr or "").strip(),
                    "stdout": (exc.stdout or "").strip(),
                },
            )
            return []

        payload = (result.stdout or "").strip()
        if not payload:
            return []

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            self.logger.warning("Unable to parse PowerShell drive JSON output.")
            return []

        rows = decoded if isinstance(decoded, list) else [decoded]
        drives: list[LogicalDriveInfo] = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            name_raw = str(row.get("Name") or "").strip()
            if not name_raw:
                continue

            drive = self._normalize_drive_name(name_raw)
            if not drive:
                continue

            size_bytes = self._to_int(str(row.get("TotalSize") or "0"))
            drive_type = self._map_drive_type(row.get("DriveType"))
            volume_label = str(row.get("VolumeLabel") or "").strip() or None
            drives.append(
                LogicalDriveInfo(
                    drive=drive,
                    type=drive_type,
                    size=self._format_size(size_bytes),
                    label=volume_label,
                    size_bytes=size_bytes,
                )
            )

        return drives

    def _parse_wmic_output(self, output: str) -> list[LogicalDriveInfo]:
        lines = [line.rstrip() for line in output.splitlines() if line.strip()]
        if not lines:
            return []

        header = lines[0].strip()
        headers = re.split(r"\s{2,}", header)
        header_positions = {name.lower(): idx for idx, name in enumerate(headers)}
        required = {"description", "name", "size"}
        if not required.issubset(header_positions.keys()):
            self.logger.warning("Unexpected WMIC logicaldisk output header: %s", header)
            return []

        drives: list[LogicalDriveInfo] = []
        for line in lines[1:]:
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) < len(headers):
                continue

            description = parts[header_positions["description"]].strip()
            name = parts[header_positions["name"]].strip()
            size_raw = parts[header_positions["size"]].strip()
            volume_label = ""
            if "volumename" in header_positions and header_positions["volumename"] < len(parts):
                volume_label = parts[header_positions["volumename"]].strip()

            if not name:
                continue

            drive_name = self._normalize_drive_name(name)
            if not drive_name:
                continue

            size_bytes = self._to_int(size_raw)
            drives.append(
                LogicalDriveInfo(
                    drive=drive_name,
                    type=self._normalize_drive_type(description),
                    size=self._format_size(size_bytes),
                    label=volume_label or None,
                    size_bytes=size_bytes,
                )
            )

        return drives

    @staticmethod
    def _to_int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0B"
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(size_bytes)
        unit_idx = 0
        while size >= 1024 and unit_idx < len(units) - 1:
            size /= 1024
            unit_idx += 1
        if unit_idx == 0:
            return f"{int(size)}{units[unit_idx]}"
        value = f"{size:.1f}".rstrip("0").rstrip(".")
        return f"{value}{units[unit_idx]}"

    @staticmethod
    def _normalize_drive_type(description: str) -> str:
        normalized = (description or "").strip()
        if not normalized:
            return "Unknown"
        if normalized.lower() == "local fixed disk":
            return "Local Disk"
        return normalized

    @staticmethod
    def _normalize_drive_name(value: str) -> str:
        normalized = (value or "").strip().replace("/", "\\")
        if not normalized:
            return ""
        if normalized.endswith("\\"):
            normalized = normalized[:-1]
        match = re.match(r"^[A-Za-z]:$", normalized)
        if not match:
            return ""
        return normalized.upper()

    @staticmethod
    def _map_drive_type(value: object) -> str:
        # Win32 DriveType values:
        # 0 Unknown, 1 No root dir, 2 Removable, 3 Fixed, 4 Network, 5 CD-ROM, 6 RAM disk.
        mapping = {
            0: "Unknown",
            1: "No Root",
            2: "Removable Disk",
            3: "Local Disk",
            4: "Network",
            5: "CD-ROM",
            6: "RAM Disk",
        }
        if isinstance(value, int):
            return mapping.get(value, "Unknown")
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.isdigit():
                return mapping.get(int(candidate), "Unknown")
            return candidate or "Unknown"
        return "Unknown"
