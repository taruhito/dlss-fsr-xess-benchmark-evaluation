#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Paths
IDLE_CSV = r"C:\Users\vince\Documents\HWiNFO\Clair Obscur Expedition 33\idle\idle.CSV"
SR_DIR   = r"C:\Users\vince\Documents\HWiNFO\Clair Obscur Expedition 33\sr"


def detect_bom_encoding(data: bytes) -> Optional[str]:
    if data.startswith(b"\xEF\xBB\xBF"):
        return "utf-8-sig"
    if data.startswith(b"\xFF\xFE"):
        return "utf-16-le"
    if data.startswith(b"\xFE\xFF"):
        return "utf-16-be"
    return None


def read_text(path: Path) -> Tuple[str, str]:
    data = path.read_bytes()
    enc = detect_bom_encoding(data)
    if enc:
        try:
            return data.decode(enc, errors="strict"), enc
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8", errors="strict"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def pick_delimiter(sample: str) -> str:
    try:
        # csv.Sniffer.sniff expects `delimiters="..."` as a string of candidate chars
        return csv.Sniffer().sniff(sample[:8192], delimiters=",\t;").delimiter
    except Exception:
        # simple fallback
        line = next((ln for ln in sample.splitlines() if ln.strip()), "")
        if line.count(",") >= max(line.count("\t"), line.count(";")):
            return ","
        return "\t" if line.count("\t") >= line.count(";") else ";"


def norm(s: str) -> str:
    return str(s).replace("\ufeff", "").strip().strip('"').strip("'")


def date_time_header(cells: List[str]) -> bool:
    low = [norm(x).lower() for x in cells]
    return any(t in low for t in {"time"}) or any(t in low for t in {"date"})


def find_header_and_rows(text: str, delimiter: str) -> Tuple[List[str], List[List[str]]]:
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    buffer_rows: List[List[str]] = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        if date_time_header(row):
            headers = [norm(h) for h in row]
            rows: List[List[str]] = []
            H = len(headers)

            def is_repeated_header(candidate: List[str]) -> bool:
                return len(candidate) == H and [norm(c) for c in candidate] == headers

            for r in reader:
                if not r or not any(c.strip() for c in r):
                    continue
                if is_repeated_header(r):
                    continue
                if len(r) < H:
                    r = r + [""] * (H - len(r))
                elif len(r) > H:
                    r = r[:H]
                rows.append([str(c) for c in r])
            return headers, rows

        buffer_rows.append(row)

    # Fallback: first non-empty row as header, no data
    for row in buffer_rows:
        if row and any(cell.strip() for cell in row):
            return [norm(h) for h in row], []
    return [], []


def parse_csv_to_dict(path: Path) -> Dict[str, Any]:
    text, enc = read_text(path)
    delim = pick_delimiter(text)
    headers, rows = find_header_and_rows(text, delim)
    return {
        "path": str(path),
        "encoding": enc,
        "delimiter": delim,
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
    }


def load_idle_and_sr(idle_csv_path: str, sr_dir_path: str) -> Dict[str, Any]:
    idle_path = Path(idle_csv_path)
    sr_dir = Path(sr_dir_path)
    if not idle_path.exists():
        raise FileNotFoundError(f"Idle CSV not found: {idle_path}")
    if not sr_dir.exists():
        raise FileNotFoundError(f"SR directory not found: {sr_dir}")

    idle_dict = parse_csv_to_dict(idle_path)
    sr_dicts = [parse_csv_to_dict(p) for p in sorted(sr_dir.glob("*.CSV"))]
    return {"idp": str(idle_path), "srd": str(sr_dir), "idle": idle_dict, "sr": sr_dicts}


def main():
    data = load_idle_and_sr(IDLE_CSV, SR_DIR)
    print(f"\nIdle CSV Path: {data['idp']}\nSR Directory Path: {data['srd']}")
    print(f"\"found {len(data['sr'])} SR logs.\"\n")
    
    idle = data["idle"]
    print("Idle:")
    print(f"- rows={idle['row_count']} cols={len(idle['headers'])} enc={idle['encoding']} delim='{idle['delimiter']}'")
    print("first 10 headers:", idle['headers'][:10])

    print("\nSR:")
    print(f"first row of first SR log: {data['sr'][0]['rows'][0] if data['sr'] and data['sr'][0]['rows'] else 'no data'}")
    print("all SR logs:")
    for sd in data["sr"]:
        print(f"* {Path(sd['path']).name}: rows={sd['row_count']} cols={len(sd['headers'])} enc={sd['encoding']} delim='{sd['delimiter']}'")

    # data['idle']['headers'], data['idle']['rows']
    # for each s in data['sr']: s['headers'], s['rows']


if __name__ == "__main__":
    main()