#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Watt ranking (per-mode) from AC power meter logs (BENETECH GM89).

What this script does
---------------------
1) Load ONE idle baseline CSV (AC watts while system is idle).
2) For every SR-mode watt CSV under a directory:
   - Parse watt samples (assumed ~1 Hz; integral uses sum(W) as Joules over the window)
   - Compute "real" watts by subtracting the idle *median* (robust baseline)
   - Summarize stats for both raw and real watt series
   - Compute energy totals (J) and (optionally) J/frame if FPS is available
3) Rank modes by average real watt (lower is better).
4) Write:
   - ./watt_out/watt_rankings.csv
   - ./watt_out/rank_real_watt.png
   - ./watt_out/rank_j_per_frame.png (only if FPS join succeeded)

Important notes
-------------------------------------
- Energy in Joules:
    energy_total_j = sum(raw_watts)
    energy_real_j  = sum(real_watts)
  This matches a 1 Hz rectangular integral approximation.
- J/frame requires FPS:
    J/frame = energy_real_j / (fps_avg * seconds)
  FPS is optionally joined from a HWiNFO perf-first output CSV.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

# ================== CONFIG ==================
# Input paths
IDLE_WATT_CSV = r"C:\Users\vince\Documents\Watt\Silent Hill 2\idle\idle.csv"
WATT_SR_DIR   = r"C:\Users\vince\Documents\Watt\Silent Hill 2\sr"

# Output directory
OUT_DIR = Path("./sh2_watt_out")

# Plot config
DPI = 140
STYLE = "whitegrid"
SHOW = False  # set True for interactive show()

# Optional join (mode -> fps_avg) for J/frame
HWINFO_PERF_RANKINGS = Path(
    r"C:\Users\vince\VSCode\SR_VScode_Project\HardWare_Rankings\sh2_hwinfo_out_perf_first\sr_rankings_perf_first.csv"
)
# ===========================================


# ================== FS / TEXT HELPERS ==================
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _detect_bom_encoding(data: bytes) -> Optional[str]:
    if data.startswith(b"\xEF\xBB\xBF"):
        return "utf-8-sig"
    if data.startswith(b"\xFF\xFE"):
        return "utf-16-le"
    if data.startswith(b"\xFE\xFF"):
        return "utf-16-be"
    return None


def _read_text(path: Path) -> Tuple[str, str]:
    data = path.read_bytes()
    enc = _detect_bom_encoding(data)
    if enc:
        try:
            return data.decode(enc, errors="strict"), enc
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8", errors="strict"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def _norm(s: str) -> str:
    return str(s).replace("\ufeff", "").strip().strip('"').strip("'")


# Parse a float from a CSV cell that may contain units/extra characters.
def _parse_float(cell: str) -> Optional[float]:
    # Behavior preserved: keep digits and . - + e E, then float().
    t = _norm(cell)
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


# Convert to float if possible and finite; otherwise return None.
def _as_finite_float(x: Any) -> Optional[float]:
    # This is the key helper that prevents Pylance "Any|None passed to float()" warnings.
    if isinstance(x, (int, float)):
        fx = float(x)
        return fx if math.isfinite(fx) else None
    return None


# ================== WATT CSV LOADER ==================
# Read a 2-column CSV like: Time (sec),Watt
# Returns: (times, watts) lists, dropping rows with invalid values.
def _read_watt_csv(path: Path) -> Tuple[List[float], List[float]]:
    # NOTE: Behavior preserved: - If header not recognized, treat the first two columns as (Time, Watt).
    text, _ = _read_text(path)
    reader = csv.reader(text.splitlines(), delimiter=",")
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        return [], []

    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]

    # Header fallback logic
    if len(headers) < 2 or ("time" not in headers[0].lower() and "watt" not in headers[1].lower()):
        data_rows = rows
        headers = ["Time", "Watt"]

    t_idx = 0
    w_idx = 1

    times: List[float] = []
    watts: List[float] = []
    for r in data_rows:
        if len(r) <= max(t_idx, w_idx):
            continue
        tt = _parse_float(r[t_idx])
        ww = _parse_float(r[w_idx])
        if tt is None or ww is None or math.isnan(ww):
            continue
        times.append(float(tt))
        watts.append(float(ww))
    return times, watts


