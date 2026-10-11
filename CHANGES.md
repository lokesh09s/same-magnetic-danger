# Changes made for the release

Every file was first copied byte for byte from the project repository (1,485 files; each copy verified by SHA-256 against its source).
Then only the changes below were made. No analysis logic was changed.

13 of the copied tables were then removed again, because the scripts that wrote them are not in the release and no paper
number depends on them (listed under "Excluded" in `MANIFEST.md`). With the 12 new files, the release holds 1,484 files.

## Edits

Line numbers are the same before and after; no edit adds or removes a line.

| File | Line | Before | After | Why |
|---|---|---|---|---|
| `scripts/04_stage5_test.py` | 22 | `H("cohort.py")` | `H("src/cohort.py")` | cohort.py now lives in src/; the frozen-code hash check reads it by path |
| `scripts/08_euv_confirm.py` | 48 | `H("cohort.py")` | `H("src/cohort.py")` | same |
| `src/euv_extra.py` | 62 | `H("cohort.py")` | `H("src/cohort.py")` | same |
| `scripts/05_diag_patha.py` | 15 | `H("cohort.py")` | `H("src/cohort.py")` | same |
| `scripts/05_diag_patha2.py` | 11 | `open("diag_patha.py")` | `open("scripts/05_diag_patha.py")` | executes part of diag_patha.py's source, now renamed |
| `scripts/05_diag_patha3.py` | 10 | `open("diag_patha.py")` | `open("scripts/05_diag_patha.py")` | same |
| `scripts/05_diag_r.py` | 14 | `open("diag_d7.py")` | `open("scripts/05_diag_d7.py")` | executes part of diag_d7.py's source, now renamed |
| `scripts/05_diag_r5_r7.py` | 10 | `open("diag_r.py")` | `open("scripts/05_diag_r.py")` | executes part of diag_r.py's source, now renamed |
| `scripts/01_run_all.py` | 25 | `"build_dataset.py"` | `"scripts/01_build_dataset.py"` | runs build_dataset.py as a subprocess, now renamed |
| `src/euv_download.py` | 11 | `"(the JSOC account email)"` | `"YOUR_EMAIL_HERE"` | personal email removed (JSOC needs a registered address: put yours here) |
| `preregistration/LOOK1_RUN_SHEET.md` | 27 | `(the JSOC account email)` | `YOUR_EMAIL_HERE` | personal email removed |
| `preregistration/decisions.md` | 2096, 2100, 7218 | `(the JSOC account email)` | `YOUR_EMAIL_HERE` | personal email removed (3 lines; line count unchanged, so cited line numbers stay valid) |
| `figures/figstyle.py` | 16 | `ROOT = os.path.dirname(HERE)` | `ROOT = HERE` | numbers.json and candidate_inventory.csv sit next to the figure scripts in the release |
| `figures/examples.py` | 6 | `REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` | `REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` | figures/ is one level below the release root (was two in the original repo) |
| `figures/f3_cvbox_color.py` | 11 | `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))` | `sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))` | imports euv_pilot, which is in src/ in the release |
| `figures/f4_twin_pair_color.py` | 12 | `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))` | `sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))` | same |
| `preregistration/LOOK1_RUN_SHEET.md` | 8 | `cd "<home path>"` | `cd "<project folder>"` | personal user name and home path removed (user-approved) |
| `preregistration/decisions.md` | 5925, 6121, 6272, 6402, 6544, 6913 | `PROJECT: <home path> —` | `PROJECT: <project folder> —` | personal user name and home path removed (user-approved); line count unchanged |
| `scripts/04_stage3_cohort.py` | 47 | `S = "<temporary session scratchpad path>"` | `S = "scratch"` | personal user name and a temporary session path removed (user-approved); the checkpoint-3 file it read there (stage3_v1/cohort_dev.csv) is not in the release, so the final region printout after all outputs are written needs it |
| `src/diag_ablation.py` | 18 | `S = "<temporary session scratchpad path>"` | `S = "scratch"` | same; it read a temporary file labelled_K.csv there, not in the release |

## Files that differ from the hash-pinned Look 1 code

`scripts/prospective_look1_analysis.py` refuses to run unless its local code matches the SHA-256 recorded in the committed
`logs/prospective_look1_reproduce.log`. That set is everything `prospective_look1_analysis.py` imports, at any depth. One file in
it was edited above (`src/euv_download.py`), so the release copy cannot reproduce that hash. `src/euv_extra.py` was also edited
but is not in the set. Original hashes:

