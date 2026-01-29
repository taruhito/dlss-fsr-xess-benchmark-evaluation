#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pairwise FR-IQA comparison between two SR modes (SR vs SR), per frame.

Purpose
-------
This helper is intentionally "one-off friendly":
- Compare two SR mode folders (A vs B) for the same resolution.
- Use per-frame median images (robust to capture noise) then compute FR metrics.

Directory layout (expected)
---------------------------
ROOT/
  {RESOLUTION}/
    sr/
      {MODE_A}/
        frame1/ cap01.png cap02.png ...
        frame2/ ...
      {MODE_B}/
        frame1/ ...
        frame2/ ...

How it computes scores
----------------------
For each matched frame index:
  1) Build per-frame median images:
        A_med = median(captures in MODE_A/frameN)
        B_med = median(captures in MODE_B/frameN)
  2) Compute FR metrics using pyiqa:
        psnr, ssim, ms_ssim, lpips, dists

Output
------
- ./res_out/pairwise_sr_vs_sr.csv
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from PIL import Image

import torch
import torch.nn.functional as F
import pyiqa

# ----------------------- Config (edit here) --------------------------
ROOT = Path(r"C:\Users\vince\Videos\Virtua Fighter 5 R.E.V.O")
RESOLUTION = "2.5k"                    # "2.5k" or "1080p"
BASE = "FSR3.1.2_UltraPerformance"     # base sr mode name WITHOUT mode suffix
A_SUFFIX = "Base"                 # compare A vs B
B_SUFFIX = "Reflex"                  # "ReflexOn" or "ReflexBoost"
DEVICE = "cuda:0"                      # "cpu", "cuda", "cuda:0"
METRICS = ["psnr", "ssim", "ms_ssim", "lpips", "dists"]
DOWNSAMPLE = 1                         # 1=none, 2=half, 4=quarter...
OUT_CSV = Path("./res_out/pairwise_sr_vs_sr.csv")
# --------------------------------------------------------------------

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS


