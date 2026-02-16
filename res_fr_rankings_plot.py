#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FR ranking + plots from full-reference IQA scores (Native vs SR).

Input (expected)
----------------
- ./res_out/fr_scores.csv

What this script does
---------------------
1) Read per-mode FR metrics (PSNR/SSIM/MS-SSIM/LPIPS/DISTS) computed against Native.
2) For each (resolution, metric) group:
   - Rank SR modes by mean_score (direction depends on metric).
   - Compute "gap_to_best" within the group (always >= 0; 0 means best).
3) Write:
   - ./res_out/fr_rankings.csv
4) Plot:
   - One ranking bar plot per (resolution, metric):
       ./res_out/{resolution}_{metric}_rank.png
   - One multi-metric summary per resolution:
       ./res_out/{resolution}_summary.png
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, cast

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

# ================== CONFIG (match res_compute_fr_metrics.py style) ==================
IN_CSV = Path("./res_out/fr_scores.csv")
OUT_DIR = Path("./res_out")

# Plot style
DPI = 140
STYLE = "whitegrid"
SHOW = False  # set True to plt.show() interactively
# =============================================================================


@dataclass(frozen=True)
class MetricCfg:
    higher_is_better: bool
    fmt: Callable[[float], str]
    xlabel: str


# Metric configuration:
# - higher_is_better controls ranking direction
# - fmt is used for bar-end labels
# - xlabel controls axis text
METRIC_CFG: Dict[str, MetricCfg] = {
    "psnr": MetricCfg(True,  lambda v: f"{v:.2f} dB", "PSNR [dB] (higher is better)"),
    "ssim": MetricCfg(True,  lambda v: f"{v:.4f}",    "SSIM (higher is better)"),
    "ms_ssim": MetricCfg(True, lambda v: f"{v:.4f}",  "MS-SSIM (higher is better)"),
    "lpips": MetricCfg(False, lambda v: f"{v:.3f}",   "LPIPS (lower is better)"),
    "dists": MetricCfg(False, lambda v: f"{v:.3f}",   "DISTS (lower is better)"),
}

# Keep a consistent palette across your whole project (used by other ranking plot scripts too)
FAMILY_COLORS: Dict[str, str] = {
    "DLSS": "#1F77B4",
    "FSR" : "#FF1E0E",
    "FSR1": "#FF7F0E",
    "FSR3.1": "#00FF91",
    "FSR3.1.2": "#2CA02C",
    "FSR3.1.4": "#EAFF00",
    "XeSS": "#9467BD",
}
DEFAULT_BAR_COLOR = "#4E79A7"


# Create output directory if missing (safe if already exists).
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# Mode naming convention:
# Example: "DLSS_Quality_1080p_Reflex" -> "DLSS"
def _extract_family(mode: str) -> str:
    if not isinstance(mode, str):
        return "UNKNOWN"
    return mode.split("_", 1)[0] if "_" in mode else mode


def _metric_info(metric: str) -> Tuple[bool, str, Callable[[float], str]]:
    cfg = METRIC_CFG.get(metric)
    if cfg is None:
        return True, metric, (lambda v: f"{v:.3f}")
    return cfg.higher_is_better, cfg.xlabel, cfg.fmt


