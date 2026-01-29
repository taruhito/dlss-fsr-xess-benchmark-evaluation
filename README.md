Standardized Benchmarking of Real-Time Super Resolution Upscalers
即時渲染超解析度升頻技術之標準化效能評測

DLSS · FSR · XeSS

Overview / 專案簡介

EN
This repository documents a standardized, reproducible benchmarking methodology for evaluating real-time super resolution (SR) upscaling technologies in modern games.

The study focuses on a comprehensive comparison of:

NVIDIA DLSS

AMD FSR

Intel XeSS

across performance, power efficiency, latency, and image quality, with the goal of providing objective, data-driven guidance for game developers, researchers, and PC gamers.

ZH
本專案建立一套可重複、可驗證、客觀量化的標準化測試流程，用以評估現代遊戲中即時超解析度升頻（Super Resolution, SR）技術之整體表現。

研究對象包含：

NVIDIA DLSS

AMD FSR

Intel XeSS

並從效能、功耗、延遲與畫質等多維度進行系統性比較，提供遊戲開發者、研究者與玩家具實用價值的選型依據。

Objectives / 研究目的

EN

Establish a reproducible benchmarking pipeline for SR evaluation

Define quantitative metrics covering performance, power, latency, and image quality

Systematically compare DLSS, FSR, and XeSS across different game genres

Provide a transparent methodology suitable for replication and peer review

ZH

建立一套可重複執行的 SR 標準化測試流程

定義涵蓋效能、功耗、延遲與畫質的量化評估指標

於不同遊戲類型中系統性比較 DLSS、FSR、XeSS

提供具可驗證性與可審查性的研究方法

Methodology Overview / 測試方法總覽

EN

The benchmarking process consists of four major dimensions:

Hardware utilization & performance
FPS, frame pacing, CPU/GPU/VRAM usage

Power consumption
AC-side system power draw and energy per frame

Latency
Approximate PC latency derived from OCAT telemetry

Image quality (FR-IQA)
Full-reference objective image quality metrics

All measurements are logged, normalized, baseline-corrected, and processed via Python scripts.

ZH

測試流程分為四大評估面向：

效能與硬體資源占用
FPS、frame time、CPU/GPU/VRAM 使用率

功耗表現
全機 AC 端耗電與單影格能耗

延遲分析
以 OCAT 推估之大略個人電腦延遲

畫質評估（FR-IQA）
全參考影像品質指標

所有數據皆經過基線扣除、正規化處理，並由 Python 腳本進行分析與視覺化。

Test Platform / 測試平台
Hardware / 硬體
Component	Specification
Laptop	ASUS ROG Zephyrus G14
CPU	AMD Ryzen 9 7940HS
GPU	NVIDIA GeForce RTX 4080 (12 GB)
Memory	32 GB DDR5
Storage	NVMe PCIe 4.0 SSD
Software / 軟體
Component	Version
OS	Windows 11 Pro
GPU Driver	NVIDIA Game Ready ≥ 580.xx
Graphics API	DirectX 12 / Vulkan
Measurement Tools / 測量工具
Performance & System Metrics

HWiNFO (sensor logging)

RTSS (FPS, 1% / 0.1% low, frame time)

Power Measurement

BENETECH GM89 (AC-side power analyzer)

Latency

OCAT
Approximate PC Latency = Game Latency (partial) + Render Latency

Image Quality

In-game photo mode or NVIDIA App (ALT+F1)

FR-IQA metrics:

PSNR

SSIM

MS-SSIM

LPIPS

DISTS

Test Scenarios / 測試場景

EN

Five modern commercial games supporting DLSS, FSR, and XeSS, covering diverse gameplay requirements:

Low-latency fighting

Open-world resource-intensive

Action

High-FPS shooter

Titles:

Virtua Fighter 5 R.E.V.O.

Clair Obscur: Expedition 33

Ghost of Tsushima – Director’s Cut

S.T.A.L.K.E.R. 2: Heart of Chornobyl

Silent Hill 2

ZH

選擇五款同時支援 DLSS、FSR、XeSS 的商業遊戲，涵蓋：

低延遲需求（格鬥）

高資源負載（開放世界）

動作遊戲

高影格率射擊遊戲

Metrics & Analysis / 評估指標與分析方法
Performance

Average FPS

1% / 0.1% Low FPS

Frame Time & Frame Pacing

Power

Baseline-corrected average wattage

Joules per frame

Latency

Approximate PC Latency (mean)

Render vs game latency decomposition

Image Quality (FR-IQA)
Metric	Interpretation
PSNR	Pixel-level fidelity
SSIM / MS-SSIM	Structural similarity
LPIPS	Perceptual distance (lower is better)
DISTS	Structure & texture similarity
Visualization / 視覺化呈現

Resource utilization rankings

FPS & frame pacing comparisons

Power efficiency (FPS/W)

Latency breakdown charts

Image quality metric rankings

Resource vs FPS scatter plots

All plots are generated programmatically for consistency and reproducibility.

How to Reproduce / 如何重現測試

EN

Prepare hardware and software matching the test platform

Establish idle baseline measurements

Run each resolution × mode × upscaler test for 60 seconds

Capture screenshots following the defined sampling protocol

Process logs and images using provided Python scripts

ZH

準備與測試平台一致的硬體與軟體環境

量測並建立系統閒置狀態基線

依解析度與模式執行 60 秒測試

依規範進行畫面擷取

使用 Python 腳本進行分析與視覺化

Citation / 引用方式
@misc{sr_benchmark_2026,
  title   = {Standardized Benchmarking of Real-Time Super Resolution Upscalers},
  author  = {Vincent Lai},
  year    = {2026},
  note    = {DLSS, FSR, XeSS Comparative Study}
}

License / 授權

This project is intended for research and educational purposes.
Results and methodology may be reused with proper attribution.