# ================== STATS / SUMMARIES ==================
def _stats(arr: np.ndarray) -> Dict[str, Optional[float]]:
    a = arr[np.isfinite(arr)]
    if a.size == 0:
        return {"mean": None, "median": None, "p95": None, "max": None, "min": None}
    return {
        "mean": float(np.mean(a)),
        "median": float(np.median(a)),
        "p95": float(np.percentile(a, 95)),
        "max": float(np.max(a)),
        "min": float(np.min(a)),
    }


def _fmt(v: Optional[float], d: int = 2) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "NA"
        return f"{float(v):.{d}f}"
    except Exception:
        return "NA"


# ================== MODE PARSING (from filename stem) ==================
_res_tokens = {
    "1080p", "1440p", "1600p", "2160p", "720p",
    "2k", "2.5k", "4k", "8k",
    "wqhd", "wqxga", "uhd",
}
_res_re_numeric = re.compile(r"^(?:(\d{3,4})p|(\d+(?:\.\d+)?)k)$", re.IGNORECASE)


def _is_resolution_token(tok: str) -> bool:
    t = tok.strip().lower()
    if t in _res_tokens:
        return True
    return bool(_res_re_numeric.match(t))


# Normalize resolution token for reporting.
def _normalize_resolution(tok: str) -> str:
    # NOTE: This keeps "2.5k" as "2.5k" (does not convert to 1600p).
    t = tok.strip().lower()
    m = _res_re_numeric.match(t)
    if m:
        if m.group(1):  # e.g., 1080p
            return f"{m.group(1)}p"
        if m.group(2):  # e.g., 2.5k
            v = m.group(2)
            if v in {"2.5", "2.5k"}:
                return "2.5k"
            if v in {"2", "2k"}:
                return "2k"
            if v in {"4", "4k"}:
                return "4k"
            if v in {"8", "8k"}:
                return "8k"
            return f"{v}k"
    if t in _res_tokens:
        if t == "wqxga":
            return "WQXGA"
        if t == "wqhd":
            return "WQHD"
        if t == "uhd":
            return "UHD"
        return t
    return tok


# Parse mode metadata from filename stem like: DLSS_Quality_1080p_Reflex
# Returns: family, sr_mode, resolution, mode
def _parse_mode_tokens(stem: str) -> Dict[str, str]:
    toks = stem.split("_")
    family = toks[0] if len(toks) >= 1 else ""
    sr_mode = toks[1] if len(toks) >= 2 else ""

    resolution = ""
    actmode = ""
    for tk in toks[2:]:
        lt = tk.lower()
        if not resolution and _is_resolution_token(tk):
            resolution = _normalize_resolution(tk)
            continue
        if lt.startswith("reflex") or lt.startswith("framegen") or lt.startswith("base"):
            actmode = tk

    if not resolution:
        for tk in toks:
            if _is_resolution_token(tk):
                resolution = _normalize_resolution(tk)
                break
    if not actmode and toks:
        actmode = toks[-1]

    return {"family": family, "sr_mode": sr_mode, "resolution": resolution, "active_mode": actmode}


# ================== OPTIONAL JOIN: mode -> fps_avg ==================
# Load mode -> fps_avg from HWiNFO perf-first rankings.
def _load_fps_map(perf_csv: Path) -> Dict[str, float]:
    # - Prefer pandas read_csv(utf-8-sig)
    # - Fallback to csv.DictReader
    fps_map: Dict[str, float] = {}
    try:
        import pandas as pd

        df = pd.read_csv(perf_csv, encoding="utf-8-sig")
        if "mode" in df.columns and "fps_avg" in df.columns:
            for _, row in df[["mode", "fps_avg"]].dropna().iterrows():
                m = str(row["mode"])
                try:
                    fps_map[m] = float(row["fps_avg"])
                except Exception:
                    pass
        return fps_map
    except Exception:
        try:
            with perf_csv.open("r", encoding="utf-8-sig", newline="") as f:
                r = csv.DictReader(f)
                for row in r:
                    m = row.get("mode")
                    v = row.get("fps_avg")
                    if not m or not v:
                        continue
                    try:
                        fps_map[str(m)] = float(v)
                    except Exception:
                        pass
        except Exception:
            return {}
    return fps_map