# Rank a single (resolution, metric) group.
# Returns a DataFrame with: rank, best_value, gap_to_best (>= 0).
def _rank_group(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    hib, _, _ = _metric_info(metric)
    d = df.copy()
    d = d[pd.notna(d["mean_score"])]

    if d.empty:
        return d

    # Sorting direction depends on metric semantics.
    d = d.sort_values("mean_score", ascending=not hib)
    best = float(d["mean_score"].iloc[0])

    # gap_to_best is always a positive "distance" to the best for interpretability.
    if hib:
        d["gap_to_best"] = (best - d["mean_score"]).clip(lower=0)
    else:
        d["gap_to_best"] = (d["mean_score"] - best).clip(lower=0)

    d["rank"] = range(1, len(d) + 1)
    d["best_value"] = best
    return d


# Right padding for x-axis so labels fit.
def _right_pad_for_metric(metric: str, vmin: float, vmax: float) -> float:
    span = max(1e-9, vmax - vmin)
    if metric == "psnr":
        return max(0.5, 0.03 * span)
    if metric in ("ssim", "ms_ssim"):
        return max(0.05, 0.03 * span)
    if metric in ("lpips", "dists"):
        return max(0.003, 0.05 * span)
    return 0.03 * span


def _set_xlim_with_margin(ax: Axes, metric: str, values: np.ndarray) -> None:
    finite_vals = values[np.isfinite(values)]
    if finite_vals.size == 0:
        return
    vmin, vmax = float(np.min(finite_vals)), float(np.max(finite_vals))
    pad = _right_pad_for_metric(metric, vmin, vmax)
    ax.set_xlim(left=min(0.0, vmin), right=vmax + pad)


def _legend_outside_right(ax: Axes, handles: Sequence[Line2D], labels: Sequence[str], title: str = "SR family") -> None:
    if not handles:
        return
    ax.legend(
        handles=handles,
        labels=list(labels),
        title=title,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        framealpha=0.95,
    )


# Convert a series to a float numpy array safely (avoid ExtensionArray edge cases).
def _bar_values_numeric(series: pd.Series) -> np.ndarray:
    return np.asarray(pd.to_numeric(series, errors="coerce").to_numpy(), dtype=float)


def _plot_rank_bar(
    g: pd.DataFrame,
    resolution: str,
    metric: str,
    out_dir: Path,
    color_by_family: bool = True,
) -> None:
    if g.empty:
        return

    # Rank 1 at the top.
    g = g.sort_values("rank", ascending=True).reset_index(drop=True)

    if color_by_family:
        fams: List[str] = g["family"].astype(str).tolist()
        colors = [FAMILY_COLORS.get(f, DEFAULT_BAR_COLOR) for f in fams]
    else:
        colors = [DEFAULT_BAR_COLOR] * len(g)

    hib, xlabel, fmt_fn = _metric_info(metric)

    height = max(4.0, 0.47 * len(g))
    fig = plt.figure(figsize=(12.5, height), dpi=DPI, constrained_layout=False)
    sns.set_style(STYLE)
    ax: Axes = plt.gca()

    y_positions = np.arange(len(g))
    vals = _bar_values_numeric(g["mean_score"])
    ax.barh(y_positions, vals, color=colors, edgecolor="black", linewidth=0.4)

    ax.set_yticks(y_positions, g["mode"].astype(str).tolist())
    title_dir = "↑" if hib else "↓"
    ax.set_title(f"{resolution} | {metric} ranking ({title_dir})")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("")
    ax.invert_yaxis()

    # Tick format per metric
    if metric == "psnr":
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))
    elif metric in ("ssim", "ms_ssim"):
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.4f"))
    else:
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.3f"))

    _set_xlim_with_margin(ax, metric, vals)

    # End-of-bar value labels (kept inside/outside depending on room)
    x0, x1 = ax.get_xlim()
    span = x1 - x0
    pad = 0.01 * span
    for i, val in enumerate(vals):
        if math.isfinite(val):
            x_text = val + pad
            ha = "left"
            if x_text > (x1 - 0.02 * span):
                x_text = val - pad
                ha = "right"
            ax.text(x_text, i, f"{fmt_fn(float(val))}", va="center", ha=ha, fontsize=9, color="black")

    # Family legend (same color coding used by other plots in this project)
    if color_by_family:
        used_fams = list(dict.fromkeys(g["family"].astype(str).tolist()))
        used_fams.sort()
        handles: List[Line2D] = []
        labels: List[str] = []
        for fam in used_fams:
            c = FAMILY_COLORS.get(fam, DEFAULT_BAR_COLOR)
            handles.append(Line2D([0], [0], marker="s", color="none", markerfacecolor=c, markersize=10, label=fam))
            labels.append(fam)
        _legend_outside_right(ax, handles, labels, title="SR family")

    fig.tight_layout(rect=(0.03, 0.02, 0.80, 0.98))
    out_file = out_dir / f"{resolution}_{metric}_rank.png"
    fig.savefig(out_file, bbox_inches="tight", dpi=DPI)
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {out_file}")


