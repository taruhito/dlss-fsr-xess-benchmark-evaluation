#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, List, Dict, cast

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.patheffects as pe
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
import pandas as pd
import seaborn as sns


# ============== CONFIG ===============================
COST_FIRST_DIR = Path("./sh2_hwinfo_out_cost_first")   # contains sr_rankings_cost_first.csv
PERF_FIRST_DIR = Path("./sh2_hwinfo_out_perf_first")   # contains sr_rankings_perf_first.csv, mem_clock_check.csv

# Plot style
DPI = 140
STYLE = "whitegrid"
SHOW = False

# Fixed colors for SR family scatter plots.
FAMILY_PALETTE = {
    "DLSS": "#1F77B4",
    "FSR" : "#FF1E0E",
    "FSR1": "#FF7F0E",
    "FSR1.0": "#FF7F0E",
    "FSR3.1": "#00FF91",
    "FSR3.1.2": "#2CA02C",
    "FSR3.1.4": "#EAFF00",
    "XeSS": "#9467BD",
}

# ============================================================
# Ranking policy switch (must match hwinfo_rankings_2.py)
FPS_PRIMARY_RANKING = 1
# ====================================


# Make sure an output directory exists.
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# Read CSVs written with utf-8-sig (BOM) to be Excel-friendly. Returns None if file is missing / unreadable.
def _read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        print(f"NOTE: missing file: {path}")
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:
        print(f"ERROR reading {path}: {e}")
        return None


# Pretty float formatting used across labels; returns 'NA' for non-finite.
def _fmt_float(v: Optional[float], digits: int = 2) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "NA"
        return f"{float(v):.{digits}f}"
    except Exception:
        return "NA"


# Find a reasonable "cost" column to use for perf/W scatter plots.
def _pick_cost_col(df: pd.DataFrame) -> Optional[str]:
    for c in ("real_cpu_gpu_power_w_avg", "cost_avg"):
        if c in df.columns and df[c].notna().any():
            return c
    return None


# Extract SR family name from mode string.
def _extract_family(mode: str) -> str:
    # Example: 'DLSS_Quality_1080p_Base' -> 'DLSS'
    if not isinstance(mode, str):
        return "UNKNOWN"
    return mode.split("_", 1)[0] if "_" in mode else mode


# Cost-first plots 
# 1) rank_real_cost.png: bar plot of average real CPU+GPU power (SR - idle) per mode.
# 2) stack_real_cpu_gpu_cost.png: stacked CPU+GPU components.
def plot_cost_first(out_dir: Path, rankings_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    cost_col = _pick_cost_col(df)

    if cost_col and df[cost_col].notna().any():
        d = df[df[cost_col].notna()].copy()
        d = d.sort_values(cost_col, ascending=True)
        plt.figure(figsize=(10, max(4, 0.4 * len(d))), dpi=DPI)
        sns.barplot(data=d, y="mode", x=cost_col, color="#4E79A7")
        plt.title("Cost ranking: Avg real CPU+GPU power (SR − idle)")
        plt.xlabel("Average real cost [W]")
        plt.ylabel("")
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.1f"))
        for i, v in enumerate(d[cost_col].values):
            if pd.notna(v):
                ax.text(v, i, f" {_fmt_float(v,1)} W", va="center")
        plt.tight_layout()
        plt.savefig(out_dir / "rank_real_cost.png")
        if SHOW:
            plt.show()
        plt.close()

    have_gpu = "real_gpu_power_w_avg" in df.columns and df["real_gpu_power_w_avg"].notna().any()
    have_cpu = "real_cpu_power_w_avg" in df.columns and df["real_cpu_power_w_avg"].notna().any()
    if have_gpu and have_cpu:
        d = df.copy()
        if cost_col and d[cost_col].notna().any():
            d = d.sort_values(cost_col, ascending=True)
        plt.figure(figsize=(10, max(4, 0.4 * len(d))), dpi=DPI)
        plt.barh(d["mode"], d["real_gpu_power_w_avg"], label="GPU real", color="#59A14F")
        plt.barh(
            d["mode"],
            d["real_cpu_power_w_avg"],
            left=d["real_gpu_power_w_avg"],
            label="CPU real",
            color="#E15759",
        )
        plt.title("Average real cost components (SR − idle)")
        plt.xlabel("Average real cost [W]")
        plt.ylabel("")
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir / "stack_real_cpu_gpu_cost.png")
        if SHOW:
            plt.show()
        plt.close()


