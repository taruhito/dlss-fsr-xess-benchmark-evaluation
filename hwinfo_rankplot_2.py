#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Robust central tendency (median) for cost family ranking

PRIMARY_RANKING (must match hwinfo_rankings_2.py):
    FPS_PRIMARY_RANKING = 0/1
    If 1:
        Family performance ranking uses avg FPS as PRIMARY
        Rank descending by family_avg_fps
    If 0:
        Weighted average for FPS performance score to get a precise per‑family quality estimate

Cost family score:
    family_cost = median(real_cpu_gpu_power_w_avg across the family’s modes)
    Rank ascending by family_cost.

Performance family score:
    For each family:
        avg_1pct_low  = mean(fps_1pct_low_avg over its modes with valid values)
        avg_0p1pct_low= mean(fps_0p1pct_low_avg over its modes with valid values)
    Composite (weighted average, emphasizing 0.1% lows):
        perf_score = (W_1PCT * avg_1pct_low + W_0P1PCT * avg_0p1pct_low) / (W_1PCT + W_0P1PCT)

Family perf_per_cost
    - If FPS_PRIMARY_RANKING=0:  perf_metric = family_perf_score
    - If FPS_PRIMARY_RANKING=1:  perf_metric = family_avg_fps
    - Efficiency = perf_metric / family_cost

Outputs:
    ./hwinfo_out_cost_first/family_total_cost.png      + CSV
    ./hwinfo_out_perf_first/family_total_perf.png      + CSV
    ./hwinfo_out_perf_first/family_perf_per_cost.png   + CSV 
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

# Dirs
COST_DIR = Path("./hwinfo_out_cost_first")
PERF_DIR = Path("./hwinfo_out_perf_first")

COST_CSV = COST_DIR / "sr_rankings_cost_first.csv"
PERF_CSV = PERF_DIR / "sr_rankings_perf_first.csv"

DPI = 140
STYLE = "whitegrid"
SHOW = False

# Weights for perf composite
W_1PCT = 1.0
W_0P1PCT = 1.3

# ============================================================
# Ranking policy switch (must match hwinfo_rankings_2.py)
# ============================================================
FPS_PRIMARY_RANKING = 1
# ============================================================

FAMILY_COLORS: Dict[str, str] = {
    "DLSS": "#1F77B4",
    "FSR1": "#FF7F0E",
    "FSR3.1.2": "#2CA02C",
    "FSR3.1.4": "#EAFF00",
    "XeSS": "#9467BD",
}
DEFAULT_COLOR = "#4E79A7"


def _extract_family(mode: str) -> str:
    if not isinstance(mode, str):
        return "UNKNOWN"
    return mode.split("_", 1)[0] if "_" in mode else mode


def _fmt(v: Optional[float], d: int = 2) -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return "NA"
    return f"{float(v):.{d}f}"


def _read(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        print(f"NOTE: missing CSV: {path}")
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:
        print(f"ERROR reading {path}: {e}")
        return None


# Minimal family plot helper:
#   - Sort by the chosen value_col only
#   - Add rank column
#   - Annotate value (and optional extra columns) at end of bar
def _plot_family(
    df: pd.DataFrame,
    value_col: str,
    title: str,
    xlabel: str,
    out_path: Path,
    ascending_best: bool,
    annotate_cols: Dict[str, str],
    fmt_digits: int = 2,
) -> None:
    if df.empty:
        print(f"NOTE: empty DataFrame for {out_path.name}, skipping.")
        return

    df = df.sort_values(value_col, ascending=ascending_best).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    sns.set_style(STYLE)
    height = max(3.5, 0.70 * len(df))
    fig, ax = plt.subplots(figsize=(9.0, height), dpi=DPI)

    colors = [FAMILY_COLORS.get(f, DEFAULT_COLOR) for f in df["family"]]
    ax.barh(df["family"], df[value_col], color=colors, edgecolor="black", linewidth=0.6)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("SR family")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter(f"%.{fmt_digits}f"))

    x0, x1 = ax.get_xlim()
    span = x1 - x0
    pad = 0.012 * span

    # End-of-bar annotation
    # NOTE: use enumerate index (int) as y position to avoid Pylance "Hashable" warning from iterrows().
    for i, row in enumerate(df.to_dict(orient="records")):
        val = row.get(value_col)
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            continue

        xt = float(val) + pad
        ha = "left"
        if xt > x1 * 0.97:
            xt = float(val) - pad
            ha = "right"

        extras = []
        for col, label in annotate_cols.items():
            v = row.get(col)
            if isinstance(v, (int, float)) and math.isfinite(v):
                extras.append(f"{label}={_fmt(v, fmt_digits)}")
        extra_text = f" ({', '.join(extras)})" if extras else ""
        ax.text(float(xt), float(i), f"{_fmt(float(val), fmt_digits)}{extra_text}", va="center", ha=ha, fontsize=9)

    # Rank labels at the left edge
    for i, r in enumerate(df["rank"].tolist()):
        ax.text(float(x0), float(i), f"#{int(r)}", va="center", ha="left", fontsize=9, color="#222222")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", dpi=DPI)
    if SHOW:
        plt.show()
    plt.close(fig)
    print(f"Plot: {out_path}")

    # CSV output matching the plot
    out_csv = out_path.with_suffix(".csv")
    keep_cols = ["rank", "family", value_col] + list(annotate_cols.keys())
    df[keep_cols].to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Wrote: {out_csv}")


