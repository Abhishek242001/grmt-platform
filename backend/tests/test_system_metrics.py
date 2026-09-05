import time

from app.core.system_metrics import collect_metrics


def test_collect_metrics_returns_all_expected_keys():
    result = collect_metrics()
    expected_keys = {
        "timestamp", "cpu_utilization_pct", "cpu_core_count", "cpu_per_core_pct",
        "memory_used_pct", "memory_used_gb", "memory_total_gb", "swap_used_pct",
        "disk_used_pct", "disk_used_gb", "disk_total_gb", "disk_read_mb_s",
        "disk_write_mb_s", "network_sent_mb_s", "network_recv_mb_s",
        "load_average_1m", "load_average_5m", "load_average_15m",
        "process_count", "uptime_seconds", "gpu_utilization_pct",
        "gpu_memory_used_mb", "gpu_memory_total_mb", "gpu_temperature_c",
    }
    assert expected_keys.issubset(result.keys())


def test_collect_metrics_values_are_real_and_sane():
    result = collect_metrics()
    assert 0.0 <= result["cpu_utilization_pct"] <= 100.0
    assert result["cpu_core_count"] >= 1
    assert 0.0 <= result["memory_used_pct"] <= 100.0
    assert result["memory_total_gb"] > 0
    assert 0.0 <= result["disk_used_pct"] <= 100.0
    assert result["process_count"] > 0
    assert result["uptime_seconds"] > 0


def test_first_call_has_zero_io_rates_no_prior_sample():
    """A fresh call to the rate-tracking internals (simulated by directly
    resetting the module's tracking state) must return 0.0 rather than a
    nonsensical since-boot average or a crash on missing prior state."""
    import app.core.system_metrics as sm
    sm._last_disk_io = None
    sm._last_disk_io_time = None
    sm._last_net_io = None
    sm._last_net_io_time = None

    result = collect_metrics()
    assert result["disk_read_mb_s"] == 0.0
    assert result["disk_write_mb_s"] == 0.0
    assert result["network_sent_mb_s"] == 0.0
    assert result["network_recv_mb_s"] == 0.0


def test_second_call_computes_a_real_rate_not_always_zero():
    """After two calls with a real time gap, rate fields must be present
    and non-negative (they may legitimately be 0.0 if nothing was actually
    read/written/sent in that window — the point is they compute without
    error, not that they're always nonzero)."""
    collect_metrics()  # establish baseline
    time.sleep(0.2)
    result = collect_metrics()
    assert result["disk_read_mb_s"] >= 0.0
    assert result["disk_write_mb_s"] >= 0.0
    assert result["network_sent_mb_s"] >= 0.0
    assert result["network_recv_mb_s"] >= 0.0


def test_gpu_metrics_gracefully_none_when_no_gpu_present():
    """This sandbox genuinely has no nvidia-smi — confirms the module
    returns None (not 0, which would misleadingly look like "0% GPU load"
    on a GPU-less machine) rather than raising."""
    result = collect_metrics()
    # Either genuinely populated (a real GPU present) or cleanly None
    # (no GPU) — never a crash, never a fake zero standing in for "unknown".
    if result["gpu_utilization_pct"] is None:
        assert result["gpu_memory_used_mb"] is None
        assert result["gpu_memory_total_mb"] is None
        assert result["gpu_temperature_c"] is None
    else:
        assert 0.0 <= result["gpu_utilization_pct"] <= 100.0
