#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Purpose:
    Aggregate real power (SR − idle) across modes for each upscaler family
    (e.g. DLSS, FSR1, FSR3.1.2, XeSS) and rank families on that cost.

Input:
    To switch to mean aggregation, change AGG_FUNC = "mean"

    watt_out/watt_rankings.csv  (produced by watt_rankings_plot.py)
        Required columns:
            mode
            real_watt_mean
            j_per_frame_real
        Extra:
            real_watt_median (also aggregate it for transparency)

Aggregation:
    For each family:
        family_real_watt_mean   = median(real_watt_mean)   (robust “typical” cost)
        family_real_watt_median = median(real_watt_median) (for transparency)
        modes                   = number of modes

Ranking:
    Ascending by family_real_watt_mean (lower = better).
    Ascending by family_j_per_frame_real (lower = better).
    

Outputs (under ./watt_out):
    family_total_watt.png   (horizontal bar ranking)
    family_total_j_per_frame.png   (horizontal bar ranking)
    family_total_watt.csv   (rank + family + aggregated columns)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.patheffects as pe

# ============================ CONFIG ============================
# Input / output paths
WATT_RANKINGS_CSV = Path("./sh2_watt_out/watt_rankings.csv")
OUT_DIR = Path("./sh2_watt_out")

# Plot style / rendering
SHOW = False  # set True for interactive show()
DPI = 140
STYLE = "whitegrid"

# Aggregation across modes per family:
#   "median" (robust) or "mean" (sensitive to outliers)
AGG_FUNC = "median"
# ===============================================================

# ====================== VISUAL: FAMILY COLORS ======================
# Consistent palette across your whole project
FAMILY_COLORS: Dict[str, str] = {
    "DLSS": "#1F77B4",
    "FSR" : "#FF1E0E",
    "FSR1": "#FF7F0E",
    "FSR1.0": "#FF7F0E",
    "FSR3.1": "#00FF91",
    "FSR3.1.2": "#2CA02C",
    "FSR3.1.4": "#EAFF00",
    "XeSS": "#9467BD",
}
DEFAULT_COLOR = "#4E79A7"
# ==============================================================


# ============================ HELPERS ============================
# Create output dir if missing (safe if already exists).
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# Mode naming convention
# Example: "DLSS_Quality_1080p_Reflex" -> "DLSS"
def _extract_family(mode: str) -> str:
    if not isinstance(mode, str):
        return "UNKNOWN"
    return mode.split("_", 1)[0] if "_" in mode else mode


# Pretty float formatting for annotations and CSV readability.
def _fmt(v: Optional[float], d: int = 2) -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        return "NA"
    return f"{float(v):.{d}f}"


# Convert to finite float if possible; otherwise None.
def _as_finite_float(x: Any) -> Optional[float]:
    if isinstance(x, (int, float)):
        fx = float(x)
        return fx if math.isfinite(fx) else None
    return None


# Aggregate a Series using AGG_FUNC (median or mean) after numeric coercion.
def _agg(series: pd.Series) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    if AGG_FUNC == "mean":
        return float(s.mean())
    # default: median
    return float(s.median())
# ===============================================================


# ===================== FAMILY TABLE BUILD ======================
# Build per-family aggregate table from per-mode watt_rankings.csv rows.
# Output columns: family, family_real_watt_mean, family_j_per_frame_real, family_real_watt_median, modes, rank (assigned after sorting by family_real_watt_mean)
def _build_family_table(df: pd.DataFrame, t: str) -> pd.DataFrame:
    d = df.copy()

    # Ensure family column exists (derive from mode name)
    if "family" not in d.columns:
        d["family"] = d["mode"].astype(str).apply(_extract_family)

    # Ensure numeric columns are numeric (important for stability and typing)
    d["real_watt_mean"] = pd.to_numeric(d["real_watt_mean"], errors="coerce")
    d["real_watt_median"] = pd.to_numeric(d["real_watt_median"], errors="coerce")  
    d["j_per_frame_real"] = pd.to_numeric(d["j_per_frame_real"], errors="coerce")
    
    rows = []
    for fam, g in d.groupby("family", dropna=False):
        row: Dict[str, Any] = {
            "family": str(fam),
            "family_real_watt_mean": _agg(g["real_watt_mean"]),
            "family_real_watt_median": _agg(g["real_watt_median"]),
            "family_j_per_frame_real": _agg(g["j_per_frame_real"]),
            "modes": int(len(g)),
        }
        rows.append(row)

    fam_df = pd.DataFrame(rows)

    # Rank ascending by family_real_watt_mean or family_j_per_frame_real (lower is better)
    if t == "w":
        ranked_only = fam_df[pd.notna(fam_df["family_real_watt_mean"])].copy()
        ranked_only = ranked_only.sort_values("family_real_watt_mean", ascending=True).reset_index(drop=True)
    elif t == "j":    
        ranked_only = fam_df[pd.notna(fam_df["family_j_per_frame_real"])].copy()
        ranked_only = ranked_only.sort_values("family_j_per_frame_real", ascending=True).reset_index(drop=True)
    else:
        raise ValueError(f"Unknown type for family ranking: {t}")
    
    # Map family -> rank (1..N)
    rank_map = {str(f): int(i + 1) for i, f in enumerate(ranked_only["family"].astype(str).tolist())}
    fam_df["rank"] = fam_df["family"].astype(str).map(rank_map)
    
    # Sort with ranked families first, then any missing/invalid rows
    fam_df = fam_df.sort_values("rank", na_position="last").reset_index(drop=True)
    return fam_df
