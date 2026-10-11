# Manifest

Every file in this release, with one line on what it is. Per-episode JSON folders are listed as one line each (count and dates).
Original paths and every edit are in `CHANGES.md`.

## Top level

- `README.md` — what the project is, the pipeline in order, how to reproduce each main number, data sources, limits
- `LICENSE` — MIT license for the whole repository (quoted third-party excerpts excepted; see README, License)
- `CITATION.cff` — how to cite
- `AI_USE.md` — AI-use disclosure
- `CHANGES.md` — every edit made for the release (file, line, before → after, why), renames, new files
- `MANIFEST.md` — this file
- `COMMIT_HISTORY.md` — all 283 commits of the project repository: full hash, time and message (the hashes cited in decisions.md)
- `requirements.txt` — pinned core packages (Python 3.12)
- `requirements-extra.txt` — torch, sktime, threadpoolctl: only for scripts/09_cnn1d.py and src/minirocket.py
- `.gitignore` — keeps data/, environments, caches and re-run logs out of git

## src/ (modules imported by other code; original names)

- `src/chunks.py` — The monthly chunk list, shared by run_all.py and every report that reads chunk files.
- `src/cohort.py` — Alarm cohort construction (STAGE 3 on dev; the SAME functions are used for test in STAGE 5).
- `src/descriptive_aia94.py` — DESCRIPTIVE AIA 94 A FOLLOW-UPS (decisions.md 2026-09-27, 947e4c0). EXPLORATORY / DESCRIPTIVE ONLY — post-hoc, not
- `src/diag_ablation.py` — DIAGNOSTIC ABLATION (user, pre-declared diagnostic). Dev 2010-2019 only; test HARPs never loaded.
- `src/diag_d7_catalogue.py` — D7 catalogue check (diagnostic): would NCEI's GOES XRS report (flare locations) recover the 121 flares lost to the
- `src/euv_confirm_retest.py` — 2025-26 RE-TEST: CV_box as a filter on top of model C (decisions.md 2026-09-27, 25fcd66). Frozen euv_extra models only.
- `src/euv_confirm_tests.py` — 2025-26 CONFIRMATION TESTS (decisions.md 2026-09-26 pre-registration). RUN ONCE.
- `src/euv_dctrl.py` — D-CTRL metric (decisions.md 2026-09-22, user definition recorded verbatim; implementation details same date).
- `src/euv_download.py` — EUV pilot downloads (decisions: EUV PILOT DOWNLOAD). JSOC export only (the approved fallback is not implemented here).
- `src/euv_extra.py` — EUV-UNSEEN FOLLOW-UP VALIDATION — CV_box as a false-alarm filter (decisions.md 2026-09-26, 338c0aa / 8cace14).
- `src/euv_f2_replication.py` — HELD-OUT REPLICATION OF F2 (decisions.md 2026-09-26; added after the held-out R4a result 7438177). Run ONCE.
- `src/euv_full.py` — FULL EUV STUDY, 94 A only (decisions.md 2026-09-23 amendment). Outputs only under data/euv_full/.
- `src/euv_heldout.py` — HELD-OUT EUV TESTS (decisions.md 2026-09-25 pre-registration f3d6489; ΔCV design 3283478 item 1h).
- `src/euv_pilot.py` — EUV PILOT (exploratory; dev data 2010-2019 only). Primary measure: PIL-localised EUV variability at 12-min cadence,
- `src/euv_run.py` — EUV pilot run (items 2-4): register, saturation cut, mask reprojection, P2 exclusion, P1/P5 metrics, overlays.
- `src/euv_spatial.py` — PHASE X (decisions.md 2026-09-25 pre-registration) -- EXPLORATORY on dev. Spatial 94 A measures from the files on disk:
- `src/euv_test_download.py` — HELD-OUT EUV TEST -- DOWNLOAD AND VERIFY ONLY (decisions.md 2026-09-25; design 3283478 item 1h). Nothing is computed on
- `src/flares.py` — SWPC flare catalogue from HEK, shared by build_dataset.py and checks.py.
- `src/goes_xrs.py` — GOES XRS 1-8 A daily maximum (1-minute science data, NOAA primary satellite) for the days
- `src/join_report.py` — Per-year M1+ flare -> HARP join diagnostics.
- `src/mag_restless.py` — Candidate #26 MAGNETIC RESTLESSNESS (MR) -- decisions.md 2026-09-30 (46207c7, amendment b2ca7ac). EXPLORATORY (dev).
- `src/minirocket.py` — Candidate #27 MINIROCKET ON THE 94 A LIGHT CURVE (MRKT) -- decisions.md 2026-09-30 (16569b6, amendment b1fbd2e). EXPLORATORY (dev).
- `src/phase_f.py` — PHASE F (decisions.md 2026-09-25) -- EXPLORATORY / DESCRIPTIVE on dev 2010-2019 ONLY. Nothing after 2019 is read;
- `src/posthoc_2026_09_28.py` — PART 1 of the 2026-09-28 documentation update (decisions.md 8aa1797 / 784b1a8). POST-HOC, exploratory: reproduces analyses originally
- `src/posthoc_twin_reuse.py` — Post-hoc twin-interval check under region reuse (decisions.md 2026-09-30, 7c9b7bb). POST-HOC diagnostic on the 50 TEST 1 pairs (ae1b174).
- `src/prospective_measures.py` — PROSPECTIVE PRE-REGISTRATION (decisions.md 2026-09-27, 2f62f88; clarification bb8a137): bursty fraction BF and late-window
- `src/stage4_models.py` — STAGE 4 -- primary cohort models on DEV only (test years never loaded). Implements the pre-registered details
- `src/swpc.py` — Flare catalogue from NOAA SWPC's ORIGINAL daily event reports (the catalogue HEK copies).

