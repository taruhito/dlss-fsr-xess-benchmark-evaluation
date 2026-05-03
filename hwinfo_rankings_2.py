#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Perf-first SR mode ranking with unified composite score and explicit tie-breakers.

Composite performance score:
    perf_score = (W_1PCT * fps_1pct_low_avg + W_0P1PCT * fps_0p1pct_low_avg) / (W_1PCT + W_0P1PCT)
    Weights:
        W_1PCT  = 1.0
        W_0P1PCT= 1.3   (emphasize deep tail stutter slightly)

Optional ranking mode (OFF by default; enable later if FPS differs across modes):
    1) Higher fps_avg
Ranking (best first) DEFAULT (existing behavior):
    1) Higher perf_score
    2) Lower frame_time_ms_avg
    3) Lower frame_time_presented_avg_ms_avg
    4) Higher fps_0p1pct_low_avg
    5) Higher fps_1pct_low_avg
    6) Mode name (alphabetical, deterministic)

Outputs:
    ./hwinfo_out_perf_first/sr_rankings_perf_first.csv
    ./hwinfo_out_perf_first/mem_clock_check.csv
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, timedelta, date
import numpy as np

# Step‑1 loader
from hwinfo_readlogs import load_idle_and_sr, IDLE_CSV, SR_DIR

OUT_DIR = r".\sh2_hwinfo_out_perf_first"
WINDOW_SECONDS = 60

# Weights (keep consistent with hwinfo_rankplot_2.py and any other consumer)
W_1PCT = 1.0
W_0P1PCT = 1.3

# ============================================================
# Ranking policy switch
#   0 = default (perf_score primary)
#   1 = FPS-primary ranking (fps_avg primary, then perf_score...)
# ============================================================
FPS_PRIMARY_RANKING = 1
# ============================================================

HEADER_TO_ALIAS: Dict[str, str] = {
    "影格率 [FPS]": "fps",
    "1% 低影格率 [FPS]": "fps_1pct_low",
    "0.1% 低影格率 [FPS]": "fps_0p1pct_low",
    "影格時間 [ms]": "frame_time_ms",
    "Frame Time Presented (avg) [ms]": "frame_time_presented_avg_ms",
    "GPU 功率 [W]": "gpu_power_w",
    "CPU 封裝功率 [W]": "cpu_pkg_power_w",
    "已用物理記憶體 [MB]": "mem_used_mb",
    "記憶體頻率 [MHz]": "mem_clock_mhz",
}

def ensure_outdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def norm(s: str) -> str:
    return str(s).replace("\ufeff", "").strip().strip('"').strip("'")

def parse_dt(date_str: Optional[str], time_str: str) -> Optional[datetime]:
    t_raw = norm(time_str).replace(",", ".")
    d_raw = norm(date_str) if date_str else None
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
        try:
            dd: Optional[date] = None
            for dfmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    dd = datetime.strptime(d_raw, dfmt).date()
                    break
                except ValueError:
                    continue
            if dd:
                try:
                    tt = datetime.strptime(t_raw, "%M:%S.%f").time()
                except ValueError:
                    tt = datetime.strptime(t_raw, "%M:%S").time()
                return datetime.combine(dd, tt)
        except Exception:
            pass
    for tfmt in ("%H:%M:%S.%f", "%H:%M:%S", "%M:%S.%f", "%M:%S"):
        try:
            t = datetime.strptime(t_raw, tfmt).time()
            return datetime.combine(date(1970, 1, 1), t)
        except ValueError:
            continue
    return None

def parse_float(cell: str) -> Optional[float]:
    t = norm(cell)
    if t == "":
        return None
    keep = [ch for ch in t if ch.isdigit() or ch in ".-+eE"]
    s = "".join(keep)
    if s in ("", ".", "-", "+"):
        return None
    try:
        return float(s)
    except Exception:
        return None

def locate_columns(headers: List[str]) -> Tuple[Optional[int], Optional[int], Dict[int, str]]:
    h2i = {h: i for i, h in enumerate(headers)}
    lower = {h.lower(): i for h, i in h2i.items()}
    date_idx = next((lower[k] for k in {"date"} if k in lower), None)
    time_idx = next((lower[k] for k in {"time"} if k in lower), None)
    idx_to_alias: Dict[int, str] = {h2i[raw]: alias for raw, alias in HEADER_TO_ALIAS.items() if raw in h2i}
    return date_idx, time_idx, idx_to_alias

