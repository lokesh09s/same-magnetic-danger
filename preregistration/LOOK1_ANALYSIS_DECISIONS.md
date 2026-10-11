# Look 1 analysis code — choices the registrations leave open (answer before the code is committed)

The registrations (2f62f88, eb3e7d5, bb8a137, d2ed360, 9a88d70, 46207c7/b2ca7ac, 8aa1797/784b1a8, b480d22, 5a6d106, daff479) leave these points open. For each, the **proposed default** follows the logged precedent in the code. Reply "defaults OK", or give the number and your choice.

**D1 — Who runs the compute step** (CV_box, CV6 and BF(a) per episode, label-blind).
- It reads the downloaded FITS and makes a JSOC *pointing-table keyword query* (aiapy). That query was recorded as allowed and "not a download" (decisions.md:5266/5269).
- **Default:** a student types it as step 8 (`RUN_BY=… prospective_look1_analysis.py compute`), like steps 0–7.

**D2 — What runs if the size rule says "TOO SMALL — DESCRIPTIVE ONLY".** The registration says "give the numbers, and give no reading".
- **Default (A):**
  - every registered statistic (PRIMARY, secondaries, COMBO-T, MR, C+) is computed and printed as DESCRIPTIVE;
  - **no reading is printed anywhere**, including COMBO-T's "BETTER PROBABILITIES / NOT SHOWN";
  - the PRIMARY then falls back to Look 2 (b480d22 item 4).
- **Alternative (B):** print only counts (episodes, true/false, HARPs, pairs) and no ratios or intervals. This avoids an interim look at Look 1 data, which also belong to the Look 2 fallback set.

**D3 — PRIMARY without alarms on 2026-08-17/18** (b480d22 item 2).
- **Default:**
  - drop those episodes (UTC date of the cohort `t`) and **re-run the twin matching** on the reduced set ("recomputed excluding every episode");
  - same CI and reading wording;
  - no reading if D2 applies.

**D4 — Which pairs for CV6, BF(a) and MR.**
- **Default:** the PRIMARY CV_box pairs (and the history-matched pairs for CV6/BF(a)), dropping pairs where the measure is undefined.
- This is how the dev precedents ran (prospective Step 2 d2ed360; MR E1).
- CV6/BF(a) values ≤ 0 are treated as undefined, as in Step 2.

**D5 — Sign test.**
- **Default:** two-sided binomial test with ties excluded (the code that logged 39/50, p 9.0e-05).
- It is reported for the CV_box, CV6 and BF(a) twin ratios, both magnetic and history-matched.

**D6 — MR window for early alarms.** For alarms in the first day, MR's (t − 24 h, t] window reaches before 2026-08-17.
- **Default:** include those SHARP rows from the 2025–26 files already on disk, as MR's definition implies.
- The cohort itself (step 4) uses only Look 1 rows, exactly as the 2025–26 set did at its own start.

**D7 — COMBO-T.**
- **Default:**
  - evaluable set = fill ≥ 0.80 and CV_box > 0, as frozen;
  - "Model C" = the frozen euv_extra C with the exact τ_C;
  - output 3 bootstrap drops a resample if either D is undefined (euv_confirm_retest code) and reports how many were used;
  - the reliability table is unweighted, as in the logged 2025–26 table;
  - no AUC.

**D8 — C+ descriptive.**
- **Default:** the code that produced the logged 2025–26 numbers (52/56, 125/322; D_true −1.3 [−3.7, 0.0], D_false +7.9 [0.7, 15.5]), with exact frozen thresholds.

**D9 — Region-reuse diagnostics** (POST-HOC).
- **Default:** run on the PRIMARY pairs with the same code as `posthoc_twin_reuse.py`, whatever the size rule says (they carry no reading).
- They are skipped if there are fewer than 2 pairs.

**D10 — Zero pairs or an undefined ratio.**
- **Default:** print "undefined (0 pairs)" and skip that bootstrap (sensitivity_combined precedent).
- If the PRIMARY has ≥ 60 evaluable episodes but its ratio is undefined, the registered reading has no undefined case. The TEST 1 code would print "NOT REPLICATED". **Default:** keep that code behaviour and flag it in the log.

**Reproduction plan** (no prospective data). The code reproduces these exactly before it is committed:
- **TEST 1:** 3.2624 [1.2956, 9.4887], 50 pairs; history twins 2.8174 [1.0169, 6.8227], 47; 39/50, p 9.0e-05.
- **Region reuse:** `posthoc_twin_reuse.log` lines 1–16.
- **COMBO-T:** the frozen dev values and the logged 2025–26 post-hoc counts and tiers.
- **C+:** the logged 2025–26 counts and D intervals.
- **CV6, BF(a), MR:** registered as never to be computed on 2025–26 (decisions.md:5198, 6025), so they are reproduced on dev 2010–19: the stored values, and the logged dev twin ratios 2.1261 [1.2479, 3.3090], 1.2125 [1.1048, 1.3194] and 1.0814 [0.9193, 1.3109].

## Added after the independent code review

**D3a — Which clock decides "on 2026-08-17/18"?**
- The Look 1 set is defined in TAI, but the cohort time `t` is in UTC (T_REC minus 37 s). So the first Look 1 slot, 2026-08-17 00:00 TAI, has t = 2026-08-16 23:59:23 UTC.
- That episode's whole 24-h label window lies in the disclosed 2026-08-17 report.
- **(UTC):** keep that episode and drop 2026-08-18 23:59:23 UTC (= 08-19 00:00 TAI). This is the wording of D3 as drafted.
- **(TAI, reviewer's suggestion):** use the T_REC date, which drops the 08-17 00:00 TAI slot and keeps the 08-19 00:00 TAI slot. This matches the purpose of the secondary: removing alarms whose labels touch the two disclosed reports.
- **Proposed default: TAI.** The code has one switch (`D3_CLOCK`). Please choose.

**D11 — The run-once analysis.**
- It refuses to run unless the student also sets `CONFIRM="run the prospective test once"` (your registered command), plus `RUN_BY`.
- Before reading any label, it checks:
  - the size rule and compute outputs, by hash;
  - the frozen-model hashes;
  - SWPC coverage;
  - that the code is committed and unchanged.
- It then writes an exclusive marker and an "ANALYSIS START" line in the run log. If anything fails afterwards, it logs "ANALYSIS FAILED" (no values), and Look 1 counts as used.
- **Default:** a student runs steps 8–10 (compute, size rule, analysis).

**Also fixed after the review** (no choice needed):
- The registered CV6 undefined counts by true/false (313c1c0) are now printed.
- No unregistered statistic (all-episode ratios, C_CV results) is computed or saved in the Look 1 run.
- The empty-set crash is fixed.
- Step order is enforced with hashes.
- The report is written line by line, and the PRIMARY result is saved before anything else.
