#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cost-first SR mode ranking (HWiNFO)

Primary ranking key (lower is better):
  real_cpu_gpu_power_w_avg  = (gpu_power_w - idle_gpu_power_w) + (cpu_pkg_power_w - idle_cpu_pkg_power_w)

used as a tie-breaker when primary rank_key is identical:
  Use a normalized "resource pressure" score built from 5 NON-power sensors:

    1) gpu_util_pct_avg            - GPU core utilization: primary "busy-ness" / workload proxy
    2) vram_ctrl_util_pct_avg      - VRAM controller util: bandwidth / memory-bound pressure proxy
    3) gpu_effective_clock_mhz_avg - Effective clock: clock residency / DVFS behavior proxy
    4) vram_used_mb_avg            - Dedicated VRAM used: memory footprint proxy
    5) cpu_util_pct_avg            - CPU utilization: CPU-side overhead / bottleneck proxy

The tie-breaker score is a weighted, normalized [0..1] composite:
  Higher score => more pressure => worse. In a tie on primary cost, prefer LOWER tie-breaker score.

"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, timedelta, date
import numpy as np

# Import 'hwinfo_readlogs' loader and paths
from hwinfo_readlogs import load_idle_and_sr, IDLE_CSV, SR_DIR

# ============== CONFIG (output + window) ==============
OUT_DIR = r".\sh2_hwinfo_out_cost_first"
WINDOW_SECONDS = 60  # wall-time window; rows inside can be < 60 if sampling cadence > 1s
# ======================================================

# Only these sensors (Chinese/English headers) → aliases
HEADER_TO_ALIAS: Dict[str, str] = {
    # GPU Core
    "GPU 頻率 [MHz]": "gpu_clock_mhz",
    "GPU 有效頻率 [MHz]": "gpu_effective_clock_mhz",

    # GPU Memory clock
    "顯示記憶體頻率 [MHz]": "vram_clock_mhz",

    # GPU Util
    "GPU 核心使用率 [%]": "gpu_util_pct",
    "顯示記憶體控制器使用率 [%]": "vram_ctrl_util_pct",

    # GPU Memory usage
    "顯示記憶體使用 [%]": "vram_usage_pct",
    "GPU D3D 專用顯示記憶體 [MB]": "vram_used_mb",

    # GPU Power
    "GPU 功率 [W]": "gpu_power_w",

    # GPU Thermals
    "GPU 溫度 [℃]": "gpu_temp_c",
    "GPU 熱點溫度 [℃]": "gpu_hotspot_c",

    # GPU Voltage
    "GPU 核心電壓 [V]": "gpu_voltage_v",

    # CPU
    "CPU 總使用率 [%]": "cpu_util_pct",
    "核心有效頻率 (avg) [MHz]": "cpu_effective_freq_mhz",
    "CPU 封裝功率 [W]": "cpu_pkg_power_w",
    "CPU (Tctl/Tdie) [℃]": "cpu_temp_c",
}


# Create output directory if missing.
def ensure_outdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# Normalize CSV cell/header strings (strip BOM/quotes/whitespace).
def norm(s: str) -> str:
    return str(s).replace("\ufeff", "").strip().strip('"').strip("'")


# Parse HWiNFO Date + Time where Time can be: - HH:MM:SS(.ms) or - mm:SS(.ms)  (observed in logs)
# or - Time-only strings (attach dummy date 1970-01-01)
def parse_dt(date_str: Optional[str], time_str: str) -> Optional[datetime]:
    t_raw = norm(time_str).replace(",", ".")
    d_raw = norm(date_str) if date_str else None

    # 1) Full date+time common formats
    if d_raw:
        s = f"{d_raw} {t_raw}"
        fmts = [
            "%d.%m.%Y %H:%M:%S.%f", "%d.%m.%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S",
            "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S",
        ]
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass

        # If that failed, might be mm:SS(.ms):
        # parse date separately, then interpret time as minutes:seconds.
        try:
            dd: Optional[date] = None
            for dfmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    dd = datetime.strptime(d_raw, dfmt).date()
                    break
                except ValueError:
                    dd = None
            if dd:
                try:
                    tt = datetime.strptime(t_raw, "%M:%S.%f").time()
                except ValueError:
                    tt = datetime.strptime(t_raw, "%M:%S").time()
                return datetime.combine(dd, tt)
        except Exception:
            pass

    # 2) Time-only
    for tfmt in ("%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", "%M:%S"):
        try:
            t = datetime.strptime(t_raw, tfmt).time()
            return datetime.combine(date(1970, 1, 1), t)
        except ValueError:
            continue

    return None