# When multiple modes share identical perf_score, annotate their raw/presented frame times on the bars.
def _annotate_duplicate_perf_frame_times(ax: Axes, d: pd.DataFrame, mode_order: List[str]) -> None:
    if "perf_score" not in d.columns:
        return

    # Group modes by exact perf_score value (float).
    # NOTE: This is "exact equal", which is what CSV outputs (usually rounded-ish values).
    groups: Dict[float, List[str]] = {}
    for _, row in d.iterrows():
        ps = row.get("perf_score")
        if isinstance(ps, (int, float)) and math.isfinite(ps):
            groups.setdefault(ps, []).append(row["mode"])
    dup_modes = {m for ps, modes in groups.items() if len(modes) > 1 for m in modes}
    if not dup_modes:
        return

    # Snapshot the relevant tie-breaker info per mode.
    info_map = {
        row["mode"]: (
            row.get("frame_time_ms_avg"),
            row.get("frame_time_presented_avg_ms_avg"),
            row.get("perf_score"),
        )
        for _, row in d.iterrows()
    }

    # seaborn/matplotlib barplot uses Rectangle patches at runtime.
    # Type-checkers see Patch base type, so we cast to Rectangle to access geometry methods.
    patches = [cast(Rectangle, p) for p in ax.patches]
    if len(patches) != len(mode_order):
        return

    for mode, patch in zip(mode_order, patches):
        if mode not in dup_modes:
            continue
        ft, ftp, ps = info_map.get(mode, (None, None, None))
        if not isinstance(ps, (int, float)) or math.isnan(ps):
            continue

        txt = f"ft={_fmt_float(ft,3)} / pres={_fmt_float(ftp,3)}"
        w = patch.get_width()
        y_center = patch.get_y() + patch.get_height() / 2.0
        ax.text(
            w * 0.50,
            y_center,
            txt,
            va="center",
            ha="center",
            color="white",
            fontsize=8,
            path_effects=[pe.withStroke(linewidth=1.2, foreground="black")],
        )


