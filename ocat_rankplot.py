#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCAT plotting

Inputs (expected under ./ocat_out)
---------------------------------
1) ocat_rankings_latency_first.csv
   - contains ranking + mean/p95/p99 of latency measures

2) ocat_consistency_check.csv
   - contains meta fields for the footer (Runtime, SyncInterval, GPU, OS...etc)
   - used to confirm all runs and print context on plots

Outputs (written under ./ocat_out)
-------------------------------
- rank_pc_latency.png
    Single-bar ranking by PC latency mean (lower is better)

- components_grouped.png
    Grouped bars per mode:
      * Game latency (partial)  = ms_in_present_api_mean
      * Render latency          = render_latency_mean
    Plus a "total=..." annotation per mode.

- render_subcomponents_grouped.png
    Grouped bars per mode:
      * Render queue = ms_estimated_driver_lag_mean
      * GPU render   = ms_until_render_complete_mean
    Plus a "total=..." annotation per mode.

- family_total_latency.png + family_total_latency.csv
    Aggregate (median) of per-mode PC latency by SR family (DLSS/FSR/XeSS),
    Approach of robust central tendency.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.figure import Figure
import pandas as pd
import seaborn as sns
import textwrap

# ================== CONFIG ==================
OCAT_OUT_DIR = Path("./ocat_out")

DPI = 140
STYLE = "whitegrid"
SHOW = False  # True only for interactive

# Bar colors (high contrast)
COLOR_PRESENT = "#D62728"   # game latency partial
COLOR_RENDER  = "#2CA02C"   # render latency
COLOR_DRIVER  = "#76B7B2"   # render queue
COLOR_GPU     = "#F28E2B"   # GPU render

# Family colors (consistent palette across all plots)
FAMILY_COLORS: Dict[str, str] = {
    "DLSS": "#1F77B4",
    "FSR1": "#FF7F0E",
    "FSR3.1.2": "#2CA02C",
    "XeSS": "#9467BD",
}
DEFAULT_COLOR = "#4E79A7"

# Layout tuning (readability with many modes)
ROW_STEP = 1.25
BAR_H = 0.34
PAIR_SEP = 0.22
# ===========================================


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# All outputs are written with utf-8-sig BOM for Excel friendliness
def _read_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        print(f"NOTE: missing file: {path}")
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:
        print(f"ERROR reading {path}: {e}")
        return None


def _fmt_float(v: Optional[float], digits: int = 2) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "NA"
        return f"{float(v):.{digits}f}"
    except Exception:
        return "NA"


# naming convention: "DLSS_Quality_1080p_Reflex" -> "DLSS"
def _extract_family(mode: str) -> str:
    if not isinstance(mode, str):
        return "UNKNOWN"
    return mode.split("_", 1)[0] if "_" in mode else mode


# ========================== Footer: meta context band ===========================================
_META_KEYS = ["Runtime", "SyncInterval", "GPU #", "GPU", "Processor", "Motherboard", "OS", "System RAM"]


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).replace("\ufeff", "").strip().strip('"').strip("'").strip()

# Read ocat_consistency_check.csv and compute:
# - meta_single: key -> single value | 'varies' | 'missing'
# - meta_unique: key -> sorted unique values
def _collect_meta_from_consistency(consistency_csv: Path) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    df = _read_csv(consistency_csv)
    if df is None or df.empty:
        print("Missing or unreadable ocat_consistency_check.csv (meta footer incomplete).")
        return {}, {}

    meta_unique: Dict[str, List[str]] = {}
    meta_single: Dict[str, str] = {}

    for k in _META_KEYS:
        if k not in df.columns:
            meta_unique[k] = []
            meta_single[k] = "missing"
            continue

        vals = [_norm_str(v) for v in df[k].tolist()]
        vals = [v for v in vals if v != ""]
        uniq = sorted(set(vals))

        meta_unique[k] = uniq
        if not uniq:
            meta_single[k] = "missing"
        elif len(uniq) == 1:
            meta_single[k] = uniq[0]
        else:
            meta_single[k] = "varies"

    meta_single["Logs"] = str(int(len(df)))
    return meta_single, meta_unique