# Returns the family cost table (for reuse by perf_per_cost), or None if not available.
def build_cost_family() -> Optional[pd.DataFrame]:
    df = _read(COST_CSV)
    if df is None or df.empty or "mode" not in df.columns:
        return None

    d = df.copy()
    d["family"] = d["mode"].astype(str).apply(_extract_family)

    # Keep same simple fallback list as your current script
    cost_col = None
    for c in ["real_cpu_gpu_power_w_avg", "rank_key"]:
        if c in d.columns and d[c].notna().any():
            cost_col = c
            break
    if cost_col is None:
        print("NOTE: no cost column found for cost family ranking.")
        return None

    fam = d.groupby("family", dropna=False)[cost_col].median().reset_index()
    fam.rename(columns={cost_col: "family_cost"}, inplace=True)

    _plot_family(
        fam,
        value_col="family_cost",
        title="SR Family Cost (median real CPU+GPU cost across modes)",
        xlabel="Median real cost [W]",
        out_path=COST_DIR / "family_total_cost.png",
        ascending_best=True,
        annotate_cols={},
        fmt_digits=2,
    )
    return fam


# Returns: (family_perf_table, perf_metric_col_name)
def build_perf_family() -> Tuple[Optional[pd.DataFrame], str]:
    df = _read(PERF_CSV)
    if df is None or df.empty or "mode" not in df.columns:
        return None, ""

    d = df.copy()
    d["family"] = d["mode"].astype(str).apply(_extract_family)

    # Coerce numeric columns once (avoid pd.to_numeric(g.get(...)) typing warnings)
    if "fps_avg" in d.columns:
        d["fps_avg"] = pd.to_numeric(d["fps_avg"], errors="coerce")
    if "fps_1pct_low_avg" in d.columns:
        d["fps_1pct_low_avg"] = pd.to_numeric(d["fps_1pct_low_avg"], errors="coerce")
    if "fps_0p1pct_low_avg" in d.columns:
        d["fps_0p1pct_low_avg"] = pd.to_numeric(d["fps_0p1pct_low_avg"], errors="coerce")

    have_1pct = "fps_1pct_low_avg" in d.columns and d["fps_1pct_low_avg"].notna().any()
    have_0p1pct = "fps_0p1pct_low_avg" in d.columns and d["fps_0p1pct_low_avg"].notna().any()

    # FPS-primary family ranking (avg FPS)
    if FPS_PRIMARY_RANKING:
        if "fps_avg" not in d.columns or d["fps_avg"].notna().sum() == 0:
            print("NOTE: FPS_PRIMARY_RANKING=1 but no fps_avg available; falling back to perf_score family ranking.")
        else:
            fam = d.groupby("family", dropna=False)["fps_avg"].mean().reset_index()
            fam.rename(columns={"fps_avg": "family_avg_fps"}, inplace=True)
            fam = fam[pd.notna(fam["family_avg_fps"])].copy()
            if fam.empty:
                print("NOTE: no valid avg FPS rows after aggregation.")
                return None, ""

            _plot_family(
                fam,
                value_col="family_avg_fps",
                title="SR Family Performance (FPS-primary: avg FPS across modes)",
                xlabel="Average FPS (family mean across modes)",
                out_path=PERF_DIR / "family_total_perf.png",
                ascending_best=False,
                annotate_cols={},
                fmt_digits=2,
            )
            return fam, "family_avg_fps"

    # Default perf_score family ranking
    if not have_1pct and not have_0p1pct:
        print("NOTE: missing 1%/0.1% lows; cannot compute perf family ranking.")
        return None, ""

    rows = []
    for fam, g in d.groupby("family"):
        avg_1pct = float(g["fps_1pct_low_avg"].mean()) if have_1pct else math.nan
        avg_0p1pct = float(g["fps_0p1pct_low_avg"].mean()) if have_0p1pct else math.nan

        comp_sum = 0.0
        weight_sum = 0.0
        if math.isfinite(avg_1pct):
            comp_sum += W_1PCT * avg_1pct
            weight_sum += W_1PCT
        if math.isfinite(avg_0p1pct):
            comp_sum += W_0P1PCT * avg_0p1pct
            weight_sum += W_0P1PCT
        perf_score = comp_sum / weight_sum if weight_sum > 0 else math.nan

        rows.append({
            "family": fam,
            "avg_1pct_low": avg_1pct,
            "avg_0p1pct_low": avg_0p1pct,
            "family_perf_score": perf_score,
        })

    fam = pd.DataFrame(rows)
    fam = fam[pd.notna(fam["family_perf_score"])].copy()
    if fam.empty:
        print("NOTE: no valid perf rows after aggregation.")
        return None, ""

    _plot_family(
        fam,
        value_col="family_perf_score",
        title=f"SR Family FPS Performance (weighted avg: 1%*{W_1PCT} + 0.1%*{W_0P1PCT})",
        xlabel="Weighted average FPS",
        out_path=PERF_DIR / "family_total_perf.png",
        ascending_best=False,
        annotate_cols={"avg_1pct_low": "1%μ", "avg_0p1pct_low": "0.1%μ"},
        fmt_digits=2,
    )
    return fam, "family_perf_score"


