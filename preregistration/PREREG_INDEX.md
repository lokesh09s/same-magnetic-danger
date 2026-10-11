# Pre-registration index

Each row is a decision-log entry that fixed a design, test or reading before the data it governs were computed or
read.
- **Date** is the entry's own date.
- **Commit** is the project-repository commit that first added the entry, with that commit's time (author time
  zone).
- **Line** is the entry's heading line in `decisions.md` (this copy keeps the original line numbers).

The hashes come from the project repository's git history (`git log` of `decisions.md`). Many are also cited inside
`decisions.md`. The git history itself is not part of this release; `COMMIT_HISTORY.md` (top level) lists every commit with its full
hash, time and message.

## Gate, labels, split and frozen models (development data only)

| Date | Commit | Line | Entry |
|---|---|---|---|
| 2026-09-21 | eecc96f (13:26) | 525 | Decision N2: model selection by grouped CV, before any model is trained |
| 2026-09-21 | 5beac0a (14:19) | 548 | N2 details; decisions O, Q, R, before any model is trained |
| 2026-09-21 | b423ca4 (15:27) | 774 | Decision S amended, before any model |
| 2026-09-21 | afa4d17 (15:39) | 814 | Decision K2: true irradiance scale for labels, before any results |
| 2026-09-21 | 4d83691 (17:12), ca53f8b (17:14) | – | `frozen/frozen_spec.json` created, then final (SHA-256 1d205068…; Stage 5 prediction rule approved before the held-out test) |
| 2026-09-21 | 08c474f (17:31) | 1714 | Confirmation-set decisions, before any 2025+ data are fetched |
| 2026-09-21 | e3e4075 (19:41) | 1759 | Confirmation set frozen |

## EUV (AIA 94 Å) study

| Date | Commit | Line | Entry |
|---|---|---|---|
| 2026-09-23 | fbfa4d9 | 2458 | Combined EUV test |
| 2026-09-23 | 36bfee3 | 2791 | Amendment: full EUV study, 94 Å only, before any full-study download |
| 2026-09-24 | 3283478 | 3072 | Step 6 pre-registration, before any ΔCV is split by label |
| 2026-09-25 | 85c8285 | 3238 | Phase X: spatial 94 Å measures |
| 2026-09-25 | f3d6489 | 3706 | Held-out tests (2021/23/24) |
| 2026-09-26 | 8420876 | 3834 | Held-out replication of F2 (CV_box twins), before computing |
| 2026-09-26 | d95e147 | 4129 | 2025–26 confirmation set: download and label-blind computation only |
| 2026-09-26 | 749208e | 4228 | **Pre-registration of the 2025–26 confirmation (TEST 1, TEST 2)**, before any 2025–26 label is used |
| 2026-09-26 | 338c0aa | 4361 | EUV-unseen follow-up validation: CV_box as a false-alarm filter |
| 2026-09-27 | 25fcd66 | 4788 | 2025–26 re-test: CV_box as a filter on top of model C (already-analysed data) |

## Prospective test (Look 1 and Look 2)

| Date | Commit | Line | Entry |
|---|---|---|---|
| 2026-09-27 | 2f62f88 | 5191 | Prospective pre-registration: bursty fraction (BF) and late-window restlessness (CV6) |
| 2026-09-27 | eb3e7d5 | 5370 | BF definition (option a) and amended prospective test, label-blind |
| 2026-09-27 | 9a88d70 | 5445 | Amendment: secondary model COMBO-T |
| 2026-09-28 | 8aa1797 | 5493 | C+ protection rule as the only confirmatory false-alarm system (designed post hoc; see `AI_USE.md`); Look 2 definition (line 5500) |
| 2026-09-28 | 784b1a8 | 5546 | Clarification: C+ thresholds are the exact frozen values |
| 2026-10-05 | b480d22 | 6625 | Prospective test and Look 2: disclosure and amendment, before any prospective data are used |
| 2026-10-05 | 5a6d106 | 6845 | Amendment: dependence-free CV_box twins secondary |
| 2026-10-09 | daff479 | 7142 | Look 1 runs early: amendment of run date and end date only (E = 2026-09-03 23:00 TAI), before any prospective download |
| 2026-10-10 | 7d9be38 | 7212 | Look 1 analysis code and open choices D1–D11, committed before any Look 1 label is read |

## Exploratory development-data candidates (pre-registered designs, dev 2010–2019 only)

| Date | Commit | Line | Entry |
|---|---|---|---|
| 2026-09-30 | d85e8dc | 5821 | Candidate #25: AIA 1600 Å UV brightening area (UVA) |
| 2026-09-30 | 46207c7 | 5920 | Candidate #26: magnetic restlessness (MR) |
| 2026-09-30 | 16569b6 | 6116 | Candidate #27: MiniRocket on the 94 Å light curve (MRKT) |
| 2026-09-30 | fdf044d | 6267 | Candidate #28: small 1D-CNN on the 94 Å light curve (CNN1D) |
| 2026-09-30 | b3b0c3a | 6397 | Candidate #29: flicker + brightness level (FBL) |

Later amendments to each candidate (checkpoint answers, Step 2 go-aheads) follow its entry in `decisions.md`.
`LOOK1_RUN_SHEET.md` and `LOOK1_ANALYSIS_DECISIONS.md` are the Look 1 run sheet and the D1–D11 choices recorded in
the 2026-10-10 entry.