## scripts/ (runnable steps, numbered in pipeline order; prospective_look1*.py = Look 1 code, reference copy)

- `scripts/00_reproduce_from_results.py` — No-download reproduction check for the public release (code by Claude Code (AI), 2026-10-11; new file, no new method).
- `scripts/01_build_dataset.py` — Build a labelled SHARP dataset for flare forecasting (Bobra & Couvidat 2015 features).
- `scripts/01_checks.py` — Sanity checks on a labelled SHARP file. Usage: python checks.py [START END]
- `scripts/01_fetch_extra.py` — Decision O: fetch the Bobra & Couvidat (2015) SHARP keywords missing from the original query,
- `scripts/01_run_all.py` — Run build_dataset.py over a long range in monthly chunks, resumably, then summarise.
- `scripts/02_make_split.py` — HARP-level train / val / test split (decisions L, M, N -- user, 2026-09-21).
- `scripts/02_split_report.py` — Report the dataset under the FROZEN split (frozen/split.csv is read, never written).
- `scripts/03_stage2_gate.py` — STAGE 2 -- the gate: Bobra & Couvidat-style SVM on 10 of their 13 features (decisions Q, S, N2, K2).
- `scripts/04_stage3_cohort.py` — STAGE 3 -- dev alarm cohort (2010-2019), from the STAGE 2 out-of-fold scores and frozen threshold.
- `scripts/04_stage5_test.py` — STAGE 5 -- held-out test, per frozen/frozen_spec.json. RUN ONCE in mode 'test'.
- `scripts/05_diag_d7.py` — D7 -- closest possible reproduction of Bobra & Couvidat (2015), Table 2 protocol (diagnostic; dev period only).
- `scripts/05_diag_patha.py` — PATH A -- "phantom false alarms" (descriptive; NOT a test of the FINAL primary result; decisions.md 2026-09-22).
- `scripts/05_diag_patha2.py` — Path A follow-up (decisions.md 2026-09-22): FAR/precision CIs (HEK vs K2, 2021-24), the 34 phantom alarms,
- `scripts/05_diag_patha3.py` — Path A consistency checks (decisions.md 2026-09-22): region flips, FAR/precision by test-year set,
- `scripts/05_diag_persistence.py` — READ-ONLY (decisions.md 2026-09-23): persistence baseline P vs the frozen gate, test 2021/2023/2024, single-region, K2.
- `scripts/05_diag_r.py` — R1-R4 reproduction runs (diagnostic; dev period only; decisions.md 2026-09-22). Main pipeline and gate unchanged.
- `scripts/05_diag_r5_r7.py` — R5-R7 reproduction runs (decisions.md 2026-09-29, d34431f). DIAGNOSTIC; dev period 2010-05-01 ... 2014-05-31 only; gate, frozen files,
- `scripts/06_euv_step6.py` — STEP 6 (decisions.md 2026-09-24 pre-registration). DEV 2010-2019 ONLY -- internal cross-validation, NOT a held-out test.
- `scripts/08_euv_confirm.py` — 2025-26 CONFIRMATION SET -- download + LABEL-BLIND computation only (decisions.md 2026-09-26, d95e147).
- `scripts/09_cnn1d.py` — Candidate #28 SMALL 1D-CNN ON THE 94 A LIGHT CURVE (CNN1D) -- decisions.md 2026-09-30 (fdf044d, amendment 8630b46). EXPLORATORY (dev).
- `scripts/09_combo_t.py` — COMBO-T (decisions.md 2026-09-27, 9a88d70): SECONDARY prospective model, fitted on dev 2010-2019 only (no 2021-2026 data read).
- `scripts/09_euv_dots.py` — EXPLORATORY — parasitic-polarity "dots" near the PIL (decisions.md 2026-09-27, dc080a8). DEV 2010-2019 (candidate #23).
- `scripts/09_euv_k3.py` — EXPLORATORY (decisions.md 2026-09-26, ae24e98): temporal contrast K3 = log10(median kappa_box LATE / EARLY), LATE =
- `scripts/09_euv_lnr4a.py` — EXPLORATORY ROBUSTNESS CHECK (decisions.md 2026-09-26, 0043520): lnR4a = ln(R4a + 3) vs raw R4a. DEV 2010-2019 ONLY.
- `scripts/09_euv_masks.py` — EXPLORATORY (decisions.md 2026-09-26, bebbfe6): three localised 94 A areas -- M1 SG-PIL, M2 CORE, M3 SPOT.
- `scripts/09_euv_novelty.py` — EXPLORATORY — "new vs repeat" brightening locations (decisions.md 2026-09-27, 912ac93). DEV 2010-2019 (candidate #24).
- `scripts/09_euv_recharge.py` — EXPLORATORY — RECHARGE vs CLUSTERING (decisions.md 2026-09-27, 1d7d117). DEV 2010-2019 ONLY. No images, no JSOC.
- `scripts/09_fbl.py` — Candidate #29 FLICKER + BRIGHTNESS LEVEL (FBL) -- decisions.md 2026-09-30 (b3b0c3a, amendment 83973d1). EXPLORATORY (dev).
- `scripts/10_incremental_posthoc.py` — POST-HOC incremental table (decisions.md 2026-10-05, "DRAFT FACT-CHECK, POST-HOC INCREMENTAL TABLE ..." item 2; decided by: user).
- `scripts/10_posthoc_region_checks.py` — POST-HOC region-level robustness checks of TEST 1 (2025-26 CV_box twins), on already-analysed data.
- `scripts/10_sensitivity_combined.py` — SENSITIVITY CHECK ONLY (decisions.md 2026-09-27, 92027fa). Post-hoc, on already-analysed data; nothing here is a test.
- `scripts/prospective_look1.py` — LOOK 1 (EARLY) — downloads and label-blind data build (decisions.md daff479; code by Claude Code (AI)).
- `scripts/prospective_look1_analysis.py` — LOOK 1 (EARLY) — compute, label-blind size rule, the single analysis run, and reproduction checks (code by Claude Code (AI)).
- `scripts/prospective_look1_coverage.py` — Look 1 (early) coverage check — METADATA ONLY (decided by: user, 2026-10-09; code by Claude Code (AI)).
- `scripts/prospective_look1_reproduce.py` — Reproduction checks for prospective_look1_analysis.py (code by Claude Code (AI)). NO PROSPECTIVE DATA: only data/euv_confirm (2025-26,

## frozen/ (byte-identical; SHA-256 verified)

- `frozen/frozen_spec.json` — the frozen specification: gate features, SVM settings, threshold, cohort rules, models A/B, matching caliper, seeds, file hashes
- `frozen/split.csv` — HARP-level train / val / test split (hash in frozen_spec.json `data.split_sha256`)
- `frozen/combo_t/dev_rows.csv` — the development rows the models were fitted on
- `frozen/combo_t/model_hashes.json` — SHA-256 list of this folder's frozen files (itself hash-pinned in scripts/prospective_look1_analysis.py)
- `frozen/combo_t/models/COMBO_T_fold0.joblib` — COMBO-T secondary prospective model (hashes in frozen/combo_t/model_hashes.json)
- `frozen/combo_t/models/COMBO_T_fold1.joblib` — COMBO-T secondary prospective model (hashes in frozen/combo_t/model_hashes.json)
- `frozen/combo_t/models/COMBO_T_fold2.joblib` — COMBO-T secondary prospective model (hashes in frozen/combo_t/model_hashes.json)
- `frozen/combo_t/models/COMBO_T_fold3.joblib` — COMBO-T secondary prospective model (hashes in frozen/combo_t/model_hashes.json)
- `frozen/combo_t/models/COMBO_T_fold4.joblib` — COMBO-T secondary prospective model (hashes in frozen/combo_t/model_hashes.json)
- `frozen/combo_t/thresholds.json` — COMBO-T secondary prospective model: frozen tau, columns and estimator settings
- `frozen/euv_extra/dev_rows.csv` — the development rows the models were fitted on
- `frozen/euv_extra/model_hashes.json` — SHA-256 list of this folder's frozen files (itself hash-pinned in scripts/prospective_look1_analysis.py)
- `frozen/euv_extra/models/A_CV_fold0.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_CV_fold1.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_CV_fold2.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_CV_fold3.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_CV_fold4.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_fold0.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_fold1.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_fold2.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_fold3.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/A_fold4.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_CV_fold0.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_CV_fold1.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_CV_fold2.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_CV_fold3.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_CV_fold4.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_fold0.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_fold1.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_fold2.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_fold3.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/models/C_fold4.joblib` — filter-test model (A, A_CV, C, C_CV fold models; hashes in frozen/euv_extra/model_hashes.json)
- `frozen/euv_extra/thresholds.json` — frozen decision thresholds (exact tau values used by the filter tests and the C+ rule)
- `frozen/stage2/models/fold0.joblib` — gate SVM fold model (hash in frozen_spec.json `gate.fold_models`)
- `frozen/stage2/models/fold1.joblib` — gate SVM fold model (hash in frozen_spec.json `gate.fold_models`)
- `frozen/stage2/models/fold2.joblib` — gate SVM fold model (hash in frozen_spec.json `gate.fold_models`)
- `frozen/stage2/models/fold3.joblib` — gate SVM fold model (hash in frozen_spec.json `gate.fold_models`)
- `frozen/stage2/models/fold4.joblib` — gate SVM fold model (hash in frozen_spec.json `gate.fold_models`)
- `frozen/stage4/models/A_fold0.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/A_fold1.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/A_fold2.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/A_fold3.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/A_fold4.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/B_fold0.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/B_fold1.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/B_fold2.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/B_fold3.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)
- `frozen/stage4/models/B_fold4.joblib` — model A or B fold model (hash in frozen_spec.json `models.fold_models`)

## results/ (small derived tables; no data with t ≥ 2026-08-17)

- `results/euv_confirm/cohort_le2.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py cohort`
- `results/euv_confirm/cohort_single.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py cohort`
- `results/euv_confirm/compute_errors.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py compute`
- `results/euv_confirm/exclusions_le2.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py cohort`
- `results/euv_confirm/exclusions_single.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py cohort`
- `results/euv_confirm/retest_checks.json` — 2025–26 confirmation set; written by `src/euv_confirm_retest.py checks`
- `results/euv_confirm/retest_comparisons.csv` — 2025–26 confirmation set; written by `src/euv_confirm_retest.py run`
- `results/euv_confirm/retest_models.csv` — 2025–26 confirmation set; written by `src/euv_confirm_retest.py run`
- `results/euv_confirm/test1_ratios.csv` — 2025–26 confirmation set; written by `src/euv_confirm_tests.py`
- `results/euv_confirm/test2_stepB.csv` — 2025–26 confirmation set; written by `src/euv_confirm_tests.py`
- `results/euv_confirm/thresholds.json` — 2025–26 confirmation set; copied on 2026-10-11 from logs/euv_confirm_tests.log:17 (TEST 2 thresholds A, C); not frozen
- `results/euv_confirm/twins_le2.csv` — 2025–26 confirmation set; written by `src/euv_confirm_tests.py` (TEST 1 pairs)
- `results/euv_confirm/verify_per_harp.csv` — 2025–26 confirmation set; written by `scripts/08_euv_confirm.py verify`
- `results/euv_extra/cohort_primary_all_eligible.csv` — EUV-unseen follow-up set (2021/23/24 and 2022); written by `src/euv_extra.py sets`
- `results/euv_extra/cohort_s2022_all_eligible.csv` — EUV-unseen follow-up set (2021/23/24 and 2022); written by `src/euv_extra.py sets`
- `results/euv_extra/compute_errors.csv` — EUV-unseen follow-up set (2021/23/24 and 2022); written by `src/euv_extra.py compute`
- `results/euv_extra/excluded_ids.json` — EUV-unseen follow-up set (2021/23/24 and 2022); written by `src/euv_extra.py sets`
- `results/euv_extra/manifest.csv` — EUV-unseen follow-up set (2021/23/24 and 2022); written by `src/euv_extra.py sets`
- `results/euv_full/episode_results.csv` — development 2010–2019, AIA 94 Å study; written by `src/euv_full.py run`
- `results/euv_full/step6/compare.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/descriptive.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/oof_PRIMARY.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/oof_S1_flare_excluded.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/oof_S2_primary_no_overhang.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/oof_S3_flare_plus_2h.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/step6_result.json` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/twins_PRIMARY.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/twins_S1_flare_excluded.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_full/step6/twins_summary.csv` — development 2010–2019, AIA 94 Å study; written by `scripts/06_euv_step6.py`
- `results/euv_test/f2_replication/ratios.csv` — held-out 2021/23/24, AIA 94 Å; written by `src/euv_f2_replication.py`
- `results/euv_test/f2_replication/twins_dev_history.csv` — held-out 2021/23/24, AIA 94 Å; written by `src/euv_f2_replication.py`
- `results/euv_test/f2_replication/twins_test_history.csv` — held-out 2021/23/24, AIA 94 Å; written by `src/euv_f2_replication.py`
- `results/euv_test/f2_replication/twins_test_primary.csv` — held-out 2021/23/24, AIA 94 Å; written by `src/euv_f2_replication.py`
- `results/phase_f/F2_episode_values.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F2_ratios.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F3_B_coverage.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F3_eval.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F3_n_B.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F3_spearman.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F4_class_medians.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F4_classes.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F5_eval.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F5_ratios.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F5_spearman.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F5_values.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F6_eval.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F6_ratios.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F6_spearman.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F6_values.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/phase_f/F7_summary.csv` — Phase F, development 2010–2019 (exploratory); written by `src/phase_f.py` (F2–F7)
- `results/stage2/oof_scores_dev.csv` — gate, development 2010–2019; written by `scripts/03_stage2_gate.py`
- `results/stage2/stage2_metrics.csv` — gate, development 2010–2019; written by `scripts/03_stage2_gate.py`
- `results/stage2/stage2_result.json` — gate, development 2010–2019; written by `scripts/03_stage2_gate.py`
- `results/stage3/cohort_dev.csv` — development alarm cohort; written by `scripts/04_stage3_cohort.py`
- `results/stage3/episodes_dev.csv` — development alarm cohort; written by `scripts/04_stage3_cohort.py`
- `results/stage3/exclusions_dev.csv` — development alarm cohort; written by `scripts/04_stage3_cohort.py`
- `results/stage4/cv_first_episode.csv` — development models A and B; written by `src/stage4_models.py`
- `results/stage4/cv_primary.csv` — development models A and B; written by `src/stage4_models.py`
- `results/stage4/matched_pairs_dev.csv` — development models A and B; written by `src/stage4_models.py`
- `results/stage4/oof_cohort_dev.csv` — development models A and B; written by `src/stage4_models.py`
- `results/stage4/stage4_result.json` — development models A and B; written by `src/stage4_models.py`
- `results/stage5/cohort_sizes.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/cohort_test_primary.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/delayed_descriptive.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/gate_gate.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/matched_pairs_test.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/models_b.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/pairs_summary.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/04_stage5_test.py test`
- `results/stage5/persistence_vs_gate.csv` — held-out test 2021/23/24 (gate and cohort); written by `scripts/05_diag_persistence.py`
- `results/euv_confirm/results/<HARP>_<YYYYMMDDTHHMM>.json` — 387 per-episode result files (2025–26 confirmation set; 2025-01-05 to 2026-08-16): frames, fill, exclusions, CV_box and related measures
- `results/euv_full/results/<HARP>_<YYYYMMDDTHHMM>.json` — 546 per-episode result files (development 2010–2019, AIA 94 Å study; 2010-06-30 to 2019-04-16): frames, fill, exclusions, CV_box and related measures
- `results/euv_test/results/<HARP>_<YYYYMMDDTHHMM>.json` — 313 per-episode result files (held-out 2021/23/24, AIA 94 Å; 2021-05-10 to 2024-12-20): frames, fill, exclusions, CV_box and related measures

## logs/ (the result logs the paper's numbers come from)

- `logs/candidate_inventory.md` — # Candidate inventory — every candidate tested on real labels
- `logs/cnn1d_eval.log` — CANDIDATE #28 CNN1D — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md fdf044d + 8630b46
- `logs/diag_r5_r7.log` — raw rows 2010-05..2014-06: 379600; QUALITY<=65536: 343198; +|LON|<=68: 252052; +features present +NOAA mapped: 140847
- `logs/euv_confirm_filter_retest.log` — 2025-26 RE-TEST: CV_box AS A FILTER ON TOP OF MODEL C — pre-registered re-test on an already-analysed set, NOT an untouched test. RUN ONCE.
- `logs/euv_confirm_tests.log` — === TEST 1 — CV_box magnetic twins, 2025-26, <= 2 set, primary 80% fill (delayed = false)
- `logs/euv_extra_filter_test.log` — PRE-REGISTERED FILTER TEST (338c0aa) — EUV-unseen follow-up validation, not an untouched test. RUN ONCE.
- `logs/euv_extra_sets.log` — excluded-ID sources: {'harps_from_dirs': 396, 'regions_from_dirs': 418, 'regions_added_from_labelled_rows_of_excluded_HARPs': 16}; excluded HARPs 396, excluded 
- `logs/euv_f2_replication.log` — HELD-OUT REPLICATION OF F2 (added after 7438177); workers 9
- `logs/euv_step6.log` — check: stored primary/sens dCV and fill reproduced from series for 546 episodes (|diff| < 1e-9)
- `logs/fbl_eval.log` — CANDIDATE #29 FBL — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md b3b0c3a + 83973d1
- `logs/incremental_posthoc.log` — INCREMENTAL TABLE — POST-HOC (decided by: user, decisions.md 2026-10-05). Frozen euv_extra A, C, C_CV (22 hashed files verified); mean of 5 fold models; no refi
- `logs/mag_restless_eval.log` — CANDIDATE #26 MR — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md 46207c7 + b2ca7ac + 5cce108
- `logs/minirocket_eval.log` — CANDIDATE #27 MRKT — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md 16569b6 + b1fbd2e
- `logs/numbers_sources.csv` — every number in the paper → its file, line, quoted source text and status (original repository paths; see README)
- `logs/phase_f_F2.log` — PHASE F F2 -- EXPLORATORY / DESCRIPTIVE, dev 2010-2019 only; workers = os.cpu_count() - 1 = 9
- `logs/posthoc_2026-09-28.md` — # Post-hoc analyses reproduced from the Claude-chat sessions (2026-09-27/28)
- `logs/posthoc_region_checks.log` — POST-HOC region-level checks of TEST 1 (not pre-registered)
- `logs/posthoc_twin_reuse.log` — Step 1: TEST 1 reproduced exactly with the existing code: ratio 3.2624 [1.2956, 9.4887], 50 pairs (pairs resampled by true HARP; 2,000, seed 0)
- `logs/prospective_look1_reproduce.log` — 40/40 reproduction checks of the Look 1 analysis code (no prospective data); pins the code's SHA-256
- `logs/prospective_step2.log` — PROSPECTIVE PRE-REGISTRATION — STEP 2: DEV EXPLORATION (EXPLORATORY; dev 2010-2019; internal 5-fold CV). 2f62f88; BF = option (a) eb3e7d5; implementation d2ed36
- `logs/sensitivity_combined.log` — SENSITIVITY CHECK ONLY — post-hoc, on already-analysed data (92027fa). Not a test; sets never pooled.

## preregistration/

- `preregistration/decisions.md` — the project's append-only decision log: every decision, pre-registration, amendment and result record, dated (3 emails and 6 home-path lines replaced, see CHANGES.md; line numbers unchanged)
- `preregistration/PREREG_INDEX.md` — each pre-registration with its date, commit and line
- `preregistration/LOOK1_RUN_SHEET.md` — the Look 1 (early) run sheet: steps 0–10, who runs each, expected output, stop rules (1 email and 1 home path replaced, see CHANGES.md)
- `preregistration/LOOK1_ANALYSIS_DECISIONS.md` — the open choices D1–D11 of the Look 1 analysis code and the proposed defaults (answers recorded in decisions.md, 2026-10-10)

## figures/

- `figures/F10_gallery.pdf` — figure PDF
- `figures/F1_method_updated.pdf` — figure PDF
- `figures/F2_timeline_updated.pdf` — figure PDF
- `figures/F3_cvbox_color.pdf` — figure PDF
- `figures/F4_twin_pair_color.pdf` — figure PDF
- `figures/F9_candidates.pdf` — figure PDF
- `figures/R1_gate.pdf` — figure PDF
- `figures/R2_patha.pdf` — figure PDF
- `figures/R3_twins.pdf` — figure PDF
- `figures/R4_filter.pdf` — figure PDF
- `figures/R5_overlap.pdf` — figure PDF
- `figures/candidate_inventory.csv` — inventory of all tested candidates and their status; read by f9_candidates.py
- `figures/examples.py` — Rule-based example selection for F3/F4 (rule recorded in decisions.md BEFORE looking, commit 983bcae).
- `figures/f10_gallery.py` — F10: image gallery of four TEST 1 twin pairs chosen by rule (decisions.md, commit f2cb21d, recorded before selection; image rule amended in bc6c4e8):
- `figures/f1_method_updated.py` — F1 (version 2) method overview, redesigned. Graphic generated by code written by Claude (AI, chat) on 2026-10-06.
- `figures/f2_timeline_updated.py` — F2 data timeline: one row per data period; every boundary date is parsed from a numbers.json macro.
- `figures/f3_cvbox_color.py` — F3 (colour): how CV_box is computed, with five AIA 94 A snapshots of the same episode across the 24-h window.
- `figures/f4_twin_pair_color.py` — F4 (colour): example twin pair with magnetogram, AIA 94 A image and 24-h box series for each member.
- `figures/f9_candidates.py` — F9 all candidates: one row per evaluation in candidate_inventory.csv that has a Δ log-loss; point = Δ, line = 95% CI.
- `figures/figstyle.py` — Shared style for every paper_template figure (code written by Claude Code (AI)).
- `figures/numbers.json` — every paper macro and its value (built from numbers_sources.csv); read by f2 and f9
- `figures/results_figs.py` — Results figures R1-R5 (graphic generated by code written by Claude (AI, chat), 2026-10-06).
- `figures/solar_images.py` — Shared helpers for the colour image figures (F3 colour, F4 colour, F10 gallery).

## Missing: scripts not found in the project repository

- **Figure 6 of the current paper** (Overleaf build "Same_Magnetic_Danger_revised_1"). It is a forest plot with 8 rows: development, held-out,
  held-out history-matched, 2025–26 primary, two-way, linked-group, flare-history matched, and flare frames removed.
  No script in the repository makes it. `figures/results_figs.py` (`R3_twins.pdf`, 13 rows) is the nearest earlier version.
- **Figure 8 of the current paper.** It shows blue = without CV_box, orange = with log10 CV_box, an "88% retention target" line, and no
  C+ star. No script in the repository makes it. The existing script is `figures/results_figs.py` (`R4_filter.pdf`, which still draws
  C+ as a star).
- The other figures in the current paper build could not be checked against this list, because that build is not in the repository.
  The figure set here follows `main_formatted.tex` plus the final 10 Oct F1 and F2.

## Available on request

- `euv_confirm/spatial/*.json` (1,161 files, 105 MB): R4a spatial maps for the 2025–26 set. R4a is an exploratory candidate.

## Excluded, and why

- **All raw and downloaded data** (`data/`: SHARP chunks, labelled files, SWPC reports, GOES files, AIA/HMI FITS cutouts and series):
  too large, and re-downloadable (README, "Data sources").
- **All prospective data and outputs** (t ≥ 2026-08-17): `data/prospective*`, `data/labelled_20260817_*`, SWPC reports from 2026-08-19,
  and `prospective_look1_coverage.log` (record counts for the prospective period). Only the Look 1/Look 2 code and the registered plan
  are included.
- **28 scripts that produce no number in the paper:** audits, completeness and validation checks, one-off diagnostics,
  `euv_cad.py`, `nb_r4a_reanalysis.py`, `removed_true_alarms.py` and others.
- **Paper drafts and their sources:** `paper_template/` (TeX, tables, Overleaf zips, `FORMAT_NOTES.md`). The final paper will be added
  by the authors.
- **`Papers/` and other downloaded journal PDFs:** copyright.
- **Working files and working notes:**
  - `.venv/`, `__pycache__/`, `.DS_Store`, `tmp/`, `output/`, `Claude outputs/`, `verification/`;
  - the exploratory GIFs, PNGs and CSVs in the project's `figures/` folder;
  - `PROJECT_SUMMARY.md`, `VERIFIED_FACTS.md`, `docs/physics_study_guide_*.md`, `docs/removed_true_alarms.*`, `docs/report/`,
    `prospective_look1_amendment_DRAFT.md` (its text is in decisions.md).
- **13 small tables written by scripts that are not in the release** (no paper number depends on them):
  `stage4/stepA_dev.csv`; `stage5/false_alarm_spotcheck.csv`, `lead_time_test_primary.csv`, `region_timelinked_test_primary.csv`,
  `flare_rate_by_alarm_primary.csv`, `operating_point_descriptive.csv`; `euv_full/results/step4_counts.csv`, `step4_choice.json`;
  `euv_full/step6/explore_1..4_*.csv`; `euv_confirm/cv_box_by_year.csv`.
- **Other model files:** the dev Step 6 fold models (`data/euv_full/step6/models/`) and `data/nb_r4a/`. They are not frozen and no
  paper number depends on them.
- **Personal information:** emails replaced by `YOUR_EMAIL_HERE`; a user name and home or temporary paths replaced (9 lines, listed
  in `CHANGES.md`). A scan for school, city and state names found none.
