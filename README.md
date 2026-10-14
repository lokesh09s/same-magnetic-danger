# Same Magnetic Danger, Different Outcome

Code, frozen files, pre-registrations and result logs for a study of false alarms in solar-flare forecasting.
Authors: Lokesh Chaudhary and Kyros Goyal.

## The question

A magnetic-field forecast raises an alarm when an active region looks likely to produce an M1.0-or-larger flare within
24 hours. Most alarms are false. **Among alarms with nearly the same magnetic score, is the extreme-ultraviolet
emission of the true alarms more restless in the 24 hours before the alarm than that of the false alarms?**

- **The magnetic gate** is an SVM on 10 SHARP features (after Bobra & Couvidat 2015), trained on development data
  only. Its threshold, models and data split are frozen in `frozen/frozen_spec.json`.
- **The EUV measure, CV_box**, is computed from AIA 94 Å images (12-min cadence) of the whole region box over
  (t − 24 h, t]. It is the standard deviation of the linearly detrended box-mean brightness divided by its mean.
- **Magnetic twins:** each true alarm is matched 1:1 to a false alarm from a different region whose gate score is
  within 0.0747 (0.2 SD).
- **The twins ratio** is the median CV_box of the true alarms divided by the median of their false twins. Its 95%
  interval comes from resampling the pairs by true-alarm region (2,000 resamples, seed 0).

## Data periods

| Period | Role |
|---|---|
| 2010-05 – 2019 | development (2020 excluded) |
| 2021, 2023, 2024 | held-out test (2022 is a separate sensitivity set, never pooled) |
| 2025-01-05 – 2026-08-16 | 2025–26 confirmation set (TEST 1 and TEST 2) |
| from 2026-08-17 | prospective Look 1 and Look 2: **only the code and the registered plan are in this release; no prospective data or results** |

Every number carries a status in `logs/numbers_sources.csv`. The main statuses are PRE-REGISTERED CONFIRMATORY,
PRE-REGISTERED SECONDARY, PRE-REGISTERED RE-TEST ON ALREADY-ANALYSED DATA, EXPLORATORY (dev), SENSITIVITY (post-hoc),
POST-HOC, DESCRIPTIVE and DATA FACT. Some rows carry another label or the recorded reading instead (for example
LITERATURE, or "NOT ELIGIBLE" with its decisions.md line).

## Layout

```
README.md  LICENSE  CITATION.cff  AI_USE.md  CHANGES.md  MANIFEST.md  COMMIT_HISTORY.md  requirements*.txt
src/              28 modules that other code imports (original file names)
scripts/          the runnable steps, numbered in pipeline order, plus the prospective Look 1 code (prospective_look1*.py)
frozen/           frozen_spec.json, split.csv, and the frozen model and threshold files (byte-identical)
preregistration/  decisions.md (append-only decision log), the Look 1 run sheet and analysis decisions, PREREG_INDEX.md
logs/             the result logs the paper's numbers come from, and numbers_sources.csv (number -> file and line)
results/          small derived tables (per-episode results, cohorts, twins) for 2010–2026, no prospective data
figures/          scripts that draw the paper figures, their inputs and PDFs
```

`frozen/` and `results/` keep the original `data/` paths with `data/` removed. The exceptions are
`frozen/frozen_spec.json` and `frozen/split.csv`, which were already at these paths and are read there. For example,
`frozen/euv_extra/models/C_fold0.joblib` was `data/euv_extra/models/C_fold0.joblib`. `MANIFEST.md` lists every
file.

## Setup