def natural_key(s: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def find_dir_ci(base: Path, names: List[str]) -> Optional[Path]:
    if not base.exists():
        return None
    mapping = {p.name.lower(): p for p in base.iterdir() if p.is_dir()}
    for n in names:
        if n.lower() in mapping:
            return mapping[n.lower()]
    return None


def list_frames(parent: Path) -> List[Path]:
    if not parent or not parent.exists():
        return []
    frames = [d for d in parent.iterdir() if d.is_dir()]

    def frame_sort_key(p: Path):
        nm = p.name.lower()
        if nm.startswith("frame"):
            idx = "".join(ch for ch in nm if ch.isdigit())
            try:
                return (0, int(idx))
            except Exception:
                return (0, 1_000_000)
        return (1, natural_key(p.name))

    frames.sort(key=frame_sort_key)
    return frames


def list_images_sorted(d: Path) -> List[Path]:
    imgs = [p for p in d.iterdir() if is_image_file(p)]
    imgs.sort(key=lambda p: natural_key(p.name))
    return imgs


# Load multiple captures as a normalized float32 stack: [N, H, W, C] in [0..1].
def load_stack_numpy(img_paths: List[Path]) -> np.ndarray:
    if not img_paths:
        raise ValueError("No images to load.")
    arrs = []
    size = None
    for p in img_paths:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        if size is None:
            size = im.size
        elif im.size != size:
            raise ValueError(f"Image size mismatch in {p}: expected {size}, got {im.size}")
        arrs.append(np.asarray(im).astype(np.float32) / 255.0)
    return np.stack(arrs, axis=0)


def median_image_numpy(img_paths: List[Path]) -> np.ndarray:
    stk = load_stack_numpy(img_paths)
    med = np.median(stk, axis=0)
    return med.astype(np.float32)


def to_tensor_4d(arr_hwC: np.ndarray, device: torch.device) -> torch.Tensor:
    return torch.from_numpy(arr_hwC).permute(2, 0, 1).unsqueeze(0).to(device)


# Downsample both inputs with area mode (deterministic and robust for small shifts).
def area_downsample(x: torch.Tensor, factor: int) -> torch.Tensor:
    if factor <= 1:
        return x
    h, w = x.shape[-2:]
    return F.interpolate(
        x,
        size=(max(1, h // factor), max(1, w // factor)),
        mode="area",
        align_corners=None
    )


class FR:
    def __init__(self, names: List[str], device: str):
        # Keep behavior: if CUDA requested but unavailable, fall back to CPU.
        if str(device).startswith("cuda") and not torch.cuda.is_available():
            print(f"WARNING: Requested device '{device}' but CUDA not available; using CPU.")
            device = "cpu"
        self.device = torch.device(device)
        name_map = {
            "psnr": "psnr",
            "ssim": "ssim",
            "ms_ssim": "ms_ssim",
            "lpips": "lpips",
            "dists": "dists",
        }
        self.metrics = {n: pyiqa.create_metric(name_map[n], device=self.device) for n in names}

    @torch.inference_mode()
    def score(self, name: str, a: torch.Tensor, b: torch.Tensor) -> float:
        return float(self.metrics[name](a, b).flatten().item())


def main():
    res_dir = ROOT / RESOLUTION
    if not res_dir.exists():
        raise SystemExit(f"Resolution dir not found: {res_dir}")

    sr_root = find_dir_ci(res_dir, ["sr", "SR"])
    if sr_root is None:
        raise SystemExit(f"No sr/ folder under {res_dir}")

    # The two modes to compare. This helper assumes a naming convention:
    #   {BASE}_{Base|ReflexOn|ReflexBoost}
    mode_a = sr_root / f"{BASE}_{A_SUFFIX}"
    mode_b = sr_root / f"{BASE}_{B_SUFFIX}"
    if not mode_a.exists() or not mode_b.exists():
        raise SystemExit(f"Missing mode dirs: {mode_a} or {mode_b}")

    if str(DEVICE).startswith("cuda") and torch.cuda.is_available():
        print("CUDA:", torch.cuda.get_device_name(0))
    print(f"[PAIRWISE] root={ROOT} res={RESOLUTION} base={BASE} A={A_SUFFIX} B={B_SUFFIX} device={DEVICE} metrics={METRICS} downsample={DOWNSAMPLE}")

    fr = FR(METRICS, DEVICE)

    frames_a = list_frames(mode_a)
    frames_b = list_frames(mode_b)
    num_frames = min(len(frames_a), len(frames_b))
    if num_frames == 0:
        raise SystemExit("No frame folders to compare.")

    rows: List[Dict[str, float]] = []
    for i in range(num_frames):
        imgs_a = list_images_sorted(frames_a[i])
        imgs_b = list_images_sorted(frames_b[i])
        if not imgs_a or not imgs_b:
            continue

        a_med = median_image_numpy(imgs_a)
        b_med = median_image_numpy(imgs_b)
        if a_med.shape != b_med.shape:
            print(f"WARNING: size mismatch at frame {i+1}: A{a_med.shape} vs B{b_med.shape}; skipping frame.")
            continue

        A = to_tensor_4d(a_med, fr.device)
        B = to_tensor_4d(b_med, fr.device)
        if DOWNSAMPLE > 1:
            A = area_downsample(A, DOWNSAMPLE)
            B = area_downsample(B, DOWNSAMPLE)

        rec: Dict[str, float] = {"frame": i + 1}
        for m in METRICS:
            rec[m] = fr.score(m, A, B)
        rows.append(rec)

    if not rows:
        raise SystemExit("No frames scored (after filtering).")

    df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Wrote: {OUT_CSV}")

    # Keep console summary identical in meaning: show mean metric values.
    metrics = ["psnr", "ssim", "ms_ssim", "lpips", "dists"]
    print(df[metrics].mean().to_frame("mean"))
    print("\nInterpretation: psnr/ssim/ms_ssim higher = A closer to B; lpips/dists lower = A closer to B.")


if __name__ == "__main__":
    main()