| File | SHA-256 in the project repository | SHA-256 in this release |
|---|---|---|
| `src/euv_extra.py` | `3ef76fb18e9aac5c5322cfcbe50bf9c57684aa0c86939f2d469878d72360e6f8` | `5435f9c83993efbf8fe201ffb6e4bf066e1103a736977637bfb6e822282e84fd` |
| `src/euv_download.py` | `827f252e45ab541c79755c59c42061a396cea51879b906cee268d17a3d3d8060` | `911fcdc3f4fccc5bd15ef063aa63aaa23f38bf7a5d64680f8e8cf047b090508d` |

The four `scripts/prospective_look1*.py` files themselves are byte-identical to the project repository.

## Renamed or moved files

- The 30 runnable scripts got a two-digit step prefix: `scripts/NN_<original name>.py`. The 28 modules that other code imports keep
  their original names in `src/`, because Python cannot import a name that starts with a digit.
- `data/<path>` became `frozen/<path>` (frozen models and thresholds) or `results/<path>` (derived tables).
- `<name>.log` became `logs/<name>.log`; `docs/posthoc_2026-09-28.md` and `paper_template/candidate_inventory.md` became `logs/`;
  `paper_template/numbers_sources.csv` became `logs/numbers_sources.csv`.
- `paper_template/figures/*` became `figures/`; `paper_template/numbers.json` and `paper_template/candidate_inventory.csv` became `figures/`;
  `tmp/pdfs/F1_method_updated.pdf` and `tmp/pdfs/F2_timeline_updated.pdf` became `figures/`.
- `decisions.md`, `LOOK1_RUN_SHEET.md` and `LOOK1_ANALYSIS_DECISIONS.md` became `preregistration/`.

| Release file | Original file |
|---|---|
| `scripts/01_run_all.py` | `run_all.py` |
| `scripts/01_build_dataset.py` | `build_dataset.py` |
| `scripts/01_fetch_extra.py` | `fetch_extra.py` |
| `scripts/01_checks.py` | `checks.py` |
| `scripts/02_make_split.py` | `make_split.py` |
| `scripts/02_split_report.py` | `split_report.py` |
| `scripts/03_stage2_gate.py` | `stage2_gate.py` |
| `scripts/04_stage3_cohort.py` | `stage3_cohort.py` |
| `scripts/04_stage5_test.py` | `stage5_test.py` |
| `scripts/05_diag_d7.py` | `diag_d7.py` |
| `scripts/05_diag_r.py` | `diag_r.py` |
| `scripts/05_diag_r5_r7.py` | `diag_r5_r7.py` |
| `scripts/05_diag_patha.py` | `diag_patha.py` |
| `scripts/05_diag_patha2.py` | `diag_patha2.py` |
| `scripts/05_diag_patha3.py` | `diag_patha3.py` |
| `scripts/05_diag_persistence.py` | `diag_persistence.py` |
| `scripts/06_euv_step6.py` | `euv_step6.py` |
| `scripts/08_euv_confirm.py` | `euv_confirm.py` |
| `scripts/09_euv_k3.py` | `euv_k3.py` |
| `scripts/09_euv_lnr4a.py` | `euv_lnr4a.py` |
| `scripts/09_euv_masks.py` | `euv_masks.py` |
| `scripts/09_euv_recharge.py` | `euv_recharge.py` |
| `scripts/09_euv_dots.py` | `euv_dots.py` |
| `scripts/09_euv_novelty.py` | `euv_novelty.py` |
| `scripts/09_cnn1d.py` | `cnn1d.py` |
| `scripts/09_fbl.py` | `fbl.py` |
| `scripts/09_combo_t.py` | `combo_t.py` |
| `scripts/10_sensitivity_combined.py` | `sensitivity_combined.py` |
| `scripts/10_incremental_posthoc.py` | `incremental_posthoc.py` |
| `scripts/10_posthoc_region_checks.py` | `posthoc_region_checks.py` |

## New files (written for the release by Claude Code (AI), 2026-10-11)

- `scripts/00_reproduce_from_results.py`: the no-download check (TEST 1 and the post-hoc region checks). It only calls registered code.
- `COMMIT_HISTORY.md`: generated from the project repository's `git log` (283 commits; 5 private session-link lines removed).
- `README.md`, `MANIFEST.md`, `CHANGES.md`, `AI_USE.md`, `CITATION.cff`, `LICENSE`, `requirements.txt`, `requirements-extra.txt`, `.gitignore`,
  `preregistration/PREREG_INDEX.md`.