Python 3.12 (the project used 3.12.13).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # add requirements-extra.txt only for scripts/09_cnn1d.py and src/minirocket.py
```

Run every command from this folder with `PYTHONPATH=src`. The scripts read and write `data/...`, `frozen/...` and
their logs relative to this folder.

## Reproduce without downloads (about 10 s)

```bash
mkdir -p data && cp -R results/. data/ && cp -R frozen/stage2 frozen/stage4 frozen/euv_extra frozen/combo_t data/
PYTHONPATH=src python scripts/00_reproduce_from_results.py
```

This re-runs two things from the released tables:
- **TEST 1** with the registered code. Expected: `twins ratio 3.2624 [1.2956, 9.4887]; true higher in 39 of 50 pairs`,
  with pairs identical to `results/euv_confirm/twins_le2.csv`.
- **The post-hoc region checks.** Expected output: identical to `logs/posthoc_region_checks.log` (14 of 18 regions,
  leave-one-region-out 2.47–3.90, paired estimate 2.86 [1.67, 5.32]).

It ends with `RESULT: PASS (2/2)`.

Four figure scripts also run without downloads (`figures/f1_method_updated.py`, `f2_timeline_updated.py`,
`f9_candidates.py`, `results_figs.py`). They overwrite the PDFs in `figures/` unless you set
`FIGSTYLE_OUTDIR=<another folder>`.

## Pipeline, in order

Steps marked † live in `src/`, because other code imports them. Run them from this folder too, as
`PYTHONPATH=src python src/<name>.py <mode>`. Each file's docstring gives its modes; for `src/euv_full.py` the modes
are the ones in this table (its docstring's usage line is out of date).

| Step | What | Code and command | Output |
|---|---|---|---|
| 01 | SHARP keywords and SWPC flare labels, 2010-05 → 2025-01, in monthly chunks | `scripts/01_run_all.py` (runs `01_build_dataset.py` per chunk), `01_fetch_extra.py`, `01_checks.py`; † `swpc.py`, `flares.py`, `goes_xrs.py`, `chunks.py`, `join_report.py` | `data/labelled_*.csv` |
| 02 | HARP-level train / val / test split | `scripts/02_make_split.py` (wrote `frozen/split.csv`; do not re-run), `02_split_report.py` | `frozen/split.csv` |
| 03 | Gate: SVM, 5-fold grouped CV, threshold = max TSS on dev out-of-fold scores | `scripts/03_stage2_gate.py` | `data/stage2/` (models frozen) |
| 04 | Dev alarm cohort; models A and B; held-out test, run once | `scripts/04_stage3_cohort.py`; † `stage4_models.py`; `scripts/04_stage5_test.py test` | `results/stage3`, `stage4`, `stage5` |
| 05 | Gate diagnostics: Bobra & Couvidat reproduction, Path A, persistence baseline | `scripts/05_diag_*.py` | `logs/diag_r5_r7.log` |
| 06 | AIA 94 Å development study: download, CV_box per episode, Step 6, Phase F | † `euv_download.py`, `euv_pilot.py`, `euv_run.py`, `euv_full.py` (`hmi_check \| hmi_test \| dryrun \| run`), `euv_spatial.py`, `phase_f.py F2`; `scripts/06_euv_step6.py` | `logs/euv_step6.log`, `logs/phase_f_F2.log` |
| 07 | Held-out 2021/23/24: download, CV_box, replication of the dev twins result | † `euv_test_download.py run \| verify`, `euv_heldout.py compute \| test`, `euv_f2_replication.py` | `logs/euv_f2_replication.log` |
| 08 | 2025–26 confirmation set: cohort, download, label-blind CV_box; TEST 1 and TEST 2; filter re-test. EUV-unseen follow-up filter test | `scripts/08_euv_confirm.py check \| cohort \| plan \| download \| verify \| compute`; † `euv_confirm_tests.py`, `euv_confirm_retest.py checks \| run`, `euv_extra.py sets \| models \| … \| filter` | `logs/euv_confirm_tests.log`, `euv_confirm_filter_retest.log`, `euv_extra_sets.log`, `euv_extra_filter_test.log` |
| 09 | Exploratory candidates (development years only) | `scripts/09_*.py`; † `mag_restless.py`, `minirocket.py`, `prospective_measures.py`, `descriptive_aia94.py`, `euv_dctrl.py`, `diag_ablation.py`, `diag_d7_catalogue.py` | `logs/*_eval.log`, `logs/prospective_step2.log` |
| 10 | Sensitivity and post-hoc checks | `scripts/10_sensitivity_combined.py`, `10_incremental_posthoc.py`, `10_posthoc_region_checks.py`; † `posthoc_2026_09_28.py`, `posthoc_twin_reuse.py` | `logs/sensitivity_combined.log`, `incremental_posthoc.log`, `posthoc_region_checks.log`, `posthoc_2026-09-28.md`, `posthoc_twin_reuse.log` |
| 11 | Figures | `figures/*.py` | `figures/*.pdf` |
| P | Prospective Look 1 (early): student-run downloads, label-blind compute and size rule, a single analysis run | `scripts/prospective_look1.py`, `prospective_look1_analysis.py`, `prospective_look1_reproduce.py`, `prospective_look1_coverage.py` (code only, see Limits) | none in this release |

## Where the main numbers come from

| Number | Value | Status | Code | Source line |
|---|---|---|---|---|
| Frozen gate threshold | −0.992496 | frozen | `scripts/03_stage2_gate.py` | `frozen/frozen_spec.json` (`gate.threshold`); `preregistration/decisions.md:1566` |
| Gate hourly TSS, held-out 2021/23/24, single-region | 0.5467 [0.4120, 0.6598] | pre-registered | `scripts/04_stage5_test.py test` | `decisions.md:1572` |
| Development twins ratio | 1.966 [1.4737, 3.1731], 81 pairs | exploratory (dev) | `src/phase_f.py F2` | `logs/phase_f_F2.log:7` |
| Held-out replication, 2021/23/24 | 1.3057 [0.9367, 2.2182], 40 pairs | pre-registered | `src/euv_f2_replication.py` | `logs/euv_f2_replication.log:10` |
| **TEST 1**, 2025–26 twins ratio | **3.2624 [1.2956, 9.4887], 50 pairs → "REPLICATED"** | pre-registered confirmatory | `src/euv_confirm_tests.py` | `logs/euv_confirm_tests.log:5`, reading `:10` |
| TEST 1, same-flare-history twins | 2.8174 [1.0169, 6.8227], 47 pairs | pre-registered secondary | same | `logs/euv_confirm_tests.log:6` |
| TEST 2, Δ log-loss A − C | 0.0173 [0.0016, 0.0350] | pre-registered | same | `logs/euv_confirm_tests.log:20` |
| Pairs with the true alarm higher | 39 of 50 | sensitivity | `scripts/10_sensitivity_combined.py` | `logs/sensitivity_combined.log:16` |
| Intervals under region reuse | [1.4764, 8.9395] to [0.6812, 18.8683] | post-hoc | `src/posthoc_twin_reuse.py` | `logs/posthoc_twin_reuse.log:6–8` |
| Region-level checks | 14/18; 2.47–3.90; 2.86 [1.67, 5.32] | post-hoc | `scripts/10_posthoc_region_checks.py` | `logs/posthoc_region_checks.log:3,6,7` |
| EUV-unseen and 2022 twins ratios | 1.6295 [0.7907, 3.8386]; 3.2350 | pre-registered secondary | `src/euv_extra.py filter` | `logs/euv_extra_filter_test.log:16,30` |
| Filter results (C, A_CV, C_CV), 2025–26 | weighted % kept / removed | pre-registered re-test | `src/euv_confirm_retest.py run` | `logs/euv_confirm_filter_retest.log` |
| C+ rule, 2025–26 | 52/56 true kept, 125/322 false removed | **post-hoc** (see AI_USE.md) | `src/posthoc_2026_09_28.py` | `logs/posthoc_2026-09-28.md:326` |

Each of the paper's numbers is traced to its file and line in `logs/numbers_sources.csv`. The paths there are the
original repository paths:
- `<name>.log` is now `logs/<name>.log`;
- `decisions.md` is now `preregistration/decisions.md` (same line numbers);
- `docs/posthoc_2026-09-28.md` and `paper_template/candidate_inventory.md` are now in `logs/`;
- `<module>.py` is now `src/<module>.py` (one row cites `euv_confirm_tests.py:29`);
- `paper_template/FORMAT_NOTES.md` (competition format rules, not results) is not included.

## Data sources (re-download; not included)

- **SHARP keywords** (`hmi.sharp_cea_720s`) come from JSOC (http://jsoc.stanford.edu) through `drms`: steps 01 and P.
- **Flare labels** come from NOAA SWPC's original daily event reports at NCEI
  (https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/daily_reports/solar_event_reports/), read by `src/swpc.py`.
- **GOES XRS** 1-minute science data come from NCEI (URLs in `src/goes_xrs.py`). They are used only for days whose
  report is empty.
- **AIA 94 Å images** (`aia.lev1_euv_12s`) and **HMI magnetograms** are fetched as JSOC export cutouts by
  `src/euv_download.py`, `src/euv_full.py`, `src/euv_test_download.py` and `scripts/08_euv_confirm.py`. AIA
  pointing is corrected with `aiapy`.
- **JSOC exports need a registered email:** register at http://jsoc.stanford.edu/ajax/register_email.html and put
  the address in `src/euv_download.py` (`EMAIL = "YOUR_EMAIL_HERE"`). Keep only one export pending at a time.

## Limits

- **Raw data are not included.** Everything except the check above needs downloads; the AIA exports take many hours.
  JSOC data can be reprocessed, so a fresh download may not match the original files byte for byte. Several scripts
  assert the SHA-256 of the original labelled file (`frozen_spec.json` `data.labelled_sha256`), and stop by design
  if it differs.
- **The Look 1/Look 2 code is a reference copy.** `prospective_look1_analysis.py` refuses to run outside the original
  git repository: it checks commit ancestry and a committed reproduction log pinned to the code's SHA-256. One file
  in that pinned set differs in this release (`src/euv_download.py`: email removed). `CHANGES.md` gives its original
  hash.
- **Missing figure scripts.** The current paper's Figure 6 (an 8-row forest plot) and Figure 8 (blue = without
  CV_box, orange = with log10 CV_box, 88% retention line, no C+ star) were not made by any script in the project
  repository. `figures/results_figs.py` draws the earlier versions (`R3_twins`, `R4_filter`). See `MANIFEST.md`.
- **Figures F3, F4 and F10** need the AIA/HMI files of the 2025–26 set.
- **The R4a spatial maps** for 2025–26 (`euv_confirm/spatial/*.json`, 105 MB) are not included; available on request.
- **C+ is post-hoc.** The rule was designed after inspecting alarms from all years; see `AI_USE.md` and
  `preregistration/decisions.md` (2026-09-28 and 2026-10-09 entries).
- **The exploratory candidates** (step 09) were evaluated on development years only.
- **The model files are Python pickles (joblib).** Load only copies whose SHA-256 matches `frozen/frozen_spec.json`
  or `frozen/*/model_hashes.json`.
- **The git history** of the project repository is not part of this release. It holds raw data and journal PDFs.
  `COMMIT_HISTORY.md` lists all its commits (full hash, time and message), including the hashes cited in
  `decisions.md` and `PREREG_INDEX.md`.

## How to publish

`public_release/` sits inside the project's own repository, so do not run `git init` here. Instead:

```bash
cp -R public_release ~/same-magnetic-danger && cd ~/same-magnetic-danger
git init -b main && git add . && git commit -m "Public release"
git remote add origin https://github.com/<account>/<new-repo>.git && git push -u origin main
```

Before pushing, run a final scan for emails, user names, absolute home-folder paths and school or place names. `.gitignore`
keeps `data/`, virtual environments and caches out. No file is larger than 50 MB (GitHub rejects files over 100 MB).

## License

Everything in this repository (code, logs, tables, figures, models and documents) is MIT-licensed (`LICENSE`). The
exception is the short excerpts from publications, competition rules and data documentation quoted in
`preregistration/decisions.md` and `logs/numbers_sources.csv`, which remain with their authors. The source data are public
SDO/JSOC and NOAA data.

AIA and HMI data courtesy of NASA/SDO and the AIA and HMI science teams, obtained from JSOC (Stanford University).
Flare reports from NOAA SWPC and GOES XRS data from NOAA NCEI.
