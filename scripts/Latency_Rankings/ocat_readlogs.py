#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCAT log loader / parser

Approximate PC Latency = Game Latency (partial) + Render Latency

Parses each OCAT capture CSV into:
  1) Per-frame time-series (used for latency computation & ranking):
      - MsInPresentAPI ≈ Game Latency (partial) inside Present() path
      - MsEstimatedDriverLag ≈ Render queue waiting
      - MsUntilRenderComplete ≈ GPU render time
      - RenderLatency = MsEstimatedDriverLag + MsUntilRenderComplete
  2) Per-file metadata fields (used for consistency check):
      - Runtime, SyncInterval, Motherboard, OS, Processor, System RAM, GPU #, GPU
"""

from __future__ import annotations

import os
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# CONFIG
# Example naming: DLSS_Quality_1080p_Reflex.csv
OCAT_DIR = os.environ.get(
    "OCAT_DIR",
    r"C:\Users\vince\Documents\OCAT\Captures\Silent Hill 2"
)

# KEEP_RAW_ROWS
KEEP_RAW_ROWS = False # For debugging only (very large output if enabled)

# Column policy
# Minimal set of columns.
# If OCAT changes column order, will locate by header names (exact match)
CHOSEN_COLS = [
    # --- PC latency components ---
    "MsInPresentAPI",
    "MsEstimatedDriverLag",
    "MsUntilRenderComplete",

    # --- Meta/context (per-file check) ---
    "Runtime",
    "SyncInterval",
    "Motherboard",
    "OS",
    "Processor",
    "System RAM",
    "GPU #",
    "GPU",
]

FRAME_KEYS = {
    "MsInPresentAPI",
    "MsEstimatedDriverLag",
    "MsUntilRenderComplete",
}
META_KEYS = [
    "Runtime", "SyncInterval", "Motherboard", "OS",
    "Processor", "System RAM", "GPU #", "GPU",
]

# --------------------------------------------------------------
# basic string utilities
def _norm(s: str) -> str:
    return str(s).replace("\ufeff", "").strip().strip('"').strip("'") # Strip BOM, whitespace, quotes


# OCAT CSV reader (robust but intentionally simple)
# - OCAT often writes UTF-8 with BOM -> use utf-8-sig
# - Some files include repeated header rows mid-file -> skip them
# - Enforce row width == header width (truncate/pad)
def _read_csv_simple(path: Path) -> Tuple[List[str], List[List[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=",")
        headers: Optional[List[str]] = None
        rows: List[List[str]] = []
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue

            if headers is None:
                headers = [_norm(h) for h in row]
                continue

            # Skip repeated headers inside the file
            if len(row) == len(headers) and [_norm(c) for c in row] == headers:
                continue

            # Width-fix
            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            elif len(row) > len(headers):
                row = row[:len(headers)]

            rows.append([str(c) for c in row])

        return headers or [], rows


# Map chosen column name -> index, but only if present
def _build_index_exact(headers: List[str]) -> Dict[str, int]:
    return {name: headers.index(name) for name in CHOSEN_COLS if name in headers}


# Parse float robustly (strip units / odd chars)
# - OCAT numeric fields should be plain numbers, but keep this tolerant as safeguard
def _parse_float(cell: str) -> Optional[float]:
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


# Coerce value based on key type
def _coerce_value(key: str, val: str) -> Any:
    if key in FRAME_KEYS:
        return _parse_float(val) # Frame series must be numeric floats

    # SyncInterval should be integer-like (0, 1, 2...)
    if key == "SyncInterval":
        f = _parse_float(val)
        if f is None:
            return None
        try:
            return int(round(f))
        except Exception:
            return None

    # Everything else keep as normalized string
    return _norm(val)


# Treat filename stem as the "mode id" used downstream for joining/ranking
def _pick_mode_stem(path: Path) -> str:
    return path.stem


# Summarize meta fields to verify stability across rows
# - Returns: { key: { value, varies, unique_values[:5] } }
def _summarize_meta(per_row_meta: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    if not per_row_meta:
        for k in META_KEYS:
            # varies=False is expected for stable test conditions; True (API switch, GPU change...etc)
            summary[k] = {"value": None, "varies": False, "unique_values": []}
        return summary

    for k in META_KEYS:
        vals = [r.get(k) for r in per_row_meta if r.get(k) not in (None, "")]
        uniq: List[Any] = []
        seen = set()
        for v in vals:
            sig = (v if isinstance(v, str) else repr(v))
            if sig not in seen:
                seen.add(sig)
                uniq.append(v)

        summary[k] = {
            "value": (uniq[0] if uniq else None),
            "varies": len(uniq) > 1,
            "unique_values": uniq[:5],
        }

    return summary


def parse_ocat_csv(path: Path) -> Dict[str, Any]:
    # 1) Read CSV + locate columns
    headers, rows = _read_csv_simple(path)
    idx = _build_index_exact(headers)

    # 2) Build per-frame series
    # Each list index corresponds to a CSV row/frame record
    series = {k: [] for k in FRAME_KEYS}
    per_row_meta: List[Dict[str, Any]] = []

    for r in rows:
        # per-frame numeric series
        for k in FRAME_KEYS:
            i = idx.get(k, -1)
            v = _coerce_value(k, r[i]) if i >= 0 else None
            series[k].append(v if isinstance(v, (int, float)) else None)

        # meta snapshot for consistency check
        m: Dict[str, Any] = {}
        for k in META_KEYS:
            i = idx.get(k, -1)
            m[k] = _coerce_value(k, r[i]) if i >= 0 else None
        per_row_meta.append(m)

    # 3) Derived series
    # RenderLatency = queue wait + GPU render time
    render_latency: List[Optional[float]] = []
    dl = series.get("MsEstimatedDriverLag", [])
    urc = series.get("MsUntilRenderComplete", [])
    for a, b in zip(dl, urc):
        render_latency.append(
            (a + b) if (isinstance(a, (int, float)) and isinstance(b, (int, float))) else None
        )

    meta_summary = _summarize_meta(per_row_meta)

    out: Dict[str, Any] = {
        "path": str(path),
        "mode": _pick_mode_stem(path),
        "headers": headers,
        "row_count": len(rows),
        # record which chosen columns were found (debug / transparency)
        "chosen_headers": {k: k for k in CHOSEN_COLS if k in idx},
        "series": {
            "MsInPresentAPI": series.get("MsInPresentAPI", []),
            "MsEstimatedDriverLag": series.get("MsEstimatedDriverLag", []),
            "MsUntilRenderComplete": series.get("MsUntilRenderComplete", []),
            "RenderLatency": render_latency,
        },
        "meta_summary": meta_summary,
    }
    if KEEP_RAW_ROWS:
        out["rows"] = rows
    return out


# Batch-load a directory of runs
def load_ocat_dir(ocat_dir_path: str) -> Dict[str, Any]:
    d = Path(ocat_dir_path)
    if not d.exists():
        raise FileNotFoundError(f"OCAT dir not found: {d}")

    files = sorted([p for p in d.glob("*.csv")])
    parsed = [parse_ocat_csv(p) for p in files]
    by_mode = {Path(x["path"]).stem: x for x in parsed}
    return {"dir": str(d), "files": parsed, "by_mode": by_mode}


# --------------------------------------------------------------
# Quick CLI preview
def main():
    data = load_ocat_dir(OCAT_DIR)
    print(f"\nOCAT dir: {data['dir']}")
    print(f"Found {len(data['files'])} logs.\n")

    print("First 3 logs:")
    for i, f in enumerate(data["files"][:3], start=1):
        print(f"[{i}] {Path(f['path']).name}: rows={f['row_count']} mode='{f['mode']}'")
        meta = f.get("meta_summary", {})
        if meta:
            keys = ["Runtime", "SyncInterval", "GPU", "GPU #", "Motherboard", "OS", "Processor", "System RAM"]
            brief = ", ".join([
                f"{k}={meta[k]['value']} ({'varies' if meta[k]['varies'] else 'ok'})"
                for k in keys if k in meta
            ])
            print(f"    meta: {brief}\n")

    log = data["files"][0]
    print(log["mode"], "first 5 records:")
    for i in range(min(5, log["row_count"])):
        record = {k: log["series"][k][i] for k in log["series"]}
        print(f"  Record {i+1}: {record}")


if __name__ == "__main__":
    main()