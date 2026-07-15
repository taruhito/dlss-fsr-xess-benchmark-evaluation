# SR_Project  
**A Reproducible Benchmarking Framework for Gaming Upscalers (DLSS / FSR / XeSS)**

> Master’s thesis implementation and experiment pipeline for evaluating real-time rendering upscaling technologies across **hardware utilization**, **power consumption**, **latency**, and **image quality**.

---

## 📌 Overview

Modern games must balance visual quality and performance (FPS + latency), especially at higher resolutions and heavier rendering workloads.  
This project implements a **repeatable, quantifiable, cross-condition benchmarking workflow** to evaluate three major upscalers:

- **NVIDIA DLSS**
- **AMD FSR** (including older and newer variants depending on game support)
- **Intel XeSS**

The framework standardizes testing under:
- different games,
- multiple resolutions,
- multiple upscaling modes (Quality / Balanced / Performance),
- optional extra modes (e.g., Reflex / Frame Generation).

---

## 🎯 Research Goals

This repository supports the thesis goal of building a benchmark process that is:

- **Repeatable** (standardized step-by-step procedure),
- **Quantifiable** (metric-driven ranking and aggregation),
- **Cross-condition comparable** (across game types, modes, and resolutions).

Core evaluation dimensions:

1. **Hardware layer**  
   CPU/GPU power, utilization, FPS behavior, frame timing.
2. **Power layer**  
   Real AC-side system power measured by external meter.
3. **Latency layer**  
   Approximate PC latency built from OCAT-derived timing fields.
4. **Image quality layer**  
   FR-IQA metrics (PSNR, SSIM, MS-SSIM, LPIPS, DISTS) with frame preprocessing.

---

## 🧪 Benchmark Scope

### Games (thesis experiments)
- Virtua Fighter 5 R.E.V.O.
- Clair Obscur: Expedition 33
- Ghost of Tsushima Director’s Cut
- S.T.A.L.K.E.R. 2: Heart of Chornobyl
- Silent Hill 2

### Resolutions
- **1080p** (1920×1080)
- **2.5K** (2560×1600)

### Upscaling modes
For each supported upscaler per game:
- Quality
- Balanced
- Performance
- (AA-native-like baseline where available, or DLAA substitute where needed)

### Extra optional modes (game-dependent)
- NVIDIA Reflex / Reflex Boost
- DLSS Frame Generation
- FSR Frame Generation
- Other game-exposed low-latency / FG toggles

---

## 🧱 Methodology Highlights

### 1) Two-phase benchmark design
- **Phase A: Idle baseline definition**
  - Reboot system, minimize noise/background load.
  - Record baseline hardware/power traces.
- **Phase B: Actual benchmark runs**
  - Fixed recording windows (typically 60s),
  - standardized in-game paths or replay logic,
  - repeated frame capture and validation.

### 2) Noise control
- Baseline subtraction for hardware/power signals,
- controlled sampling windows,
- consistency checks (API/sync/device metadata),
- robust aggregation (median where appropriate).

### 3) Image-quality preprocessing
- Multi-capture same-scene sampling,
- RGB float normalization,
- per-scene median compositing before FR-IQA scoring.

---

## 📊 Metrics Summary

### Hardware
- Core signals: CPU/GPU power, usage, memory/controller usage, FPS, 1%/0.1% lows, frame time.
- Composite ranking for:
  - resource occupancy,
  - FPS performance,
  - overall hardware efficiency (FPS per power-related composite).

### Power
- AC-meter sampled watt traces.
- Rankings for:
  - actual average power draw,
  - joules per frame (energy efficiency).

### Latency
- Approximate PC latency from OCAT-derived timing fields:
  - present/API waiting part,
  - driver queue lag,
  - render complete timing.
- Consistency validation from runtime/system metadata.

### Image Quality
- FR-IQA:
  - **PSNR**
  - **SSIM**
  - **MS-SSIM**
  - **LPIPS**
  - **DISTS**
- Also includes extra-mode suitability comparisons (enabled vs baseline).

---

## 🖥️ Experiment Environment (Thesis)

### Hardware
- ASUS ROG Zephyrus G14
- AMD Ryzen 9 7940HS
- NVIDIA GeForce RTX 4080 12GB
- 32GB DDR5
- NVMe SSD

### Software
- Windows 11 Pro (64-bit)
- NVIDIA Game Ready Driver (580.xx+ during experiment period)
- DirectX 12 game runtime context

### Measurement tools
- HWiNFO + RTSS (hardware/FPS logging)
- OCAT (latency-related data capture)
- BENETECH GM89 (external AC power measurement)
- In-game photo mode / Steam screenshot for IQA frames

---

## 🚀 How to Use This Repo

> Update this section according to your script names if needed.

1. **Prepare environment**
   - Install Python dependencies (`requirements.txt` if provided).
   - Ensure logging tools are configured (HWiNFO/RTSS/OCAT).
2. **Collect raw logs**
   - Run benchmark sessions per game/resolution/mode.
   - Export hardware/power/latency logs and captured frames.
3. **Run processing scripts**
   - Parse raw logs,
   - apply baseline correction and aggregation,
   - compute rankings and FR-IQA metrics.
4. **Generate outputs**
   - Tables/CSV summaries,
   - charts and suitability comparisons,
   - per-game and cross-game conclusions.

---

## 🔁 Reproducibility Notes

To maximize repeatability:
- keep fixed system power mode,
- control background tasks,
- use fixed test windows and scene logic,
- validate completeness of every capture,
- rerun or discard incomplete/abnormal samples,
- document version drift (OS/driver/game) if unavoidable.

---

## 🧠 Key Findings (High-level)

Across tested games, no single upscaler dominates every condition.  
Performance depends strongly on:
- game engine characteristics,
- CPU/GPU bottleneck profile,
- selected upscaling mode,
- extra feature interactions (Reflex/FG),
- target objective (quality vs FPS vs latency vs energy).

In many scenarios:
- **DLSS** shows strong overall image quality and balanced system performance,
- **FSR** can offer scenario-dependent efficiency/performance advantages,
- **XeSS** often provides competitive quality but may incur higher resource cost in some conditions.

---

## 📚 Citation

If you use this repository, please cite the thesis work:

```bibtex
@mastersthesis{SR_Upscalers_thesis_2026,
  title   = {The Three Most Representative SR Upscalers: DLSS, FSR, and XeSS for Real-Time Game Rendering --- Benchmark Design, Evaluation Methods, and Testing Results},
  author  = {Vincent Lai},
  school  = {National Taipei University of Education},
  year    = {2026},
  type    = {Master's thesis},
  address = {Taipei, Taiwan}
}
```

---

## License

This repository uses a dual-license model:

- **Code** (e.g., scripts, source files, configs): licensed under **MIT**.  
  See [LICENSE-CODE](https://github.com/taruhito/dlss-fsr-xess-benchmark-evaluation/blob//main/LICENSE-CODE)
- **Non-code content** (e.g., thesis text, figures, benchmark datasets/results, documentation): licensed under **CC BY 4.0**.  
  See [LICENSE-CONTENT](https://github.com/taruhito/dlss-fsr-xess-benchmark-evaluation/blob/main/LICENSE-CONTENT)

If a file or subdirectory includes its own license notice, that specific notice takes precedence for that content.

---

## 🙏 Acknowledgements

Thanks to all advisors, committee members, and lab peers who supported the research design, validation process, and thesis completion.