# ===============================================================


# ===================== PLOT: FAMILY COST BAR =====================
# Plot horizontal bar chart ranking upscaler families by aggregated real watts.
# Notes:
    # - only plot rows with a finite numeric family_real_watt_mean.
    # - Rank numbers (#1, #2, ...) are printed at the left axis for readability.
def _plot_family_cost(df: pd.DataFrame, outfile: Path) -> None:
    if df.empty or "family_real_watt_mean" not in df.columns:
        print("NOTE: nothing to plot (missing family_real_watt_mean).")
        return

    d = df.copy()
    d["family_real_watt_mean"] = pd.to_numeric(d["family_real_watt_mean"], errors="coerce")
    d = d[d["family_real_watt_mean"].notna()].copy()
    if d.empty:
        print("NOTE: no finite watt values; skipping plot.")
        return

    d = d.sort_values("family_real_watt_mean", ascending=True).reset_index(drop=True)

    sns.set_style(STYLE)
    height = max(3.8, 0.65 * len(d))
    fig, ax = plt.subplots(figsize=(9.2, height), dpi=DPI)

    # Color bars by family palette (fallback if unknown family label)
    fam_list = d["family"].astype(str).to_list()
    colors = [FAMILY_COLORS.get(f, DEFAULT_COLOR) for f in fam_list]

    # Main bars
    ax.barh(d["family"].astype(str).to_list(), d["family_real_watt_mean"].to_list(),
            color=colors, edgecolor="black", linewidth=0.6)

    ax.set_title(f"SR Family Real Watt Cost ({AGG_FUNC} across modes)")
    ax.set_xlabel(f"{AGG_FUNC} real Watt [W]")
    ax.set_ylabel("SR family")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

    # Compute text padding based on axis span
    x0, x1 = ax.get_xlim()
    span = x1 - x0
    pad = 0.012 * span if span > 0 else 0.05

    # End-of-bar labels (value + extra median)
    mean_vals = d["family_real_watt_mean"].to_list()
    for i, val in enumerate(mean_vals):
        fv = _as_finite_float(val)
        if fv is None:
            continue

        xt = fv + pad
        ha = "left"
        if xt > (x1 - 0.02 * span):
            xt = fv - pad
            ha = "right"

        extra = ""
        med_val = _as_finite_float(d.loc[i, "family_real_watt_median"])
        if med_val is not None:
            extra = f" (median_raw={_fmt(med_val, 2)})"

        ax.text(xt, i, f"{_fmt(fv, 2)}{extra}", va="center", ha=ha, fontsize=9)

    # Rank labels at the left edge
    # Avoid `.values[0]` (Pylance hates it when types are uncertain); use a safe lookup instead.
    d_rank = df[["family", "rank"]].copy()
    d_rank["family"] = d_rank["family"].astype(str)

    for i, fam in enumerate(fam_list):
        rank_series = d_rank.loc[d_rank["family"] == fam, "rank"]
        rk = int(rank_series.iloc[0]) if not rank_series.empty and pd.notna(rank_series.iloc[0]) else 0
        ax.text(
            x0, i, f"#{rk}" if rk > 0 else "#?",
            va="center", ha="left", fontsize=9, color="#222222",
            path_effects=[pe.withStroke(linewidth=2, foreground="white")]
        )

    fig.tight_layout()
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {outfile}")
# ===============================================================


