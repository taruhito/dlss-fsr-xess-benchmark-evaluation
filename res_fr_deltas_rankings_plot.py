#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Delta (Base vs mode) plots for FR-IQA metrics (Native vs SR).

Input (expected)
----------------
- ./res_out/fr_scores.csv
  Required columns:
    - frame1_score, frame2_score, frame3_score ... (any number of frame*_score columns)

Mode naming convention (pairing)
--------------------------------
This script expects mutually-exclusive active-mode suffixes:
  - "..._Base"
  - "..._Reflex"
  - "..._FrameGen"
  - "..._FrameGenD"
  - "..._FrameGenF"

It groups by:
  (resolution, metric, base_mode)
and computes deltas:
  - Reflex vs Base   (if both exist)
  - FrameGen vs Base (if both exist)
  - FrameGenD vs Base (if both exist)
  - FrameGenF vs Base (if both exist)

Delta definition (always "positive = active mode better")
---------------------------------------------------------
For higher-is-better metrics:
    Δ = Active − Base
  e.g. PSNR, SSIM, MS-SSIM

For lower-is-better metrics:
    Δ = Base − Active
  e.g. LPIPS, DISTS

Aggregation across frames
-------------------------
The script extracts per-frame scores from frame*_score columns and then computes:
  - mean delta
  - median delta
  - trimmed mean delta (drop the single worst absolute delta if >= 3 frames)

DELTA_AGG controls which aggregated delta is plotted.

Outputs
-------
Written under ./res_out/deltas/
  - deltas.csv
  - {resolution}_{metric}_{active_mode}_deltas.png
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.patheffects as pe
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

import numpy as np
import pandas as pd
import seaborn as sns

# ================== CONFIG (edit here) ==================
IN_CSV = Path("./res_out/fr_scores.csv")
OUT_DIR = Path("./res_out/deltas")

DPI = 140
STYLE = "whitegrid"
SHOW = False  # True to plt.show() interactively

# Which aggregated delta to plot: "mean", "median", or "trimmed"
DELTA_AGG = "mean"

# Text formatting
DECIMALS = 5
SCI_ALL = False
# =========================================================

# Metric semantics:
# higher_is_better determines delta direction so that "positive means active mode better".
METRIC_CFG = {
    "psnr":     {"higher_is_better": True,  "xlabel": "Δ PSNR [dB] (Active − Base)"},
    "ssim":     {"higher_is_better": True,  "xlabel": "Δ SSIM (Active − Base)"},
    "ms_ssim":  {"higher_is_better": True,  "xlabel": "Δ MS-SSIM (Active − Base)"},
    "lpips":    {"higher_is_better": False, "xlabel": "Δ LPIPS (Base − Active)"},
    "dists":    {"higher_is_better": False, "xlabel": "Δ DISTS (Base − Active)"},
}

FAMILY_COLORS = {
    "DLSS": "#1F77B4",
    "FSR" : "#FF1E0E",
    "FSR1": "#FF7F0E",
    "FSR3.1.2": "#2CA02C",
    "FSR3.1.4": "#EAFF00",
    "XeSS": "#9467BD",
}
DEFAULT_BAR_COLOR = "#4E79A7"

# Expected active-mode tags (case-insensitive)
ACTIVE_TAGS = ("Base", "Reflex", "FrameGen", "FrameGenD", "FrameGenF")


def _extract_family(mode: str) -> str:
    return mode.split("_", 1)[0] if isinstance(mode, str) and "_" in mode else str(mode)


# Split "mode" into (base_mode, active_mode)
# Example: "DLSS_Quality_1080p_FrameGen" -> ("DLSS_Quality_1080p", "FrameGen")
def _base_mode(mode: str) -> Tuple[str, str]:
    if not isinstance(mode, str):
        return str(mode), ""
    for tag in ACTIVE_TAGS:
        suf = f"_{tag}"
        if mode.endswith(suf):
            return mode[: -len(suf)], tag
    return mode, ""


# Find all per-frame metric columns ("frame1_score", "frame2_score", ...).
def _frame_cols(df: pd.DataFrame) -> List[str]:
    cols = [c for c in df.columns if c.startswith("frame") and c.endswith("_score")]

    def key(c: str) -> int:
        digits = "".join(ch for ch in c if ch.isdigit())
        return int(digits) if digits.isdigit() else 10**9

    return sorted(cols, key=key)


