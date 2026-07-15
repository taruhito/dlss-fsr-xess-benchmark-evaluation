#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCAT latency ranking

  Approximate PC Latency (per-frame) =
      MsInPresentAPI + RenderLatency
  where RenderLatency = MsEstimatedDriverLag + MsUntilRenderComplete

Ranking policy (latency-first)

Primary key:
  1) pc_latency_mean (lower is better)

Tie-breakers (only when above identical):
  2) render_latency_mean (lower is better)
  3) ms_in_present_api_mean (lower is better)

Outputs:
Written under ./ocat_out/
  - ocat_rankings_latency_first.csv
      Per-mode latency summaries + rank column
  - ocat_consistency_check.csv
      Minimal per-mode column presence + meta fields (for plot footer)
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Loader (must provide per-frame series + meta summaries)
from ocat_readlogs import load_ocat_dir, OCAT_DIR

# CONFIG (output directory)
OUT_DIR = Path("./sh2_ocat_out")


# -----------------------
# Filesystem helpers
# -----------------------
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# -----------------------
# numpy helpers (robust)
# -----------------------
def _to_float_array(lst: List[Optional[float]]) -> np.ndarray:
    if not lst:
        return np.array([], dtype=float)
    return np.array(lst, dtype=float)


def _finite(a: np.ndarray) -> np.ndarray:
    if a.size == 0:
        return a
    return a[np.isfinite(a)]


def _mean(a: np.ndarray) -> Optional[float]:
    a = _finite(a)
    return float(a.mean()) if a.size else None


def _pct(a: np.ndarray, q: float) -> Optional[float]:
    a = _finite(a)
    return float(np.percentile(a, q)) if a.size else None


def _save_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# -----------------------
# Ranking key (latency-first)
# -----------------------
# Missing/non-finite => +inf (push to bottom)
def _sort_key(row: Dict[str, Any]) -> Tuple[float, float, float]:
    def f(x: Any) -> float:
        return float(x) if isinstance(x, (int, float)) and math.isfinite(float(x)) else float("inf")

    return (
        f(row.get("pc_latency_mean")),
        f(row.get("render_latency_mean")),
        f(row.get("ms_in_present_api_mean")),
    )


# -----------------------------------------------
def main():
    # Step 1) Load all OCAT files
    _ensure_dir(OUT_DIR)

    data = load_ocat_dir(OCAT_DIR)
    files = data["files"]

    rankings: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    # Meta fields persisted into consistency output
    META_KEYS = ["Runtime", "SyncInterval", "GPU #", "GPU", "Processor", "Motherboard", "OS", "System RAM"]

    for f in files:
        mode = f.get("mode")
        s = f.get("series", {})

        # Step 2) Per-frame series
        mip = _to_float_array(s.get("MsInPresentAPI", []))           # partial game latency inside Present()
        mdl = _to_float_array(s.get("MsEstimatedDriverLag", []))     # render queue wait
        murc = _to_float_array(s.get("MsUntilRenderComplete", []))   # GPU render time
        rl  = _to_float_array(s.get("RenderLatency", []))            # mdl + murc (derived in loader)

        # Step 3) Approximate PC latency
        valid_pc = np.isfinite(mip) & np.isfinite(rl) # both parts must be valid
        pc = np.where(valid_pc, mip + rl, np.nan)

        # Summaries
        pc_mean = _mean(pc)
        pc_p95  = _pct(pc, 95)
        pc_p99  = _pct(pc, 99)

        mip_mean = _mean(mip)
        mip_p95  = _pct(mip, 95)

        rl_mean = _mean(rl)
        rl_p95  = _pct(rl, 95)
        rl_p99  = _pct(rl, 99)

        mdl_mean = _mean(mdl)
        mdl_p95  = _pct(mdl, 95)

        murc_mean = _mean(murc)
        murc_p95  = _pct(murc, 95)

        # Sample counts (how many frames are usable)
        samples_pc  = int(np.isfinite(pc).sum()) if pc.size else 0
        samples_mip = int(np.isfinite(mip).sum()) if mip.size else 0
        samples_rl  = int(np.isfinite(rl).sum()) if rl.size else 0
        samples = max(samples_pc, samples_mip, samples_rl)

        rankings.append({
            "mode": mode,
            "samples": samples,

            # --- primary metric for ranking ---
            "pc_latency_mean": pc_mean,
            "pc_latency_p95": pc_p95,
            "pc_latency_p99": pc_p99,

            # --- components (interpretability) ---
            "ms_in_present_api_mean": mip_mean,
            "ms_in_present_api_p95": mip_p95,

            "render_latency_mean": rl_mean,
            "render_latency_p95": rl_p95,
            "render_latency_p99": rl_p99,

            "ms_estimated_driver_lag_mean": mdl_mean,
            "ms_estimated_driver_lag_p95": mdl_p95,

            "ms_until_render_complete_mean": murc_mean,
            "ms_until_render_complete_p95": murc_p95,
        })

        # Step 4) Consistency / meta check
        meta = f.get("meta_summary", {}) or {}

        check_row: Dict[str, Any] = {
            "mode": mode,
            "samples": samples,
            "has_MsInPresentAPI": bool(mip.size and np.isfinite(mip).sum() > 0),
            "has_MsEstimatedDriverLag": bool(mdl.size and np.isfinite(mdl).sum() > 0),
            "has_MsUntilRenderComplete": bool(murc.size and np.isfinite(murc).sum() > 0),
            "has_RenderLatency": bool(rl.size and np.isfinite(rl).sum() > 0),
        }
        for k in META_KEYS:
            check_row[k] = (meta.get(k) or {}).get("value")

        checks.append(check_row)

    if not rankings:
        raise SystemExit("No OCAT files summarized. Check OCAT_DIR and ocat_readlogs output.")

    # Step 5) Rank (latency-first)
    ranked = sorted(rankings, key=_sort_key)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
        
    # Step 6) Write outputs
    rank_fields = [
        "rank", "mode", "samples",
        "pc_latency_mean", "pc_latency_p95", "pc_latency_p99",
        "ms_in_present_api_mean", "ms_in_present_api_p95",
        "render_latency_mean", "render_latency_p95", "render_latency_p99",
        "ms_estimated_driver_lag_mean", "ms_estimated_driver_lag_p95",
        "ms_until_render_complete_mean", "ms_until_render_complete_p95",
    ]
    _save_csv(OUT_DIR / "ocat_rankings_latency_first.csv", ranked, rank_fields)

    check_fields = [
        "mode", "samples",
        "has_MsInPresentAPI", "has_MsEstimatedDriverLag", "has_MsUntilRenderComplete", "has_RenderLatency",
        "Runtime", "SyncInterval", "GPU #", "GPU", "Processor", "Motherboard", "OS", "System RAM",
    ]
    _save_csv(OUT_DIR / "ocat_consistency_check.csv", checks, check_fields)

    print(f"Wrote: {OUT_DIR / 'ocat_rankings_latency_first.csv'}")
    print(f"Wrote: {OUT_DIR / 'ocat_consistency_check.csv'}")


if __name__ == "__main__":
    main()