def _plot_summary_per_resolution(
    ranks: pd.DataFrame,
    resolution: str,
    metrics: List[str],
    out_dir: Path,
    color_by_family: bool = True,
) -> None:
    sub = ranks[ranks["resolution"] == resolution].copy()
    present = [m for m in metrics if m in sub["metric"].unique().tolist()]
    if not present:
        return

    sns.set_style(STYLE)
    n = len(present)

    # Auto-height: one panel per metric, scaled by number of bars in each panel.
    height = sum(max(2.8, 0.40 * len(sub[sub["metric"] == m])) for m in present)
    height = max(4.5, min(18.0, height))
    fig, axes = plt.subplots(n, 1, figsize=(12.5, height), dpi=DPI, squeeze=False)

    legend_handles: List[Line2D] = []
    legend_labels: List[str] = []

    for idx, metric in enumerate(present):
        g = sub[sub["metric"] == metric].copy()
        if g.empty:
            continue
        g = g.sort_values("rank", ascending=True).reset_index(drop=True)

        ax: Axes = axes[idx, 0]
        hib, xlabel, fmt_fn = _metric_info(metric)

        y_positions = np.arange(len(g))
        vals = _bar_values_numeric(g["mean_score"])

        if color_by_family:
            fams = g["family"].astype(str).tolist()
            colors = [FAMILY_COLORS.get(f, DEFAULT_BAR_COLOR) for f in fams]
        else:
            colors = [DEFAULT_BAR_COLOR] * len(g)

        ax.barh(y_positions, vals, color=colors, edgecolor="black", linewidth=0.4)
        ax.set_yticks(y_positions, g["mode"].astype(str).tolist())
        title_dir = "↑" if hib else "↓"
        ax.set_title(f"{metric} ({title_dir})")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("")
        ax.invert_yaxis()

        if metric == "psnr":
            ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))
        elif metric in ("ssim", "ms_ssim"):
            ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.4f"))
        else:
            ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.3f"))

        _set_xlim_with_margin(ax, metric, vals)

        x0, x1 = ax.get_xlim()
        span = x1 - x0
        pad = 0.01 * span
        for i, val in enumerate(vals):
            if math.isfinite(val):
                x_text = val + pad
                ha = "left"
                if x_text > (x1 - 0.02 * span):
                    x_text = val - pad
                    ha = "right"
                ax.text(x_text, i, f"{fmt_fn(float(val))}", va="center", ha=ha, fontsize=9, color="black")

        # Build legend once (from first panel that has it)
        if color_by_family and not legend_handles:
            used = sorted(list(dict.fromkeys(g["family"].astype(str).tolist())))
            for fam in used:
                c = FAMILY_COLORS.get(fam, DEFAULT_BAR_COLOR)
                legend_handles.append(Line2D([0], [0], marker="s", color="none", markerfacecolor=c, markersize=10, label=fam))
                legend_labels.append(fam)

    if legend_handles:
        _legend_outside_right(axes[0, 0], legend_handles, legend_labels, title="SR family")

    fig.suptitle(f"{resolution} FR metrics ranking", y=0.995, fontsize=12)
    fig.tight_layout(rect=(0.03, 0.03, 0.80, 0.975))
    out_file = out_dir / f"{resolution}_summary.png"
    fig.savefig(out_file, bbox_inches="tight", dpi=DPI)
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {out_file}")


def main() -> None:
    _ensure_dir(OUT_DIR)

    if not IN_CSV.exists():
        raise SystemExit(f"Input CSV not found: {IN_CSV}")

    try:
        df = pd.read_csv(IN_CSV, encoding="utf-8-sig")
    except Exception as e:
        raise SystemExit(f"Failed to read {IN_CSV}: {e}")

    need_cols = {"resolution", "mode", "metric", "mean_score"}
    if not need_cols.issubset(df.columns):
        missing = sorted(need_cols - set(df.columns))
        raise SystemExit(f"CSV missing required columns: {missing}")

    d = df.copy()
    d = d[pd.notna(d["mean_score"])].copy()
    d["family"] = d["mode"].astype(str).apply(_extract_family)

    # Force these to real python str (avoids pandas Scalar/bytes typing issues in some linters)
    d["metric"] = d["metric"].astype(str).str.lower()
    d["resolution"] = d["resolution"].astype(str)

    # Filter to the known metric set (keeps plots predictable)
    known_metrics = set(METRIC_CFG.keys())
    unknown = sorted(set(d["metric"].unique()) - known_metrics)
    if unknown:
        print(f"NOTE: ignoring unknown metrics in CSV: {unknown}")
        d = d[d["metric"].isin(known_metrics)].copy()

    if d.empty:
        raise SystemExit("No valid FR rows to rank/plot.")

    # Rank each (resolution, metric) group independently
    rank_rows: List[pd.DataFrame] = []
    for (res, metric), g in d.groupby(["resolution", "metric"], sort=False):
        ranked = _rank_group(g[["mode", "mean_score", "metric"]], str(metric))
        if ranked.empty:
            continue
        ranked.insert(0, "resolution", str(res))
        fam_map = g.set_index("mode")["family"].to_dict()
        ranked["family"] = ranked["mode"].map(fam_map)
        rank_rows.append(ranked)

    if not rank_rows:
        raise SystemExit("No groups ranked; check CSV content.")

    ranks = pd.concat(rank_rows, ignore_index=True)

    # Export rank table
    out_csv = OUT_DIR / "fr_rankings.csv"
    cols = ["resolution", "metric", "rank", "mode", "family", "mean_score", "best_value", "gap_to_best"]
    ranks[cols].to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Wrote rankings: {out_csv}")

    # One plot per (resolution, metric)
    for (res, metric), g in ranks.groupby(["resolution", "metric"], sort=False):
        _plot_rank_bar(g, resolution=str(res), metric=str(metric), out_dir=OUT_DIR, color_by_family=True)

    # One summary plot per resolution (stacked metrics)
    metric_order = [m for m in METRIC_CFG.keys() if m in ranks["metric"].unique().tolist()]
    for res, _g in ranks.groupby("resolution", sort=False):
        _plot_summary_per_resolution(ranks, resolution=str(res), metrics=metric_order, out_dir=OUT_DIR, color_by_family=True)

    print("Done. FR plots and rankings written under:", OUT_DIR)


if __name__ == "__main__":
    main()