# Compute signed delta with the convention: positive = active mode better.
def _delta_active_minus_base(metric: str, active_val: float, base_val: float) -> float:
    hib = METRIC_CFG.get(metric, {}).get("higher_is_better", True)
    return (active_val - base_val) if hib else (base_val - active_val)


# Aggregate per-frame deltas into mean/median/trimmed variants.
def _agg_deltas(per_frame_active: List[float], per_frame_base: List[float], metric: str) -> Dict[str, Optional[float]]:
    k = min(len(per_frame_active), len(per_frame_base))
    if k == 0:
        return {"mean": None, "median": None, "trimmed": None, "frames_used": 0}

    deltas = [_delta_active_minus_base(metric, per_frame_active[i], per_frame_base[i]) for i in range(k)]
    arr = np.asarray(deltas, dtype=float)

    mean = float(np.mean(arr))
    median = float(np.median(arr))

    # "trimmed": drop the worst outlier by absolute delta (only if enough samples)
    if arr.size >= 3:
        worst_idx = int(np.argmax(np.abs(arr)))
        trimmed = float(np.mean(np.delete(arr, worst_idx)))
    else:
        trimmed = mean

    return {"mean": mean, "median": median, "trimmed": trimmed, "frames_used": int(k)}


def _fmt_sci(v: Optional[float], d: int = DECIMALS) -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return "NA"
    return f"{float(v):.{d}e}"


def _set_xticks_formatter(ax: Axes, metric: str) -> None:
    if SCI_ALL or metric in ("ssim", "ms_ssim", "lpips", "dists"):
        ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, pos: f"{x:.1e}"))
    else:
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.3f"))


def _pick_plot_series(d: pd.DataFrame) -> Tuple[pd.Series, str]:
    if DELTA_AGG == "median":
        return d["delta_median"], "median"
    if DELTA_AGG == "trimmed":
        return d["delta_trimmed"], "trimmed"
    return d["delta_mean"], "mean"


def _plot_deltas(resolution: str, metric: str, active_mode: str, rows: List[Dict], out_dir: Path) -> None:
    if not rows:
        return

    d = pd.DataFrame(rows)
    y_series, agg_name = _pick_plot_series(d)

    d["y"] = pd.to_numeric(y_series, errors="coerce")
    d = d.sort_values("y", ascending=False)

    sns.set_style(STYLE)
    fig, ax = plt.subplots(figsize=(12.5, max(4.0, 0.52 * len(d))), dpi=DPI)

    colors = [FAMILY_COLORS.get(f, DEFAULT_BAR_COLOR) for f in d["family"].astype(str).tolist()]
    y_vals = d["y"].to_numpy(dtype=float)

    bars = ax.barh(
        np.arange(len(d)),
        y_vals,
        color=colors,
        edgecolor="black",
        linewidth=0.4,
    )

    xlabel = METRIC_CFG.get(metric, {}).get("xlabel", f"Δ {metric}")
    ax.set_yticks(np.arange(len(d)), d["base_mode"].astype(str).tolist())
    ax.set_xlabel(f"{xlabel}  [{agg_name}]")
    ax.set_title(f"{resolution} | {active_mode} vs Base deltas for {metric} (positive = {active_mode} better)")
    _set_xticks_formatter(ax, metric)

    finite_vals = y_vals[np.isfinite(y_vals)]
    if finite_vals.size:
        vmin, vmax = float(np.min(finite_vals)), float(np.max(finite_vals))
        span = max(1e-12, vmax - vmin)
        pad = 0.06 * span if span > 0 else 0.001
        ax.set_xlim(left=min(0.0, vmin - pad), right=max(0.0, vmax + pad))

    x0, x1 = ax.get_xlim()
    inside_threshold = 0.06 * (x1 - x0)
    outside_offset = 0.015 * (x1 - x0)

    for bar, yval in zip(bars, y_vals):
        if not isinstance(yval, (int, float)) or not math.isfinite(float(yval)):
            continue
        txt = _fmt_sci(float(yval))
        put_inside = abs(float(yval)) >= inside_threshold

        if put_inside:
            xt = float(yval) / 2.0
            ha = "center"
            color = "white"
            path_fx = [pe.withStroke(linewidth=1.4, foreground="black", alpha=0.9)]
        else:
            xt = max(float(yval), 0.0) + outside_offset
            ha = "left"
            color = "black"
            path_fx = None

        ax.text(
            xt,
            bar.get_y() + bar.get_height() / 2.0,
            txt,
            va="center",
            ha=ha,
            fontsize=9,
            color=color,
            path_effects=path_fx,
        )

    used = sorted(list(dict.fromkeys(d["family"].astype(str).tolist())))
    handles: List[Line2D] = []
    labels: List[str] = []
    for fam in used:
        handles.append(
            Line2D([0], [0], marker="s", color="none",
                   markerfacecolor=FAMILY_COLORS.get(fam, DEFAULT_BAR_COLOR),
                   markersize=10, label=fam)
        )
        labels.append(fam)
    if handles:
        ax.legend(handles=handles, labels=labels, title="SR family",
                  loc="center left", bbox_to_anchor=(1.01, 0.5))

    fig.tight_layout(rect=(0.03, 0.03, 0.80, 0.98))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{resolution}_{metric}_{active_mode}_deltas.png"
    fig.savefig(out_path, bbox_inches="tight", dpi=DPI)
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {out_path}")