# Perf-first plots
# 1) stack_1pct_low_0p1pct_low_score.png: component bars
# 2) rank_perf_score.png (default) OR rank_fps_avg.png (FPS_PRIMARY_RANKING=1)
# 3) cost vs perf scatter (or cost vs avg fps scatter, depending on toggle)
# 4) mem_clock_drift.png (sanity check for RAM clock drift)
def plot_perf_first(out_dir: Path, rankings_csv: Path, mem_clk_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    cost_col = _pick_cost_col(df)
    have_1pct = "fps_1pct_low_avg" in df.columns and df["fps_1pct_low_avg"].notna().any()
    have_0p1pct = "fps_0p1pct_low_avg" in df.columns and df["fps_0p1pct_low_avg"].notna().any()
    have_perf_score = "perf_score" in df.columns and df["perf_score"].notna().any()
    have_fps_avg = "fps_avg" in df.columns and df["fps_avg"].notna().any()

    # Always prefer the CSV rank order if present.
    d_ranked = df.copy()
    if "rank" in d_ranked.columns:
        d_ranked = d_ranked.sort_values("rank", ascending=True)

    # 1) Grouped perf_score components bar (1% low + 0.1% low)
    if have_1pct or have_0p1pct:
        order = d_ranked["mode"].tolist()
        melt_cols: List[str] = []
        if have_1pct:
            melt_cols.append("fps_1pct_low_avg")
        if have_0p1pct:
            melt_cols.append("fps_0p1pct_low_avg")

        md = d_ranked[["mode"] + melt_cols].melt(
            id_vars=["mode"], var_name="metric", value_name="value"
        )
        label_map = {
            "fps_1pct_low_avg": "1% low",
            "fps_0p1pct_low_avg": "0.1% low",
        }
        md["metric"] = md["metric"].map(label_map).fillna(md["metric"])

        plt.figure(figsize=(10.5, max(4, 0.50 * len(order))), dpi=DPI)
        sns.barplot(
            data=md,
            y="mode",
            x="value",
            hue="metric",
            order=order,
            orient="h",
            palette={"1% low": "#1F77B4", "0.1% low": "#FF7F0E"},
        )
        plt.title("Average FPS performance score components")
        plt.xlabel("FPS")
        plt.ylabel("")
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.1f"))

        # Bar value labels: seaborn gives containers; the bars are Rectangle patches at runtime.
        # Cast to Rectangle for geometry methods (to silence type-checker warnings and clarify intent).
        for container in ax.containers:
            bars = [cast(Rectangle, b) for b in container]
            for bar in bars:
                w = bar.get_width()
                if isinstance(w, (int, float)) and not math.isnan(w):
                    y = bar.get_y() + bar.get_height() / 2
                    ax.text(w, y, f" {_fmt_float(w,1)}", va="center")

        plt.legend(title="", loc="lower right")
        plt.tight_layout()
        plt.savefig(out_dir / "stack_1pct_low_0p1pct_low_score.png")
        if SHOW:
            plt.show()
        plt.close()

    # 2) Primary ranking bar:
    #    - default: perf_score bar
    #    - FPS_PRIMARY_RANKING=1: fps_avg bar
    # NOTE:
    #   Even in FPS_PRIMARY mode, the ordering is still from 'rank' column in CSV; this plot simply reflects what the rank represents.
    if FPS_PRIMARY_RANKING and have_fps_avg:
        base_cols = ["mode", "fps_avg", "perf_score", "frame_time_ms_avg", "frame_time_presented_avg_ms_avg"]
        if "rank" in d_ranked.columns:
            base_cols.append("rank")

        dp = d_ranked[base_cols].dropna(subset=["fps_avg"]).copy()
        if "rank" in dp.columns:
            dp = dp.sort_values("rank", ascending=True)
        else:
            dp = dp.sort_values("fps_avg", ascending=False)

        order = dp["mode"].tolist()
        plt.figure(figsize=(11.0, max(4, 0.50 * len(order))), dpi=DPI)
        ax = sns.barplot(data=dp, y="mode", x="fps_avg", order=order, color="#4E79A7", orient="h")
        plt.title("FPS-primary ranking (avg FPS)")
        plt.xlabel("fps_avg")
        plt.ylabel("")
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

        patches = [cast(Rectangle, p) for p in ax.patches]
        for patch, (_, row) in zip(patches, dp.iterrows()):
            w = patch.get_width()
            y = patch.get_y() + patch.get_height() / 2
            ax.text(w, y, f" {_fmt_float(row['fps_avg'],2)}", va="center", ha="left", fontsize=8)

        plt.tight_layout()
        plt.savefig(out_dir / "rank_fps_avg.png")
        if SHOW:
            plt.show()
        plt.close()

    elif have_perf_score:
        base_cols = ["mode", "perf_score", "frame_time_ms_avg", "frame_time_presented_avg_ms_avg"]
        if "rank" in d_ranked.columns:
            base_cols.append("rank")

        dp = d_ranked[base_cols].dropna(subset=["perf_score"]).copy()
        if "rank" in dp.columns:
            dp = dp.sort_values("rank", ascending=True)
        else:
            dp = dp.sort_values("perf_score", ascending=False)

        order = dp["mode"].tolist()
        plt.figure(figsize=(11.0, max(4, 0.50 * len(order))), dpi=DPI)
        ax = sns.barplot(data=dp, y="mode", x="perf_score", order=order, color="#4E79A7", orient="h")
        plt.title("Composite FPS performance score ranking (weighted 1% + 0.1%)")
        plt.xlabel("perf_score")
        plt.ylabel("")
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

        patches = [cast(Rectangle, p) for p in ax.patches]
        for patch, (_, row) in zip(patches, dp.iterrows()):
            w = patch.get_width()
            y = patch.get_y() + patch.get_height() / 2
            ax.text(w, y, f" {_fmt_float(row['perf_score'],2)}", va="center", ha="left", fontsize=8)

        # Only meaningful in perf_score-primary mode (where perf_score ties are the key tie case)
        _annotate_duplicate_perf_frame_times(ax, dp, order)

        plt.tight_layout()
        plt.savefig(out_dir / "rank_perf_score.png")
        if SHOW:
            plt.show()
        plt.close()

    # 3) Scatter(s): performance vs cost
    #    - default: emphasize perf_score and low-FPS metrics
    #    - FPS_PRIMARY_RANKING=1: emphasize avg FPS
    if cost_col and df[cost_col].notna().any():
        d_cost = d_ranked[d_ranked[cost_col].notna()].copy()
        if not d_cost.empty:
            d_cost["family"] = d_cost["mode"].astype(str).apply(_extract_family)
            plots: List[tuple[str, str, str]] = []

            if FPS_PRIMARY_RANKING and have_fps_avg:
                plots.append(("fps_avg", "Average FPS", "cost_vs_fps_avg_scatter.png"))
            else:
                if have_perf_score:
                    plots.append(("perf_score", "Composite FPS performance score", "cost_vs_perf_score_scatter.png"))
                if have_1pct:
                    plots.append(("fps_1pct_low_avg", "1% low FPS", "cost_vs_1pct_low_scatter.png"))
                if have_0p1pct:
                    plots.append(("fps_0p1pct_low_avg", "0.1% low FPS", "cost_vs_0p1pct_low_scatter.png"))
                # Fallback: if the lows/perf_score are missing, at least plot avg FPS.
                if not plots and have_fps_avg:
                    plots.append(("fps_avg", "Average FPS", "cost_vs_fps_avg_scatter.png"))

            for col, ylabel, fname in plots:
                dd = d_cost[d_cost[col].notna()]
                if dd.empty:
                    continue
                hue_order = [family for family in FAMILY_PALETTE if family in set(dd["family"])]
                if not hue_order:
                    hue_order = sorted(dd["family"].dropna().unique().tolist())
                plt.figure(figsize=(7.5, 6.0), dpi=DPI)
                sns.scatterplot(
                    data=dd,
                    x=cost_col,
                    y=col,
                    hue="family",
                    hue_order=hue_order,
                    palette=FAMILY_PALETTE,
                    s=80,
                    alpha=0.85,
                )
                plt.title(f"Cost vs {ylabel}")
                plt.xlabel("Average real cost [W]")
                plt.ylabel(ylabel)
                ax = plt.gca()
                ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.1f"))
                plt.legend(title="SR family", bbox_to_anchor=(1.02, 1), loc="upper left")
                plt.tight_layout()
                out_path = out_dir / fname
                plt.savefig(out_path, bbox_inches="tight")
                if SHOW:
                    plt.show()
                plt.close()
                print(f"Plot: {out_path}")

            # Export a compact table of cost vs perf data for reference.
            cols_to_save = ["rank", "mode", "family", cost_col] if "rank" in d_cost.columns else ["mode", "family", cost_col]
            for c in ["perf_score", "fps_1pct_low_avg", "fps_0p1pct_low_avg", "fps_avg",
                      "frame_time_ms_avg", "frame_time_presented_avg_ms_avg"]:
                if c in d_cost.columns:
                    cols_to_save.append(c)
            tbl = d_cost[cols_to_save].copy()
            if "rank" in tbl.columns:
                tbl = tbl.sort_values("rank", ascending=True)
            tbl.to_csv(out_dir / "cost_vs_perf_table.csv", index=False, encoding="utf-8-sig")

    # 4) Memory clock drift plot (sanity check)
    mem = _read_csv(mem_clk_csv)
    if mem is not None and not mem.empty and {"mem_clock_min_mhz", "mem_clock_max_mhz"}.issubset(mem.columns):
        m = mem.copy()
        m["delta_mhz"] = pd.to_numeric(m["mem_clock_max_mhz"], errors="coerce") - pd.to_numeric(
            m["mem_clock_min_mhz"], errors="coerce"
        )
        m = m.sort_values("mode", ascending=True)
        plt.figure(figsize=(10, max(4, 0.35 * len(m))), dpi=DPI)
        sns.barplot(data=m, y="mode", x="delta_mhz", color="#9C755F")
        plt.title("DRAM Memory Clock Drift (max − min) over window")
        plt.xlabel("Delta [MHz] (flag > ~10 MHz)")
        plt.ylabel("")
        for i, (dv, flag) in enumerate(
            zip(m["delta_mhz"].fillna(0).values, m.get("drift_flag", [""] * len(m)))
        ):
            plt.text(dv, i, f" {_fmt_float(dv,0)} ({flag})", va="center")
        plt.tight_layout()
        plt.savefig(out_dir / "mem_clock_drift.png")
        if SHOW:
            plt.show()
        plt.close()


def main():
    sns.set_style(STYLE)

    plot_cost_first(
        out_dir=COST_FIRST_DIR,
        rankings_csv=COST_FIRST_DIR / "sr_rankings_cost_first.csv",
    )
    plot_perf_first(
        out_dir=PERF_FIRST_DIR,
        rankings_csv=PERF_FIRST_DIR / "sr_rankings_perf_first.csv",
        mem_clk_csv=PERF_FIRST_DIR / "mem_clock_check.csv",
    )

    print("Done. Plots written under:")
    print(f"- {COST_FIRST_DIR}")
    print(f"- {PERF_FIRST_DIR}")


if __name__ == "__main__":
    main()