# family_perf_per_cost = (family performance metric) / (family_cost)
# - When FPS_PRIMARY_RANKING=0: performance metric is "family_perf_score"
# - When FPS_PRIMARY_RANKING=1: performance metric is "family_avg_fps"
def build_family_perf_per_cost(fam_cost: Optional[pd.DataFrame], fam_perf: Optional[pd.DataFrame], perf_metric_col: str) -> None:
    if fam_cost is None or fam_perf is None:
        return
    if "family" not in fam_cost.columns or "family_cost" not in fam_cost.columns:
        return
    if "family" not in fam_perf.columns or perf_metric_col not in fam_perf.columns:
        return

    # Join on family
    merged = pd.merge(fam_perf, fam_cost, on="family", how="inner")
    if merged.empty:
        return

    merged["family_cost"] = pd.to_numeric(merged["family_cost"], errors="coerce")
    merged[perf_metric_col] = pd.to_numeric(merged[perf_metric_col], errors="coerce")

    # Avoid divide-by-zero
    merged["family_perf_per_cost"] = merged[perf_metric_col] / merged["family_cost"].replace(0, math.nan)
    merged = merged[pd.notna(merged["family_perf_per_cost"])].copy()
    if merged.empty:
        return

    xlabel = f"{perf_metric_col} / family_cost"
    title = "SR Family Performance per Cost"

    _plot_family(
        merged[["family", "family_perf_per_cost", perf_metric_col, "family_cost"]].copy(),
        value_col="family_perf_per_cost",
        title=title,
        xlabel=xlabel,
        out_path=PERF_DIR / "family_perf_per_cost.png",
        ascending_best=False,
        annotate_cols={perf_metric_col: "perf", "family_cost": "cost"},
        fmt_digits=3,  # ratio tends to be smaller; 3 decimals helps readability
    )


def main():
    sns.set_style(STYLE)

    fam_cost = build_cost_family()
    fam_perf, perf_metric_col = build_perf_family()

    build_family_perf_per_cost(fam_cost, fam_perf, perf_metric_col)

    print("Generated:")
    print(f"- {COST_DIR / 'family_total_cost.png'} (+ .csv)")
    print(f"- {PERF_DIR / 'family_total_perf.png'} (+ .csv)")
    print(f"- {PERF_DIR / 'family_perf_per_cost.png'} (+ .csv)")


if __name__ == "__main__":
    main()