#     Footer rule:
# - Always show meta footer when possible.
# - If a key varies, show unique values (capped) to expose inconsistency.
def _compose_meta_line(meta_single: Dict[str, str], meta_unique: Dict[str, List[str]]) -> str:
    if not meta_single:
        return ""

    parts: List[str] = []

    def fmt_key(k: str, label: str) -> None:
        val = meta_single.get(k)
        if not val or val == "missing":
            parts.append(f"{label}: missing")
            return
        if val == "varies":
            uniq = meta_unique.get(k, [])
            if uniq:
                cap = 6
                shown = uniq[:cap]
                more = f" (+{len(uniq) - cap} more)" if len(uniq) > cap else ""
                parts.append(f"{label}: [{' → '.join(shown)}]{more}")
            else:
                parts.append(f"{label}: varies")
            return
        parts.append(f"{label}: {val}")

    fmt_key("Runtime", "Runtime")
    fmt_key("SyncInterval", "SyncInterval")
    fmt_key("GPU #", "GPU #")
    fmt_key("GPU", "GPU")
    fmt_key("Processor", "Processor")
    fmt_key("Motherboard", "Motherboard")
    fmt_key("OS", "OS")
    fmt_key("System RAM", "System RAM")

    logs = meta_single.get("Logs")
    if logs:
        parts.append(f"Logs: {logs}")

    header = " | ".join(parts)
    return "\n".join(textwrap.wrap(header, width=140))


# Reserve bottom area and draw the meta string into it
def _reserve_footer_and_draw(fig: Figure) -> None:
    consistency_csv = OCAT_OUT_DIR / "ocat_consistency_check.csv"
    meta_single, meta_unique = _collect_meta_from_consistency(consistency_csv)
    txt = _compose_meta_line(meta_single, meta_unique)
    if not txt:
        return

    lines = txt.count("\n") + 1
    footer_h = min(0.34, max(0.14, 0.09 + 0.028 * (lines - 1)))  # fraction of fig height
    fig.tight_layout(rect=(0.02, footer_h, 0.98, 0.98))

    y = footer_h / 2.4
    fig.text(
        0.01, y, txt,
        ha="left", va="center",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.6", alpha=0.95),
    )
# ==================================================================


