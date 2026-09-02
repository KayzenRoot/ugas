"""Low-dependency system and NVIDIA telemetry collectors.

Every probe is best effort.  Unsupported hardware is represented explicitly;
the collector never substitutes zeroes for unavailable GPU data.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ctypes
import ctypes.wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Sequence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run(args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a probe without a shell and with a short timeout."""

    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, check=False, shell=False)


def _windows_memory() -> dict[str, Any] | None:
    if sys.platform != "win32":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.wintypes.DWORD), ("dwMemoryLoad", ctypes.wintypes.DWORD),
                    ("ullTotalPhys", ctypes.wintypes.ULARGE_INTEGER), ("ullAvailPhys", ctypes.wintypes.ULARGE_INTEGER),
                    ("ullTotalPageFile", ctypes.wintypes.ULARGE_INTEGER), ("ullAvailPageFile", ctypes.wintypes.ULARGE_INTEGER),
                    ("ullTotalVirtual", ctypes.wintypes.ULARGE_INTEGER), ("ullAvailVirtual", ctypes.wintypes.ULARGE_INTEGER),
                    ("ullAvailExtendedVirtual", ctypes.wintypes.ULARGE_INTEGER)]
    value = MemoryStatus(); value.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        return None
    total = int(value.ullTotalPhys); available = int(value.ullAvailPhys); used = total - available
    return {"used_bytes": used, "total_bytes": total, "percent": round(used / total * 100, 2) if total else None, "status": "AVAILABLE"}


def _proc_memory() -> dict[str, Any] | None:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, raw = line.split(":", 1); values[key] = int(raw.strip().split()[0]) * 1024
        total = values["MemTotal"]; available = values.get("MemAvailable", values.get("MemFree", 0)); used = total - available
        return {"used_bytes": used, "total_bytes": total, "percent": round(used / total * 100, 2) if total else None, "status": "AVAILABLE"}
    except (OSError, KeyError, ValueError):
        return None


def memory_metrics() -> dict[str, Any]:
    windows = _windows_memory()
    if windows:
        return windows
    linux = _proc_memory()
    if linux:
        return linux
    return {"used_bytes": None, "total_bytes": None, "percent": None, "status": "UNAVAILABLE", "reason": "platform memory API unavailable"}


class CpuSampler:
    def __init__(self) -> None:
        self._previous: tuple[int, int] | None = None

    def _windows_times(self) -> tuple[int, int] | None:
        if sys.platform != "win32":
            return None
        class FileTime(ctypes.Structure):
            _fields_ = [("low", ctypes.wintypes.DWORD), ("high", ctypes.wintypes.DWORD)]
        idle = FileTime(); kernel = FileTime(); user = FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        def value(item: FileTime) -> int:
            return (int(item.high) << 32) | int(item.low)
        idle_v, total_v = value(idle), value(kernel) + value(user)
        return total_v, idle_v

    def _proc_times(self) -> tuple[int, int] | None:
        try:
            values = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
            numbers = [int(item) for item in values[1:]]
            idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
            return sum(numbers), idle
        except (OSError, IndexError, ValueError):
            return None

    def sample(self) -> dict[str, Any]:
        current = self._windows_times() or self._proc_times()
        if current is None:
            return {"percent": None, "logical_cpus": os.cpu_count() or 1, "status": "UNAVAILABLE", "reason": "platform CPU times unavailable"}
        percent = None
        if self._previous is not None:
            total_delta = current[0] - self._previous[0]; idle_delta = current[1] - self._previous[1]
            if total_delta > 0:
                percent = round(max(0.0, min(100.0, (total_delta - idle_delta) / total_delta * 100)), 2)
        self._previous = current
        return {"percent": percent, "logical_cpus": os.cpu_count() or 1, "status": "AVAILABLE" if percent is not None else "WARMING_UP"}