# ================== MAIN PIPELINE ==================
def main() -> None:
    sns.set_style(STYLE)
    _ensure_dir(OUT_DIR)

    # ---------- 1) Idle baseline ----------
    idle_path = Path(IDLE_WATT_CSV)
    sr_dir = Path(WATT_SR_DIR)

    if not idle_path.exists():
        raise SystemExit(f"Idle watt CSV not found: {idle_path}")
    if not sr_dir.exists():
        raise SystemExit(f"SR watt directory not found: {sr_dir}")

    _, idle_watts = _read_watt_csv(idle_path)
    if not idle_watts:
        raise SystemExit("Idle CSV has no usable data.")

    idle_arr = np.array(idle_watts, dtype=float)
    idle_stats = _stats(idle_arr)

    # Ensure idle_median is ALWAYS a finite float.
    idle_median_opt = _as_finite_float(idle_stats.get("median"))
    idle_median: float = idle_median_opt if idle_median_opt is not None else float(np.median(idle_arr))
    if not math.isfinite(idle_median):
        raise SystemExit("Failed to compute idle median.")

    # ---------- 2) Discover SR CSVs (dedupe by stem, case-insensitive) ----------
    sr_files = sorted(
        [p for p in sr_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"],
        key=lambda p: p.name.lower(),
    )

    deduped: List[Path] = []
    seen: set[str] = set()
    for p in sr_files:
        key = p.stem.lower()
        if key in seen:
            print(f"NOTE: duplicate mode stem detected: '{p.stem}' ({p.name}); skipping duplicate.")
            continue
        seen.add(key)
        deduped.append(p)
    sr_files = deduped

    if not sr_files:
        raise SystemExit("No SR watt CSVs found.")

    # ---------- 3) Optional FPS join for J/frame ----------
    mode_to_fps: Dict[str, float] = {}
    if HWINFO_PERF_RANKINGS.exists():
        mode_to_fps = _load_fps_map(HWINFO_PERF_RANKINGS)

    # ---------- 4) Summarize each SR CSV ----------
    rows: List[Dict[str, Any]] = []

    for p in sr_files:
        stem = p.stem

        _, w = _read_watt_csv(p)
        if not w:
            print(f"WARNING: {p.name}: no usable data; skipping.")
            continue

        arr = np.array(w, dtype=float)
        real = arr - idle_median

        s = _stats(arr)
        r = _stats(real)

        # Energy over window (rect integral at ~1 Hz)
        energy_total_j = float(np.nansum(arr))
        energy_real_j = float(np.nansum(real))
        seconds = int(len(arr))

        meta = _parse_mode_tokens(stem)

        row: Dict[str, Any] = {
            "mode": stem,
            "family": meta["family"],
            "sr_mode": meta["sr_mode"],
            "resolution": meta["resolution"],
            "active_mode": meta["active_mode"],
            "seconds": seconds,
            "samples": seconds,

            # Raw watts
            "watt_mean": s["mean"],
            "watt_median": s["median"],
            "watt_p95": s["p95"],
            "watt_max": s["max"],
            "watt_min": s["min"],

            # Real watts (SR − idle)
            "real_watt_mean": r["mean"],
            "real_watt_median": r["median"],
            "real_watt_p95": r["p95"],
            "real_watt_max": r["max"],

            # Energy
            "energy_total_j": energy_total_j,
            "energy_real_j": energy_real_j,

            # Ranking key (lower is better)
            "rank_key": r["mean"],
        }

        # Optional J/frame using joined FPS_avg
        fps = mode_to_fps.get(stem)
        if isinstance(fps, (int, float)) and math.isfinite(float(fps)) and float(fps) > 0 and seconds > 0:
            row["fps_avg_joined"] = float(fps)
            row["j_per_frame_real"] = energy_real_j / (float(fps) * float(seconds))
        else:
            row["fps_avg_joined"] = ""
            row["j_per_frame_real"] = ""

        rows.append(row)

    if not rows:
        raise SystemExit("No SR rows summarized.")

    # ---------- 5) Rank by real_watt_mean ----------
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    for r in rows:
        rk = _as_finite_float(r.get("rank_key"))
        if rk is None:
            invalid.append(r)
        else:
            rr = dict(r)
            rr["rank_key"] = rk  # normalize to float for safe sorting
            valid.append(rr)

    valid.sort(key=lambda x: float(x["rank_key"]))

    ranked: List[Dict[str, Any]] = []
    for i, r in enumerate(valid, start=1):
        rr = dict(r)
        rr["rank"] = i
        ranked.append(rr)
    ranked.extend(invalid)

    # ---------- 6) Write CSV ----------
    _ensure_dir(OUT_DIR)
    fields = [
        "rank", "mode", "family", "sr_mode", "resolution", "active_mode", "seconds", "samples",
        "watt_mean", "watt_median", "watt_p95", "watt_max", "watt_min",
        "real_watt_mean", "real_watt_median", "real_watt_p95", "real_watt_max",
        "energy_total_j", "energy_real_j",
        "fps_avg_joined", "j_per_frame_real",
        "rank_key",
    ]
    out_csv = OUT_DIR / "watt_rankings.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ranked:
            w.writerow({k: r.get(k, "") for k in fields})

    # ---------- 7) Plot: rank by real_watt_mean ----------
    try:
        import pandas as pd

        df = pd.DataFrame(ranked)
        d = df.copy()
        if "rank" in d.columns:
            d = d[d["rank"].notna()].sort_values("rank", ascending=True)
        else:
            d = d.sort_values("real_watt_mean", ascending=True)

        plt.figure(figsize=(10.5, max(4, 0.45 * len(d))), dpi=DPI)
        sns.barplot(data=d, y="mode", x="real_watt_mean", color="#4E79A7", orient="h")
        plt.title("Cost ranking: Average real watt")
        plt.xlabel("Average real Watt [W]")
        plt.ylabel("")
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.1f"))

        for i, v in enumerate(d["real_watt_mean"].values):
            if isinstance(v, (int, float)) and math.isfinite(v):
                plt.text(v, i, f" {_fmt(float(v), 1)} W", va="center")

        plt.tight_layout()
        fig_path = OUT_DIR / "rank_real_watt.png"
        plt.savefig(fig_path)
        if SHOW:
            plt.show()
        plt.close()
    except Exception as e:
        print(f"NOTE: plotting failed/skipped: {e}")

    # ---------- 8) Plot: J/frame (if available) ----------
    try:
        import pandas as pd

        df = pd.DataFrame(ranked)
        dj = df.copy()
        dj["j_per_frame_real"] = pd.to_numeric(dj["j_per_frame_real"], errors="coerce")
        dj = dj[dj["j_per_frame_real"].notna()].copy()

        if not dj.empty:
            dj["mj_per_frame_real"] = dj["j_per_frame_real"] * 1000.0
            dj = dj.sort_values("j_per_frame_real", ascending=True)

            plt.figure(figsize=(10.5, max(4, 0.45 * len(dj))), dpi=DPI)
            sns.barplot(data=dj, y="mode", x="mj_per_frame_real", color="#59A14F", orient="h")
            plt.title("Energy per frame")
            plt.xlabel("mJ per frame")
            plt.ylabel("")
            ax = plt.gca()
            ax.xaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f"))

            for i, v in enumerate(dj["mj_per_frame_real"].values):
                if isinstance(v, (int, float)) and math.isfinite(v):
                    plt.text(v, i, f" {float(v):.0f} mJ", va="center")

            plt.tight_layout()
            plt.savefig(OUT_DIR / "rank_j_per_frame.png")
            if SHOW:
                plt.show()
            plt.close()
        else:
            print("NOTE: No J/frame data found; skipping J/frame plot.")
    except Exception as e:
        print(f"NOTE: J/frame plotting skipped: {e}")

    print(f"Idle baseline median: {_fmt(idle_median, 2)} W")
    print(f"Wrote: {out_csv}")
    print(f"Plot: {OUT_DIR / 'rank_real_watt.png'}")
    print(f"Plot: {OUT_DIR / 'rank_j_per_frame.png'}")


if __name__ == "__main__":
    main()