# ===================== PLOT: FAMILY PERF BAR =====================
def _plot_family_perf(df: pd.DataFrame, outfile: Path) -> None:
    if df.empty or "family_j_per_frame_real" not in df.columns:
        print("NOTE: nothing to plot (missing family_j_per_frame_real).")
        return
    
    d = df.copy()
    d["family_j_per_frame_real"] = pd.to_numeric(d["family_j_per_frame_real"], errors="coerce")
    d = d[d["family_j_per_frame_real"].notna()].copy()
    if d.empty:
        print("NOTE: no finite J/frame values; skipping plot.")
        return
    
    d = d.sort_values("family_j_per_frame_real", ascending=True).reset_index(drop=True)
    
    sns.set_style(STYLE)
    height = max(3.8, 0.65 * len(d))
    fig, ax = plt.subplots(figsize=(9.2, height), dpi=DPI)
    
    fam_list = d["family"].astype(str).to_list()
    colors = [FAMILY_COLORS.get(f, DEFAULT_COLOR) for f in fam_list]
    
    ax.barh(d["family"].astype(str).to_list(), d["family_j_per_frame_real"].to_list(),
            color=colors, edgecolor="black", linewidth=0.6)
    ax.set_title(f"SR Family Real J/frame Cost ({AGG_FUNC} across modes)")
    ax.set_xlabel(f"{AGG_FUNC} real J/frame [J]")
    ax.set_ylabel("SR family")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.3f"))
    
    x0, x1 = ax.get_xlim()
    span = x1 - x0
    pad = 0.012 * span if span > 0 else 0.05
    mean_vals = d["family_j_per_frame_real"].to_list()
    for i, val in enumerate(mean_vals):
        fv = _as_finite_float(val)
        if fv is None:
            continue
        
        xt = fv + pad
        ha = "left"
        if xt > (x1 - 0.02 * span):
            xt = fv - pad
            ha = "right"
        
        ax.text(xt, i, f"{_fmt(fv, 3)} J", va="center", ha=ha, fontsize=9)
    fig.tight_layout()
    outfile.parent.mkdir(parents=True, exist_ok=True)
    
    d_rank = df[["family", "rank"]].copy()
    d_rank["family"] = d_rank["family"].astype(str)

    for i, fam in enumerate(fam_list):
        rank_series = d_rank.loc[d_rank["family"] == fam, "rank"]
        rk = int(rank_series.iloc[0]) if not rank_series.empty and pd.notna(rank_series.iloc[0]) else 0
        ax.text(
            x0, i, f"#{rk}" if rk > 0 else "#?",
            va="center", ha="left", fontsize=9, color="#222222",
            path_effects=[pe.withStroke(linewidth=2, foreground="white")]
        )
    
    fig.savefig(outfile, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {outfile}")
# ===============================================================


# =============================== MAIN ===============================
# 1) Load per-mode watt ranking CSV
# 2) Validate columns
# 3) Aggregate per-family
# 4) Plot and export CSV
def main() -> None:
    if not WATT_RANKINGS_CSV.exists():
        raise SystemExit(f"Input CSV not found: {WATT_RANKINGS_CSV}")

    try:
        df = pd.read_csv(WATT_RANKINGS_CSV, encoding="utf-8-sig")
    except Exception as e:
        raise SystemExit(f"Failed reading {WATT_RANKINGS_CSV}: {e}")

    need = {"mode", "real_watt_mean", "real_watt_median", "j_per_frame_real"}
    if not need.issubset(df.columns):
        raise SystemExit(f"Missing required columns: {sorted(need - set(df.columns))}")

    fam_w_df = _build_family_table(df, "w")
    fam_j_df = _build_family_table(df, "j")
    if fam_w_df.empty or fam_j_df.empty:
        raise SystemExit("No families aggregated (empty DataFrame).")

    _ensure_dir(OUT_DIR)

    # Plot
    _plot_family_cost(fam_w_df, OUT_DIR / "family_total_watt.png")
    _plot_family_perf(fam_j_df, OUT_DIR / "family_total_j_per_frame.png")

    # Export one combined CSV (rank + aggregated columns)
    cols = ["rank", "family", "family_real_watt_mean", "family_real_watt_median", "family_j_per_frame_real", "modes"]

    out_csv = OUT_DIR / "family_total_watt.csv"
    fam_w_df[cols].sort_values("rank", na_position="last").to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Wrote: {out_csv}")

    print("Done. Simplified family watt ranking generated (single CSV).")


if __name__ == "__main__":
    main()