def bucket_per_second(headers: List[str], rows: List[List[str]]) -> Tuple[List[datetime], Dict[str, List[float]]]:
    date_idx, time_idx, idx_to_alias = locate_columns(headers)
    if time_idx is None:
        return [], {}
    buckets: Dict[datetime, Dict[str, List[float]]] = {}
    for row in rows:
        date_val = row[date_idx] if (date_idx is not None and date_idx < len(row)) else None
        time_val = row[time_idx] if (time_idx is not None and time_idx < len(row)) else None
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
    all_aliases = sorted({a for vals in buckets.values() for a in vals.keys()})
    per_sec: Dict[str, List[float]] = {a: [] for a in all_aliases}
    for s in seconds:
        vals = buckets[s]
        for a in all_aliases:
            arr = vals.get(a, [])
            per_sec[a].append(float(np.median(arr)) if arr else np.nan)
    return seconds, per_sec

def trim_to_last_window(seconds: List[datetime], per_sec: Dict[str, List[float]], window_seconds: int) -> Tuple[List[datetime], Dict[str, List[float]]]:
    if not seconds:
        return [], {}
    t_end = seconds[-1]
    t_start = t_end - timedelta(seconds=window_seconds)
    idxs = [i for i, t in enumerate(seconds) if t_start <= t <= t_end]
    if not idxs:
        return [], {}
    trimmed = {k: [arr[i] for i in idxs] for k, arr in per_sec.items()}
    chosen = [seconds[i] for i in idxs]
    return chosen, trimmed

