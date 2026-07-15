# Dataset Access (Image Evaluation Frames)

The full raw image dataset used for FR-IQA evaluation is hosted externally due to repository size limits.

## Download Links (Google Drive)

- Raw image dataset (full):  
  https://drive.google.com/drive/folders/16T0uHvjEuWsCARLtAg0KymsZt38cAcK2?usp=sharing
- Processed/clean subset:  
  - Virtua Fighter 5 R.E.V.O: https://drive.google.com/drive/folders/1tcfds0fB_JuB-1wxVqyN8JE-lB_zDDhP?usp=sharing
  - Clair Obscur Expedition 33: https://drive.google.com/drive/folders/1asrbhxaZQ5-yU0_ZnJG5CT8dygDOyVLK?usp=sharing
  - Ghost of Tsushima: https://drive.google.com/drive/folders/1Ss1E0NMSeUQAu2T1PZi98RoI--BWzNp_?usp=sharing
  - S.T.A.L.K.E.R. 2 Heart of Chornobyl: https://drive.google.com/drive/folders/1XnFY4nslNRA4UwxGWICp6WEGQQHCD5Px?usp=sharing
  - Silent Hill 2: https://drive.google.com/drive/folders/1qRfPzLK3AUwoPsKAuDPGmPf9wNZ7_YD9?usp=sharing  
  
## Notes

- This repository does **not** track full raw image files in Git.
- Please download and extract into suggested directory layout.

## Suggested Local Structure

```text
root/
├─ 1080p/
│  ├─ native/
│  │  ├─ frame1/ cap01.png ... cap10.png
│  │  ├─ frame2/ ...
│  │  └─ ...
│  └─ sr/
│     ├─ dlss/
│     │  ├─ frame1/ cap01.png cap02.png cap03.png
│     │  └─ ...
│     ├─ fsr/
│     │  └─ ...
│     └─ ...
└─ 2.5k/
   └─ ...
```

## Version

- Dataset version: `v1.0`  
- Last updated: `2026-06-30`