def main():
    if not IN_CSV.exists():
        raise SystemExit(f"Input CSV not found: {IN_CSV}")

    df = pd.read_csv(IN_CSV, encoding="utf-8-sig")
    if df.empty:
        raise SystemExit("CSV is empty.")

    df["metric"] = df["metric"].astype(str).str.lower()
    df["family"] = df["mode"].astype(str).apply(_extract_family)
    df["base_mode"], df["active_mode"] = zip(*df["mode"].astype(str).map(_base_mode))
    df["resolution"] = df["resolution"].astype(str)

    df = df[df["metric"].isin(METRIC_CFG.keys())].copy()
    if df.empty:
        raise SystemExit("No supported metrics in CSV after filtering.")

    results: List[Dict] = []
    fcols = _frame_cols(df)

    # For each base_mode group, compare Base to each other active mode separately.
    for (res, metric, base), g in df.groupby(["resolution", "metric", "base_mode"]):
        g_base = g[g["active_mode"].str.lower() == "base"]
        if g_base.empty:
            continue
        base_row = g_base.iloc[0]

        for active in ("Reflex", "FrameGen", "FrameGenD", "FrameGenF"):
            g_active = g[g["active_mode"].str.lower() == active.lower()]
            if g_active.empty:
                continue
            active_row = g_active.iloc[0]

            per_active, per_base = [], []
            for c in fcols:
                vb = base_row.get(c, np.nan)
                va = active_row.get(c, np.nan)
                if pd.notna(vb) and pd.notna(va):
                    per_base.append(float(vb))
                    per_active.append(float(va))

            aggs = _agg_deltas(per_active, per_base, str(metric))

            results.append({
                "resolution": str(res),
                "metric": str(metric),
                "base_mode": str(base),
                "active_mode": active,
                "family": _extract_family(str(base)),
                "delta_mean": aggs["mean"],
                "delta_median": aggs["median"],
                "delta_trimmed": aggs["trimmed"],
                "frames_used": aggs["frames_used"],
                "active_mode_row": active_row["mode"],
                "base_mode_row": base_row["mode"],
            })

    if not results:
        raise SystemExit("No Base vs (Reflex/FrameGen) pairs found.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / "deltas.csv"
    pd.DataFrame(results).to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Wrote: {out_csv}")

    df_out = pd.DataFrame(results)
    for (res, metric, active_mode), grp in df_out.groupby(["resolution", "metric", "active_mode"], sort=False):
        _plot_deltas(str(res), str(metric), str(active_mode), grp.to_dict(orient="records"), OUT_DIR)

    print(f"DELTA_AGG={DELTA_AGG}  DECIMALS={DECIMALS}  SCI_ALL={'1' if SCI_ALL else '0'}")


if __name__ == "__main__":
    main()