# =============== Plots (per-mode rankings) ================
def plot_latency_rank(out_dir: Path, rankings_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    d = df.copy()
    if "rank" in d.columns:
        d = d.sort_values("rank", ascending=True)
    else:
        d = d.sort_values("pc_latency_mean", ascending=True)

    order = d["mode"].tolist()

    fig = plt.figure(figsize=(10.5, max(4, 0.5 * len(order))), dpi=DPI)
    sns.barplot(
        data=d,
        y="mode",
        x="pc_latency_mean",
        order=order,
        color="#4E79A7",
        orient="h",
    )
    ax = plt.gca()
    ax.set_title("Latency ranking: Approximate PC latency (mean)")
    ax.set_xlabel("PC latency mean [ms] (lower is better)")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

    for i, v in enumerate(d["pc_latency_mean"].values):
        if pd.notna(v):
            ax.text(float(v), float(i), f" {_fmt_float(float(v))} ms", va="center")

    _reserve_footer_and_draw(fig)
    plt.savefig(out_dir / "rank_pc_latency.png", dpi=DPI, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)


def plot_components_grouped(out_dir: Path, rankings_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    need = {"mode", "ms_in_present_api_mean", "render_latency_mean"}
    if not need.issubset(df.columns):
        print("NOTE: missing columns for components plot; skipping.")
        return

    d = df.copy()
    if "rank" in d.columns:
        d = d.sort_values("rank", ascending=True)
    else:
        d["pc_latency_mean"] = d["ms_in_present_api_mean"].fillna(0) + d["render_latency_mean"].fillna(0)
        d = d.sort_values("pc_latency_mean", ascending=True)

    modes = d["mode"].tolist()
    game_p = d["ms_in_present_api_mean"].astype(float).tolist()
    render = d["render_latency_mean"].astype(float).tolist()

    N = len(modes)
    y = [i * ROW_STEP for i in range(N)]
    offset = PAIR_SEP

    fig, ax = plt.subplots(figsize=(11.0, max(4, 0.60 * N)), dpi=DPI)

    # RenderLatency vs GameLatency(partial)
    ax.barh([yy + offset for yy in y], render, height=BAR_H, color=COLOR_RENDER,
            edgecolor="black", linewidth=0.5, label="Render Latency")
    ax.barh([yy - offset for yy in y], game_p, height=BAR_H, color=COLOR_PRESENT,
            edgecolor="black", linewidth=0.5, label="Game Latency (Partial)")

    ax.set_yticks(y, modes)
    ax.set_xlabel("Latency [ms]")
    ax.set_ylabel("")
    ax.set_title("Approximate PC latency components (mean)")
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

    # Value annotations for each component bar
    for yy, pv, rv in zip(y, game_p, render):
        if pv == pv:
            ax.text(float(pv), float(yy - offset), f" {_fmt_float(float(pv))}",
                    va="center", ha="left", fontsize=9, color="black")
        if rv == rv:
            ax.text(float(rv), float(yy + offset), f" {_fmt_float(float(rv))}",
                    va="center", ha="left", fontsize=9, color="black")

    # Total per mode annotation: pc_latency_mean = partial + render
    total = d["ms_in_present_api_mean"].fillna(0) + d["render_latency_mean"].fillna(0)
    for yy, tv in zip(y, total.tolist()):
        ax.text(float(tv), float(yy), f"  total={_fmt_float(float(tv))} ms",
                va="center", ha="left", fontsize=9, color="#333333")

    ax.legend(loc="upper right", framealpha=0.95)

    _reserve_footer_and_draw(fig)
    plt.savefig(out_dir / "components_grouped.png", dpi=DPI, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)


def plot_render_subcomponents(out_dir: Path, rankings_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    need = {"mode", "ms_estimated_driver_lag_mean", "ms_until_render_complete_mean"}
    if not need.issubset(df.columns):
        print("NOTE: missing render subcomponent columns; skipping.")
        return

    d = df.copy()
    if "render_latency_mean" in d.columns:
        d = d.sort_values("render_latency_mean", ascending=True)
    else:
        d = d.sort_values("rank", ascending=True)

    modes = d["mode"].tolist()
    q = d["ms_estimated_driver_lag_mean"].astype(float).tolist()
    r = d["ms_until_render_complete_mean"].astype(float).tolist()

    N = len(modes)
    y = [i * ROW_STEP for i in range(N)]
    offset = PAIR_SEP

    fig, ax = plt.subplots(figsize=(11.0, max(4, 0.60 * N)), dpi=DPI)

    ax.barh([yy + offset for yy in y], r, height=BAR_H, color=COLOR_GPU,
            edgecolor="black", linewidth=0.5, label="GPU Render")
    ax.barh([yy - offset for yy in y], q, height=BAR_H, color=COLOR_DRIVER,
            edgecolor="black", linewidth=0.5, label="Render Queue")

    ax.set_yticks(y, modes)
    ax.set_xlabel("Latency [ms]")
    ax.set_ylabel("")
    ax.set_title("Render latency components (mean)")
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

    for yy, qv, rv in zip(y, q, r):
        if qv == qv:
            ax.text(float(qv), float(yy - offset), f" {_fmt_float(float(qv))}",
                    va="center", ha="left", fontsize=9, color="black")
        if rv == rv:
            ax.text(float(rv), float(yy + offset), f" {_fmt_float(float(rv))}",
                    va="center", ha="left", fontsize=9, color="black")

    total = d["ms_estimated_driver_lag_mean"].fillna(0) + d["ms_until_render_complete_mean"].fillna(0)
    for yy, tv in zip(y, total.tolist()):
        ax.text(float(tv), float(yy), f"  total={_fmt_float(float(tv))} ms",
                va="center", ha="left", fontsize=9, color="#333333")

    ax.legend(loc="upper right", framealpha=0.95)

    _reserve_footer_and_draw(fig)
    plt.savefig(out_dir / "render_subcomponents_grouped.png", dpi=DPI, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)
# ============================================================================


# =============== Family aggregation plot ====================
def _family_latency_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["family"] = d["mode"].astype(str).apply(_extract_family)

    # Aggregate per family using MEDIAN (robust central tendency)
    def _med(series: pd.Series) -> Optional[float]:
        s = pd.to_numeric(series, errors="coerce").dropna()
        return float(s.median()) if not s.empty else None

    rows = []
    for fam, g in d.groupby("family"):
        rows.append({
            "family": fam,
            "family_pc_latency_mean": _med(g["pc_latency_mean"]) if "pc_latency_mean" in g.columns else None,
            "family_ms_in_present_api_mean": _med(g["ms_in_present_api_mean"]) if "ms_in_present_api_mean" in g.columns else None,
            "family_render_latency_mean": _med(g["render_latency_mean"]) if "render_latency_mean" in g.columns else None,
            "modes": int(len(g)),
        })

    fam_df = pd.DataFrame(rows)
    d_rank = fam_df[pd.notna(fam_df["family_pc_latency_mean"])].copy()
    d_rank = d_rank.sort_values("family_pc_latency_mean", ascending=True).reset_index(drop=True)
    rank_map = {f: i + 1 for i, f in enumerate(d_rank["family"])}
    fam_df["rank"] = fam_df["family"].map(rank_map)
    fam_df = fam_df.sort_values("rank", na_position="last")
    return fam_df


def plot_family_total_latency(out_dir: Path, rankings_csv: Path) -> None:
    df = _read_csv(rankings_csv)
    if df is None or df.empty:
        return
    _ensure_dir(out_dir)

    fam = _family_latency_table(df)
    d = fam[fam["family_pc_latency_mean"].notna()].copy()
    if d.empty:
        print("NOTE: no family latency values; skipping family plot.")
        return

    d = d.sort_values("family_pc_latency_mean", ascending=True).reset_index(drop=True)

    sns.set_style(STYLE)
    height = max(3.8, 0.65 * len(d))
    fig, ax = plt.subplots(figsize=(9.2, height), dpi=DPI)

    colors = [FAMILY_COLORS.get(str(f), DEFAULT_COLOR) for f in d["family"].astype(str).tolist()]
    ax.barh(d["family"].astype(str).tolist(), d["family_pc_latency_mean"].astype(float).tolist(),
            color=colors, edgecolor="black", linewidth=0.6)

    ax.set_title("SR Family Total Latency (median PC latency across modes)")
    ax.set_xlabel("Median PC latency [ms] (lower is better)")
    ax.set_ylabel("SR family")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))

    x0, x1 = ax.get_xlim()
    span = x1 - x0
    pad = 0.012 * span

    for i, row in enumerate(d.to_dict(orient="records")):
        val = row.get("family_pc_latency_mean")
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            continue

        xt = float(val) + pad
        ha = "left"
        if xt > (x1 - 0.02 * span):
            xt = float(val) - pad
            ha = "right"

        extra_parts = []
        pres = row.get("family_ms_in_present_api_mean")
        rend = row.get("family_render_latency_mean")
        if isinstance(pres, (int, float)) and math.isfinite(pres):
            extra_parts.append(f"game(partial)={_fmt_float(float(pres),2)}")
        if isinstance(rend, (int, float)) and math.isfinite(rend):
            extra_parts.append(f"render={_fmt_float(float(rend),2)}")
        extra = f" ({', '.join(extra_parts)})" if extra_parts else ""
        ax.text(float(xt), float(i), f"{_fmt_float(float(val),2)}{extra}", va="center", ha=ha, fontsize=9)

    # Rank labels at left edge
    for i, fam_name in enumerate(d["family"].astype(str).tolist()):
        rk_series = fam.loc[fam["family"].astype(str) == fam_name, "rank"]
        rk = int(rk_series.iloc[0]) if (not rk_series.empty and pd.notna(rk_series.iloc[0])) else 0
        ax.text(float(x0), float(i), f"#{rk}" if rk > 0 else "#?", va="center", ha="left", fontsize=9, color="#222222")

    _reserve_footer_and_draw(fig)
    plt.savefig(out_dir / "family_total_latency.png", dpi=DPI, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)

    cols = [
        "rank", "family", "family_pc_latency_mean",
        "family_ms_in_present_api_mean", "family_render_latency_mean", "modes",
    ]
    fam[cols].sort_values("rank", na_position="last").to_csv(out_dir / "family_total_latency.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote: {out_dir / 'family_total_latency.csv'}")
    print(f"Plot: {out_dir / 'family_total_latency.png'}")


# ========================== Main ==========================
def main():
    sns.set_style(STYLE)
    rankings_csv = OCAT_OUT_DIR / "ocat_rankings_latency_first.csv"

    plot_latency_rank(out_dir=OCAT_OUT_DIR, rankings_csv=rankings_csv)
    plot_components_grouped(out_dir=OCAT_OUT_DIR, rankings_csv=rankings_csv)
    plot_render_subcomponents(out_dir=OCAT_OUT_DIR, rankings_csv=rankings_csv)
    plot_family_total_latency(out_dir=OCAT_OUT_DIR, rankings_csv=rankings_csv)

    print("OCAT plots written under:", OCAT_OUT_DIR)


if __name__ == "__main__":
    main()