def probe_nvidia_smi(*, executable: str = "nvidia-smi", timeout: float = 0.8, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None) -> dict[str, Any]:
    runner = runner or _run
    query = [executable, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw", "--format=csv,noheader,nounits"]
    try:
        result = runner(query, timeout=timeout)
    except FileNotFoundError:
        return {"status": "GPU_UNAVAILABLE", "capability": "UNSUPPORTED", "reason": "nvidia-smi executable not found", "timestamp": _now()}
    except subprocess.TimeoutExpired:
        return {"status": "GPU_UNAVAILABLE", "capability": "TIMEOUT", "reason": "nvidia-smi probe timed out", "timestamp": _now()}
    except OSError as exc:
        return {"status": "GPU_UNAVAILABLE", "capability": "ERROR", "reason": f"nvidia-smi probe failed: {type(exc).__name__}", "timestamp": _now()}
    if result.returncode != 0 or not result.stdout.strip():
        reason = (result.stderr or "nvidia-smi returned no GPU").strip()[:300]
        return {"status": "GPU_UNAVAILABLE", "capability": "UNSUPPORTED", "reason": reason, "timestamp": _now()}
    fields = [item.strip() for item in result.stdout.strip().splitlines()[0].split(",")]
    if len(fields) < 6:
        return {"status": "GPU_UNAVAILABLE", "capability": "MALFORMED", "reason": "nvidia-smi returned an unexpected row", "timestamp": _now()}
    def number(value: str) -> float | None:
        try: return float(value)
        except ValueError: return None
    gpu = {"name": fields[0], "utilization_percent": number(fields[1]), "vram_used_mb": number(fields[2]),
           "vram_total_mb": number(fields[3]), "temperature_c": number(fields[4]), "power_draw_w": number(fields[5])}
    try:
        processes = runner([executable, "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"], timeout=timeout)
        gpu_processes = []
        if processes.returncode == 0:
            for row in processes.stdout.strip().splitlines():
                values = [item.strip() for item in row.split(",")]
                if len(values) >= 3:
                    gpu_processes.append({"pid": values[0], "process_name": values[1], "memory_used_mb": number(values[2])})
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        gpu_processes = []
    gpu["processes"] = gpu_processes
    return {"status": "GPU_AVAILABLE", "capability": "NVIDIA_SMI", "reason": None, "gpu": gpu, "timestamp": _now()}


def process_resource_metrics(pid: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {"pid": pid, "cpu_percent": None, "rss_bytes": None, "status": "UNAVAILABLE", "reason": "optional process metrics dependency not installed"}
    if not pid:
        result["reason"] = "process id unavailable"; return result
    try:
        import psutil  # type: ignore
        process = psutil.Process(pid)
        result.update({"cpu_percent": process.cpu_percent(interval=None), "rss_bytes": process.memory_info().rss, "status": "AVAILABLE", "reason": None, "name": process.name()})
    except ImportError:
        if sys.platform == "linux":
            try:
                result.update({"rss_bytes": int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE"), "status": "PARTIAL", "reason": "RSS available; CPU requires psutil"})
            except (OSError, IndexError, ValueError):
                pass
    except (OSError, ValueError):
        result["reason"] = "process exited or cannot be inspected"
    return result


def collect_system_metrics(repo_root: Path, *, pid: int | None = None, cpu_sampler: CpuSampler | None = None, gpu_probe: dict[str, Any] | None = None) -> dict[str, Any]:
    cpu = (cpu_sampler or CpuSampler()).sample()
    memory = memory_metrics()
    volume = Path(repo_root).resolve().anchor or str(repo_root)
    try:
        disk = shutil.disk_usage(volume)
        disk_metrics = {"used_bytes": disk.used, "free_bytes": disk.free, "total_bytes": disk.total, "percent": round(disk.used / disk.total * 100, 2) if disk.total else None, "status": "AVAILABLE", "volume": volume}
    except OSError as exc:
        disk_metrics = {"used_bytes": None, "free_bytes": None, "total_bytes": None, "percent": None, "status": "UNAVAILABLE", "reason": f"disk probe failed: {type(exc).__name__}", "volume": volume}
    gpu = gpu_probe if gpu_probe is not None else probe_nvidia_smi()
    return {"timestamp": _now(), "cpu": cpu, "memory": memory, "disk": disk_metrics, "gpu": gpu, "ugas_process": process_resource_metrics(pid)}
