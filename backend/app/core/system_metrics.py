"""Real-time system resource metrics for the admin panel (update44) — 15
genuine hardware readings via psutil (+ nvidia-smi for GPU, since psutil
itself has no GPU support). Every value here is a real measurement, not a
placeholder — this module exists specifically so the admin dashboard shows
this Studio's actual current load, not invented numbers.

Split as a pure `collect_metrics()` function (no FastAPI/WebSocket
dependency) so it's directly testable — the broadcasting loop that calls
this every few seconds and publishes to the "admin:system-metrics" WS
channel lives in app/main.py's startup, not here."""
import shutil
import subprocess
import time

import psutil

_last_disk_io = None
_last_disk_io_time = None
_last_net_io = None
_last_net_io_time = None


def _disk_io_rates_mb_s() -> tuple[float, float]:
    """Read and write MB/s since the last call — the first call in a
    process's lifetime has no prior sample to diff against, so it returns
    (0.0, 0.0) rather than a nonsensical since-boot average."""
    global _last_disk_io, _last_disk_io_time
    now = time.time()
    counters = psutil.disk_io_counters()
    if counters is None:
        return 0.0, 0.0
    if _last_disk_io is None:
        _last_disk_io, _last_disk_io_time = counters, now
        return 0.0, 0.0
    elapsed = max(now - _last_disk_io_time, 0.001)
    read_mb_s = (counters.read_bytes - _last_disk_io.read_bytes) / elapsed / (1024 * 1024)
    write_mb_s = (counters.write_bytes - _last_disk_io.write_bytes) / elapsed / (1024 * 1024)
    _last_disk_io, _last_disk_io_time = counters, now
    return round(max(read_mb_s, 0.0), 2), round(max(write_mb_s, 0.0), 2)


def _net_io_rates_mb_s() -> tuple[float, float]:
    global _last_net_io, _last_net_io_time
    now = time.time()
    counters = psutil.net_io_counters()
    if _last_net_io is None:
        _last_net_io, _last_net_io_time = counters, now
        return 0.0, 0.0
    elapsed = max(now - _last_net_io_time, 0.001)
    sent_mb_s = (counters.bytes_sent - _last_net_io.bytes_sent) / elapsed / (1024 * 1024)
    recv_mb_s = (counters.bytes_recv - _last_net_io.bytes_recv) / elapsed / (1024 * 1024)
    _last_net_io, _last_net_io_time = counters, now
    return round(max(sent_mb_s, 0.0), 2), round(max(recv_mb_s, 0.0), 2)


def _gpu_metrics() -> dict:
    """Parses real nvidia-smi output — returns None values (not zeros,
    which would misleadingly look like "0% GPU load" on a machine that
    simply has no GPU) when nvidia-smi isn't available at all."""
    if shutil.which("nvidia-smi") is None:
        return {
            "gpu_utilization_pct": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_temperature_c": None,
        }
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # First GPU only (--query-gpu returns one line per GPU; this
        # project's Studios are single-GPU, per PROJECT_HANDOFF.md's own
        # T4 references throughout).
        first_line = result.stdout.strip().splitlines()[0]
        util, mem_used, mem_total, temp = [p.strip() for p in first_line.split(",")]
        return {
            "gpu_utilization_pct": float(util),
            "gpu_memory_used_mb": float(mem_used),
            "gpu_memory_total_mb": float(mem_total),
            "gpu_temperature_c": float(temp),
        }
    except Exception:
        # A transient nvidia-smi failure (busy, driver hiccup) shouldn't
        # break the whole metrics broadcast — degrade to unknown for this
        # one cycle rather than crash the broadcasting loop.
        return {
            "gpu_utilization_pct": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "gpu_temperature_c": None,
        }


def collect_metrics() -> dict:
    """Returns 15 real, current hardware readings. Call this on a fixed
    interval (see app/main.py's broadcast loop) — disk/network rates are
    computed as a delta since the PREVIOUS call, so calling this in a tight
    loop with no delay between calls will report near-zero rates, not an
    error — that's an expected consequence of the delta math, not a bug."""
    cpu_pct = psutil.cpu_percent(interval=None)
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    disk_read_mb_s, disk_write_mb_s = _disk_io_rates_mb_s()
    net_sent_mb_s, net_recv_mb_s = _net_io_rates_mb_s()
    load1, load5, load15 = psutil.getloadavg()
    gpu = _gpu_metrics()

    return {
        "timestamp": time.time(),
        # 1
        "cpu_utilization_pct": cpu_pct,
        # 2
        "cpu_core_count": psutil.cpu_count(logical=True),
        # 3
        "cpu_per_core_pct": per_core,
        # 4
        "memory_used_pct": mem.percent,
        # 5
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        # 6
        "swap_used_pct": swap.percent,
        # 7
        "disk_used_pct": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        # 8, 9
        "disk_read_mb_s": disk_read_mb_s,
        "disk_write_mb_s": disk_write_mb_s,
        # 10, 11
        "network_sent_mb_s": net_sent_mb_s,
        "network_recv_mb_s": net_recv_mb_s,
        # 12
        "load_average_1m": round(load1, 2),
        "load_average_5m": round(load5, 2),
        "load_average_15m": round(load15, 2),
        # 13
        "process_count": len(psutil.pids()),
        # 14
        "uptime_seconds": round(time.time() - psutil.boot_time()),
        # 15 (four related GPU readings — see _gpu_metrics)
        **gpu,
    }