def compute_idle_baseline(per_sec: Dict[str, List[float]]) -> Dict[str, float]:
    base: Dict[str, float] = {}
    for k in ("gpu_power_w", "cpu_pkg_power_w"):
        if k in per_sec:
            arr = np.array(per_sec[k], dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size:
                base[k] = float(np.median(arr))
    return base

def compute_sr_minus_idle(per_sec: Dict[str, List[float]], idle: Dict[str, float]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    n = len(next(iter(per_sec.values()))) if per_sec else 0

    def get(name: str) -> np.ndarray:
        return np.array(per_sec[name], dtype=float) if name in per_sec else np.full(n, np.nan, dtype=float)

    if "gpu_power_w" in idle and "gpu_power_w" in per_sec:
        out["real_gpu_power_w"] = (get("gpu_power_w") - float(idle["gpu_power_w"])).tolist()
    if "cpu_pkg_power_w" in idle and "cpu_pkg_power_w" in per_sec:
        out["real_cpu_power_w"] = (get("cpu_pkg_power_w") - float(idle["cpu_pkg_power_w"])).tolist()
    if "real_gpu_power_w" in out and "real_cpu_power_w" in out:
        out["real_cpu_gpu_power_w"] = (np.array(out["real_gpu_power_w"]) + np.array(out["real_cpu_power_w"])).tolist()
    return out

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
        "fps", "fps_1pct_low", "fps_0p1pct_low",
        "frame_time_ms", "frame_time_presented_avg_ms",
        "gpu_power_w",
        "cpu_pkg_power_w",
        "mem_used_mb",
        "real_gpu_power_w", "real_cpu_power_w", "real_cpu_gpu_power_w",
    ]:
        s[metric + "_avg"] = avg(metric)

    s["cost_avg"] = s.get("real_cpu_gpu_power_w_avg")
    return s

def save_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

def compute_perf_score(row: Dict[str, Any]) -> float:
    p1_any = row.get("fps_1pct_low_avg")
    p01_any = row.get("fps_0p1pct_low_avg")
    if not isinstance(p1_any, (int, float)) or not math.isfinite(float(p1_any)):
        raise ValueError("fps_1pct_low_avg missing/non-finite")
    if not isinstance(p01_any, (int, float)) or not math.isfinite(float(p01_any)):
        raise ValueError("fps_0p1pct_low_avg missing/non-finite")

    p1 = float(p1_any)
    p01 = float(p01_any)
    return (W_1PCT * p1 + W_0P1PCT * p01) / (W_1PCT + W_0P1PCT)

def _num_or_default(v: Any, default: float) -> float:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else default

def ranking_key(row: Dict[str, Any]) -> Tuple[float, float, float, float, float, float, str]:
    fps = row.get("fps_avg")
    perf = row.get("perf_score")
    ft_raw = row.get("frame_time_ms_avg")
    ft_pres = row.get("frame_time_presented_avg_ms_avg")
    p01 = row.get("fps_0p1pct_low_avg")
    p1 = row.get("fps_1pct_low_avg")
    mode = str(row.get("mode", ""))

    # Higher-is-better keys (negated for ascending sort)
    fps_key = -_num_or_default(fps, -1e30)
    perf_key = -_num_or_default(perf, -1e30)
    p01_key = -_num_or_default(p01, -1e30)
    p1_key = -_num_or_default(p1, -1e30)

    # Lower-is-better keys (use +inf fallback)
    ft_key = _num_or_default(ft_raw, float("inf"))
    ftp_key = _num_or_default(ft_pres, float("inf"))

    if FPS_PRIMARY_RANKING:
        # fps_avg primary, then perf_score, then the existing tie-breakers
        return (fps_key, perf_key, ft_key, ftp_key, p01_key, p1_key, mode)

    # perf_score primary
    # still return 7-tuple to satisfy type checker (fps_key at the front, but neutralized)
    return (0.0, perf_key, ft_key, ftp_key, p01_key, p1_key, mode)  # set to 0.0 so it never affects ordering in default mode

def main():
    out_dir = Path(OUT_DIR)
    ensure_outdir(out_dir)

    data = load_idle_and_sr(IDLE_CSV, SR_DIR)
    idle_dict = data["idle"]
    sr_dicts: List[Dict[str, Any]] = data["sr"]

    idle_headers = idle_dict.get("headers", [])
    idle_rows = idle_dict.get("rows", [])
    idle_secs_all, idle_per_all = bucket_per_second(idle_headers, idle_rows)
    if not idle_secs_all:
        raise SystemExit("Idle CSV has no usable time series.")
    _, idle_per = trim_to_last_window(idle_secs_all, idle_per_all, WINDOW_SECONDS)
    idle_base = compute_idle_baseline(idle_per)

    summary_rows: List[Dict[str, Any]] = []
    mem_clock_rows: List[Dict[str, Any]] = []

    for sd in sr_dicts:
        headers = sd.get("headers", [])
        rows = sd.get("rows", [])
        mode = Path(sd.get("path", "unknown")).stem

        secs_all, per_all = bucket_per_second(headers, rows)
        if not secs_all:
            print(f"WARNING: {mode}: no usable time series; skipping.")
            continue
        secs, per = trim_to_last_window(secs_all, per_all, WINDOW_SECONDS)
        if not secs:
            print(f"WARNING: {mode}: no samples within last {WINDOW_SECONDS}s; skipping.")
            continue

        real = compute_sr_minus_idle(per, idle_base)
        merged = dict(per, **real)
        summ = summarize_avg(merged, mode, WINDOW_SECONDS)

        # Composite perf score (weighted 1% + 0.1% lows)
        try:
            summ["perf_score"] = compute_perf_score(summ)
        except Exception:
            summ["perf_score"] = float("nan")

        # Mem clock drift (DRAM)
        if "mem_clock_mhz" in per:
            arr = np.array(per["mem_clock_mhz"], dtype=float)
            vals = arr[~np.isnan(arr)]
            if vals.size:
                mem_clock_rows.append({
                    "mode": mode,
                    "mem_clock_min_mhz": float(np.min(vals)),
                    "mem_clock_max_mhz": float(np.max(vals)),
                    "drift_flag": "YES" if (np.max(vals) - np.min(vals)) > 10 else "NO"
                })
            else:
                mem_clock_rows.append({"mode": mode, "mem_clock_min_mhz": "", "mem_clock_max_mhz": "", "drift_flag": "UNKNOWN"})
        else:
            mem_clock_rows.append({"mode": mode, "mem_clock_min_mhz": "", "mem_clock_max_mhz": "", "drift_flag": "MISSING"})

        summary_rows.append(summ)

    if not summary_rows:
        raise SystemExit("No SR runs summarized.")

    ranked = sorted(summary_rows, key=ranking_key)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i

    fields = [
        "rank", "mode", "seconds", "samples",
        "perf_score",
        "fps_avg", "fps_1pct_low_avg", "fps_0p1pct_low_avg",
        "frame_time_ms_avg", "frame_time_presented_avg_ms_avg",
        "gpu_power_w_avg",
        "cpu_pkg_power_w_avg",
        "mem_used_mb_avg",
        "real_gpu_power_w_avg", "real_cpu_power_w_avg", "real_cpu_gpu_power_w_avg",
        "cost_avg",
    ]
    save_csv(Path(OUT_DIR) / "sr_rankings_perf_first.csv", ranked, fields)

    mem_fields = ["mode", "mem_clock_min_mhz", "mem_clock_max_mhz", "drift_flag"]
    save_csv(Path(OUT_DIR) / "mem_clock_check.csv", mem_clock_rows, mem_fields)

    print(f"Ranking policy: {'FPS_PRIMARY' if FPS_PRIMARY_RANKING else 'PERF_SCORE_PRIMARY (default)'}")
    print(f"Wrote: {Path(OUT_DIR) / 'sr_rankings_perf_first.csv'}")
    print(f"Wrote: {Path(OUT_DIR) / 'mem_clock_check.csv'}")

if __name__ == "__main__":
    main()