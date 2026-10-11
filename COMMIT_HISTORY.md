# Commit history of the project repository

All 283 commits of the project's private repository, oldest first. They are on its only branch, `main`, from
2026-09-21 to 2026-10-11, ending at `9450245`.
- **Why it is here:** these are the hashes that `preregistration/decisions.md` and `preregistration/PREREG_INDEX.md`
  cite. Each pre-registration and amendment was committed before the data it governs were used, and this list shows
  when each was made.
- **Why the history itself is not pushed:** it contains raw data files (one is 130.5 MB, above GitHub's limit) and
  downloaded journal PDFs.
- **What is left out:** every commit has the same author (the project account), so authors are not repeated, and no
  email is shown. 5 private session-link lines were removed. The messages are otherwise as written, including the
  co-author lines that record AI assistance (see `AI_USE.md`).
- **Times:** shown in the committer's local time zone, as git recorded them.
- **Last entry:** the list ends at `9450245`. Commits made after this file was written are not listed.

### 1. `0863e28` — 2026-09-21 00:34 +0530

**Part 1: explicit date banner + CLI validation in build_dataset.py**

Full hash: `0863e28f7d3111a7131521be5ac5918e43bad697`

```text
Date handling was already correct; the mismatched query string came from a
no-argument run using the defaults. Every run now prints argv, parsed CLI
dates and the JSOC literals before querying.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 2. `7c58d2a` — 2026-09-21 00:36 +0530

**Part 2: checks.py with four sanity checks; share flare fetching via flares.py**

Full hash: `7c58d2a054af3ececdf658337d66408eec3e1b79`

```text
All four checks pass on January 2014.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 3. `2b3adae` — 2026-09-21 00:38 +0530

**Part 3: run_all.py -- resumable monthly chunking + whole-range summary**

Full hash: `2b3adae2fe23bc5f85630ec0232f1dc823c135e7`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 4. `fce77b9` — 2026-09-21 01:28 +0530

**handle legitimately-empty chunks after filtering (May 2016)**

Full hash: `fce77b9fe91400b90754befabac89aeb22de0e01`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 5. `82198fa` — 2026-09-21 01:40 +0530

**handle HEK windows with zero SWPC flares (solar minimum)**

Full hash: `82198fa953164ef4ff58ff3fac9a0916da5f68f0`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 6. `0150af5` — 2026-09-21 02:38 +0530

**retry transient JSOC/HEK timeouts per chunk**

Full hash: `0150af5346da45f272b9979a521fc028a7b3efb8`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 7. `c1382c2` — 2026-09-21 03:42 +0530

**widen transient-error retry (connection resets, 5xx); 5 attempts**

Full hash: `c1382c2f0809e7ea81b958fe434714641128ec15`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 8. `7ab7a12` — 2026-09-21 09:29 +0530

**unknown-region flares: never join ar_noaanum <= 0 or NaN**

Full hash: `7ab7a12e40380cd9bb52ae50d5a1a9185c451821`

```text
HEK returns ar_noaanum = 0 for whole years (e.g. 2022: 246 of 258 SWPC flares
in March). Those were joining against NOAA region 0, matching no HARP, and
silently emitting false-negative labels -- entire years read as zero-positive
while raw SHARP row counts were rising.

- flares.py: treat <= 0 and NaN as UNKNOWN, drop from the join, count instead;
  carry the M1+ unknown count on m1.attrs for the join report
- flares.py: count duplicates separately from unknown-region drops (the
  'duplicates removed' line was conflating the two)
- join_report.py: per-year M1+ join coverage, 90% usable-region threshold fixed
  before results were seen; also reports positive rows and distinct positive
  HARPs per year for the chronological split
- checks.py: CHECK 5 fails any year below the threshold
- quality_report.py: per-month QUALITY counts, bit meanings quoted verbatim
  from the JSOC docs, with what JSOC does and does not document about 0x80
- decisions.md: full entry, tables marked PENDING

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 9. `06e3c40` — 2026-09-21 09:52 +0530

**run_all: re-parse t_rec_utc after concat (empty chunks yield object dtype)**

Full hash: `06e3c40066eda2defe8b555cda96a62618d80164`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 10. `1f148c5` — 2026-09-21 10:14 +0530

**SWPC original event reports as flare source; relabel from cached raw**

Full hash: `1f148c5d767325b580211fecc56b2a0198f63fde`

```text
- swpc.py: parse SWPC daily 'Edited Events' reports (XRA lines), single region
  rule reg<10000 -> +10000, blank Reg# = unknown (never joined), dedup on
  (begin, class), 404 days recorded rather than treated as flare-free
- build_dataset.py: FLARE_SOURCE switch (one for the whole range, default
  swpc); loads cached raw SHARP instead of re-querying JSOC; NOAA_ARS forced
  to str so all-single-region months don't read back as float
- HEK labels archived to data/labels_hek/ for comparison
- regression: FLARE_SOURCE=hek regenerated from cache is byte-identical to
  the original HEK labels for 2014-01 and 2019-11
- validate_swpc.py: SWPC vs HEK, March 2011-2019 (sample fixed in advance)
- chunks.py: explicit chunk list shared by all reports (no globbing)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 11. `4fd57aa` — 2026-09-21 10:17 +0530

**decisions.md: SWPC source switch, multi-region rule, missing-day rule (user decisions)**

Full hash: `4fd57aa1601e02f882c4adc90f7149418d7224bc`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 12. `b2a713a` — 2026-09-21 10:19 +0530

**history_incomplete flag: prev-48h window overlaps a missing SWPC day (user decision)**

Full hash: `b2a713aa8e3a4d736c852d2dab583deb8b3d498a`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 13. `75b0d29` — 2026-09-21 10:22 +0530

**decisions.md: validation pass; GOES XRS rule for empty SWPC reports (user decision)**

Full hash: `75b0d29c891e4af42974f6f3bbfa5a898bc1b2ef`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 14. `c53f080` — 2026-09-21 10:27 +0530

**decisions.md: GOES fallback, coverage rule, history control (user decisions H, I, J)**

Full hash: `c53f080d27243ca7d7bdb6c4721bc193fbfb4c87`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 15. `fb06512` — 2026-09-21 10:42 +0530

**GOES empty-day classification with secondary fill; HEK sanity check; scale issue logged**

Full hash: `fb065126c68d171115a7cfaafeb104eeec13f543`

```text
- goes_xrs.py: Table 11 primary+secondary transcribed; per-minute gap fill
  from secondary; statuses missing_M1 / missing_nodata / missing_lowcov /
  incomplete_C1 / genuine_zero (decisions E, H, I)
- swpc.py: label_missing_days / history_incomplete_days driven by the GOES
  table; build refuses to run without it
- join_report.py: source-aware (swpc|hek), adds %in_SHARP and per-year dups
- run_all.py: per-year region_group subsets, excluded and history_incomplete rows
- checks 1 and 5 read the SWPC source
- decisions.md: results tables; flux-scale change at 2019-12 logged as open

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 16. `7015872` — 2026-09-21 10:43 +0530

**decisions.md: decision K, harmonise flare classes to old operational scale (user)**

Full hash: `7015872a2e78bbab7c54d2f04cc3a566ba752f6b`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 17. `190fe03` — 2026-09-21 10:45 +0530

**decision K: harmonise flare classes to the old operational scale**

Full hash: `190fe036e02f6d1891cc7c57a08a0b51029ff7a6`

```text
- swpc.py: per-event Obs column decides the scale; GOES-16+ flux x0.7,
  GOES-13/14/15 as reported; unknown observers fail loudly; 5 SDO events kept
  as reported and counted scale_unverified; impossible HH:MM skipped and counted;
  peak time parsed; conversion_report() per year
- goes_xrs.py: true-flux thresholds M1 = 1.43e-5, C1 = 1.43e-6 (all years);
  empty-day table re-derived (2 days C1 -> genuine zero)
- data/scale_conversion_report.csv

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 18. `822ea8b` — 2026-09-21 10:49 +0530

**relabel all chunks on SWPC originals (old operational scale); checks 1-5; results in decisions.md**

Full hash: `822ea8bf2b321c5c3e34f9988d2cced589456dee`

```text
Check 5 fails on 2020 only (1 M1+ flare, no region); reported, rule unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 19. `a19949e` — 2026-09-21 11:16 +0530

**HARP-level split (decisions L, M, N): 2020 excluded, test 2021-2024, 25% stratified val**

Full hash: `a19949e576c6c3923641920e2c95afcd8f0bcf3a`

```text
data/split.csv sha256 f3ab4056dd7b123aa8116b5d76650ddd916805139ee262381f9a7ffda728d145
No HARPNUM in more than one set (asserted). No model trained.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 20. `eecc96f` — 2026-09-21 13:26 +0530

**decisions.md: decision N2, grouped stratified 5-fold CV for threshold and hyperparameters (user)**

Full hash: `eecc96f2c11920310fdd63d1e429bd5ab72f548d`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 21. `5beac0a` — 2026-09-21 14:19 +0530

**decisions.md: N2 details approved; decisions O, Q, R (user)**

Full hash: `5beac0ab942fa7916c96ecd32454c0c5c6ed2019`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 22. `b967a0a` — 2026-09-21 14:21 +0530

**decision O: fetch_extra.py for the 10 B&C keywords that exist; 1:1 merge with assert; findings logged**

Full hash: `b967a0ac3099011e76177c9e44a0176c43896f6b`

```text
7 Lorentz-force parameters are not JSOC keywords (3 in the 13-feature SVM set): blocking for Q,
awaiting user. QUALITY>65536 vs ==0 difference flagged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 23. `c73956c` — 2026-09-21 14:24 +0530

**untrack data/; frozen/split.csv; gate = B&C-style SVM on 10 of 13 features (user decisions)**

Full hash: `c73956c23199330669a4d8eac7cdaf7f72493572`

```text
- data/ in .gitignore, removed from the index (no files deleted on disk)
- split.csv moved to frozen/ (sha256 unchanged); make_split.py writes there
- decisions.md: P was an unadopted draft superseded by R; Q amended to
  'Bobra & Couvidat-style SVM, 10 of 13 features'; QUALITY==0 documented as
  stricter than B&C; combined CSV hashes recorded
- flagged: user's exclusion examples list R_VALUE and AREA_ACR, which are
  among the 10

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 24. `0ff1757` — 2026-09-21 14:26 +0530

**decisions.md: gate examples were user error (exactly 10 features); no history rewrite, repo local-only; verification/ recorded as pre-registration exploratory run (Codex); untrack frozen.csv**

Full hash: `0ff1757f11b439029e4f1a2781e47c298958ad06`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 25. `fd10354` — 2026-09-21 15:10 +0530

**fetch_extra.log: progress snapshot of decision-O keyword fetch (in progress)**

Full hash: `fd1035486c62b0bae3db77c1617364f875c1c682`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 26. `84fcbdf` — 2026-09-21 15:23 +0530

**decision O complete: 10 B&C keywords merged 1:1; all pre-existing values and labels verified identical**

Full hash: `84fcbdff1ef00cf5d4097062149b61c2534fad2f`

```text
Labelled file sha256 85b88518...; raw file sha256 unchanged (2a65e05b...).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 27. `e1ca3f0` — 2026-09-21 15:25 +0530

**decisions.md: decision S recorded; 06/18 TAI QUALITY finding; timing fit and grid pending user**

Full hash: `e1ca3f0aab5fca20171b2a9b92d135f06a539da0`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 28. `b963274` — 2026-09-21 15:25 +0530

**decisions.md: B&C SVM parameters verified from §5 (reference only)**

Full hash: `b96327417f819ce4860d6622774a55f3e991939b`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 29. `b423ca4` — 2026-09-21 15:27 +0530

**decisions.md: decision S amended (TAI {4,10,16,22} thinning, B&C fixed hyperparameters, natural N/P, 3h guard)**

Full hash: `b423ca4085c1fdbd755d38966641c2ebd4f12436`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 30. `afa4d17` — 2026-09-21 15:39 +0530

**decisions.md: stop-check (nothing running, no model output); decision K2 true-irradiance scale supersedes K (user)**

Full hash: `afa4d1711db200b6ef218cff00df08cba6a9e467`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 31. `1dfc572` — 2026-09-21 15:44 +0530

**decision K2: relabel on true irradiance scale; checks; per-year, split, fallback and thinned tables**

Full hash: `1dfc572eabe0803d75ae17f3936cebf92c80e50b`

```text
Labelled sha256 d25304cf...; non-label columns verified identical; rows 255,292.
Check 5 fails 2020 and 2022 (89.7%); 2022 is a test year -- not excluded, user decision.
Fallback selects single-region (71 positive test HARPs; 55 without 2022).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 32. `00eaf41` — 2026-09-21 15:47 +0530

**decision L2: 2022 excluded from primary test; K2 completeness check; primary-test tables**

Full hash: `00eaf41ab5929f8dd006da57407ba711f7900767`

```text
Completeness at K2: 140 GOES M1+ peaks, 134 matched; of 6 unmatched, 3 are peak-rule
artefacts and 3 appear to be genuine near-threshold flares absent from SWPC (report only).
Primary test single-region positive HARPs = 55 -> single-region.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 33. `69f706a` — 2026-09-21 15:50 +0530

**decisions.md: SWPC M1+ completeness at K2 = 134/137, near-threshold misses, labels unchanged**

Full hash: `69f706a5a21e9af95daa14aca3b972633e11aaa5`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 34. `3afd6fe` — 2026-09-21 15:56 +0530

**audit 2018-2020: 0 bugs; all SWPC M1+ explained (limb or no region); one GOES/SWPC mismatch is G15/G16 cross-calibration**

Full hash: `3afd6fe4c578d08ed9f26ac47c5e5ec28bf17bb8`

```text
- goes_xrs.peaks() shared by completeness_check.py and audit_2018_2020.py

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 35. `73171b0` — 2026-09-21 16:05 +0530

**decisions.md: training authorised (plan not yet signed); residual G15/G16 calibration note; staged plan; B&C median/std scaling**

Full hash: `73171b0838d1341faf1fabb712b9ac26ac63c0ab`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 36. `b0af53e` — 2026-09-21 16:08 +0530

**STAGE 2: gate SVM (B&C-style, 10 features), grouped 5-fold CV on dev; pooled OOF threshold**

Full hash: `b0af53e8eadf4bc42004d88395d13dc3c641d062`

```text
Pooled OOF TSS 0.679 at threshold -0.992496 (primary subset, hourly). Test years not touched.
CHECKPOINT 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 37. `b0cea10` — 2026-09-21 16:14 +0530

**fix month-boundary duplicate rows (JSOC ranges inclusive at both ends); rerun stage 2**

Full hash: `b0cea10f510288e259dfdbad8cedbc156ebc10a9`

```text
393 identical duplicate labelled rows removed (255,292 -> 254,899); asserted identical before dropping.
Stage 2 threshold and fold models unchanged; pooled OOF TSS 0.6789 -> 0.6793.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 38. `f593823` — 2026-09-21 16:15 +0530

**STAGE 3: dev alarm cohort (179 regions: 25 true, 154 false, 16 delayed); CHECKPOINT 3**

Full hash: `f59382375be9f154de8df2ab9d3203a75e44229b`

```text
cohort.py holds the rules for reuse in Stage 5. Flags episode fragmentation by the 06/18 TAI QUALITY gap.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 39. `9cc998a` — 2026-09-21 16:17 +0530

**decisions.md: T1 episode merging across <=3 missing hours, T2 all eligible episodes region-weighted, T3 unchanged (user; after cohort sizes, before any trend/model result)**

Full hash: `9cc998a3434e1b0d3a04f6e5ca45896c83e60f0a`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 40. `2c21994` — 2026-09-21 16:18 +0530

**revised STAGE 3 under T1/T2 (500 episodes, 169 regions; 33 of 55 flaring regions contribute a true episode); proposed B&C replication protocol (comparator Table 2, TSS 0.610 +- 0.048)**

Full hash: `2c219941513e1b6f0c9bfd273cd279c4d606dc7d`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 41. `e5305f7` — 2026-09-21 16:25 +0530

**decisions.md: diagnostic ablation D1-D6 pre-declared (user)**

Full hash: `e5305f780f0dc9bb64b00978abb671d07fdb3c7a`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 42. `7de3fa0` — 2026-09-21 16:34 +0530

**diagnostic ablation D1-D6 (dev only): single results table; primary pipeline unchanged**

Full hash: `7de3fa0a7812f24c69cc715eb846d362dac0f546`

```text
Baseline reproduces 0.6793; FLARE_SCALE=K rebuild validated against file 85b88518.
D6 sample-scale bug caught and fixed before reporting.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 43. `1a2808d` — 2026-09-21 16:46 +0530

**decisions.md: ablation uncertainty diagnostic (user)**

Full hash: `1a2808daacf1494f81e1c58abd35e3173c0391f6`

### 44. `ebdecde` — 2026-09-21 16:52 +0530

**ablation uncertainty (dev only): B&C comparator verified; 20-seed TSS spread; HARP bootstrap CIs; D2 vs baseline differences**

Full hash: `ebdecde8686c50427d662cc1a59e36b82b3d8e11`

```text
diag_ablation.py refactored (main guard, seedable folds); reproduces the committed ablation table byte-for-byte.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 45. `405c80b` — 2026-09-21 16:56 +0530

**decisions.md: ablation accepted (user wording); replication protocol approved; T4 first evaluable hour (user)**

Full hash: `405c80b5b450d0214ba49d92f071fb0a572c63f9`

### 46. `d619529` — 2026-09-21 16:57 +0530

**STAGE 3b: dev cohort under T1-T4 (547 episodes, 180 regions; 41 of 86 positive HARPs contribute a true episode); CHECKPOINT 3b**

Full hash: `d6195297a066ec218b0d3cb611b0da6e4f3cb92c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 47. `471021e` — 2026-09-21 16:59 +0530

**decisions.md: Stage 4 on hold; D7 full-fidelity B&C reproduction planned (user)**

Full hash: `471021e3c4531ef90ec9cf3d6cac87320b5f7665`

### 48. `bb60a17` — 2026-09-21 17:00 +0530

**decisions.md: D7 step 1, B&C protocol audit**

Full hash: `bb60a17fe18be76d09b2b6ef8e08327b7cdb78bd`

### 49. `d2f3b57` — 2026-09-21 17:02 +0530

**D7 closest B&C reproduction (1,000 random 70/30 splits: TSS 0.527 +- 0.050) and D7b our baseline in the same period (0.586 [0.467, 0.680]); diagnostic, dev only**

Full hash: `d2f3b574489cef5c83f363c9fe660a7bbc5993f6`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 50. `faf6654` — 2026-09-21 17:04 +0530

**decisions.md: D7t pre-declared (user)**

Full hash: `faf66548685a4dd0ff68532c1272d7dc7c60252c`

### 51. `2312d82` — 2026-09-21 17:05 +0530

**D7t: threshold by max TSS on the training 70% (TSS 0.707 +- 0.040 over 1,000 splits); diagnostic, dev only**

Full hash: `2312d8202ad409eeef39d5896388a36efaa38219`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 52. `b7f5ac0` — 2026-09-21 17:11 +0530

**decisions.md: replication conclusion (user); Stage 4 released; Stage 4 details pre-registered before any trend/model result**

Full hash: `b7f5ac0806c760757ee0f1db99e2e1a2d2bef324`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 53. `4d83691` — 2026-09-21 17:12 +0530

**STAGE 4 (dev only): models A and B, grouped CV, bootstrap CI on delta log-loss, matched pairs, exploratory; frozen_spec.json; CHECKPOINT 4**

Full hash: `4d836913c9da157ad6efd67e0ea6ee72ae1407a9`

```text
frozen/frozen_spec.json sha256 598be4fa9dc21eb309f9a3e89162f4d62e3c7d2e3c631ff1e119b79a7f964632

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 54. `ca53f8b` — 2026-09-21 17:14 +0530

**frozen_spec: Stage 5 prediction rule approved (sha256 1d205068...); Stage 5 execution details fixed before the test run**

Full hash: `ca53f8b77efc3a98ed66974f42e0884baef71b2c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 55. `2baee39` — 2026-09-21 17:15 +0530

**stage5_test.py; dry run on dev stand-in passed; trend-window detail recorded before the test run**

Full hash: `2baee3950f0733de5c7e601b8be04894db6ab12c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 56. `f84a613` — 2026-09-21 17:16 +0530

**STAGE 5: held-out test run once per frozen_spec (sha256 1d205068...); results tables recorded; CHECKPOINT 5**

Full hash: `f84a6134e4ee104968b5058b3b914fbf8b1191d2`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 57. `9745de2` — 2026-09-21 17:27 +0530

**decisions.md: primary result final; Step A; Step B pre-registered before computing R (tau_A pending confirmation); Step C**

Full hash: `9745de21aea7ff64425e0dbac422bc1d0566aeca`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 58. `96e1618` — 2026-09-21 17:28 +0530

**Step A (dev, exploratory) results; Step C feasibility report (metadata only, nothing fetched)**

Full hash: `96e1618e0a2656f81eddeae3b7a6b161350c90cf`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 59. `08c474f` — 2026-09-21 17:31 +0530

**decisions.md: tau_A approved; confirmation set 2025+ rules; confirmatory tests (a) and (b) pre-registered; Step A exploratory; checks approved (user)**

Full hash: `08c474fb8e03c7646a805bf7451cda7d9766a661`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 60. `40de310` — 2026-09-21 17:33 +0530

**confirmation-set checks: SHARP to 2026-08-17 00:00 TAI; SWPC/GOES to 2026-09-20; Reg# +10000 verified past 14000; end date proposed (not frozen)**

Full hash: `40de310bbc638075b72cbb45b3e89b0b6326513c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 61. `e3e4075` — 2026-09-21 19:41 +0530

**decisions.md: confirmation set frozen 2025-01-01 00:00 TAI -> 2026-08-16 23:00 TAI; NOAA_ARS linking-only note (user)**

Full hash: `e3e4075c39c8d8b115bf33d7a1ec3a1687eed32e`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 62. `76fcb1a` — 2026-09-21 20:01 +0530

**confirmation set Step 1: data fetched and labelled (49,935 rows); checks 1-5 pass; check 5 both years usable; overlap with 2021-2024 flagged; hashes**

Full hash: `76fcb1a92ec75715ddbe6cc57fe24120292d0447`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 63. `2d2064f` — 2026-09-21 20:01 +0530

**decisions.md: correct the HARP-overlap sentence**

Full hash: `2d2064f8a5f28a3d6f286c1ab6cba8970bf78d5d`

### 64. `efb0ad7` — 2026-09-21 20:04 +0530

**decisions.md: D8 pre-declared (user)**

Full hash: `efb0ad72ae7bfd9e195a1e72587a317159f489b4`

### 65. `24e318c` — 2026-09-21 20:05 +0530

**D8 (B&C Table 3 setting, C1/C2 = 15) and the D7/D8 vs B&C comparison table; diagnostic, dev period only**

Full hash: `24e318cee10ffb9d1edfe33d660019fc5f9dc717`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 66. `528d888` — 2026-09-21 21:04 +0530

**decisions.md: confirmation set paused (overlap HARPs excluded, <=2 fallback); D8 conclusion not supplied; EUV/UV pilot recorded (user)**

Full hash: `528d88882c27064228c3889444ac1ee166bfa489`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 67. `26e26e7` — 2026-09-21 21:06 +0530

**EUV pilot Step 1: BADPIT spec from arXiv:2604.26036; code unavailable (GitHub 404, no SWH/Zenodo/ancillary); unstated details with proposed choices; conflicts flagged; CHECKPOINT 1**

Full hash: `26e26e71af3721e0706d8a91bfb924cd6c6723ae`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 68. `acc2b68` — 2026-09-21 21:06 +0530

**decisions.md: correct AR 11429 longitude note**

Full hash: `acc2b6800f42530ed8dabb137f4b4815c16a8348`

### 69. `6e1b406` — 2026-09-21 21:20 +0530

**decisions.md: EUV pilot decisions part 1 (D8 conclusion verbatim, U1-U10 approved, power-law dropped, LoS masks); message truncated**

Full hash: `6e1b40693f5d235436646a80ffb197afb856b348`

### 70. `0fdb9b4` — 2026-09-21 21:20 +0530

**decisions.md: hmi.sharp_720s has a LoS magnetogram segment (provisional; JSOC disk-full error)**

Full hash: `0fdb9b465f6fc266eb78460d7d929c919a745261`

### 71. `65a5900` — 2026-09-21 21:23 +0530

**decisions.md: EUV pilot decisions part 2 (user); pilot implementation details P1-P6 fixed before download (for approval)**

Full hash: `65a5900e7a8499b9688976d3d24692c71e2da709`

### 72. `5862a09` — 2026-09-21 21:26 +0530

**EUV pilot: episodes chosen by P6; AARP metadata check; JSOC still failing (retrying)**

Full hash: `5862a094d015ae1109e3ddcfd43dfb74d03628a8`

### 73. `463b00c` — 2026-09-21 21:50 +0530

**decisions.md: P1/P3/P5/P6 approved, P2 amended, P4 clarified, AARP not used (user)**

Full hash: `463b00c99e8c74816e1c89f25d63b61042a8c248`

### 74. `52c8c1f` — 2026-09-21 21:51 +0530

**EUV pilot prep: swpc end times (labels unchanged), im_patch tracking confirmed, euv_pilot.py pure logic + selftest; JSOC address check failed**

Full hash: `52c8c1fa10a67360b6af274f115633ac2d7cbe33`

### 75. `ecabe4b` — 2026-09-21 22:43 +0530

**decisions.md: EUV pilot download decisions (user); fallback deadline recorded**

Full hash: `ecabe4b2198f29c0e28b626e183030d09f2b5595`

### 76. `33fc1bd` — 2026-09-21 22:44 +0530

**euv_download.py (JSOC path, resumable, manifest, log); retry loop to fallback deadline; fallback-geometry gap raised**

Full hash: `33fc1bdbd8989eddd552231505fd8ea5d29d1455`

### 77. `6636e62` — 2026-09-22 08:05 +0530

**decisions.md: JSOC recovered, LoS segment confirmed; export address unregistered, downloads halted**

Full hash: `6636e6285d94230f86e0c13482b21c635a6ca591`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 78. `6c6342e` — 2026-09-22 08:18 +0530

**euv_download: list files from item dir (manifest was empty); item 1 downloaded**

Full hash: `6c6342e6a219edae77c845b716cef6ab68fa8e4a`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 79. `1082cda` — 2026-09-22 09:31 +0530

**euv_check.py: counts, wavelength, coverage, box containment, gaps; items 2-3 downloaded (JSOC)**

Full hash: `1082cda496d4f7acf61b7fe10cbe5e4eb0f501b2`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 80. `3f8a534` — 2026-09-22 09:34 +0530

**euv_check: item 1 (segments, HARPNUM, T_REC, SHA-256) added to check.csv**

Full hash: `3f8a534e6891407ec2f0b757f6cb4527377c3bc4`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 81. `9662e80` — 2026-09-22 09:35 +0530

**decisions.md: JSOC allows 1 pending export per address (measured)**

Full hash: `9662e80e914aab093b31b4081c72bc03b5aea8de`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 82. `8896dd2` — 2026-09-22 10:20 +0530

**euv_run.py: pilot processing (items 2-4, streaming P5, quality exclusion), item-4 process-and-delete; items 2-3 processed; implementation notes for approval**

Full hash: `8896dd233471ebf1440e8728f80ca3a119eeb86e`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 83. `fe1e003` — 2026-09-22 10:22 +0530

**euv_download: attach to pending JSOC request (N=1), retry transient wait timeouts**

Full hash: `fe1e0039c7cbc4f60548998598ba4e881a437597`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 84. `d164496` — 2026-09-22 10:33 +0530

**decisions.md: Checkpoint 2 approvals; design fix CV_PIL - CV_ctrl (user, from method reasoning); control-mask rule (me)**

Full hash: `d164496315aa4a94ffca8bea22b6360702524ca3`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 85. `b3e8ed6` — 2026-09-22 10:42 +0530

**pilot: update_pointing, ctrl mask + CV (design fix), items 2-3 recomputed; reuse finished JSOC request**

Full hash: `b3e8ed65d6ccb162f9e671cfd7b6900333620132`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 86. `28afe13` — 2026-09-22 11:46 +0530

**euv_download: per-file download with skip-present and retries (JSOC read stalls)**

Full hash: `28afe13ed6ab72f66e7a8f3c7e4755e7ffb63fb6`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 87. `3b646a6` — 2026-09-22 12:09 +0530

**decisions.md: item 4 paused by user**

Full hash: `3b646a6980794dd5e512cb43d800ea6ffcd92c98`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 88. `8ac3677` — 2026-09-22 12:09 +0530

**decisions.md: correct item-4 file count at pause (191 of 1,800)**

Full hash: `8ac367763b5e311925582d80a8f1d133edfffdf2`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 89. `39b7754` — 2026-09-22 14:04 +0530

**decisions.md: D7 reproduction-improvement scope (user; diagnostic only, gate stays 10 features)**

Full hash: `39b77540186e50ffc099827bdaf22a19bd4a49d1`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 90. `b6ca6a5` — 2026-09-22 14:17 +0530

**D7 improvement: formulas (B14, B&C15, cgem.lorentz), NCEI catalogue check (8 of 121 recoverable)**

Full hash: `b6ca6a5938e9a195dcc1f0df46dea640b7fe59a2`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 91. `0e78962` — 2026-09-22 14:54 +0530

**decisions.md: correction (TOTBSQ/TOTFZ/EPSZ available in cgem.lorentz), R4a/R4b, SWAN-SF pass rule, Step 0 results (user decisions)**

Full hash: `0e789621eda5f04900786ee4484436c50ec9f01e`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 92. `73e4959` — 2026-09-22 19:53 +0530

**SWAN-SF validation (pre-registered): cgem.lorentz vs SWAN-SF on 4,757 D7 records; masked variant closer; 1 of 6 pass**

Full hash: `73e495925edc01257be58f71ec51fbe7f99ecb7c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 93. `3e04525` — 2026-09-22 20:52 +0530

**decisions.md: R1-R4 definitions (user) and implementation details (me), before running**

Full hash: `3e0452510f526ad1cdf9cad057b68de727ff4814`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 94. `ac4686b` — 2026-09-22 20:57 +0530

**PROJECT_SUMMARY.md: summary generated from decisions.md, frozen/ and git log; unverified items marked**

Full hash: `ac4686b390211acc34bc6a65fb4ac803ca476048`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 95. `30fe69a` — 2026-09-22 20:58 +0530

**PROJECT_SUMMARY.md: drop a vague line**

Full hash: `30fe69ab9788d5fd4e60a9fe846ffe297ab7f654`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 96. `57c925d` — 2026-09-22 21:10 +0530

**R1-R4 results (diagnostic, dev period): no run in the pre-registered TSS target; summary updated**

Full hash: `57c925d2644079c7bf1ea6a2475e738ae44dc6b4`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 97. `221f182` — 2026-09-22 21:29 +0530

**decisions.md: item 4 resumed; cadence check pre-declared (user); undefined items flagged (synoptic check, Path A, 20-draw control)**

Full hash: `221f1828bccd14033ea6c3cc36fce9b1d8b1ce0c`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 98. `2306cb3` — 2026-09-22 21:32 +0530

**decisions.md: D-CTRL, synoptic check, Path A, cadence check definitions recorded verbatim (user)**

Full hash: `2306cb36b09acfe9800652902facb132cf247d35`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 99. `92b1ba7` — 2026-09-22 21:38 +0530

**decisions.md: D-CTRL/synoptic/cadence implementation details (me), before computing**

Full hash: `92b1ba75ad0339906ebe936f4b3901b749953fac`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 100. `6b16541` — 2026-09-22 21:39 +0530

**decisions.md: SDAC not an AIA provider; VSO->JSOC test stopped (one-JSOC-account rule)**

Full hash: `6b16541312ed40ffc9dacf5474cdd03bd7e558a4`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 101. `7eb9c55` — 2026-09-22 21:40 +0530

**Path A results (descriptive): gate under HEK/K/K2 labels; phantom false alarms by cause; literature links**

Full hash: `7eb9c55601c7beb5bd7fc51713c64b309b7524a7`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 102. `65e6417` — 2026-09-22 22:03 +0530

**item 4: url-tar test for 6975, per-file resume for 4231; parallel synoptic downloads**

Full hash: `65e6417bfbaa0d5d729ddc63f949968c3ad4aaa6`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 103. `50c5895` — 2026-09-22 22:28 +0530

**decisions.md: Path A follow-up and prior work (Hu et al., arXiv:2512.13417v3) recorded verbatim (user)**

Full hash: `50c5895aa55d09387ca5c7902e4ac875943b8214`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 104. `2ba51d3` — 2026-09-22 22:31 +0530

**Path A follow-up: FAR/precision CIs HEK vs K2 (2021-24), 34 phantom list, 3-case evidence pack**

Full hash: `2ba51d3072849d7c40b8bfe498e11db47a16f367`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 105. `fb1fdd4` — 2026-09-22 23:34 +0530

**Path A consistency checks: 26 region flips with reasons, FAR/precision by year set, HEK ar=0 per year, 4 no-HEK phantoms**

Full hash: `fb1fdd466bafdd1e7b9a4253fc53001450ae6e24`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 106. `fbfa4d9` — 2026-09-23 00:51 +0530

**decisions.md: combined EUV test (user) - phases 0-4, download set-up and decision rules recorded before running**

Full hash: `fbfa4d90804f8e89d4e522e0558ecb5c93cf8443`

```text
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 107. `6752423` — 2026-09-23 00:53 +0530

**decisions.md: combined EUV test implementation details (me), before running phases 2-3**

Full hash: `6752423f55dc0578c3092a54ce4f8c039aa5dd83`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 108. `16be89d` — 2026-09-23 01:04 +0530

**combined EUV test: phase 1 results (exposure rule, offset test), crop verification, 15 alarms selected**

Full hash: `16be89dec732fb3941a0c79c8228de9fc7dba70e`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 109. `5078b64` — 2026-09-23 10:18 +0530

**euv_cad: socket timeout; resume after sleep stall (recorded)**

Full hash: `5078b64830de89b7c43355477c53248ba99f2d11`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 110. `e63a3aa` — 2026-09-23 11:08 +0530

**combined EUV test: phase 2 (cadence 12 min, n=8) and phase 3 (synoptic fails -> JSOC cutouts) decisions**

Full hash: `e63a3aafbf33338c66463b3747bf25301e872aee`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 111. `9a56c68` — 2026-09-23 12:10 +0530

**combined EUV test: phase 4 (131 A), summary of choices, full-study cost table; STOP before full download**

Full hash: `9a56c686f1f286633c439560023c9d30865da7fe`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 112. `ee479b6` — 2026-09-23 12:37 +0530

**decisions.md: validity count test (user) + empty-slot reason precedence (me), before running**

Full hash: `ee479b6d37b23fe5239da8ff744bc54e688bc0b7`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 113. `4c25475` — 2026-09-23 12:38 +0530

**validity count test (descriptive): valid counts by source x cadence x threshold x label; empty-slot reasons; corrects 12-min synoptic valid 11/15**

Full hash: `4c25475ecf9f8ded53741e6b0c624c5044aab2fc`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 114. `0fd731c` — 2026-09-23 14:01 +0530

**descriptive: flare-followed fraction alarmed vs non-alarmed, primary test years (frozen gate, reproduces Stage 5)**

Full hash: `0fd731c7ab2be4638a5d223e414869aecdea76e8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 115. `f572994` — 2026-09-23 14:22 +0530

**VERIFIED_FACTS.md: full read-only fact check of PROJECT_SUMMARY.md, Claude-chat status, decisions.md results (159 rows); verify_facts.py**

Full hash: `f5729942b830fa98aa4d6cd52c1422a641024524`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 116. `faa0a57` — 2026-09-23 14:27 +0530

**PROJECT_SUMMARY.md: aligned with VERIFIED_FACTS.md (f572994): outdated EUV items marked done, D6 CI provenance, header line**

Full hash: `faa0a577b4ec514a0209ffa450edccbcea490244`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 117. `3b7938f` — 2026-09-23 14:36 +0530

**descriptive test-result checks: lead time, time-linked region metric (39/105 vs 48/105), false-alarm label spot-check, hourly base rate**

Full hash: `3b7938f8d822bd86d0d45376227e01e64a290eb5`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 118. `bb23ec0` — 2026-09-23 14:56 +0530

**descriptive: persistence baseline vs frozen gate on test years (hour and region, CIs, gate on P=0 hours)**

Full hash: `bb23ec0044d3083a8a577b7d97c9c258b2838644`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 119. `a13a6a4` — 2026-09-23 15:19 +0530

**decisions.md: descriptive operating point defined before computing (model naming mapped to project A/B)**

Full hash: `a13a6a49533707f28d34e75d2c3e78e05b332e3b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 120. `14083a5` — 2026-09-23 15:19 +0530

**descriptive operating point (not pre-registered): 88% dev-true-kept thresholds for A and B applied to frozen test probabilities**

Full hash: `14083a521c000f984cff5c64c13afa6ae6930ce1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 121. `bf5e194` — 2026-09-23 15:29 +0530

**decisions.md: exploratory diagnostic R-split design + Claude chat prediction, recorded before running**

Full hash: `bf5e194e62cb21a172c52f9bd8c84d8c2623a675`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 122. `9e0c672` — 2026-09-23 15:29 +0530

**exploratory diagnostic R-split (dev years only): per-seed and summary results vs Deshmukh 2022 (as supplied) and Stage 5; prediction recorded vs outcome**

Full hash: `9e0c6720d20d7c3130c7c2b88b27f2ae7b44ff67`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 123. `68f07c0` — 2026-09-23 16:19 +0530

**track verification/claude_chat_status_to_verify.md (source checked in VERIFIED_FACTS.md); ignore output/ (literature PDFs, not for git)**

Full hash: `68f07c0f3baf646b6961b7e91cbb1f88cd2013f1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 124. `36bfee3` — 2026-09-23 16:19 +0530

**decisions.md: AMENDMENT full EUV study 94 A only (user) + verbatim rules + implementation details, before any download**

Full hash: `36bfee3cfda4a56004d9a4ac3a4ad174047fc98a`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 125. `49c7735` — 2026-09-23 16:23 +0530

**step 2a: HMI direct access passes the user's rule but WCS not reproducible at full precision -> masks via normal exports (recorded)**

Full hash: `49c7735b178a1063b0f1776a87d72425a6d02e2b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 126. `6226981` — 2026-09-23 16:24 +0530

**euv_full.py: full 94 A pipeline (per-HARP url-tar exports, pipelined, worker pool, both DCV versions) + dry-run check**

Full hash: `62269819be79250e27e9806c7f3ae0ce66ebecb8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 127. `b3fcccf` — 2026-09-23 16:32 +0530

**decisions.md: per-HARP HMI export test (user) recorded before running**

Full hash: `b3fcccf0bcf8d0d15fbc8f62b261e38919a6cc84`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 128. `8936ca2` — 2026-09-23 16:36 +0530

**step 2b dry run PASS (DCV identical to pilot, single = multi-process); hmi_test code**

Full hash: `8936ca2fca9f900fc6db5b6940f14944d50e103c`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 129. `9e6538a` — 2026-09-23 17:01 +0530

**per-HARP HMI export test: data/masks/DCV identical (headers differ only in POLICY/HEADSUM) -> per-HARP HMI exports**

Full hash: `9e6538a39df5270247768258437ff5c28b7889cb`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 130. `93278a0` — 2026-09-23 17:46 +0530

**decisions.md: HARP 8 has no AIA data (aia.lev1_euv_12s starts 2010-05-13)**

Full hash: `93278a0a96aff2cadea909662b51255ddd6ac632`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 131. `833c27e` — 2026-09-24 05:54 +0530

**full run pass 1: 535/547; fixes (HMI file-finder header fallback, missing SAT_ROT keeps header pointing) before resume pass**

Full hash: `833c27e2730b78d529cf40cc72fa49b7f00d2063`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 132. `ff3c11c` — 2026-09-24 06:17 +0530

**full EUV run complete (546/547; HARP 8 no AIA data); step 4 count-first threshold = 80% (counts only); STOP**

Full hash: `ff3c11c3f37a92d2950ae8bc04de8615a296d214`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 133. `2593a77` — 2026-09-24 21:14 +0530

**decisions.md: Claude chat documentation entry 2026-09-24 (frame-rule check, literature, justification, open proposals, Q&A)**

Full hash: `2593a77339a330cade11892f319b30da8540edb4`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 134. `3283478` — 2026-09-24 22:54 +0530

**decisions.md: step 6 go-ahead pre-registration (primary E94 vs A, S1-S3, twins, descriptive; held-out EUV test pre-registered, not run)**

Full hash: `3283478a624202cd5accc2d3d9e1c318bdadd8f7`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 135. `85d20b4` — 2026-09-24 22:57 +0530

**decisions.md: step 6 addition before label split -- episode with empty PIL mask (undefined dCV) excluded from all sets**

Full hash: `85d20b483e5bb4edce910e6eccc8428e68bde8e0`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 136. `04a2abf` — 2026-09-24 22:59 +0530

**step 6 (dev 2010-2019, internal CV): E94 vs A primary + S1-S3, twins, descriptive; pre-stated reading: no detectable improvement**

Full hash: `04a2abfec90a6fd329d00f578c5e77cb1f4317b1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 137. `e108199` — 2026-09-24 22:59 +0530

**held-out EUV test: download/time estimate only (no export, no download)**

Full hash: `e108199a2da511970f189cfe026acc2ac880f122`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 138. `42c3627` — 2026-09-24 23:25 +0530

**decisions.md: EXPLORATORY DIAGNOSTIC on step 6 dCV recorded before running (not pre-registered)**

Full hash: `42c3627405730ce4b2d7c1a6e687e6a90d7f09dc`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 139. `064725c` — 2026-09-24 23:26 +0530

**EXPLORATORY DIAGNOSTIC (not pre-registered) on step 6 dCV: overlap with history, timing, dCV-alone AUC, skew**

Full hash: `064725c2a654615dda6a98914dcec6b275f9c7ad`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 140. `85c8285` — 2026-09-25 00:11 +0530

**decisions.md: PHASE X spatial 94 A measures pre-registered (exploratory on dev; R1-R4, selection rule, held-out plan not run)**

Full hash: `85c828571f82ee0415f4de7aa4bcb12ab86ede7d`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 141. `315ca5b` — 2026-09-25 11:14 +0530

**PHASE X (exploratory, dev): spatial 94 A measures R1-R4 computed and evaluated; no PIL candidate qualifies**

Full hash: `315ca5b56c67dc93da32f2c4af429cf951adf2b3`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 142. `4cc1fe2` — 2026-09-25 12:28 +0530

**decisions.md: R4a flare check recorded before computing (exploratory follow-up to Phase X)**

Full hash: `4cc1fe2f93be90f5221a238d6534a1a57498e579`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 143. `7cb3d1d` — 2026-09-25 13:28 +0530

**held-out EUV test: download-only driver (compute=False) and verify; recorded before the first export**

Full hash: `7cb3d1d3ef5bd24fb8e7f2bfe067d5a4f3584ec8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 144. `382df4e` — 2026-09-25 13:55 +0530

**R4a flare check (exploratory, dev): R4a_nf computed (9 workers, pool == single) and evaluated**

Full hash: `382df4e8b865b91e4b612848ca590d7ec4c6807f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 145. `0299c69` — 2026-09-25 14:24 +0530

**decisions.md: exploratory dev operating point for A vs A+R4a / A+R4a_nf recorded before running**

Full hash: `0299c6977ea08013cee8e0d769804088f0b2b5f0`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 146. `04b6f4f` — 2026-09-25 14:24 +0530

**exploratory dev operating point: A vs A+R4a / A+R4a_nf (528 episodes, tau in-sample)**

Full hash: `04b6f4f7ba941d22a5ad62e71aa0e566ae121011`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 147. `5aaa8a3` — 2026-09-25 15:03 +0530

**decisions.md: PHASE F (exploratory/descriptive, dev 2010-2019) recorded before computing**

Full hash: `5aaa8a3b7a48c409502140ffa2cc93314e270374`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 148. `0fa1f26` — 2026-09-25 15:07 +0530

**Phase F F2 (exploratory, dev): literature ratios under magnetic matching**

Full hash: `0fa1f26771b75fc32b1717aabe485e2d3bd9ddfc`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 149. `33e5f5f` — 2026-09-25 15:07 +0530

**Phase F F3 (exploratory, dev): B-class coverage, n_B, R4a correlations, A+n_B / A+n_B+R4a**

Full hash: `33e5f5f5ffc15a5ce70b646f4bab3ef9c3e6dd51`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 150. `90946ff` — 2026-09-25 15:07 +0530

**Phase F F4 (descriptive, dev): anatomy of false alarms**

Full hash: `90946ff6f0d4c611ab9d566da6c08868f5038806`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 151. `4218c32` — 2026-09-25 15:08 +0530

**Phase F F5 (exploratory, dev): size measures S1/S2**

Full hash: `4218c32ca96e5a170ca17bfe71c38d31849fe18a`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 152. `e09e9ab` — 2026-09-25 15:08 +0530

**Phase F F6 (exploratory, dev): PIL brightness level B1/B2 (primary and flare-excluded)**

Full hash: `e09e9abdfed2ab0ce24182bd53903356f223d1d1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 153. `fcafca8` — 2026-09-25 15:08 +0530

**Phase F F7 (exploratory, dev): summary of every candidate evaluated on dev**

Full hash: `fcafca866c2381931da8c677b057e1d55e1d8658`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 154. `d27a05a` — 2026-09-25 20:48 +0530

**held-out EUV test: download complete and verified (313/313 HMI pairs, 31,105/31,290 AIA frames, 12.2 GB, 0 failures); nothing computed**

Full hash: `d27a05a5d7411a16d82e6f7633d04eeec2e70311`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 155. `f3d6489` — 2026-09-25 21:36 +0530

**held-out: re-export check (archive gaps) + PRE-REGISTRATION of held-out R4a, operating-point and R4c tests (before any test-year computation)**

Full hash: `f3d6489348d1980fb89998161954c49dcd7f7b2c`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 156. `b0c7a22` — 2026-09-25 23:44 +0530

**held-out step 2: test-year EUV values computed (313/313, 0 errors, 2.10 h, 9 workers); fill counts only**

Full hash: `b0c7a2207d91d4bfcbd8ef63fa709a9384dc5d28`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 157. `7438177` — 2026-09-25 23:45 +0530

**held-out tests run once: dCV (primary/S1/S2), R4a (+ operating point), R4c, descriptive rho; readings applied mechanically**

Full hash: `743817720026dacaa0b4e58800c22d3e953c2e8f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 158. `8420876` — 2026-09-26 00:12 +0530

**decisions.md: held-out replication of F2 recorded before computing (hypothesis adopted by the student; added after 7438177)**

Full hash: `84208766c9106969c3e591fc1b2d56e86249abb5`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 159. `ec00afb` — 2026-09-26 00:13 +0530

**held-out replication of F2 run once: CV_box twins ratio 1.306 [0.937, 2.218] -> direction consistent, not confirmed**

Full hash: `ec00afb89ba178e419edd0b651f40c4ccf622c64`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 160. `bebbfe6` — 2026-09-26 00:25 +0530

**decisions.md: exploratory three localised 94 A areas (M1 SG-PIL, M2 CORE, M3 SPOT) recorded before computing; dev only**

Full hash: `bebbfe67389b960716727e96b47d60494732755e`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 161. `ae24e98` — 2026-09-26 00:35 +0530

**decisions.md: exploratory temporal contrast K3 recorded before computing; three-mask evaluation on hold (label-blind computation continues)**

Full hash: `ae24e980f31f7d874aa9ca9cb66aaffbda43ec88`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 162. `e2b491e` — 2026-09-26 00:36 +0530

**K3 step 1 (label-blind): K3/K3_nf computed from stored pairs; counts and percentiles**

Full hash: `e2b491efa87a9777fda78dfbc6615d2cb63a126b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 163. `da4b582` — 2026-09-26 00:36 +0530

**K3 step 2 (exploratory, dev): evaluated once -> NOT ELIGIBLE**

Full hash: `da4b582f264d747f666ccf15c405965a3e50f1b1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 164. `0043520` — 2026-09-26 00:46 +0530

**decisions.md: exploratory robustness check log R4a recorded before computing**

Full hash: `004352027ce52e9e8d8af70368c1edfd94c14d42`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 165. `6efb692` — 2026-09-26 00:47 +0530

**log R4a robustness check (exploratory, dev): raw vs log makes no clear difference**

Full hash: `6efb692b8373f93f7495584db850e6002a0e1513`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 166. `c174926` — 2026-09-26 01:38 +0530

**three localised areas steps 1-2 (label-blind): selftests, full dev run 546/546, mask report; evaluation on hold**

Full hash: `c174926c58a60f1379d18d4196d32149aefc6017`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 167. `946ea8c` — 2026-09-26 01:41 +0530

**decisions.md: go-ahead for the three-mask evaluation (final dev candidates; total 21); M2 named 'brightest core'**

Full hash: `946ea8c292f8f5c41117fdf0124ca0feb846ea13`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 168. `490e8bd` — 2026-09-26 01:41 +0530

**three localised areas step 3 (exploratory, dev): evaluated once, all three NOT ELIGIBLE; final dev candidates (21)**

Full hash: `490e8bd8ad018ec03ea1c0e8cc219185f964a69a`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 169. `d95e147` — 2026-09-26 01:47 +0530

**decisions.md: 2025-26 confirmation set download + label-blind computation recorded before doing anything**

Full hash: `d95e1476d1e218b2a0b7f04260e0e9296e4c12ce`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 170. `723774d` — 2026-09-26 01:48 +0530

**confirmation set: checks (hash, GOES true scale, 6 overlap HARPs), label-blind cohorts (single 165/62, <=2 387/101), download plan**

Full hash: `723774dc14779248971df18346ff27f078befb18`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 171. `2ade915` — 2026-09-26 09:30 +0530

**confirmation set: download complete and verified (387/387 HMI, 33,179/33,370 AIA, 15.0 GB, 0 failures)**

Full hash: `2ade91515613659de7854d950e8a90a3ff278434`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 172. `04208c4` — 2026-09-26 12:24 +0530

**confirmation set step 3: values computed label-blind (387/387, 0 errors, 2.89 h); fill counts only; STOP**

Full hash: `04208c4652eb63c9b6a8720e6479cecc45d5e2ea`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 173. `9655e1c` — 2026-09-26 14:52 +0530

**confirmation set: re-export check of 4 short HARPs -> identical counts (archive gaps)**

Full hash: `9655e1c95cf32e38ad93b6d58f2f8372535bb151`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 174. `749208e` — 2026-09-26 14:53 +0530

**PRE-REGISTRATION 2025-26 confirmation (TEST 1 CV_box twins, TEST 2 Step B) recorded verbatim before any 2025-26 label is used**

Full hash: `749208ee4e3e22c1cefd27535ad495de589af914`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 175. `ae1b174` — 2026-09-26 14:53 +0530

**2025-26 confirmation run once: TEST 1 CV_box twins REPLICATED (3.26 [1.30, 9.49]); TEST 2 Step B C beats A (0.0173 [0.0016, 0.0350])**

Full hash: `ae1b174919a2831a60f54824c1a16e83c16f6fc3`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 176. `eacd2d0` — 2026-09-26 15:27 +0530

**decisions.md: descriptive-only follow-up (model C coefficient; CV_box by year) recorded before computing**

Full hash: `eacd2d0f1ac4492d1486226b6f6f48bfce51f652`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 177. `5ecb255` — 2026-09-26 15:27 +0530

**descriptive follow-up: model C log(1+R) coefficient negative in 5/5 folds; CV_box by year 2010-2026 (label-blind)**

Full hash: `5ecb2557fc08fabd51bd80e6f21e815dcca6aa8d`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 178. `338c0aa` — 2026-09-26 23:08 +0530

**decisions.md: EUV-unseen follow-up validation (CV_box as a false-alarm filter) recorded verbatim before anything else**

Full hash: `338c0aa13f287ee508b3428a07ca81f71bb6ff24`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 179. `8cace14` — 2026-09-26 23:08 +0530

**decisions.md: implementation of the EUV-unseen set construction (exclusion sources and order) before building**

Full hash: `8cace14ecde7303a1c4fb56bb852b5c8f049ba79`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 180. `315757b` — 2026-09-26 23:10 +0530

**EUV-unseen follow-up step 1: label-blind sets (PRIMARY 158 ep / 40 HARPs, all two-region; 2022 152 / 44); size rule PASS**

Full hash: `315757b931980ebfa39a9d133711cf956131e917`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 181. `c68c750` — 2026-09-26 23:11 +0530

**EUV-unseen follow-up step 2: dev models A, A_CV, C, C_CV fitted; thresholds frozen and hashed (before any new-set download)**

Full hash: `c68c7503f0ce32623ef25489213fc115d815b704`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 182. `820baef` — 2026-09-26 23:11 +0530

**EUV-unseen follow-up step 3: download dry run (310 episodes, 168 exports, ~12.7 GB, ~6.6 h)**

Full hash: `820baef5af4fb5e0be460322a7a73dfaff652f1b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 183. `1d7d117` — 2026-09-26 23:54 +0530

**decisions.md: exploratory recharge vs clustering test (dev candidate #22) recorded verbatim before computing**

Full hash: `1d7d11788f342b66ebd16d11f16f90cd5db6993e`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 184. `bd89593` — 2026-09-26 23:54 +0530

**exploratory recharge vs clustering (dev #22): NO DETECTABLE EFFECT (delta +0.0017 [-0.0144, 0.0184]; S_last sign + in 5/5)**

Full hash: `bd895938cb08ad1c0f14a0c783bf0d2a938f9f37`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 185. `dc080a8` — 2026-09-27 00:46 +0530

**decisions.md: exploratory parasitic-polarity dots (dev #23) recorded verbatim + implementation clarifications, before computing**

Full hash: `dc080a8e545c125a0007b22248cb713ff19bb8c2`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 186. `0d27b05` — 2026-09-27 00:47 +0530

**dots step 1 (label-blind): N_dots for 547 dev episodes (median 15, IQR 9-22; 0 missing)**

Full hash: `0d27b0570b2e926f939abc472545c5a0fb5fb576`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 187. `d89a1a0` — 2026-09-27 00:48 +0530

**dots step 2 (exploratory, dev #23): NOT ELIGIBLE (delta -0.0056 [-0.0218, +0.0083]); conditional follow-up not run**

Full hash: `d89a1a04ec8e46e97f3f1aebff6a7ba51de29c7a`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 188. `912ac93` — 2026-09-27 00:56 +0530

**decisions.md: exploratory new-vs-repeat brightening locations (dev #24) recorded verbatim before computing**

Full hash: `912ac93734e557a6dd683ac67c7d946d0aa3090e`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 189. `4e384b6` — 2026-09-27 01:03 +0530

**novelty (#24): selftests pass; step 1 deferred until the euv_extra download finishes (user decision)**

Full hash: `4e384b6aa2c2c23ae77aa1e44bf30e6da6022501`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 190. `30a4f4b` — 2026-09-27 06:30 +0530

**EUV-unseen follow-up steps 3-4: download verified (0 failures), values computed (310/310, 0 errors); counts only**

Full hash: `30a4f4b04e3fd20cb10842515e11ebcfbc0ffb97`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 191. `a15ed4a` — 2026-09-27 07:44 +0530

**novelty (#24) step 1 (label-blind): F_new for 541 dev episodes (median 0.543); checks pass**

Full hash: `a15ed4a78bc148439db7ce64278bdfb3d2f34e53`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 192. `0303d05` — 2026-09-27 07:44 +0530

**novelty (#24) step 2 (exploratory, dev): NOT ELIGIBLE (delta +0.0075 [-0.0062, +0.0208]; sign negative 5/5); follow-up not run**

Full hash: `0303d05351800fadc2170d0d87b68bd3fb94c85f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 193. `8509975` — 2026-09-27 08:59 +0530

**EUV-unseen follow-up: re-export check HARP 8923 -> archive gap; dots (#23) status recorded (NOT ELIGIBLE, no follow-up)**

Full hash: `85099756b88013c84446588903544f550a8b0768`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 194. `f7c6646` — 2026-09-27 08:59 +0530

**EUV-unseen follow-up: filter-test implementation details recorded before the run**

Full hash: `f7c66466e065f35f0157e50b1dbce1776be47e4b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 195. `5abc40a` — 2026-09-27 09:00 +0530

**pre-registered filter test run once: PRIMARY A vs A_CV D_false +60.2 [+46.9, +72.8] pts, D_true -16.2 [-37.6, -2.0] pts -> REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)**

Full hash: `5abc40aafc140481fa6bb8c2e9b9f60781d80ecd`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 196. `25fcd66` — 2026-09-27 09:25 +0530

**decisions.md: 2025-26 re-test (CV_box filter on top of model C) recorded verbatim before anything else**

Full hash: `25fcd66f95db1968914c5bb9a50063db20bef98b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 197. `e4eb16e` — 2026-09-27 09:26 +0530

**2025-26 re-test step 1: label-blind checks pass (378/101 = TEST 1; inputs complete; hashes ok); baseline guard passed (C keeps 72.55%)**

Full hash: `e4eb16e3d0243d4ad2e9cb1c0d5ee305864cf689`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 198. `6aecccf` — 2026-09-27 09:31 +0530

**2025-26 re-test: implementation details recorded before the run (same phase_f statistics as 5abc40a)**

Full hash: `6aecccf33ec6837e8b50b1d74c0f1e83cb2b47c2`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 199. `4b65f23` — 2026-09-27 09:32 +0530

**2025-26 re-test run once: C vs C_CV D_false +24.05 [+14.63, +33.45], D_true -13.98 [-28.47, -4.42] -> REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)**

Full hash: `4b65f239887c2278229713b152513f141baa652d`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 200. `947e4c0` — 2026-09-27 09:46 +0530

**decisions.md: descriptive AIA 94 A follow-ups (alert tiers, artifact check, calm-flarer profile) recorded verbatim before anything else**

Full hash: `947e4c03d322f3898c2defa23fe80a571bcec10d`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 201. `5af931b` — 2026-09-27 09:50 +0530

**descriptive AIA 94 A follow-ups (post-hoc, not pre-registered): alert tiers, CV_box artifact check, calm-flarer profile; figure**

Full hash: `5af931ba68eb37bdeebc970c9b25d52c8a087597`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 202. `92027fa` — 2026-09-27 13:58 +0530

**decisions.md: sensitivity check (CV_box twins with magnetic + flare-history matching, flare frames removed, image-only spike removal) recorded verbatim before anything else**

Full hash: `92027fa491bfc320c086cb81eb0b9f735ff38fa6`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 203. `9a6a1dc` — 2026-09-27 14:02 +0530

**decisions.md: sensitivity implementation note (first run crashed before output on a 0-pair V2 cell; handling recorded before the complete run)**

Full hash: `9a6a1dc3bba64d819e3bb6f64af640c02a93938a`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 204. `1465063` — 2026-09-27 14:04 +0530

**sensitivity (post-hoc, not a test): CV_box twins T_a/T_b x V0/V1/V2; V2 image-only spike removal leaves 0 pairs at 3 s in all sets; figure**

Full hash: `146506368643e83fb4b5d61e302a664ffc9963f6`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 205. `68e57b1` — 2026-09-27 14:19 +0530

**decisions.md: post-hoc re-analysis n_B + R4a (Phase F F3 candidate) on already-analysed test sets, recorded verbatim before anything else**

Full hash: `68e57b1ad1f2c0d9bc5f7f8ba0c134b1131677d9`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 206. `f70f1e7` — 2026-09-27 14:22 +0530

**n_B + R4a re-analysis: dev models and tau frozen and hashed before any test set is read; dev F3 reproduced exactly**

Full hash: `f70f1e7d9bbacaeb336be59dcdf5f72b134accce`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 207. `b7e7749` — 2026-09-27 14:22 +0530

**n_B + R4a re-analysis step 1: n_B NOT COMPARABLE ACROSS YEARS — TEST NOT RUN (2023 B-class region attribution -21.76 pp vs dev mean, -20.13 pp vs pooled); permanent stop**

Full hash: `b7e7749b59aea754f0130739bec5f5c7aea6ecbe`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 208. `2f62f88` — 2026-09-27 16:49 +0530

**decisions.md: prospective pre-registration (bursty fraction BF, late-window CV6) recorded verbatim before anything else**

Full hash: `2f62f8832811d99df276a1feb206382cb9a47e79`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 209. `11f762c` — 2026-09-27 16:50 +0530

**decisions.md: prospective step 1 stopped before computing - BF item b) (co-registration reference) needs a user decision; options listed**

Full hash: `11f762c3fc298a1ec0c3b7502c79eb4274876ebd`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 210. `bb8a137` — 2026-09-27 16:52 +0530

**decisions.md: prospective BF part b) clarification (alarm-time HMI grid, as CV_box) and defaults, before any BF value is computed**

Full hash: `bb8a13736e1472980ab94de4f858ae2d1a23d50b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 211. `71de5e4` — 2026-09-27 18:27 +0530

**prospective step 1 (dev, label-blind): BF defined 541/547, CV6 522/547; per-pixel stack reproduces stored box series; dev_values.csv hashed**

Full hash: `71de5e4e592e4f2b493c7d70f436ba2f0be4cd95`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 212. `21e9e89` — 2026-09-27 18:40 +0530

**decisions.md: BF label-blind noise diagnostic recorded verbatim before anything else**

Full hash: `21e9e896e1da1c792fc7685b9179e2b9ece4030f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 213. `721ffa9` — 2026-09-27 18:41 +0530

**decisions.md: BF noise diagnostic implementation recorded before computing**

Full hash: `721ffa9583af08b0b0ae20182793f7a9f137ca20`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 214. `a215701` — 2026-09-27 21:53 +0530

**BF label-blind noise diagnostic: median BF_noise/BF 1.1464 -> BF IS NOISE-DOMINATED; options (a) macropixels, (b) noise-corrected floor, (c) brightness cut listed, not chosen**

Full hash: `a2157013e9dd7a88d9c9629c1da64047b8e13df7`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 215. `eb3e7d5` — 2026-09-27 21:56 +0530

**decisions.md: BF = option (a) 5x5 HMI-pixel blocks; prospective test amended (PRIMARY CV_box twins; CV6, BF(a) secondary) - recorded verbatim before Step 2**

Full hash: `eb3e7d53cc64e7b502cdda2fa7f02f4245af9523`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 216. `d2ed360` — 2026-09-27 21:56 +0530

**decisions.md: prospective Step 2 implementation recorded before running**

Full hash: `d2ed3604ebd338d0aa80a4d7de65907572da6641`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 217. `208202b` — 2026-09-27 21:57 +0530

**prospective step 2 (dev exploration, EXPLORATORY): twins ratios and delta log-loss for BF(a), CV6, CV_box**

Full hash: `208202b1d660c50e1d498549f3aae13079fbfa4b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 218. `313c1c0` — 2026-09-27 21:59 +0530

**decisions.md: CV6 dev exclusion is label-dependent (12/96 true vs 7/445 false); prospective report must give CV6 undefined counts by true/false**

Full hash: `313c1c071ac5768335a88816524e93ce006673e3`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 219. `9a88d70` — 2026-09-27 23:57 +0530

**decisions.md: pre-registration amendment - secondary model COMBO-T recorded verbatim before implementation**

Full hash: `9a88d702c5ce99b32abaca158a4d1e037c0af1af`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 220. `e17a8a3` — 2026-09-27 23:58 +0530

**COMBO-T frozen on dev only (secondary prospective model): tau 0.0792; fold models, thresholds and dev rows hashed**

Full hash: `e17a8a363dc256844ef108c1e6efb21db0f16ede`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 221. `8aa1797` — 2026-09-28 00:55 +0530

**decisions.md: PART 0 - pre-registration of the C+ protection rule as the only confirmatory false-alarm system (Look 1 descriptive, Look 2 confirmatory); documentation-update Parts 1-5 recorded verbatim**

Full hash: `8aa1797c4037d405d94adafc0b77b001fb48922e`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 222. `784b1a8` — 2026-09-28 01:05 +0530

**decisions.md: C+ rule thresholds = exact frozen values (clarification before any Look 1/2 data); Part 1 definitions and chat reference numbers recorded verbatim before computing**

Full hash: `784b1a8182a58c8f25b5a6593b7fc12a8453fcf4`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 223. `4a0eb43` — 2026-09-28 01:11 +0530

**PART 1: Claude-chat post-hoc analyses reproduced with repo label code and frozen models (all 288 compared values match); docs/posthoc_2026-09-28.md**

Full hash: `4a0eb43f38a6a9f1ef6738c81a29d00c6c90b1cc`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 224. `d34431f` — 2026-09-29 17:38 +0530

**decisions.md: reproduction runs R5-R7 defined (penalty placement, negative-draw variability) before running**

Full hash: `d34431fa9ee26173985bbd47bf3406ff4ed00dc6`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 225. `78775fc` — 2026-09-29 17:44 +0530

**R5-R7 reproduction runs (diagnostic, dev 2010-05..2014-05): R2 reproduced exactly; results table**

Full hash: `78775fcc679eca64d1c299d734ed1d1b94551c03`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 226. `44ac3dc` — 2026-09-30 13:20 +0530

**decisions.md: read-only search for post-hoc 2025-26 twins intervals - only 1.30-9.49 (TEST 1, ae1b174) found; the other three not in the repo**

Full hash: `44ac3dca2106b7c282871bc9bae9dc9307b8daee`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 227. `7c9b7bb` — 2026-09-30 13:22 +0530

**decisions.md: post-hoc twin-interval check under region reuse defined before computing (replaces untraceable 1.48-8.94, 0.86-12.2, 0.68-18.9)**

Full hash: `7c9b7bb456940354a749b67505931501b2d21c27`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 228. `5ac3d3e` — 2026-09-30 13:23 +0530

**post-hoc twin-interval check under region reuse: TEST 1 reproduced; false-HARP [1.4764, 8.9395], two-way [0.8632, 12.2290], linked groups (4) [0.6812, 18.8683]**

Full hash: `5ac3d3ee5ba83a78c97a7a63e1dc01a1fdf29727`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 229. `d85e8dc` — 2026-09-30 15:30 +0530

**decisions.md: dev candidate #25 AIA 1600 A UV brightening area (UVA) pre-registered before any download; literature and aiapy checks; clarifications flagged**

Full hash: `d85e8dc9a8bfa26b3e98f604bf79902149e78a65`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 230. `8504f07` — 2026-09-30 16:19 +0530

**docs/report: literature link check (arXiv/Crossref metadata only) for the project report**

Full hash: `8504f07c5c66a70c71a1b970d321ef66b0962c0f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 231. `2b5aa9f` — 2026-09-30 16:40 +0530

**docs/report: project report (33-page PDF) built from committed sources; verify_report.py PASS (910 sourced values, 0 mismatches)**

Full hash: `2b5aa9faa74379f78d2969e1bfd344611fee4009`

```text
Not a competition submission. Every number is tagged with its file:line or git source and re-checked against the committed repo at d85e8dc.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 232. `ecd3533` — 2026-09-30 16:40 +0530

**decisions.md: project report generated (2b5aa9f)**

Full hash: `ecd3533838f9dd989e219720832ebac323b1cdd4`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 233. `46207c7` — 2026-09-30 17:46 +0530

**decisions.md: dev candidate #26 magnetic restlessness (MR) pre-registered before any computation; literature read (Kniezewski 2025 arXiv abstract, Efremov 2017 abstract); clarifications flagged**

Full hash: `46207c7ccd68431055b7644c216835647d7803c4`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 234. `b2ca7ac` — 2026-09-30 17:54 +0530

**decisions.md: candidate #26 MR - checkpoint 1 decisions recorded verbatim (longitude cut, E1 via ratio_jobs/boot_many, held-out readings, prospective secondary) before Step 1**

Full hash: `b2ca7ac3accce32eaed504836fed42e63cc802d2`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 235. `53146c2` — 2026-09-30 17:57 +0530

**candidate #26 MR step 1 (label-blind, dev): MR defined for 547/547; QUALITY removed 1251 window records, longitude cut 166; examples figure**

Full hash: `53146c236a404fd36aaf83bb6b5f43cafa4677a8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 236. `5cce108` — 2026-09-30 18:02 +0530

**decisions.md: candidate #26 MR amendment A1-A2 (secondary MR_quad) recorded verbatim before any label is read**

Full hash: `5cce108867ae5906b3cf79b909769d0c747f68d8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 237. `7d6e28b` — 2026-09-30 18:03 +0530

**candidate #26 MR: MR_quad computed label-blind (amendment A1); Step 1 reproduced exactly; defined 547/547**

Full hash: `7d6e28bc95da9283bd5dc58b8fc2e8a186572e98`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 238. `0ced557` — 2026-09-30 18:06 +0530

**candidate #26 MR step 2 (dev, run once): E1 T_a 1.0814 [0.9193, 1.3109], E2 delta -0.0113 [-0.0299, 0.0026] -> NOT ELIGIBLE**

Full hash: `0ced557eb1330366f988afd0c3edb681485f6c94`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 239. `16569b6` — 2026-09-30 20:10 +0530

**decisions.md: dev candidate #27 MiniRocket on the 94 A light curve (MRKT) pre-registered before any computation; sktime 1.2.0 + numba 0.67.0 installed and pinned; clarifications flagged**

Full hash: `16569b69ecb6a6d2b49e32924f43aed2972fc065`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 240. `b1fbd2e` — 2026-09-30 20:11 +0530

**decisions.md: candidate #27 MRKT - checkpoint 1 decisions recorded verbatim before Step 1**

Full hash: `b1fbd2eb53e0cd37cc7d403f9d63d35427d84b42`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 241. `ca96c9b` — 2026-09-30 20:17 +0530

**candidate #27 MRKT step 1 (label-blind): 541 curves defined, fill reproduced; synthetic-label crash tests pass (pipeline 55 s)**

Full hash: `ca96c9badc83c1330558599ce0fc1bfc99aefe59`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 242. `bf2dbc4` — 2026-09-30 20:31 +0530

**decisions.md: candidate #27 MRKT - Step 2 go and reload-check addition recorded verbatim before any real label is read**

Full hash: `bf2dbc424d87ba2e5e90f93098fc6bcf485d1a2f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 243. `dd6210c` — 2026-09-30 20:31 +0530

**minirocket.py: freeze and reload check (user addition bf2dbc4) as functions; crash test 3 on synthetic labels passed (max abs diff 0.0; scratch deleted)**

Full hash: `dd6210c0b715815a063547d4371ce4663443a749`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 244. `62fc126` — 2026-09-30 20:33 +0530

**candidate #27 MRKT step 2 (dev, run once): E1 delta -0.0103 [-0.0219, -0.0018], E2 (88%) -8.24 pts -> NOT ELIGIBLE; stable over 5 seeds**

Full hash: `62fc1269cbfe5692c0f068ae9d867cd34c0e7f63`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 245. `fdf044d` — 2026-09-30 20:39 +0530

**decisions.md: dev candidate #28 small 1D-CNN on the 94 A light curve (CNN1D) pre-registered; torch 2.14.0 installed (protected packages unchanged); 737 parameters; clarifications flagged**

Full hash: `fdf044dce64c7475dcf264f586a86230f5eb71a1`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 246. `8630b46` — 2026-09-30 21:24 +0530

**decisions.md: candidate #28 CNN1D - checkpoint 1 decisions recorded verbatim before Step 1**

Full hash: `8630b46be2ba8d9cb1e3586f98b3c0290d2ca1ca`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 247. `d9aa061` — 2026-09-30 21:28 +0530

**candidate #28 CNN1D step 1 (label-blind): curve file identical to #27 (sha256 eafb4b00...), 737 parameters, synthetic crash test incl. freeze/reload passed (48 s); code committed before the real run**

Full hash: `d9aa0611ca34ad2a8bf8948b4e97a52921dcc9ec`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 248. `d419770` — 2026-09-30 21:30 +0530

**candidate #28 CNN1D: epoch-cap decision recorded verbatim before Step 2; E5 reports networks with best epoch = 200 and the pre-stated limitation rule**

Full hash: `d41977013f3a607bc0e55b8ab1847b586c238d89`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 249. `d6c417d` — 2026-09-30 21:31 +0530

**candidate #28 CNN1D step 2 (dev, run once): E1 delta +0.0002 [-0.0041, +0.0041], E2 (88%) -2.38 pts -> NOT ELIGIBLE; epoch cap binding 2/30**

Full hash: `d6c417de6859686c6ace387cdc740b0204f0bb1f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 250. `b3b0c3a` — 2026-09-30 21:48 +0530

**decisions.md: dev candidate #29 flicker + brightness level (FBL) pre-registered with the user's stopping rule; prior evidence quoted; clarifications flagged**

Full hash: `b3b0c3ab4f2941321e5d6f79aca4e2b146494cb8`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 251. `83973d1` — 2026-09-30 23:09 +0530

**decisions.md: candidate #29 FBL - checkpoint 1 answers recorded verbatim before Step 1 (tolerance, drift rule, units check, rho with year)**

Full hash: `83973d1dda3f8ef01ec0842a2ad081185f82bab7`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 252. `29a4d1d` — 2026-09-30 23:12 +0530

**candidate #29 FBL step 1 (label-blind): box is DN/s; L defined 546/547; CV_box x mean reproduces SD (5.96e-15); drift flag 0.3501 dex; synthetic crash test incl. freeze/reload passed; code committed before the real run**

Full hash: `29a4d1d6b5768e2d91320143a988c8b1f62a4432`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 253. `6fca646` — 2026-10-01 00:03 +0530

**decisions.md: candidate #29 FBL - step 2 go and interpretation note recorded verbatim before the run**

Full hash: `6fca646db66caf31462f2029b506e24b40db319f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 254. `ae77d1a` — 2026-10-01 00:03 +0530

**candidate #29 FBL step 2 (dev, run once): E1 delta -0.0044 [-0.0095, +0.0005], E2 (88%) -4.03 pts -> NOT ELIGIBLE; stopping rule applied: 94 A feature testing closed**

Full hash: `ae77d1a416c48449e8970f26e378b2ea816b9815`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 255. `52e7d5e` — 2026-10-05 15:27 +0530

**decisions.md: LaTeX paper scaffold instructions recorded verbatim before starting; note that the prospective amendment is still pending**

Full hash: `52e7d5e5797e8b0d71f7e0beb0f7a80745e6dc87`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 256. `6acb7f9` — 2026-10-05 15:49 +0530

**paper_template: Step 1 FORMAT_NOTES.md (34-paper format survey; IRIS 2026-27 and ISEF 2027 official requirements, verified); decisions.md entry**

Full hash: `6acb7f9c794342bcbce47641b77e9aa77a7b2adf`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 257. `8868647` — 2026-10-05 15:58 +0530

**decisions.md: paper-scaffold instructions (A, B1-B3) recorded verbatim; A not clean (SWPC reports 2026-08-17/18 on disk) - Step 2 not started**

Full hash: `886864757478d96216301e9c1f126686a3999e96`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 258. `b480d22` — 2026-10-05 16:00 +0530

**decisions.md: prospective test - permanent disclosure of the 2026-08-17/18 SWPC reports; start kept at 2026-08-17; amendment (excl.-0817/18 secondary, size rule, Look 2 fallback, by_group secondary, student-run downloads)**

Full hash: `b480d228a2dee0e3fe67d7b250addefba2f8f730`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 259. `983bcae` — 2026-10-05 16:01 +0530

**decisions.md: paper scaffold - F4/F3 example selection rules stated before looking**

Full hash: `983bcaecbe2e3e07d4831ebc7a5e7cd077db6398`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 260. `e3cd1ed` — 2026-10-05 17:07 +0530

**paper_template: Step 2 (checkpoint 2) - 1,097 verified macros, candidate inventory (35 candidates / 56 rows), figures F1-F9, tables T1-T6, checks PASS, MISSING list**

Full hash: `e3cd1edc3ba7481faf056f870b6d1750be001f9b`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 261. `c798248` — 2026-10-05 18:04 +0530

**paper_template: Step 3 (checkpoint 3) - LaTeX template (main.tex, synopsis.tex), Overleaf zip, static checks PASS, VERIFY.md, README; not compiled (no LaTeX)**

Full hash: `c798248c9b1362a9822992cd7f03d7c381f8217e`

```text
- STUDENTS WRITE / WORD LIMIT boxes only; every number a macro (1,138, verify_numbers PASS)
- T7/T8 appendix tables; T6 as longtable; T2/T4/T5 fixes; F8 neutral styles (Path A descriptive)
- check_tex.py: paths/zip, syntax stand-ins, refs, macros, no prose outside boxes, no hand-typed numbers,
  anonymity, chat-only numbers, commits, frozen-spec SHA; mutation-tested
- check_build.py: Step 3f, pending until overleaf_build/main.pdf + main.log exist
- two independent review workflows; all confirmed findings fixed (decisions.md Step 3 entry)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 262. `f86a918` — 2026-10-05 18:25 +0530

**paper_template: Checkpoint 3 answers applied - 2022 scope (never pooled in twins/filter tests), values that include 2022 moved to appendix T9, per-set rho, hypothesis text not shown, 39/50 label**

Full hash: `f86a918a739249a907774fb5729c7968e98de2bc`

```text
- T9 (appendix): Path A 2022 values and 2021-24 totals, C+ 2021-26 combined row, pooled rho; each labelled "includes 2022"
- T1/T2 gate-sensitivity rows labelled "pre-registered sensitivity, includes 2022"; T5 per set only
- F7 title without pooled rho, caption "pooled over sets, includes 2022"; F8 panel (b) test years only
- check_tex: guard that moved values stay out of the main text; references resolved per document
- build_numbers / verify_numbers / check_outputs / check_tex PASS; independent review (3 finders + skeptics): 9 confirmed fixed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 263. `55e5d0e` — 2026-10-05 22:05 +0530

**paper_template: DRAFT_FACTCHECK.md - fact-check of the private Codex draft against HEAD (645 rows: 558 MATCH, 24 OUTDATED, 9 WRONG, 40 UNSUPPORTED, 14 OVERCLAIM); facts and sources only**

Full hash: `55e5d0e75f9375efa1f4f7010ed8cf9550446858`

```text
- decisions.md: user instruction (fact-check, post-hoc incremental table, terms/Aditya-L1 facts, prospective secondary) recorded verbatim first
- 8 section checkers + 8 independent re-verifiers; every fragment verified verbatim and <= 15 words; every row has a source
- the draft's prose is not edited (private draft, not for submission)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 264. `5f66228` — 2026-10-05 22:05 +0530

**incremental_posthoc.py + log: POST-HOC PR-AUC and Brier score of the frozen euv_extra A, C, C_CV models on 2025-26 (378) and the 2021/23/24 held-out test set (306), HARP bootstrap 2,000 seed 0, paired C-A and C_CV-C**

Full hash: `5f662285f5224ccbcfb40c2df94483d73b4f4831`

```text
- logged log-loss/AUC reproduced exactly first (2025-26: A, C, C_CV; test set: C, the only logged model); A and C_CV test-set log-loss/AUC newly computed (POST-HOC)
- frozen models hash-verified, no refitting, no new features; local files only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 265. `3507fe8` — 2026-10-05 22:06 +0530

**paper_template: T10 (POST-HOC) - PR-AUC and Brier score with HARP-bootstrap CIs and paired C-A / C_CV-C for the frozen A, C, C_CV models (2025-26; 2021/23/24 test set); 68 macros; all checks PASS**

Full hash: `3507fe8988663ee472b3895fad9ae0160536f968`

```text
- logged log-loss/AUC reproduced exactly before any new number (incremental_posthoc.log)
- T10 in a new appendix section; Model C box points to it; identifier/caption checks accept T10

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 266. `42a7ff1` — 2026-10-05 22:07 +0530

**paper_template: TERMS.md - 27 verified solar-flare-forecasting terms (one-line definitions, published sources) and 21 Aditya-L1 facts from official ISRO/IUCAA/ISSDC/URSC/PRL pages (1 NOT VERIFIED: MAG resolution)**

Full hash: `42a7ff163318020b90997753a0561f13bc09d7f5`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 267. `5a6d106` — 2026-10-05 22:08 +0530

**decisions.md: prospective pre-registration amendment - dependence-free CV_box twins SECONDARY for Look 1 and the Look 2 fallback (decided by: user), recorded verbatim after confirming no prospective data analysed; open clarifications a-e flagged; template prospective box updated**

Full hash: `5a6d106e451c529102f00b6536e9f261118c253f`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 268. `79e1556` — 2026-10-05 23:52 +0530

**POST-HOC, descriptive: true alarms kept by Model C but removed by C_CV, per set (2025-26 13, test 4, extra 2, 2022 5, dev 9); section 1c/1e counts reproduced first; per-alarm table, group summary and 2025-26 light-curve figure**

Full hash: `79e1556916dcccc03ee0eb581b52fda42fb3fa4f`

```text
- frozen euv_extra fold models and exact thresholds; no new features, refits, tests or rules; no prospective data; no downloads
- independently re-verified (own code, raw SWPC reports): counts, eid lists and 561 row fields identical

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 269. `ddf6891` — 2026-10-06 02:04 +0530

**Step A: missing reading-list papers downloaded from arXiv (11, titles verified, 0 mismatches) + papers_manifest.csv (45 papers: 31 on disk, 11 downloaded, 2 not downloadable, 1 not open access; 1 not identified)**

Full hash: `ddf689114125bf62ef583fc4b3b149ec95d40128`

```text
- arXiv only (>= 3 s between requests); no paywall workaround; wrong doria_rosales file left in place
- decisions.md: user prompt recorded verbatim first; Step A entry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 270. `cec3186` — 2026-10-06 02:33 +0530

**Step B (interim): Section 2 Background and related work (AI-drafted, disclosed): background.tex (~1,199 words, 27 papers on disk), background_claims.csv (121 rows: 2 EXACT, 118 PARAPHRASE, 1 SYNTHESIS), background_keys.txt; main.tex Background box -> \input{sections/background}; deterministic checks PASS; independent verification pending**

Full hash: `cec3186d88120cd40c01686cf21cbab8d28f9275`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 271. `740ece8` — 2026-10-06 03:07 +0530

**Step B: Section 2 independently verified (3 rounds, final 125/125 rows PASS, 0 must-fix); 4 claims removed and ~16 corrected after verifier findings; ~1,203 words, 27 papers on disk (2 EXACT, 122 PARAPHRASE, 1 SYNTHESIS)**

Full hash: `740ece8818672e819d5f41903a29626f1c5da7a6`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 272. `0ac1e3a` — 2026-10-06 03:34 +0530

**Section 2 merged text installed (740ece8 + user-approved chat corrections, AI-drafted, disclosed); claims rebuilt (172 rows: 1 EXACT, 164 PARAPHRASE, 3 SYNTHESIS, 4 PROJECT); one verification round 167 PASS / 1 FAIL (Hu2025 'every measure', left unfixed as instructed) / 4 UNVERIFIED (PROJECT); keys: Crossref journal versions for Kniezewski2024, AndreHoffmann2026, Dissauer2025, Zhong2026**

Full hash: `0ac1e3a193232756649916138ae80f90ffc67552`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 273. `4caf989` — 2026-10-06 03:38 +0530

**Hu2025 row FAIL from 0ac1e3a resolved (wording by Claude (chat), user-approved); rows 130-131 updated (PDF p.26); fresh verifier 2/2 PASS; deterministic checks PASS**

Full hash: `4caf9893baa1a8926d17c4fdd56879e9c35e7de3`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 274. `f2cb21d` — 2026-10-05 23:44 +0000

**decisions.md: rule for colour F3/F4 and image gallery recorded before selection (illustration only)**

Full hash: `f2cb21d9e8bd580a5d670c905bb622d6ca0577de`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 275. `bc6c4e8` — 2026-10-05 23:54 +0000

**decisions.md: gallery image rule amended to nearest VALID frame (one invalid black frame); pairs unchanged**

Full hash: `bc6c4e825b32b8bcd6cba39ba9d411bfad3cea46`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 276. `89db76e` — 2026-10-05 23:57 +0000

**Colour image figures: F3_cvbox_color, F4_twin_pair_color (same 983bcae pair/episode), F10_gallery (rule f2cb21d, frame rule bc6c4e8); illustration only, by Claude (AI, chat); stored CV_box reproduced to 1e-12**

Full hash: `89db76eae929eb7a6bf1b8b9675e36a0df454591`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 277. `8de7c2e` — 2026-10-06 04:43 +0000

**F2/F9: remove in-image AI credit line (IRIS confirmed not required; AI use stays in the paper's disclosure section)**

Full hash: `8de7c2ea76a333b209237acf1d74521dc37b1280`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 278. `f48c810` — 2026-10-07 10:49 +0530

**Physics study guide and fix list for the students (AI use, drafted by Claude Code; 70 page-cited passages verified against the PDFs); ISEF AI-table summary; no paper text changed**

Full hash: `f48c810ba2fc2415a33c6f6c8361e306d15b16eb`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 279. `daff479` — 2026-10-09 22:26 +0530

**Look 1 runs early: amendment of run date and end date only (E = 2026-09-03 23:00 TAI; decided by: user), recorded before any prospective download; metadata-only coverage check script and log; dependence-free secondary dropped from Look 1 (a-e undecided)**

Full hash: `daff4796f5f3234723c04c4027a6b97d06ea239c`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 280. `b8ad61d` — 2026-10-09 22:33 +0530

**Look 1 (early): prospective_look1.py — student-run download and label-blind build steps (dryrun, swpc, goes, sharp, cohort, plan, download, verify); refuses without RUN_BY; logs who ran each step with file counts, sizes and SHA-256 (code by Claude Code (AI); nothing run)**

Full hash: `b8ad61da181fe839379ca2326edfacd6dfdbcd96`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 281. `21ed533` — 2026-10-09 23:17 +0530

**prospective_look1.py: RUN_BY accepts only "Lokesh" or "Kyros" (exact, case-sensitive); requested by the students before any step was run**

Full hash: `21ed5331639ee40fdcc1beab9b2b6abcde9c47b6`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 282. `7d9be38` — 2026-10-10 01:41 +0530

**Look 1 analysis code committed before any label is read: prospective_look1_analysis.py (steps 8-10: label-blind compute, label-blind size rule, run-once analysis; registered code only) + reproduction 40/40 PASS (log committed; closure pinned); D1-D11 decided by the user (D3a = TAI); run sheet steps 8-10; no prospective data used**

Full hash: `7d9be3835676318cbd72afbccb3633c78f624dda`

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### 283. `9450245` — 2026-10-11 17:19 +0000

**Post-hoc region checks of TEST 1, TEST 2 thresholds file, number sources; add all working files**

Full hash: `9450245b01fa5ad2af631bb3bcfe3a8c46460ef4`

```text
- posthoc_region_checks.py/.log: POST-HOC region-level sign test (14/18 HARPs; p = 0.031, ties against),
  leave-one-true-HARP-out ratio 2.47-3.90, paired estimate 2.86 [1.67, 5.32]; on already-analysed
  2025-26 data only (no t >= 2026-08-17). Code by Claude (AI) at the user's request.
- data/euv_confirm/thresholds.json: TEST 2 thresholds copied verbatim from euv_confirm_tests.log:17
  (data/ is gitignored, so this file is not tracked; recorded in decisions.md).
- paper_template/numbers_sources.csv: 10 rows tracing the new numbers to their logs.
- decisions.md: dated 2026-10-11 entry recording the above as POST-HOC.
- Also commits all previously untracked working files (figures, paper drafts, synopsis, Overleaf zip,
  notes) at the user's request ("commit everything"). No frozen file changed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
