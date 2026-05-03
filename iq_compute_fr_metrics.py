#!/usr/bin/env python3

"""
Full-reference IQA for SR vs Native using per-frame median images

 Directory layout (example):
root/
  1080p/
    native/
      frame1/ cap01.png ... cap10.png
      frame2/ ...
    sr/
      dlss/
        frame1/ cap01.png cap02.png cap03.png
      fsr/
      xess/

FR-IQA Native vs SR (PSNR, SSIM/MS‑SSIM, LPIPS, DISTS)
- FR uses native as the reference directly, so the output is an absolute similarity/distance to native per frame.

What the script computes
- For each frame index:
    Build per‑frame median images
      - nat_med = median(native caps for that frame)
      - sr_med = median(SR caps for that frame)
    Optional area downsample both by the same factor (to reduce tiny misalignments).
    
    Compute FR metrics between sr_med (upscaled) and nat_med (ref) using pyiqa:
      - PSNR: 10 * log10(MAX^2 / MSE(upscaled, ref)), MAX = 255, higher is better.
      - SSIM: structural similarity in [0,1], higher is better.
      - MS-SSIM: multi‑scale SSIM [0,1], higher is better.
      - LPIPS: learned perceptual distance in feature space [0,1], lower is better.
      - DISTS: deep structure/texture distance [0,1], lower is better.
    Per metric, average the per‑frame scores to get mean_score.

Output
    - CSV file with columns: resolution, mode, metric, num_frames, mean_score, frame1_score, frame2_score, frame3_score
    - rows are ordered by: resolution -> metric (declared order) -> SR mode (natural order)
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from PIL import Image

# ----------------------- Config --------------------------
DEFAULT_ROOT = r"C:\Users\vince\Videos\Silent Hill 2"
DEFAULT_DEVICE = "cuda:0"   # "cpu", "cuda", "cuda:0"
DEFAULT_FR_METRICS = ["psnr", "ssim", "ms_ssim", "lpips", "dists"]
DEFAULT_DOWNSAMPLE = 1  # 1=none, 2=half, 4=quarter...
DEFAULT_VERBOSE = False # True to enable verbose prints that help debug missing folders/images
OUT_DIR = Path("./sh2_res_out")
# --------------------------------------------------------


# -----------------------
# Optional imports with friendly errors
# -----------------------
try:
    import torch
    import torch.nn.functional as F
except Exception as e:
    print("Error importing PyTorch. Install from https://pytorch.org/", file=sys.stderr)
    print(f"Underlying error: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import pyiqa
except Exception as e:
    print("Error: pyiqa not installed. Install with:\n  pip install pyiqa pillow numpy pandas tqdm", file=sys.stderr)
    print(f"Underlying error: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm   # type: ignore[assignment]
except Exception:
    # Fallback: tqdm is optional; if missing, iterate normally.
    def tqdm(x, **kwargs):
        return x


# -----------------------
# File / path helpers
# -----------------------
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS


def natural_key(s: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# Case-insensitive directory lookup: find "native" vs "Native", "sr" vs "SR", etc.
def find_dir_ci(base: Path, names: List[str]) -> Optional[Path]:
    if not base.exists():
        return None
    mapping = {p.name.lower(): p for p in base.iterdir() if p.is_dir()}
    for n in names:
        if n.lower() in mapping:
            return mapping[n.lower()]
    return None


# Frame ordering:
#   "frame1", "frame2", ... first; then natural sort fallback.
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


# Sort capture filenames naturally: cap01.png, cap02.png, cap10.png, ...
def list_images_sorted(d: Path) -> List[Path]:
    imgs = [p for p in d.iterdir() if is_image_file(p)]
    imgs.sort(key=lambda p: natural_key(p.name))
    return imgs


# -----------------------
# Image loading / median
# -----------------------
# Load N RGB images, normalize to float32 [0..1], return stack [N,H,W,C].
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


# Median is used for robustness against capture noise/outliers.
def median_image_numpy(img_paths: List[Path]) -> np.ndarray:
    stk = load_stack_numpy(img_paths)
    med = np.median(stk, axis=0)
    return med.astype(np.float32)


def to_tensor_4d(arr_hwC: np.ndarray, device: torch.device) -> torch.Tensor:
    return torch.from_numpy(arr_hwC).permute(2, 0, 1).unsqueeze(0).to(device)


# Optional downsample to reduce sensitivity to tiny alignment differences.
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


# -----------------------
# FR metric wrapper
# -----------------------
class FRMetrics:
    def __init__(self, names: List[str], device: str):
        # Keep behavior: if CUDA requested but unavailable, fall back to CPU.
        if str(device).startswith("cuda") and not torch.cuda.is_available():
            print(f"WARNING: Requested device '{device}' but CUDA not available; using CPU.", file=sys.stderr)
            device = "cpu"

        self.device = torch.device(device)

        # pyiqa metric IDs
        name_map = {
            "psnr": "psnr",
            "ssim": "ssim",
            "ms_ssim": "ms_ssim",
            "lpips": "lpips",
            "lpips-vgg": "lpips-vgg",
            "lpips-alex": "lpips-alex",
            "dists": "dists",
        }

        supported = set(name_map.keys())
        unknown = set(names) - supported
        if unknown:
            raise ValueError(f"Unknown FR metrics: {unknown}. Supported: {sorted(supported)}")

        self.metrics = {n: pyiqa.create_metric(name_map[n], device=self.device) for n in names}

    @torch.inference_mode()
    def score(self, name: str, upscaled: torch.Tensor, ref: torch.Tensor) -> float:
        return float(self.metrics[name](upscaled, ref).flatten().item())


# Compute per-frame median images + per-frame FR metric scores for one SR mode directory.
def compute_fr_for_mode(
    mode_dir: Path,
    native_frames: List[Path],
    fr: FRMetrics,
    fr_metric_names: List[str],
    downsample: int,
) -> Dict[str, Dict]:
    sr_frames = list_frames(mode_dir)
    if not sr_frames:
        return {}

    # Compare only frames that exist in both trees.
    num_frames = min(len(sr_frames), len(native_frames))
    if num_frames == 0:
        return {}

    out: Dict[str, Dict] = {n: {"frame_scores": []} for n in fr_metric_names}

    for fi in range(num_frames):
        nat_imgs = list_images_sorted(native_frames[fi])
        sr_imgs = list_images_sorted(sr_frames[fi])
        if not nat_imgs or not sr_imgs:
            continue

        nat_med = median_image_numpy(nat_imgs)
        sr_med = median_image_numpy(sr_imgs)

        # FR metrics require same spatial shape (H,W,C).
        if nat_med.shape != sr_med.shape:
            print(
                f"WARNING: Size mismatch in {mode_dir.name} frame {fi+1}: "
                f"native {nat_med.shape[:2]} vs sr {sr_med.shape[:2]} -> skipping frame.",
                file=sys.stderr
            )
            continue

        ref_t = to_tensor_4d(nat_med, fr.device)
        upscaled_t = to_tensor_4d(sr_med, fr.device)

        if downsample > 1:
            ref_t = area_downsample(ref_t, downsample)
            upscaled_t = area_downsample(upscaled_t, downsample)

        for n in fr_metric_names:
            out[n]["frame_scores"].append(fr.score(n, upscaled_t, ref_t))

    # Summarize per-metric mean + frame count.
    for n in fr_metric_names:
        fs = out[n]["frame_scores"]
        if fs:
            out[n]["mean_score"] = float(np.mean(fs))
            out[n]["num_frames"] = len(fs)
        else:
            out[n]["mean_score"] = float("nan")
            out[n]["num_frames"] = 0

    return out


def main():
    root_str = DEFAULT_ROOT
    out_csv = OUT_DIR / "fr_scores.csv"
    device = DEFAULT_DEVICE
    fr_metrics = list(DEFAULT_FR_METRICS)
    downsample = DEFAULT_DOWNSAMPLE
    verbose = DEFAULT_VERBOSE

    root = Path(root_str)
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    if torch.cuda.is_available():
        print("CUDA available on:", torch.cuda.get_device_name(0))
    else:
        print("Running on CPU.")

    print(f"[FR] root={root} out={out_csv} device={device} metrics={fr_metrics} downsample={downsample}")

    fr = FRMetrics(fr_metrics, device)

    # Resolutions in natural order (e.g. 1080p, 2.5k, ...)
    resolutions = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda p: natural_key(p.name))

    rows = []
    for res_dir in resolutions:
        res_name = res_dir.name

        native_dir = find_dir_ci(res_dir, ["native"])
        sr_root = find_dir_ci(res_dir, ["sr", "SR"])
        if native_dir is None or sr_root is None:
            if verbose:
                print(f"Skip {res_name}: missing native or sr folder", file=sys.stderr)
            continue

        native_frames = list_frames(native_dir)
        if not native_frames:
            if verbose:
                print(f"Skip {res_name}: no native frames", file=sys.stderr)
            continue

        # SR modes in natural order (folder name is the mode id).
        sr_modes = sorted([d for d in sr_root.iterdir() if d.is_dir()], key=lambda p: natural_key(p.name))

        for mode_order, mode_dir in enumerate(tqdm(sr_modes, desc=f"{res_name} modes")):
            per_metric = compute_fr_for_mode(mode_dir, native_frames, fr, fr_metrics, downsample)

            for mname, data in per_metric.items():
                if data.get("num_frames", 0) == 0:
                    continue

                # NOTE: helper columns mode_order/metric_order are used only for sorting.
                row = {
                    "resolution": res_name,
                    "mode": mode_dir.name,
                    "metric": mname,
                    "num_frames": data["num_frames"],
                    "mean_score": data["mean_score"],
                    "mode_order": mode_order,
                    "metric_order": fr_metrics.index(mname),
                }

                # Add per-frame scores as frame1_score, frame2_score, ...
                fs = data["frame_scores"]
                for i in range(len(fs)):
                    row[f"frame{i+1}_score"] = fs[i]

                rows.append(row)

    if not rows:
        raise SystemExit("No FR metrics computed. Check directory structure and images.")

    df = pd.DataFrame(rows)

    # Desired ordering: resolution -> metric (input order) -> mode (natural order)
    df = df.sort_values(by=["resolution", "metric_order", "mode_order"])

    # Drop helper columns for output (keep only stable public columns).
    df_to_save = df.drop(columns=["mode_order", "metric_order"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_to_save.to_csv(out_csv, index=False)
    print(f"Wrote FR results to {out_csv}")

    # Console summaries: per resolution + metric, print modes in the same order as CSV.
    for (res, metric), g in df.groupby(["resolution", "metric"], sort=False):
        print(f"\n=== FR Summary: resolution={res}, metric={metric} ===")
        g_sorted = g.sort_values(by="mode_order")
        for _, row in g_sorted.iterrows():
            mode = row["mode"]
            ms = row["mean_score"]

            parts = []
            for i in range(1, 4):
                sc = row.get(f"frame{i}_score", None)
                if pd.notna(sc):
                    parts.append(f"{sc:.4f}")
            frames_str = ", ".join(parts)

            print(f"- {mode:30s} mean={ms:.4f} frames=[{frames_str}]")


if __name__ == "__main__":
    main()