# Parse numeric cell robustly: - strips units/symbols, - allows scientific notation, - returns None on empty/invalid
def parse_float(cell: str) -> Optional[float]:
    t = norm(cell)
    if t == "":
        return None
    keep = []
    for ch in t:
        if ch.isdigit() or ch in ".-+eE":
            keep.append(ch)
    s = "".join(keep)
    if s in ("", ".", "-", "+"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def locate_columns(headers: List[str]) -> Tuple[Optional[int], Optional[int], Dict[int, str]]:
    # Find date/time indices (case-insensitive).
    h2i = {h: i for i, h in enumerate(headers)}
    lower = {h.lower(): i for h, i in h2i.items()}
    date_idx = next((lower[k] for k in {"date"} if k in lower), None)
    time_idx = next((lower[k] for k in {"time"} if k in lower), None)

    # Only keep metrics you explicitly mapped in HEADER_TO_ALIAS.
    idx_to_alias: Dict[int, str] = {}
    for raw, alias in HEADER_TO_ALIAS.items():
        if raw in h2i:
            idx_to_alias[h2i[raw]] = alias
    return date_idx, time_idx, idx_to_alias


# Convert raw HWiNFO rows into per-second series: 1) Parse Date/Time -> timestamp; 2) Floor to whole seconds
# 3) If multiple samples fall into the same second, aggregate by MEDIAN (robust vs spikes)
def bucket_per_second(headers: List[str], rows: List[List[str]]) -> Tuple[List[datetime], Dict[str, List[float]]]:
    date_idx, time_idx, idx_to_alias = locate_columns(headers)
    if time_idx is None:
        return [], {}

    buckets: Dict[datetime, Dict[str, List[float]]] = {}
    for row in rows:
        date_val = row[date_idx] if date_idx is not None and date_idx < len(row) else None
        time_val = row[time_idx] if time_idx < len(row) else None
        if not time_val:
            continue

        ts = parse_dt(date_val, time_val)
        if not ts:
            continue

        sec = ts.replace(microsecond=0)
        b = buckets.setdefault(sec, {})

        for i, alias in idx_to_alias.items():
            if i < len(row):
                v = parse_float(row[i])
                if v is not None and not np.isnan(v):
                    b.setdefault(alias, []).append(v)

    if not buckets:
        return [], {}

    seconds = sorted(buckets.keys())
    all_aliases = sorted(set(a for per in buckets.values() for a in per.keys()))

    per_sec: Dict[str, List[float]] = {a: [] for a in all_aliases}
    for s in seconds:
        vals = buckets[s]
        for a in all_aliases:
            arr = vals.get(a, [])
            per_sec[a].append(float(np.median(arr)) if arr else np.nan)

    return seconds, per_sec


# Take the last `window_seconds` of wall time.
def trim_to_last_window(
    seconds: List[datetime],
    per_sec: Dict[str, List[float]],
    window_seconds: int
) -> Tuple[List[datetime], Dict[str, List[float]]]:
    # NOTE: don't require perfect 1-second contiguity.
    if not seconds:
        return seconds, per_sec
    t_end = seconds[-1]
    t_start = t_end - timedelta(seconds=window_seconds)
    sel_idx = [i for i, t in enumerate(seconds) if t_start <= t <= t_end]
    if not sel_idx:
        return [], {}
    trimmed: Dict[str, List[float]] = {}
    for k, arr in per_sec.items():
        trimmed[k] = [arr[i] for i in sel_idx]
    chosen = [seconds[i] for i in sel_idx]
    return chosen, trimmed


# Compute robust idle baseline values (median over the idle window).
def compute_idle_baseline(per_sec: Dict[str, List[float]]) -> Dict[str, float]:
    # baseline-subtract the two power channels used for "real_*" costs.
    base: Dict[str, float] = {}
    for k in ("gpu_power_w", "cpu_pkg_power_w"):
        if k in per_sec and per_sec[k]:
            arr = np.array(per_sec[k], dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size:
                base[k] = float(np.median(arr))
    return base


# Derive "real" power = (SR run power) - (idle baseline power).
def compute_sr_minus_idle(per_sec: Dict[str, List[float]], idle: Dict[str, float]) -> Dict[str, List[float]]:
    # These are the primary "cost" metrics when baseline data is available.
    out: Dict[str, List[float]] = {}
    n = len(next(iter(per_sec.values()))) if per_sec else 0

    def get(col: str) -> np.ndarray:
        if col in per_sec:
            return np.array(per_sec[col], dtype=float)
        return np.full(n, np.nan, dtype=float)

    if "gpu_power_w" in idle and "gpu_power_w" in per_sec:
        out["real_gpu_power_w"] = (get("gpu_power_w") - idle["gpu_power_w"]).tolist()
    if "cpu_pkg_power_w" in idle and "cpu_pkg_power_w" in per_sec:
        out["real_cpu_power_w"] = (get("cpu_pkg_power_w") - idle["cpu_pkg_power_w"]).tolist()
    if "real_gpu_power_w" in out and "real_cpu_power_w" in out:
        out["real_cpu_gpu_power_w"] = (
            np.array(out["real_gpu_power_w"]) + np.array(out["real_cpu_power_w"])
        ).tolist()
    return out


# Compute average values (mean over per-second series) for all tracked metrics.
def summarize_avg(per_sec: Dict[str, List[float]], mode: str, window_seconds: int) -> Dict[str, Any]:
    samples = len(next(iter(per_sec.values()))) if per_sec else 0
    s: Dict[str, Any] = {"mode": mode, "seconds": window_seconds, "samples": samples}

    def avg(name: str) -> Optional[float]:
        if name not in per_sec:
            return None
        arr = np.array(per_sec[name], dtype=float)
        arr = arr[~np.isnan(arr)]
        return float(np.mean(arr)) if arr.size else None

    for metric in [
        # GPU clocks + util + memory + power/thermals/voltage
        "gpu_clock_mhz", "gpu_effective_clock_mhz",
        "vram_clock_mhz",
        "gpu_util_pct", "vram_ctrl_util_pct",
        "vram_usage_pct", "vram_used_mb",
        "gpu_power_w",
        "gpu_temp_c", "gpu_hotspot_c",
        "gpu_voltage_v",

        # CPU
        "cpu_util_pct", "cpu_effective_freq_mhz", "cpu_pkg_power_w", "cpu_temp_c",

        # Derived deltas (SR - idle)
        "real_gpu_power_w", "real_cpu_power_w", "real_cpu_gpu_power_w",
    ]:
        s[metric + "_avg"] = avg(metric)
    return s


# Write a utf-8-sig CSV for Excel-friendly output.
def save_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# Tie-breaker metric: normalized "resource pressure" from 5 non-power sensors.
def tie_breaker_score(summ: Dict[str, Any]) -> Optional[float]:
    """
    Chosen sensors:
      1) gpu_util_pct_avg            GPU core utilization (workload proxy)
      2) vram_ctrl_util_pct_avg      VRAM controller utilization (bandwidth pressure proxy)
      3) gpu_effective_clock_mhz_avg Effective clock (DVFS / clock residency proxy)
      4) vram_used_mb_avg            Dedicated VRAM used (memory footprint proxy)
      5) cpu_util_pct_avg            CPU utilization (CPU overhead / bottleneck proxy)
    
    Normalize each to [0..1] with heuristic caps, then weighted mean.
    Higher score => worse (more pressure). Used ONLY when primary cost ties.
    """
    
    gpu_util = summ.get("gpu_util_pct_avg")
    vram_ctrl = summ.get("vram_ctrl_util_pct_avg")
    gpu_eff_clk = summ.get("gpu_effective_clock_mhz_avg")
    vram_used = summ.get("vram_used_mb_avg")
    cpu_util = summ.get("cpu_util_pct_avg")

    vals = [gpu_util, vram_ctrl, gpu_eff_clk, vram_used, cpu_util]
    if all(v is None for v in vals):
        return None

    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    def norm_pct(x: Optional[float]) -> Optional[float]:
        if not isinstance(x, (int, float)) or np.isnan(x):
            return None
        return clamp01(float(x) / 100.0)

    def norm_clock_mhz(x: Optional[float], cap_mhz: float) -> Optional[float]:
        if not isinstance(x, (int, float)) or np.isnan(x):
            return None
        return clamp01(float(x) / cap_mhz)

    def norm_vram_mb(x: Optional[float], cap_mb: float) -> Optional[float]:
        if not isinstance(x, (int, float)) or np.isnan(x):
            return None
        return clamp01(float(x) / cap_mb)

    # Caps are heuristics (safe ceilings for normalization).
    n_gpu_util = norm_pct(gpu_util)
    n_vram_ctrl = norm_pct(vram_ctrl)
    n_gpu_eff_clk = norm_clock_mhz(gpu_eff_clk, cap_mhz=3000.0)
    n_vram_used = norm_vram_mb(vram_used, cap_mb=12000.0)
    n_cpu_util = norm_pct(cpu_util)

    # Weights: emphasize GPU-side pressure; CPU still included.
    weighted: List[Tuple[Optional[float], float]] = [
        (n_gpu_util, 0.32),
        (n_vram_ctrl, 0.22),
        (n_gpu_eff_clk, 0.20),
        (n_vram_used, 0.16),
        (n_cpu_util, 0.10),
    ]

    num = 0.0
    den = 0.0
    for v, w in weighted:
        if v is None:
            continue
        num += w * float(v)
        den += w

    return (num / den) if den > 0 else None


# Sort helper: treat missing/non-finite as +inf so they go last.
def _finite_or_inf(v: Any) -> float:
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        return float(v)
    return float("inf")


def main():
    out_dir = Path(OUT_DIR)
    ensure_outdir(out_dir)

    # Load dicts from step 1 (idle + multiple SR logs)
    data = load_idle_and_sr(IDLE_CSV, SR_DIR)
    idle_dict = data["idle"]
    sr_dicts: List[Dict[str, Any]] = data["sr"]

    # Idle -> per-second medians -> last WINDOW_SECONDS -> idle baseline
    idle_headers = idle_dict.get("headers", [])
    idle_rows = idle_dict.get("rows", [])
    idle_secs_all, idle_per_all = bucket_per_second(idle_headers, idle_rows)
    if not idle_secs_all:
        raise SystemExit("Idle CSV has no usable time series.")
    _, idle_per = trim_to_last_window(idle_secs_all, idle_per_all, WINDOW_SECONDS)
    idle_base = compute_idle_baseline(idle_per)

    # SR files
    summary_rows: List[Dict[str, Any]] = []

    for sd in sr_dicts:
        headers = sd.get("headers", [])
        rows = sd.get("rows", [])
        mode = Path(sd.get("path", "unknown")).stem

        # Convert to per-second series and pick last window
        secs_all, per_all = bucket_per_second(headers, rows)
        if not secs_all:
            print(f"WARNING: {mode}: no usable time series; skipping.")
            continue
        secs, per = trim_to_last_window(secs_all, per_all, WINDOW_SECONDS)
        if not secs:
            print(f"WARNING: {mode}: no samples within last {WINDOW_SECONDS}s; skipping.")
            continue

        # Derived SR - idle power deltas
        real = compute_sr_minus_idle(per, idle_base)
        merged = dict(per, **real)

        # Summaries (seconds = WINDOW_SECONDS, samples = count of per-second points)
        summ = summarize_avg(merged, mode, WINDOW_SECONDS)

        # Primary key (lower is better): SR - idle real CPU+GPU power (W).
        summ["rank_key"] = summ.get("real_cpu_gpu_power_w_avg")

        # Secondary tie-break key (lower is better): normalized resource pressure.
        # Used ONLY when rank_key is identical.
        summ["tie_key"] = tie_breaker_score(summ)

        summary_rows.append(summ)

    if not summary_rows:
        raise SystemExit("No SR runs summarized.")

    # Rank:
    #   1) rank_key ascending (lower real cost is better)
    #   2) tie_key  ascending (lower pressure is better) - only meaningful if rank_key ties
    #   3) mode string (final deterministic tie-break)
    valid = [r for r in summary_rows if r.get("rank_key") is not None]
    invalid = [r for r in summary_rows if r.get("rank_key") is None]

    valid.sort(key=lambda x: (_finite_or_inf(x.get("rank_key")), _finite_or_inf(x.get("tie_key")), str(x.get("mode", ""))))

    ranked: List[Dict[str, Any]] = []
    for i, r in enumerate(valid, start=1):
        rr = dict(r)
        rr["rank"] = i
        ranked.append(rr)
    ranked.extend(invalid)

    # Save rankings CSV
    fields = [
        "rank", "mode", "seconds", "samples",
        "gpu_clock_mhz_avg", "gpu_effective_clock_mhz_avg",
        "vram_clock_mhz_avg",
        "gpu_util_pct_avg", "vram_ctrl_util_pct_avg",
        "vram_usage_pct_avg", "vram_used_mb_avg",
        "gpu_power_w_avg",
        "gpu_temp_c_avg", "gpu_hotspot_c_avg",
        "gpu_voltage_v_avg",
        "cpu_util_pct_avg", "cpu_effective_freq_mhz_avg", "cpu_pkg_power_w_avg", "cpu_temp_c_avg",
        "real_gpu_power_w_avg", "real_cpu_power_w_avg", "real_cpu_gpu_power_w_avg",
        "rank_key",
        "tie_key",
    ]
    save_csv(Path(OUT_DIR) / "sr_rankings_cost_first.csv", ranked, fields)

    print(f"Wrote: {Path(OUT_DIR) / 'sr_rankings_cost_first.csv'}")


if __name__ == "__main__":
    main()