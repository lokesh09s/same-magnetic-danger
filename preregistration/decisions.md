# Decisions

## 2026-09-21 — initial dataset build (January 2014)

- **Hourly sampling via JSOC `@1h`**: the query `hmi.sharp_cea_720s[][...@1h]` returns records
  that exist at hourly slots. No interpolation. 10145 of 10268 expected hourly records present
  (123 missing, counted per-HARP over each HARP's own first→last span).
- **TAI→UTC with astropy**: `Time(..., scale="tai").utc`. The `_TAI` suffix is never just stripped.
  `2014.01.01_00:00:00_TAI` = `2013-12-31 23:59:25 UTC` (35 s). Both columns stored; all window
  comparisons in UTC.
- **Flare catalogue**: HEK, `frm_name = SWPC` only — one operational catalogue, no cross-pipeline
  duplicates of the same physical flare. 193 retrieved, 0 duplicates on
  (start_time, noaa_ar, goes_class), 30 M1+ after local numeric parsing.
- **Broad fetch, local filter**: GOES class parsed to a numeric flux (`M1.5 → 1.5e-5`) in Python
  and thresholded at `>= 1e-5`. No catalogue-side `GOESCls > "M1.0"` — string comparison there
  mishandles the boundary.
- **Padded window**: first SHARP time − 48 h to last + 24 h, so the prev-48h and next-24h windows
  are complete at both edges.
- **NOAA mapping**: `NOAA_ARS` parsed into a list → status single / multiple / missing.
  Missing rows kept in the raw CSV, excluded from the labelled CSV (2473 rows dropped):
  blank means "association unknown", not "no flare"; labelling them 0 injects false negatives.
- **Multi-region HARPs (ANY rule)**: positive if *any* associated NOAA region flares; previous
  counts are the deduplicated union over associated regions. Dropping them would systematically
  remove the most magnetically complex patches.
- **Windows (half-open)**: `next24 = (t, t+24h]`, `prev48 = [t-48h, t)`.
- **Missing values**: `drms` already returns JSOC MISSING as NaN for float keywords, so no
  magnitude-based sentinel mask is applied — USFLUX/TOTPOT are legitimately ~1e22. Reported only;
  no filling or dropping (modelling decision, deferred).
- **Date range is a parameter**: `python build_dataset.py START END`, defaults 2014-01-01 2014-02-01.

## 2026-09-21 — verification session

### Part 1 — date discrepancy (RESOLVED, no bug)
`build_dataset.py 2014-02-01 2014-03-01` produces
`hmi.sharp_cea_720s[][2014.02.01_TAI-2014.03.01_TAI@1h]` — reproduced directly.
The January query string reported came from a **no-argument** run, which uses the
defaults `2014-01-01 2014-02-01`. No offset, no stale string, argument order is (START, END).
Mitigations added so this can never be ambiguous again:
- every run prints a banner with `argv`, the parsed CLI dates, the JSOC date literals and the
  full record-set string, *before* querying;
- dates are validated with `strptime`, `START < END` is enforced, and a wrong argument count
  exits with a usage message instead of silently falling back to the defaults.
- START is inclusive, END is exclusive.
- SWPC flare fetching moved to `flares.py` so `checks.py` and `build_dataset.py` cannot drift apart.

### Part 2 — sanity checks (`checks.py`, all PASS, January 2014)
- **CHECK 1 PASS** — X1.2 at 2014-01-07 18:04 UTC, NOAA 11944 → HARP 3563. All 21 rows present in
  `[t0-24h, t0)` are labelled 1; the first rows after t0 are 0. 7 of the 11 rows earlier than
  t0−24h are also 1, correctly, because other M1+ flares from 11944 fall inside *their* windows.
  The visible gaps (−25.1h → −22.1h, −13.1h → −11.1h) are genuinely absent hourly records, not
  dropped joins — consistent with the 123 missing hours reported for January.
- **CHECK 2 PASS** — median USFLUX 4.02e22 (positive) vs 5.76e21 (negative), **6.98×**;
  median TOTUSJH 3040 vs 412, **7.39×**. Distributions separate in the expected direction.
- **CHECK 3** — 2715 rows but only **23 distinct HARPNUMs**, 5 of which contain a positive row.
  Rows per HARP: mean 118, median 141, min 21, max 178. The effective independent sample size is
  the number of regions, not the number of rows; any train/test split must be grouped by HARPNUM.
- **CHECK 4 PASS** — missing-mapping rows have median USFLUX 1.63e20 vs 5.91e21 for mapped rows
  (**0.028×**), and **0.0%** of them exceed the mapped median. They are minor patches that never
  received a NOAA designation. Excluding them is not discarding real data.

## 2026-09-21 — flare/HARP join defect, and the decisions taken because of it

### The defect (found by me, mid-run)
Whole years were producing zero M1+ positives while raw SHARP row counts were *rising*
(2021-12: 0 positives from 2307 rows; 2022-01: 0 from 1790; 2022-03: 0 from 1538). A genuine
solar-minimum zero comes with *low* row counts, so this was the opposite signature.

Cause: HEK returns the flares, but with `ar_noaanum = 0`. March 2022 — 258 SWPC flares, of which
**246 carry no usable region number**; every M1+ flare that month has `ar_noaanum = 0`. The code
dropped flares whose region was *NaN*, but `0` is a valid integer: it survived, joined against
NOAA region "0", matched no HARP, and emitted a clean, silent `0` label. False negatives, not
quiet Sun.

January 2014 is unaffected (27 M1+ with real region numbers), which is exactly why CHECK 1–4 all
passed. **CHECK 1 structurally could not catch this** — it only exercises a month where the join
works. That is the lesson: a check that samples one good month certifies nothing about the rest.

### Decisions

**1. `ar_noaanum <= 0` or NaN = UNKNOWN region; never joined.  (decided by: user, approved 2026-09-21)**
Reason: same principle already agreed for `noaa_mapping_status = "missing"` — absence of an
association is not evidence of absence of a flare. Joining or zero-labelling them injects false
negatives. They are excluded from the join and *counted* per year instead.
Consequence: these are label noise (missed positives) even in years that pass the threshold, so
the count is reported per year, not just per failing year.
Implementation: `flares.py`; the unknown M1+ count is computed *before* the drop and carried on
`m1.attrs["n_unknown_m1"]`.

**2. Usable-year threshold: >= 90% of M1+ flares must carry a usable region number.
   (decided by: user; fixed 2026-09-21 BEFORE any per-year results were seen)**
Reason: pre-registering the threshold prevents fitting it to whatever the data turned out to be.
**No catalogue-source switch, and no mixing of catalogue methods across years** — the train/test
split is chronological, so a per-year method change would confound period with method.
Table: PENDING: per-year join report (`data/join_report.csv`, running).

**3. Flare catalogue stays SWPC via HEK.  (decided by: user)**
No source switch while the join defect is being characterised. SWAN-SF is to be used as a
**cross-check only**, not as a label source. A check against the original SWPC event lists is
**PENDING** — not yet specified or run; nothing in this repo depends on it yet.

**4. `QUALITY == 0` stays.  (decided by: user; I asked, having found whole months excluded)**
May 2016: all 4907 raw records carry bit `0x00000080` = `QUAL_TEMPERROR`, so the month yields
zero rows. What JSOC actually documents
(http://jsoc.stanford.edu/doc/data/hmi/Quality_Bits/QUALITY.notes, modified 2017-09-19), verbatim:
  "In cases where 45s or 720s data exists and there is a code error detected we will set bit 0x80
   for existing records while they are waiting replacement with reprocesed data."
It enumerates exactly one case: **Sept 2017** (CALVER64 / modL, pending reprocessing of
`hmi.S_720s`, "should not be visible once the reprocessing is done").
**No documented case covers May 2016**, and those records still carried `0x80` when queried on
2026-09-21 — so we have no JSOC statement that they were reprocessed, and none explaining the flag.
Correction to my earlier framing: I initially read the bit *name* as suggesting the data were
fine. That was wrong and the user corrected it. `0x80` is a flagged processing error; it is not
evidence about the underlying data in either direction. We do not infer quality from a bit name.
Bit meanings are quoted verbatim with their JSOC source in `quality_report.py`.
Table: PENDING: per-month QUALITY counts (`quality_report.py`, runs after the chunk run).

**5. CHECK 5 — per-year join coverage.  (decided by: user)**
Fails any year below the 90% threshold. M1+ only. Reports per year: M1+ retrieved,
M1+ with unknown region, % usable region, % joining >= 1 HARP, positive rows, distinct positive
HARPs. The last two are for the user to fix the train/val/test split before any model is trained.
Reuses `join_report.build()` rather than duplicating the logic.
Table: PENDING: same as decision 2.

### Implementation choices (decided by: me — mechanical, no science content)
- **Empty-frame guards.** Two crashes, both legitimate-empty rather than buggy:
  (a) May 2016 — every record fails `QUALITY == 0`, so `df.apply` on an empty frame returned no
  columns; (b) Nov 2019 — deep solar minimum, HEK returned *zero* SWPC events, so the result table
  had no columns at all. Both now yield an empty/zero-label chunk, which is the correct answer.
  Neither guard changes any filter or window.
- **Retry on transient errors only** (`run_all.py`): timeouts, connection resets, 502/503 —
  5 attempts, 60s * attempt backoff. Hard errors still abort immediately, so real bugs are not
  papered over by retries. Added after four JSOC interruptions on the 2020-12 chunk alone.
- **Bug fixed while reporting:** the "duplicates removed" line was conflating deduplication with
  the unknown-region drops (it read 246 for March 2022, when 0 were duplicates). Counted separately now.
- **Bug fixed after the user's note:** once `fetch` began dropping unknown-region flares, the join
  report would have counted zero unknowns for every year — showing 100% usable everywhere and
  passing CHECK 5 silently. Caught only because the user asked for the unknown count per usable
  year. The count is now taken before the drop.
- **Date banner / CLI validation** (earlier today, see previous entry) — kept.

### Not yet done
- PENDING: per-year join table (decisions 2 and 5)
- PENDING: per-month QUALITY table (decision 4)
- PENDING: SWPC originals cross-check (decision 3)
- No relabelling has been run. Raw SHARP chunk files are unaffected by any of this and remain
  valid; only the labelled files for low-coverage years are suspect.

## 2026-09-21 — flare source switched to SWPC originals; multi-region and missing-day rules

### Evidence that prompted the switch (found by me; `swpc_check.py`)
HEK copies SWPC's catalogue but loses region numbers that SWPC recorded:

| month   | M1+ SWPC / HEK | matched (time+class) | SWPC has Reg# | HEK usable region | region agrees |
|---------|----------------|----------------------|---------------|-------------------|---------------|
| 2014-03 | 23 / 23        | 23                   | 23            | 23                | 23 / 23       |
| 2022-03 | 14 / 14        | 14                   | 13            | **0**             | **0 / 14**    |

The events are the same flares; only the region field is lost, and only in HEK.

### Decision A — flare labels from SWPC original daily event reports, ALL years 2010–2024
**(decided by: user, 2026-09-21)**
Reason: it is the same catalogue HEK copies, and it keeps the region numbers HEK drops in later
years. **One source for the whole range, never switched per year** — the split is chronological,
so a per-year source change would confound period with catalogue.
Source: NCEI archive of SWPC "Edited Events",
`https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/daily_reports/solar_event_reports/`.
Rules (`swpc.py`, identical for every year):
- XRA lines only; begin time = Begin column on the report date, UTC.
- **Region: one explicit rule, `Reg# < 10000 -> Reg# + 10000`**, nothing else. Blank Reg# = unknown,
  never joined (same principle as decision 1 of the previous entry).
- **Dedup on (begin time, GOES class)**, logged per year — guards against one flare listed from two
  GOES satellites (e.g. G16 and G18). If one copy has a region and the other doesn't, the copy with
  the region is kept.
- The HEK-based labels are **kept** in `data/labels_hek/` for comparison, not deleted.
Preconditions set by the user before relabelling:
1. Validation, SWPC vs HEK: flares, times, class, region, one month per year 2011–2019.
   Sample fixed in advance by me: **March of each year**. Reported **all-class**, and **M1+-only**
   where there are enough events. PENDING: validation table.
2. % of converted SWPC regions found in SHARP `NOAA_ARS` for the same period. PENDING: table.
3. Dedup removals per year. PENDING: table.
Then: relabel all 176 chunks from cached raw (no JSOC re-download), rerun checks 1–5 against the
SWPC source with the **same 90% threshold**, regenerate the per-year table.
PENDING: post-relabel per-year table.

Regression evidence that relabelling from cache is faithful (me): with `FLARE_SOURCE=hek`,
labels regenerated from the cached raw files are **byte-identical** to the original HEK labels for
2014-01 and 2019-11 (the latter has only single-region mappings, the case where `NOAA_ARS` could
otherwise read back from CSV as a float and silently lose its region). A first run of this test
falsely "passed" because the run crashed and I compared the archive with itself; the test now
deletes its output first, so a crash cannot pass.

### Decision B — multi-region HARPs  (decided by: user, 2026-09-21)
Prompted by the 2024 audit: 80% of 2024 positive rows (3,656 / 4,596) came from multi-region HARPs;
positive rate 4.51% on single-region rows vs 31.5% on multi-region rows; HARPs of up to 11 NOAA
regions; mean regions per multi-region HARP 3.79 in 2024 vs 2.0–2.8 in 2010–2022. Under the ANY rule
an 11-region patch is positive whenever any one of its regions flares.
- **Primary analysis: single-region HARPs only (`noaa_ar_count == 1`).**
- **Robustness: repeat with the ANY rule on all HARPs.**
- **Fallback, fixed now before results: if single-region gives < 40 positive HARPs in the candidate
  test years, use `noaa_ar_count <= 2` instead.**
- **The dataset is NOT filtered.** A `region_group` column ("1", "2", "3+") is added so every analysis
  selects its own subset from one file.
Note (me): the fallback depends on "candidate test years", which are not chosen yet. The per-year
counts below are reported for all three groups so the fallback can be evaluated once the split is
fixed; it cannot be evaluated before then.
PENDING: per year, rows / positives / positive HARPs for (a) single-region, (b) <= 2, (c) all.

### Decision C — days with no SWPC report  (decided by: user, 2026-09-21)
**Any row whose 24h label window `(t, t+24h]` overlaps a day with no SWPC report gets label =
unknown and is excluded from the labelled file.** Count reported per year.
Reason: a missing report means "flares unknown", not "no flares"; labelling those rows 0 would be
false negatives — same principle as the missing-mapping and unknown-region rules.
Implementation (me): a missing day is one the NCEI archive returns 404 for (listed in
`data/swpc_events/_missing_days.txt`). Excluded rows are written to
`data/excluded_missing_swpc_<chunk>.csv` so the exclusion is auditable, not silent.
Note (me): the rule as specified covers the forward 24h label window. The backward 48h window
(`n_*_prev_48h` features) can also overlap a missing day, which would *undercount* prior flares.
That is a feature, not a label, and I have not changed it — flagged for your decision.
PENDING: excluded rows per year.

## 2026-09-21 — fallback timing, and incomplete flare history  (decided by: user)

**Fallback (Decision B).** Applied by the user when choosing the split, from the per-year
`region_group` counts, **before any model is trained**. Not applied in this dataset build.

**Decision D — `history_incomplete` column.**
`history_incomplete = True` if the backward window `(t-48h, t]` overlaps a day with no SWPC report.
In those rows `n_flares_prev_48h` and `n_C/M/X_prev_48h` may be undercounted.
- **Rows are kept** — they remain usable for **gate training on SHARP features only**.
- **Excluded from the cohort analysis**, because flare history is its mandatory control.
Reason: a missing report makes the history unknown, not zero; keeping the SHARP features avoids
throwing away magnetic data that is unaffected.
Implementation (me): overlap of `(t-48h, t]` with day `[D, D+1d)` is `t-48h < D+1d and t >= D`.
The counting window itself is `[t-48h, t)`; the two differ only when `t` falls exactly on midnight,
which cannot happen here (hourly `T_REC` converts to `hh:59:2x` UTC), so the flag and the counts
cover the same span. HEK comparison labels carry `history_incomplete = False` — the missing-day
rules apply to the SWPC source only.
PENDING: `history_incomplete` rows per year.

## 2026-09-21 — validation verdict; empty SWPC reports resolved with GOES XRS  (decided by: user)

### Validation: PASS — SWPC original event reports are the label source
March 2011–2019, SWPC vs HEK (`validate_swpc.py`, sample fixed in advance):
- 1,281 of 1,285 SWPC events matched HEK on begin time; **class agreement 100%** on matched pairs.
- **Region agreement: 1 disagreement in ~1,100** pairs (2011-03-09 C5.0: SWPC 11169, HEK 11165).
- **M1+-only** (months with >= 5 SWPC M1+ — fixed in advance): 2011, 2012, 2014, 2015 → 96 of 97
  matched, class and region 100% on matched.
- 0 duplicates removed in every sampled month.
- Found in passing (me): the same flare can carry different begin times in the two catalogues
  (2015-03-02 M1.1 AR 12290: 08:52 HEK vs 09:37 SWPC; 2012-03-29 C7.7: 72 min; 2013-03-10 B6.7: 1 h).
  Rare, but exactly what flips a label at the 24h edge. SWPC's time is used, consistently.
- 2014-03: 3 flares where SWPC has a region and HEK does not — HEK's region loss predates 2020.

### The gap found during validation (me)
The NCEI archive has a file for **every** day 2010-04-29 → 2025-01-02 (5,363 files, **0 × 404**), so
decisions C and D as first implemented would exclude nothing. But many files read only
`NO EVENT REPORTS.` — 39 (2010), 2 each (2011–13), 25 (2016), 79 (2017), 196 (2018), 236 (2019),
193 (2020), 61 (2021). Some are genuinely quiet; **2017-03-14 is empty in SWPC while HEK lists 32
flares.** The file alone cannot distinguish "no flares" from "report not compiled".
I offered three options; **the user rejected all three** (genuine-zero, all-missing, HEK-flagged).

### Decision E — GOES XRS 1–8 Å flux decides what an empty-report day means
For each empty-report day, take the **GOES XRS 1–8 Å daily maximum, 1-minute data, primary
satellite**:
- **max >= 1e-5 W/m² (M1)** → day is **MISSING for labels**: exclude rows whose `(t, t+24h]`
  overlaps it (decision C, now driven by this rule).
- **max >= 1e-6 W/m² (C1)** → day is **incomplete for history**: `history_incomplete = True` for rows
  whose `(t-48h, t]` overlaps it (decision D, now driven by this rule).
- **otherwise** → **genuine zero**: the day is quiet and the empty report is trusted.
Reason: the X-ray flux is the physical measurement flare classes are defined from, so it answers
directly whether a flare of the relevant class could have been missed — independent of any
catalogue. It does not depend on HEK.
Note (me): an M1 day is also a C1 day, so it sets both flags.
PENDING: per year — empty days, days flagged missing (M1), days flagged incomplete (C1).

### Decision F — history control is C/M/X only
`n_B` is **not** a history feature; the flare-history control uses `n_C_prev_48h`, `n_M_prev_48h`,
`n_X_prev_48h` only. (`n_flares_prev_48h` still counts all classes — see note.)
Note (me): the labelled file has never had an `n_B_prev_48h` column; B flares only entered
through the all-class total `n_flares_prev_48h`. Flagged for the user: if the total should also
exclude B, that is a change to a feature definition, and I have not made it.

### Decision G — HEK stays cross-check only
HEK flare counts on SWPC-empty days are reported **as a sanity check against the GOES rule**, never
used to flag days or set labels. PENDING: HEK-on-empty-days vs GOES-rule comparison.

Then: relabel all 176 chunks. PENDING: post-relabel tables.

## 2026-09-21 — GOES data gaps and the flare-history control  (decided by: user)

Context (me): testing the GOES rule on 2017-03-14 (SWPC report empty, HEK lists 32 flares at
B2–B5) — GOES-15 and GOES-16 both show an A-level day (max 1.9e-8 and 2.6e-8 W/m², all minutes,
flagged or not), ~10x below B2. The SWPC empty report was correct; HEK's entries for that day do
not correspond to anything in the X-ray flux. First direct evidence that HEK, used as the
cross-check, can be wrong in the opposite direction from the gap it was meant to catch.

**Decision H — no primary GOES data on a day.** Fall back to the **secondary** satellite
(Table 11, secondary column). If **neither** has data, the day is **missing**: label exclusion
**and** `history_incomplete`.

**Decision I — partial coverage.** Primary gaps are **filled with secondary `good_data` minutes**.
If combined coverage is **< 90% of the day AND the day would otherwise be "genuine zero"**, the day
is **missing** (label exclusion + `history_incomplete`). Days reaching M1 or C1 on partial data keep
that classification — a flare seen in part of a day is still a flare.
Reason: a quiet reading over part of a day cannot rule out a flare in the unseen part; a flare
reading over part of a day already establishes one.
PENDING: coverage distribution, and how many days this rule flags.

**Decision J — `n_flares_prev_48h`.** **Kept in the file, excluded from all analysis.** The flare
history control is **`n_C_prev_48h`, `n_M_prev_48h`, `n_X_prev_48h` only.**
Reason: the total includes B flares, which decision F removed from the history control. Keeping the
column preserves the raw count; excluding it keeps B out of every analysis.

Implementation (me): the secondary column of Table 11 is transcribed alongside the primary; minutes
are combined per UTC minute (primary where good, else secondary where good), so a minute is never
counted twice.

## 2026-09-21 — RESULTS: GOES empty-day table and HEK sanity check (fills PENDING for E, H, I, G)

`goes_xrs.py` → `data/goes_empty_days.csv`; 835 empty-report days, 1,510 GOES files.
**No empty-report day reaches M1** — no M1+ flare is hidden behind an empty SWPC report in 2010–2024.

| year | empty | genuine zero | incomplete C1 | missing: no data (H) | missing: low cov (I) | label-missing | history-incomplete |
|------|------:|-----:|---:|---:|---:|---:|---:|
| 2010 |  39 |  34 | 0 | 5 | 0 | 5 | 5 |
| 2011 |   2 |   2 | 0 | 0 | 0 | 0 | 0 |
| 2012 |   2 |   1 | 1 | 0 | 0 | 0 | 1 |
| 2013 |   2 |   2 | 0 | 0 | 0 | 0 | 0 |
| 2016 |  25 |  24 | 0 | 0 | 1 | 1 | 1 |
| 2017 |  79 |  78 | 1 | 0 | 0 | 0 | 1 |
| 2018 | 196 | 195 | 0 | 0 | 1 | 1 | 1 |
| 2019 | 236 | 235 | 0 | 0 | 1 | 1 | 1 |
| 2020 | 193 | 192 | 1 | 0 | 0 | 0 | 1 |
| 2021 |  61 |  61 | 0 | 0 | 0 | 0 | 0 |
| **all** | **835** | **824** | **3** | **5** | **3** | **8** | **11** |

- **H (no data):** 2010-06-15, 08-22, 08-23, 12-18, 12-25 — all inside 2010 windows where Table 11 lists
  **no secondary satellite**, so no fallback existed.
- **I (coverage):** 27 days had primary coverage < 90%; the secondary fill brought 19 above 90%, leaving 8
  (the 5 above + 2016-09-12 at 89.9%, 2018-07-27 at 38.0%, 2019-09-25 at 87.6% — all quiet, so missing).
  Coverage distribution: 756 days >= 99%, 49 at 95–99%, 22 at 90–95%, 2 at 80–90%, 6 below 50%.
- **C1 days:** 2012-01-29, 2017-07-20, 2020-09-26.

**HEK sanity check (decision G):** HEK lists flares on only 3 empty days (2017-03-08, 03-09, 03-14),
45 B-class, 0 C, 0 M1+. On all three GOES has 100% coverage and daily maxima 9.6e-8, 7.1e-8, 2.6e-8 —
**all below B1.0**, so HEK's B2–B5 entries are inconsistent with the measured flux. Conversely, GOES
finds C1+ on 3 days where HEK lists nothing. The two agree on the result that matters (0 M1+ on
empty days); where they disagree, the X-ray flux shows HEK is wrong. Supports keeping HEK
cross-check only.

## 2026-09-21 — OPEN: SWPC flare-class scale changes at end of 2019 (found by me; awaiting user)
NCEI readme §3.1: pre-GOES-16 operational fluxes carried SWPC scaling factors (0.7 for XRS-B) that
the science data removes; "flare indices for the operational data were reported as 42% (1.0/0.7)
smaller than for the science GOES 13-15 and GOES-R data". SWPC's own `Obs` column shows its XRA events
came from **GOES-13/14/15 through 2019-11** and **GOES-16/18 from 2019-12**. So "SWPC class >= M1.0"
means **1.43e-5 W/m² true flux before 2019-12 and 1.0e-5 after** — a 30% drop in the label threshold
across the chronological split. (Table 11's GOES-16 primary date, 2017-02-07, is for science data,
not SWPC's operational source.)
Not affected: decision E — no empty day reached even 1.0e-5, so the result above holds on either scale.
Options put to the user: (a) harmonise to true irradiance per event from its `Obs` satellite
[recommended by me]; (b) harmonise to the old scale; (c) leave as reported.
**Relabel is on hold until decided.**

## 2026-09-21 — Decision K: flare-class scale harmonised to the OLD operational scale  (decided by: user)

Resolves the open item above. **Option (b).**
Reason (user): comparability with Bobra & Couvidat (2015), SWAN-SF, and published SWPC forecast
verification, all of which use the old operational scale for 2010–2019.

- **SWPC events from GOES-16/17/18/19 (per each event's `Obs` column): flux × 0.7 before classifying.**
  Events from GOES-13/14/15 are used **as reported**. The satellite is read per event, never inferred
  from the date.
- **Applies to labels AND to the `n_C/M/X_prev_48h` history features** — one scale for everything.
- **GOES science-flux thresholds (true flux), all years:** **M1 = 1.43e-5 W/m², C1 = 1.43e-6 W/m²** —
  used by decision E (empty-day rule) and by the March 2011–2019 completeness check.
  Empty-day C1 flags re-derived at 1.43e-6.
- **Report per year how many events changed class under the conversion.**

Implementation notes (me):
- The reported class and flux are kept alongside the harmonised ones (`goes_class_reported`,
  `flux_reported`), so the conversion is auditable per event.
- Dedup stays on (begin time, **reported** class), as specified earlier — dedup identifies the same
  physical listing, which is a property of the report, not of the scale.
- Consequence worth knowing: on the harmonised scale a GOES-16/18-era event needs a reported class of
  **>= M1.5** to be M1+ (M1.4 × 0.7 = 9.8e-6 = C9.8; M1.5 × 0.7 = 1.05e-5 = M1.0). The same applies
  at the C1 boundary for history counts.
- The thresholds are used exactly as given (1.43e-5, 1.43e-6); 1e-5/0.7 = 1.4286e-5, so the given
  value is 0.1% above the exact conversion. Stated for completeness; no effect on any class boundary,
  since SWPC reports one decimal place.

## 2026-09-21 — RESULTS: relabel on SWPC originals, old operational scale (fills PENDING for A, B, C, D, K)

All 176 chunks relabelled from cached raw SHARP (no JSOC re-download). HEK-era labels kept in
`data/labels_hek/`.

**Scale conversion (decision K), per year** (`data/scale_conversion_report.csv`): 2010–2018 no events
converted (all GOES-13/14/15). Converted from GOES-16/18 and class changes:
2019: 3 / 0 · 2020: 550 / 121 · 2021: 2,064 / 470 · 2022: 3,131 / 590 · 2023: 3,213 / 434 ·
2024: 3,765 / 494. M1+ as reported → harmonised: 2020 2→1, 2021 29→16, 2022 195→117,
2023 365→202, **2024 935→545** (−42%). Part of the late-period rise in positives was the scale.
Also: 5 XRA events attributed to `SDO` (none M1+) kept as reported, counted `scale_unverified`
(decision K does not cover them); 2 events with impossible begin times skipped (all B-class, 2020).

**Empty-day flags at decision-K thresholds:** 2 days moved C1 → genuine zero (2012-01-29,
2020-09-26; peaks between 1.0e-6 and 1.43e-6). Final: 8 label-missing, 9 history-incomplete days.
Max peak on any empty day: 1.95e-6.

**Whole range:** 255,292 labelled rows (255,460 before the missing-day rule; −168), **10,146 positives
(3.97%)**, 2,053 HARPs, 254 with a positive.

**Missing-day rules (C, D), per year:** excluded — 2010: 168, all other years 0.
history_incomplete — 2010: 224, 2017: 56 (the 2017-07-20 C1 day), all other years 0.
The 3 low-coverage missing days (2016-09-12, 2018-07-27, 2019-09-25) exclude 0 rows because no labelled
row lies within 24h/48h of them — verified against the pre-exclusion row set. The 2017-07-20 C1 day
keeps its 14 label-window rows, as specified (C1 marks history incomplete, not the label missing).

**Per year, region subsets (decision B)** — rows / positives / positive HARPs:

| year | single (primary) | <= 2 (fallback) | all (robustness) |
|------|------------------|-----------------|------------------|
| 2010 |  7,134 /  61 /  3 |  7,805 /    81 /  4 |  7,805 /    81 /  4 |
| 2011 | 17,311 / 484 / 10 | 21,996 /   657 / 17 | 23,915 /   747 / 22 |
| 2012 | 17,008 / 183 /  6 | 21,703 /   485 / 14 | 23,100 /   781 / 21 |
| 2013 | 21,924 / 454 / 17 | 25,711 /   602 / 23 | 28,024 /   790 / 29 |
| 2014 | 17,215 / 568 / 13 | 21,819 /   761 / 17 | 25,475 / 1,273 / 30 |
| 2015 | 19,555 / 569 / 12 | 22,973 /   618 / 15 | 24,421 /   715 / 17 |
| 2016 |  4,637 /   0 /  0 |  5,200 /    67 /  1 |  5,329 /    67 /  1 |
| 2017 |  4,784 / 124 /  3 |  5,233 /   124 /  3 |  5,233 /   124 /  3 |
| 2018 |  3,472 /   0 /  0 |  3,472 /     0 /  0 |  3,472 /     0 /  0 |
| 2019 |  2,128 /   0 /  0 |  2,128 /     0 /  0 |  2,128 /     0 /  0 |
| 2020 |  4,240 /   0 /  0 |  4,331 /     0 /  0 |  4,481 /     0 /  0 |
| 2021 | 10,940 / 134 /  5 | 11,958 /   156 /  6 | 12,386 /   178 /  7 |
| 2022 | 18,536 / 246 /  9 | 22,218 /   453 / 15 | 24,685 /   695 / 20 |
| 2023 | 21,659 / 420 / 15 | 27,080 /   772 / 25 | 32,367 / 1,337 / 44 |
| 2024 | 20,863 / 666 / 16 | 25,725 / 1,307 / 27 | 32,471 / 3,358 / 57 |

Positive rate, all rows: 2014 5.00%, 2024 10.34% (was 14.15% on HEK before harmonisation).

**Checks on SWPC (January 2014 file for 1–4):**
- CHECK 1 PASS — X1.2 2014-01-07 18:04, NOAA 11944 → HARP 3563; all 21 rows in [t0−24h, t0) = 1.
- CHECK 2 PASS — median USFLUX positive/negative **12.87×** (HEK: 6.98×), TOTUSJH **15.87×** (HEK: 7.39×).
- CHECK 3 — 23 HARPs, 5 with a positive (descriptive).
- CHECK 4 PASS — unchanged (does not depend on flare source).
- **CHECK 5 FAIL — 2020 only.** 2020 has exactly **1** M1+ flare (harmonised) and SWPC gives it no region:
  0 of 1 usable → below the pre-registered 90%. Reported as a FAIL; the rule was not changed.
  Maximum label cost: one missed positive episode in a year that is otherwise all zeros.
  Whether a percentage threshold should apply to a one-flare year is the user's decision.
  All other years with M1+ flares pass (2021 100%, 2022 90.6%, 2023 97.5%, 2024 96.0%).

**Per-year join table (SWPC)** (`data/join_report_swpc.csv`): %usable 93.8–100% in every year with
>= 8 M1+ flares; `%in_SHARP` 100% except 2014 (91.7%: 16 M1+ flares with a region no HARP contains)
and 2024 (99.6%); dups removed per year 0–5.

## 2026-09-21 — RESULT: completeness check, GOES M1+ peaks vs SWPC (report only; no label changes)

`completeness_check.py`, March 2011–2019. Rules fixed before running (me): a GOES M1+ peak is a run of
good minutes >= 1.43e-5 W/m² true flux (old-scale M1, decision K), primary with secondary fill; runs
<= 5 min apart are merged; a match is an SWPC harmonised M1+ event whose peak (begin if peak missing)
is within ±30 min.

| month | GOES M1+ peaks | matched | unmatched | SWPC M1+ | GOES coverage |
|-------|---:|---:|---:|---:|---:|
| 2011-03 | 24 | 22 | 2 | 22 | 94.6% |
| 2012-03 | 21 | 21 | 0 | 22 | 86.3% |
| 2013-03 |  3 |  3 | 0 |  3 | 87.5% |
| 2014-03 | 22 | 22 | 0 | 23 | 94.4% |
| 2015-03 | 29 | 29 | 0 | 29 | 97.9% |
| 2016–2019-03 | 0 | 0 | 0 | 0 | 95.8–100% |
| **total** | **99** | **97** | **2** | | |

The 2 unmatched peaks (2011-03-08 21:41 and 22:23, both old-scale M1.0) lie on the decay of SWPC's
M1.4 in AR 11165 (begin 19:46, peak 20:16, end 21:19): the old-scale flux drifts from 1.36e-5 at 20:30
to ~9e-6 by 22:00 and re-crosses the threshold twice, > 5 min after the previous crossing. My merge rule
split one decay into extra "peaks"; SWPC treats it as one event. **Interpretation (me): no distinct GOES
M1+ flare is missing from SWPC in this sample.** Caveat: 2012-03 and 2013-03 have 86–88% GOES coverage;
a peak inside a gap where neither satellite has data is invisible to this check.

## 2026-09-21 — Decisions L, M, N  (decided by: user)

**L. 2020 excluded entirely.** It fails CHECK 5 under the pre-registered rule (1 M1+ flare, no region,
0% usable). **The rule is unchanged**; the year is dropped rather than the threshold adjusted.

**M. Region rule, from the fallback test (decision B).** Positive HARPs, single-region, 2021–2024 =
5 + 9 + 15 + 16 = **45 >= 40**, so **primary = single-region** (`noaa_ar_count == 1`).
**Robustness = `<= 2` regions and all HARPs (ANY rule).** The fallback is not triggered.

**N. Split.**
- **Test = 2021–2024, untouched until final evaluation.**
- **Train + validation = 2010–2019.**
- **Validation = random 25% of the 2010–2019 HARPs, assigned at HARP level, fixed seed, stratified so
  it contains positive HARPs.**
- **Assert: no HARPNUM in more than one set.**
- Written to `data/split.csv` (HARPNUM → train / val / test), SHA-256 recorded below.
- **No model is trained** — waiting on the signed research plan.

### RESULT: split (decision N) — `make_split.py` → `data/split.csv` (moved to `frozen/split.csv`, see below)
**SHA-256 `f3ab4056dd7b123aa8116b5d76650ddd916805139ee262381f9a7ffda728d145`** (rerun reproduces it).
Seed 20260921. 2020 removed first: 255,292 → 250,811 rows (−4,481); 34 HARPs exist only in 2020 and
are not in the split. 2,019 HARPs: train 913, val 305, test 801.
**Assert passed: no HARPNUM in more than one set; every HARP assigned.** No HARP has rows in both
2010–2019 and 2021–2024 (asserted in code). One HARP spans 2020→2021: its 2020 rows are dropped, its
2021 rows are in test; its early-2021 `n_*_prev_48h` still count late-2020 flares — decision L drops
2020 *rows*, not 2020 flares from the catalogue.
Stratification (me, fixed before running): three HARP strata from 2010–2019 rows — positive in
single-region rows (64 HARPs → 16 val), positive only in multi-region rows (62 → 16), negative
(1,092 → 273); 25% of each, rounded. This guarantees primary-subset positives in validation, not only
ANY-rule positives.

| set | subset | rows | positive rows | HARPs | positive HARPs | positive rate |
|-----|--------|-----:|------:|----:|---:|------:|
| train | single |  87,115 | 1,862 | 742 |  48 | 2.14% |
| train | <= 2   | 103,553 | 2,608 | 860 |  71 | 2.52% |
| train | all    | 111,991 | 3,480 | 913 |  94 | 3.11% |
| val   | single |  28,053 |   581 | 244 |  16 | 2.07% |
| val   | <= 2   |  34,487 |   787 | 290 |  23 | 2.28% |
| val   | all    |  36,911 | 1,098 | 305 |  32 | 2.97% |
| test  | single |  71,998 | 1,466 | 605 |  45 | 2.04% |
| test  | <= 2   |  86,981 | 2,688 | 709 |  73 | 3.09% |
| test  | all    | 101,909 | 5,568 | 801 | 128 | 5.46% |

HARP counts differ across subsets because `noaa_ar_count` is per row: a HARP can be single-region in
some hours and multi-region in others, so it appears in every subset whose rows it has.
**No model trained.** Waiting on the signed research plan.

## 2026-09-21 — Decision N2: model selection by grouped CV  (decided by: user; before any model is trained)

- **Threshold and hyperparameters are chosen by grouped 5-fold cross-validation over ALL 2010–2019
  HARPs** — train and val from `split.csv` **pooled**.
- **Folds: GroupKFold on HARPNUM**, **stratified by the same three HARP strata** as the split
  (positive in single-region rows / positive only in multi-region rows / negative), **fixed seed**.
- **Decision threshold = the one maximising TSS on the pooled out-of-fold scores.**
- **`split.csv` test assignment is unchanged**: 2021–2024 stays untouched until final evaluation.
- **Not implemented yet** — waiting on the signed research plan.

Notes (me), recorded for when this is implemented; none changes the decision:
- Under N2 the `train` / `val` labels in `split.csv` no longer separate data used for selection;
  both feed the CV pool. The file (and its SHA-256 above) is left exactly as written, so the test
  assignment it certifies is unaffected.
- Seed: the decision says "fixed seed" without a value. Unless told otherwise I will use the split's
  seed, **20260921**, and record the per-fold HARP and positive-HARP counts before any fitting.
- Expected fold size for the primary subset: 64 single-region-positive HARPs in 2010–2019 → about
  13 per fold, so each fold's TSS rests on ~13 independent positive regions.
- Pooling out-of-fold scores to pick one threshold assumes the five fold models produce scores on a
  comparable scale. If the models are poorly calibrated relative to each other, the pooled
  threshold can differ from each fold's own optimum; worth reporting the per-fold optimal thresholds
  alongside the pooled one when this runs.

## 2026-09-21 — N2 details approved; decisions O, Q, R  (decided by: user; before any model is trained)

**N2 details (approved):**
- Seed **20260921**.
- **Per-fold optimal thresholds are reported alongside the pooled out-of-fold threshold.**
- **Test scores = mean of the 5 fold models' scores. No refit on the full 2010–2019 set.**

**Decision O — expand SHARP keywords to the Bobra & Couvidat (2015) feature set.**
List their features from the paper (arXiv:1411.1405); show which are missing from the current 8;
re-query **only the missing keywords** for the **existing rows** (same record set, same filters);
merge on HARPNUM + T_REC; **verify row counts and labels unchanged.** Data only.

**Decision Q (final) — the gate.**
**Primary gate = reproduction of the Bobra & Couvidat (2015) SVM with their feature set.**
SolarMonitor = optional robustness gate only. **No further gate changes.**

**Decision R — research question and analysis plan (supersedes P).**
Note (me): no decision P appears in this log. R is recorded as superseding a "P" that was not written
down here; if P was decided elsewhere, its content should be added for the record.

*Question:* does 24h magnetic evolution add information beyond current magnetic risk and recent flare
history for separating M1+ **true alarms** from **false alarms**?
- **Trends:** fitted 24h slope of **USFLUX** and **TOTUSJH**; window **strictly before** the alarm time;
  **relative slope = slope / window mean**; **require >= 18 of 24 hourly points, else exclude.**
- **Primary analysis:** within the alarm cohort, logistic model **(gate score + n_C, n_M, n_X)** vs the
  **same + the 2 trends**. Fit on 2010–2019 (grouped CV, per N2), **evaluate once on 2021–2024.**
  **Metric: held-out log-loss difference, region-level bootstrap 95% CI.**
- **Supporting:** score-matched pairs.
- **Exploratory:** delayed alarms = no M1+ in (t, t+24h] and >= 1 M1+ in (t+24h, t+48h];
  **complete follow-up required.**
- **Pre-stated: a wide or inconclusive CI is an expected possible outcome.**

Consistency with earlier decisions (me, no change made):
- The history control is n_C, n_M, n_X only (J); cohort rows with `history_incomplete = True` are
  excluded from this analysis (D).
- "Complete follow-up" for delayed alarms needs the (t+24h, t+48h] window free of label-missing days;
  the current missing-day rule (C) only checks (t, t+24h]. To be implemented as an extra condition
  for the exploratory analysis only — the labelled file is not changed.

## 2026-09-21 — Decision O: findings (me) — two items need a user decision

Source: Bobra & Couvidat (2015), arXiv:1411.1405, **Table 1** (25 SHARP parameters, F-score ranked);
§5.1: the SVM uses **the first 13** ("Included"), chosen where a cubic fit to TSS vs feature count peaks.

| B&C 13 (Included) | have | | B&C Discarded (12) | have |
|---|---|---|---|---|
| TOTUSJH  | yes | | MEANSHR | **yes** (in our 8, but B&C discard it) |
| TOTBSQ   | **not a JSOC keyword** [corrected 2026-09-22: not a SHARP keyword; available in JSOC `cgem.lorentz`] | | MEANGAM | fetched |
| TOTPOT   | yes | | MEANGBT | fetched |
| TOTUSJZ  | fetched | | MEANGBZ | fetched |
| ABSNJZH  | yes | | MEANGBH | fetched |
| SAVNCPP  | yes | | MEANJZH | fetched |
| USFLUX   | yes | | TOTFY   | **not a JSOC keyword** |
| AREA_ACR | yes | | MEANJZD | fetched |
| TOTFZ    | **not a JSOC keyword** | | MEANALP | fetched |
| MEANPOT  | fetched | | TOTFX   | **not a JSOC keyword** |
| R_VALUE  | yes | | EPSY    | **not a JSOC keyword** |
| EPSZ     | **not a JSOC keyword** | | EPSX    | **not a JSOC keyword** |
| SHRGT45  | fetched | | | |

**Item 1 — BLOCKING for decision Q.** The 7 Lorentz-force parameters (TOTBSQ, TOTFX, TOTFY, TOTFZ,
EPSX, EPSY, EPSZ) are **not keywords in `hmi.sharp_cea_720s` or `hmi.sharp_720s`** (checked against the
live JSOC key lists, 2026-09-21). B&C describe them as adapted from Fisher et al. (2012); they are
computed from the vector-field image data. Three are in the 13-feature SVM set (TOTBSQ, TOTFZ, EPSZ). [**Corrected 2026-09-22:** not SHARP keywords, but available as keywords in JSOC `cgem.lorentz`; see the 2026-09-22 correction entry.]
Reproducing the 13-feature gate exactly therefore conflicts with the keyword-only constraint.
Options put to the user: (1) compute the 3 from image segments — faithful, breaks keyword-only, large
download; (2) reproduce with the **10 of 13** available as keywords and document the deviation;
(3) other. SWAN-SF carries the parameters but ends in 2018 (no 2021–2024 test coverage) and is
cross-check only. **No option acted on.**

**Item 2 — reproduction difference, flagged, not acted on.** B&C (§5) discard SHARP entries with
**QUALITY > 65536** (0x10000). This dataset keeps **QUALITY == 0** (user decision, retained after the
May 2016 finding). The gate will therefore be trained on a stricter subset than B&C used. Recorded so the
"reproduction" claim can state it; the filter is not changed.

**Done under O (data only):** the **10 missing keywords that exist** are being re-queried for the
existing record sets (`fetch_extra.py` → `data/raw_sharp_extra_<chunk>.csv`; original raw files
untouched), merged 1:1 on HARPNUM + T_REC with an assert. Pre-O labelled file SHA-256 (for the
"labels unchanged" check): `d69ecbc46f3150d149915178a5d533d80156f83372287c56b09e7d280a55f632`.
PENDING: fetch completion, row-count and label verification.

## 2026-09-21 — Decisions on P, the gate features, QUALITY, and git  (decided by: user)

**1. Decision P.** P was drafted but never sent; its content was superseded by R before adoption.
**R supersedes an unadopted draft P.** (Replaces my earlier note that P "was not written down here".)

**2. Lorentz-force features: option 2. Decision Q amended.**
Q now reads: **primary gate = Bobra & Couvidat-style SVM, 10 of 13 features; TOTBSQ, TOTFZ, EPSZ
unavailable as keywords.** ("Reproduction" is withdrawn as a description.) [**Corrected 2026-09-22:** not SHARP keywords, but available as keywords in JSOC `cgem.lorentz`; see the 2026-09-22 correction entry.]
**The gate uses exactly these 10 features and no others** — B&C Table 1 "Included" features that exist
as SHARP keywords, in Table 1 rank order:

  1. TOTUSJH   2. TOTPOT   3. TOTUSJZ   4. ABSNJZH   5. SAVNCPP
  6. USFLUX    7. AREA_ACR 8. MEANPOT   9. R_VALUE  10. SHRGT45

(B&C ranks 1, 3, 4, 5, 6, 7, 8, 10, 11, 13; ranks 2 TOTBSQ, 9 TOTFZ, 12 EPSZ unavailable.) [**Corrected 2026-09-22:** not SHARP keywords, but available as keywords in JSOC `cgem.lorentz`; see the 2026-09-22 correction entry.]
**Not in the gate:** MEANSHR and every other SHARP parameter, including B&C's 12 "Discarded".
The gate's test TSS will be reported against B&C's published TSS later, as a check.

**Correction (user, 2026-09-21):** the instruction's examples of features to exclude named R_VALUE and
AREA_ACR; **those examples were an error by the user**. The gate is **exactly the 10 listed above,
including R_VALUE and AREA_ACR.** (The conflict flag previously recorded here is withdrawn.)

**3. QUALITY: keep == 0.** Documented as a **stricter-than-B&C difference**: B&C (2015, §5) discard only
QUALITY > 65536 (0x10000); this dataset keeps QUALITY == 0. The gate is trained on a stricter subset.

**4. Git.**
- `data/` added to `.gitignore` and **removed from tracking** (`git rm -r --cached data`); **no files
  deleted on disk** (617 entries in `data/` before and after).
- **Frozen artefacts are tracked under `frozen/`:** `data/split.csv` → **`frozen/split.csv`**
  (SHA-256 unchanged: `f3ab4056dd7b123aa8116b5d76650ddd916805139ee262381f9a7ffda728d145`);
  `make_split.py` writes there. Future `frozen_spec.json` goes in `frozen/` too.
- **SHA-256 of the combined files at this point (post-relabel, pre-O merge):**
  - `data/labelled_20100501_20250101.csv`:
    `d69ecbc46f3150d149915178a5d533d80156f83372287c56b09e7d280a55f632`
  - `data/raw_sharp_20100501_20250101.csv`:
    `2a65e05ba070dec1aca9bad546ba4825503eff04deb56774b964b1e542a8b28f`
  The labelled hash will change when the decision-O keywords are merged (new columns); it will be
  re-recorded then, alongside the check that labels and row counts are unchanged.
- Note (me): `git rm --cached` does not remove files from **history**. Past commits still contain
  `data/`, including the 137 MB raw CSV, so pushing this repository to GitHub would still be rejected
  (100 MB file limit). Fixing that requires rewriting history (e.g. `git filter-repo`), which is
  destructive — not done; the user's call.

## 2026-09-21 — Repository policy, and the pre-registration exploratory run  (decided by: user)

**Git history is not rewritten.** Commit hashes cited in this log are the audit trail.
**137 MB raw CSV remains in history; repo is not to be pushed; a separate clean code-only repo will
be made if sharing is needed.** The repository stays local.

### Pre-registration exploratory run — `verification/` (AI-generated, run via Codex)
Recorded for transparency and for the **AI-use disclosure**. Not part of the final analysis.

- **What:** `verification/freeze.py` fits comparators and freezes predictions; `verification/evaluate.py`
  scores the frozen predictions under three views (row-mapped, per flare episode, first alert per
  episode) with a bootstrap (10,000 draws, seed 20260921). Models: `xgb_joint`
  (XGBClassifier, 300 trees, depth 4, lr 0.05, 5 seeds), `xgb_nohist`, `proxy_pastflare`
  (rule: any M/X flare in the previous 48h), `climatology` (constant).
- **Who / how:** AI-generated, run via **Codex**, concurrently with this session's chunk run. I (Claude)
  did not write or run it; my `git add -A` swept it into commits `fce77b9` and `82198fa`, which is how
  it entered the repository.
- **When (file mtimes, 2026-09-21):** `freeze.py` 01:27:53, `frozen.csv` 01:28:09, `evaluate.py` and the
  three tables 01:28:55 — while the chunk run had reached about April 2016, which is where the data stops.
- **Labels:** the **HEK-era** labels (since superseded by SWPC originals, decision A).
- **Features:** the original 8 SHARP keywords (**including MEANSHR**), LAT_FWT, LON_FWT, and
  **`n_flares_prev_48h`**, n_C/n_M/n_X_prev_48h — several since excluded (decisions J, Q).
- **Data period:** 2010-05-01 → 2016-04-13 (137,991 rows). **Chronological split:** fit 2010-05 → 2014-07,
  threshold 2014-07 → 2015-04, **score 2015-04 → 2016-04**.
- **Results were seen by the user.** Table 1 (score period, row-mapped TSS): xgb_joint 0.808,
  xgb_nohist 0.829, proxy_pastflare 0.495, climatology 0.000. Full tables in `verification/out/`.
- **Test set (2021–2024) not touched:** 0 rows from 2021–2024 in `frozen.csv` (verified).
- **Results are not used in the final analysis.** Note: the score period now lies inside the
  2010–2019 development pool used for grouped CV (N2), so these numbers are an earlier look at data
  that will be cross-validated on — disclosed here, test set unaffected.
- **Files (SHA-256):**
  - `verification/freeze.py` `e83033ae8bcd0c6080bee0a5d2087315029490e32395b58a0f723d2f548c4fc7`
  - `verification/evaluate.py` `91b7cb5ca60b1112aa45a50bf92494c1ade86466d1aa499da503ee319307ed6d`
  - `verification/out/frozen.csv` `041d7a6f964630ff629748ef7a4915773a2d1bb25d33bc9378283aa249a35710`
    — **untracked from git, kept on disk** (23 MB)
  - `verification/out/table1_views.csv` `936dd8a3c17048e4573e41b67b43b700eaa64d88d3443e28bee873e29ffdbb3c`
  - `verification/out/table2_decomposition.csv` `155fa607a7e03f8ff6d9040c2c227c3f65b2fa7da9058a83de7a7349ee51dd9f`
  - `verification/out/table3_bootstrap.csv` `542e475019c4ac3fa4bb2d4238093dbd14f4f7a10ca0d5cd79e823e3e11d0f50`
- **Code stays tracked** (`verification/*.py`, and the three small tables).

### AI-use disclosure — running list (me)
- **Claude (Anthropic), via Claude Code:** wrote and ran the data pipeline in this repository
  (`build_dataset.py`, `swpc.py`, `goes_xrs.py`, `run_all.py`, `checks.py`, `join_report.py`,
  `make_split.py`, `fetch_extra.py` and the audit/validation scripts) and drafted the non-decision
  entries in this log. Every scientific decision is recorded above as the user's.
- **Codex:** generated and ran `verification/` (exploratory run above).

## 2026-09-21 — RESULT: decision O keyword merge (fills PENDING under O)

- `fetch_extra.py`: **176 / 176 chunks**, no failures; same record-set strings as the original query,
  keywords only. Original raw chunk files untouched.
- Merged in `build_dataset.py` on HARPNUM + T_REC with `validate="one_to_one"` and an assert that every
  raw row matches and the extras have the same row count. **The assert held in all 176 chunks** (a
  mismatch stops the build). Example: 2024-05 — "1:1, 10378 rows"; rerunning that chunk reproduces the
  file byte-for-byte.
- **Verification against the pre-O file** (SHA-256 `d69ecbc4…`):
  - rows: **255,292 → 255,292**
  - **every pre-existing column identical — every value, every row, same order** (not only labels);
    positives 10,146 unchanged
  - 10 new columns appended: totusjz, meanpot, shrgt45, meangam, meangbt, meangbz, meangbh, meanjzh,
    meanjzd, meanalp
  - missingness of new columns: totusjz 0.000%, meanpot / shrgt45 / meangam 0.022%, the rest 0.029%.
    Not filled or dropped (unchanged policy).
- **New SHA-256, combined labelled file (post-O):**
  `85b88518e4672e676c451aa8f5fe78d5b1b08ed2e40e9cb70a02520f74bee245`
- Combined raw file **unchanged**: `2a65e05ba070dec1aca9bad546ba4825503eff04deb56774b964b1e542a8b28f`
  (extras live in `data/raw_sharp_extra_<chunk>.csv`, not in the raw files).
- All 10 gate features (decision Q) are now in the labelled file: TOTUSJH, TOTPOT, TOTUSJZ, ABSNJZH,
  SAVNCPP, USFLUX, AREA_ACR, MEANPOT, R_VALUE, SHRGT45.
- `frozen/split.csv` is unaffected: HARP set and assignment depend only on rows, which did not change.
**No model trained.**

## 2026-09-21 — Decision S: 6-hourly thinning for gate training; parallelism; timing  (decided by: user)

- **For gate training only**, thin dev (2010–2019) rows to **one per HARP every 6 hours
  (T_REC hour ∈ {0, 6, 12, 18})**. **Scoring, alarms and the cohort stay hourly.**
- CV folds / grid points run in parallel, **n_jobs = performance cores − 1**. This machine (Apple M5):
  4 performance + 6 efficiency cores → **n_jobs = 3**.
- **Time one SVM fit on one fold and report before launching the grid; if the full grid would exceed
  ~3 hours, stop and report.**

### Finding (me) — the {0, 6, 12, 18} grid hits two systematically bad hours. NOT implemented; awaiting user.
Raw SHARP records exist at every hour, but **at 06:00 and 18:00 TAI 99.5% fail QUALITY == 0**
(hour 06: 216 of 45,181 pass; hour 18: 220 of 44,312; every other hour 84–95%). Their QUALITY is
dominated by **0x00010000 `QUAL_LOWINTERPNUM`** — JSOC QUALITY.txt: "the number of averaging points is
lower than TempIntNum, AND/OR 2 interpolation points were separated by more than the cadence" — often
with 0x400 `QUAL_NOCOSMICRAY` (values 65536, 66560). Hours 07–09 and 19 are mildly depleted (84–93%).
Consequence: the specified grid keeps 00 and 12 and almost nothing at 06 and 18 — **9.5% of dev rows
survive instead of ~16.7%**, and the sampling is effectively 12-hourly.
Side note: B&C's cutoff QUALITY > 65536 keeps exactly the 0x10000-only records that QUALITY == 0
drops — plausibly why they chose it. Decision 3 (keep == 0) is unchanged.
T_REC hour is taken in **TAI** (the native slots; the UTC equivalent is hh:59:2x of the previous hour).

### Blocking questions (me)
1. **The timing fit is a model fit.** Standing instruction since decision N: "Train nothing — waiting on
   the signed research plan." S asks for one SVM fit to time it. Not run until the user confirms it is
   authorised (the fitted model would be discarded, used for timing only).
2. **No hyperparameter grid has been specified**, so the full-grid time cannot be estimated.
   For reference only (not a proposal) — verified in B&C (2015) §5: a single setting, not a grid:
   RBF kernel, C = 4, γ = 0.075, tolerance 1e-8 on the relative change in the cost function, class-
   imbalance ratio N/P = 16.5 in both training and testing sets, penalty ratio C1/C2 = 2.0 (positive/negative).

## 2026-09-21 — Decision S amended  (decided by: user; before any model; supersedes the S grid and timing step)

**1. Thinning grid = T_REC TAI hours {4, 10, 16, 22}** (gate training only; scoring, alarms and cohort
stay hourly). Chosen to avoid the QUAL_LOWINTERPNUM slots 06/18 and the depleted 07–09 / 19.
**Documented: QUALITY == 0 systematically excludes TAI 06:00 and 18:00 (99.5% of records there fail it);
kept deliberately.**
Result (dev = 2010–2019, 2020 excluded):
- rows **148,902 → 27,482 (18.5%)**; HARPs 1,218 → 1,213
  (18.5% rather than 1/6 because 06/18 are almost empty, so the surviving rows sit in ~22 usable hours)

| subset | rows | positive rows | negatives | **natural N/P** | positive HARPs |
|--------|-----:|------:|-------:|------:|---:|
| single (primary) | 21,237 | 455 | 20,782 | **45.7** | 63 (of 64 in dev) |
| <= 2 | 25,469 | 633 | 24,836 | **39.2** | 93 |
| all | 27,482 | 853 | 26,629 | **31.2** | 123 |

**2. Hyperparameters: B&C (2015) fixed values, no grid.** RBF kernel, **C = 4, γ = 0.075, tol = 1e-8,
class-weight ratio C1/C2 = 2.0** (positive / negative). **StandardScaler fitted inside each training fold
only.** Documented differences from B&C:
- **γ is not retuned for 10 vs 13 features.** With fewer features the typical squared distance between
  scaled points is smaller, so the same γ gives a relatively wider kernel than B&C's.
- **No negative subsampling to N/P = 16.5.** Natural N/P after thinning is used (table above: 45.7 for
  the primary subset — ~2.8× B&C's).
- Scaling (noted by me): B&C subtract the **median** and divide by the standard deviation (§5);
  StandardScaler subtracts the **mean**. B&C remark the median "appears to slightly improve the results".
  Recorded as a difference; not changed.

**3. Timing-fit step dropped.** Guard kept: **if the 5-fold run exceeds 3 hours, stop and report.**

**Train nothing until the user confirms the research plan is signed.**

## 2026-09-21 — STOP instruction: check for running training / model output (me)
The user ordered all training stopped and any model output recorded as discarded unseen.
**Checked: nothing to stop and nothing to discard.** No project process was running (the only
processes were the ChatGPT/Codex desktop app and MCP servers, none working in this repository); no
model artefacts exist in the project (`*.pkl`, `*.joblib`, `*.model`, fold / OOF / prediction / score
files); no file newer than commit `b423ca4`; working tree clean. No training has been run in this
repository by Claude at any point. (The only model outputs in the repository remain the Codex
exploratory run in `verification/`, recorded above.)

## 2026-09-21 — Decision K2: TRUE irradiance scale  (decided by: user; SUPERSEDES K; before any results seen)

**Switch to option (a) — true irradiance scale, per the NOAA/NCEI recommendation.**
Reasons (user):
- NOAA states the pre-GOES-16 0.7 scaling was incorrect (NCEI GOES 1–15 XRS readme §3.1).
- Recent practice divides old values by 0.7 (Hudson et al. 2023, arXiv:2310.11457;
  SWSC 2025, doi:10.1051/swsc/2025007).
- It increases positive regions in both periods.
**Trade-off (recorded): labels are no longer on the same scale as Bobra & Couvidat (2015) or SWAN-SF;
comparisons with them are approximate.** (This reverses K's stated reason — comparability with B&C,
SWAN-SF and SWPC verification — in favour of physical correctness.)

Implementation (as specified):
1. SWPC events from **GOES-13/14/15** (per each event's `Obs` column): **flux / 0.7** before assigning
   class. **GOES-16/18 events: as reported.** SDO-observed events: kept as reported, flagged
   `scale_unverified` (unchanged rule).
2. Applies to **labels AND n_C/n_M/n_X history features**.
3. GOES empty-day rule thresholds (true flux): **M1 = 1.0e-5, C1 = 1.0e-6**. Empty-day flags re-derived
   from the cached GOES files; changes vs K reported.
4. Relabel all 176 chunks from cache. Verify rows unchanged (255,292) and all non-label columns
   identical; only label/history columns may differ. New SHA-256 recorded.
5. Checks 1–5 rerun. 6. Per-year report incl. events whose class changed K → K2.
7. Per set × subset table under the unchanged `frozen/split.csv`. 8. Fallback rule re-applied.
9. Thinned training set (TAI {4,10,16,22}) re-reported.
**Train nothing until the user confirms.**

## 2026-09-21 — RESULTS: decision K2 (true irradiance scale)

**Conversion** (`data/scale_conversion_report_K2.csv`): GOES-13/14/15 events ÷ 0.7 (exact decimal
arithmetic — binary floating point gives e.g. X1.4 / 0.7 = 1.9999…e-4, not 2.0e-4); GOES-16/18 as
reported; 5 SDO events as reported, `scale_unverified`. 4,170 of 27,219 events changed class K → K2
(both periods: 2010–2019 through ÷0.7; 2020–2024 because K had applied ×0.7).

**Empty-day flags at M1 = 1.0e-5, C1 = 1.0e-6:** 2 changes vs K — 2012-01-29 and 2020-09-26
genuine zero → incomplete_C1 (peaks between 1.0e-6 and 1.43e-6). Now: 824 genuine zero, 3 C1,
5 no data, 3 low coverage → **8 label-missing days (unchanged), 11 history-incomplete (K: 9).**

**Relabel verification:** 176/176 chunks, no failures. **Rows 255,292 → 255,292; row keys identical and
in the same order; every non-label column identical.** Rows changed: `flared_M1_next_24h` 4,003,
`n_C_prev_48h` 35,828, `n_M_prev_48h` 13,338, `n_X_prev_48h` 975, `history_incomplete` 250;
`n_flares_prev_48h` 0 (all-class total is scale-independent — as expected).
**New SHA-256 labelled file:** `d25304cf4b1fc7ee22808da3c6bc015f45f2114510d55f384003c010b35811d9`.
Raw file unchanged: `2a65e05ba070dec1aca9bad546ba4825503eff04deb56774b964b1e542a8b28f`.

**Per year** (K2 [K]):

| year | M1+ flares | positive rows | % positive | events changed class K→K2 |
|------|-----:|------:|------:|-----:|
| 2010 |  11 [8]   |    86 [81]    |  1.10% [1.04%]  |  53 |
| 2011 | 189 [119] |   917 [747]   |  3.83% [3.12%]  | 345 |
| 2012 | 201 [136] | 1,012 [781]   |  4.38% [3.38%]  | 396 |
| 2013 | 169 [111] | 1,143 [790]   |  4.08% [2.82%]  | 315 |
| 2014 | 346 [223] | 1,731 [1,273] |  6.79% [5.00%]  | 264 |
| 2015 | 194 [127] | 1,031 [715]   |  4.22% [2.93%]  | 333 |
| 2016 |  28 [16]  |    98 [67]    |  1.84% [1.26%]  | 188 |
| 2017 |  56 [43]  |   146 [124]   |  2.79% [2.37%]  | 109 |
| 2018 |   1 [0]   |     0 [0]     |  0.00% [0.00%]  |  27 |
| 2019 |   2 [0]   |     0 [0]     |  0.00% [0.00%]  |  35 |
| 2020 |   2 [1]   |     0 [0]     |  0.00% [0.00%]  | 119 |
| 2021 |  29 [16]  |   259 [178]   |  2.09% [1.44%]  | 469 |
| 2022 | 195 [117] | 1,019 [695]   |  4.13% [2.82%]  | 587 |
| 2023 | 365 [202] | 2,108 [1,337] |  6.51% [4.13%]  | 432 |
| 2024 | 935 [545] | 4,599 [3,358] | 14.16% [10.34%] | 493 |

**Checks on K2 labels:** CHECK 1 PASS (X1.2 = true 1.71e-4; all 21 rows in [t0−24h, t0) = 1).
CHECK 2 PASS (median ratio USFLUX 13.90×, TOTUSJH 17.09×). CHECK 3 descriptive (23 HARPs, 5 positive).
CHECK 4 PASS (unchanged). **CHECK 5 FAIL — 2020 and 2022.**
- 2020: 2 M1+, both no region → 0% (was 0 of 1 under K; decision L already excludes 2020).
- **2022: 195 M1+, 20 no region → 89.7% usable, below the pre-registered 90%** (K: 117 M1+, 11 no region,
  90.6% — passed). The additional true-scale M1+ flares include proportionally more without a region.
  **2022 is a test year. It is NOT excluded and the rule is NOT changed — user decision pending.**
  By the precedent of decision L, the fixed rule would exclude it.
- All other years pass (93.0–100%); 2018 and 2019 now have 1 and 2 M1+ flares (all joined), but 0
  positive rows — the HARPs holding them have no rows passing the filters in those windows.

**Split** (`frozen/split.csv` unchanged, SHA-256 `f3ab4056…`; per-set rows identical to before, only
positives moved; 2020 rows excluded per L). Note: the val stratification was drawn under K labels;
under K2 it still contains 21 single-region-positive HARPs.

| set | subset | rows | positive rows | HARPs | positive HARPs |
|-----|--------|-----:|------:|----:|---:|
| train | single |  87,115 | 2,460 | 742 |  65 |
| train | <= 2   | 103,553 | 3,384 | 860 |  91 |
| train | all    | 111,991 | 4,697 | 913 | 118 |
| val   | single |  28,053 |   712 | 244 |  21 |
| val   | <= 2   |  34,487 | 1,032 | 290 |  30 |
| val   | all    |  36,911 | 1,467 | 305 |  40 |
| test  | single |  71,998 | 2,384 | 605 |  71 |
| test  | <= 2   |  86,981 | 4,039 | 709 | 110 |
| test  | all    | 101,909 | 7,985 | 801 | 172 |

**Fallback rule (M re-applied):** single-region positive test HARPs = **71 >= 40 → single-region.**
Without 2022 (if the user excludes it): **55 >= 40 → still single-region.** (Without 2022: single 53,462 rows /
1,978 pos / 55 pos HARPs; <= 2 64,763 / 3,404 / 87; all 77,224 / 6,966 / 142.)

**Thinned dev (TAI {4,10,16,22}):** 148,902 → 27,482 rows (18.5%, unchanged).

| subset | rows | positive rows | natural N/P | positive HARPs |
|--------|-----:|------:|------:|---:|
| single | 21,237 | 587 | **35.2** (K: 45.7) | 83 |
| <= 2   | 25,469 | 818 | **30.1** (K: 39.2) | 118 |
| all    | 27,482 | 1,142 | **23.1** (K: 31.2) | 154 |

Not re-run under K2 (report-only, not requested): the March 2011–2019 completeness check; its thresholds
now match K2's M1 = 1.0e-5.
**No model trained.**

## 2026-09-21 — Decision L2  (decided by: user; fixed rule applied)

**2022 fails CHECK 5 under K2 (89.7% < 90%) → 2022 is excluded from the PRIMARY test. Rule unchanged.**
- **Primary test = 2021, 2023, 2024.**
- **2022-included results are reported only as a labelled sensitivity analysis.**
- `frozen/split.csv` **unchanged** — 2022 HARPs keep their `test` assignment; the primary test excludes
  2022 **rows** at evaluation time (as 2020 rows are excluded under L).
- **When training starts, CV fold strata are computed from the K2 labels** (the val stratification in
  `split.csv` was drawn under K; `split.csv` itself is not changed).
- Also requested: rerun the GOES completeness check at K2 thresholds; report primary-test positive HARPs.
**Train nothing until the user confirms.**

### RESULTS for L2 (me)

**Completeness check at K2 thresholds (M1 = 1.0e-5 true flux; rules otherwise unchanged; report only):**

| month | GOES M1+ peaks | matched | unmatched | SWPC M1+ | GOES coverage |
|-------|---:|---:|---:|---:|---:|
| 2011-03 | 35 | 32 | 3 | 32 | 94.6% |
| 2012-03 | 29 | 28 | 1 | 29 | 86.3% |
| 2013-03 |  3 |  3 | 0 |  3 | 87.5% |
| 2014-03 | 34 | 33 | 1 | 34 | 94.4% |
| 2015-03 | 39 | 38 | 1 | 39 | 97.9% |
| 2016–2019-03 | 0 | 0 | 0 | 0 | 95.8–100% |
| **total** | **140** | **134** | **6** | | (K: 99 / 97 / 2) |

The 6 unmatched, each checked against the flux and the SWPC list within ±3 h:
- **Artefacts of the peak rule (3):** 2012-03-07 04:43 (M1.2; long decay of the X5.4 of 00:02);
  2015-03-03 02:27 (M1.0; decay of the M8.2 peaking 01:35); 2011-03-09 13:29 (M1.1; bump inside SWPC's
  M1.7 event 13:17–14:02, 33 min before its listed peak — just outside ±30 min).
- **Apparently genuine flares absent from SWPC (3):** 2011-03-09 05:18 (isolated peak ~5e-6 → 1.07e-5,
  true M1.1 ≈ operational C7.6; nearest SWPC events 3 h earlier); 2011-03-09 06:56 (1.12e-5 as data
  resume after a 05:30–06:52 gap, eclipse season — true peak may lie in the gap; SWPC lists nothing
  02:33–08:23); 2014-03-11 19:46 (clean rise 4e-6 → 1.15e-5, true M1.1 ≈ operational C8.2, shortly after
  an 18:00–18:37 gap; SWPC lists nothing 18:00–21:40).
- **Interpretation (me):** SWPC appears to miss ~3 of 137 distinct GOES M1+ flares (~2%) in this sample,
  all just above threshold, two beside eclipse-season data gaps. Each is a small set of false-negative
  labels. The K-scale check did not see them because at 1.43e-5 they were below threshold.
  **Report only — no labels changed.** Same coverage caveat as before for 2012-03 / 2013-03.

**Primary test (2022 excluded; `frozen/split.csv` unchanged, SHA-256 `f3ab4056…`):**

| set | subset | rows | positive rows | HARPs | positive HARPs |
|-----|--------|-----:|------:|----:|---:|
| train | single |  87,115 | 2,460 | 742 |  65 |
| train | <= 2   | 103,553 | 3,384 | 860 |  91 |
| train | all    | 111,991 | 4,697 | 913 | 118 |
| val   | single |  28,053 |   712 | 244 |  21 |
| val   | <= 2   |  34,487 | 1,032 | 290 |  30 |
| val   | all    |  36,911 | 1,467 | 305 |  40 |
| **test (primary)** | **single** | **53,462** | **1,978** | **450** | **55** |
| test (primary) | <= 2   |  64,763 | 3,404 | 528 |  87 |
| test (primary) | all    |  77,224 | 6,966 | 605 | 142 |

Fallback rule on the primary test: **55 >= 40 → single-region** (unchanged).
2022-included test (sensitivity only): single 71, <= 2 110, all 172 positive HARPs.
`split_report.py` prints both the 2022-included (sensitivity) and 2022-excluded (primary) tables.
**No model trained.**

## 2026-09-21 — SWPC M1+ completeness at K2 (summary, per user)
**SWPC M1+ completeness at K2 = 134/137 in the sampled months** (March 2011–2019): of 137 distinct GOES
M1+ flares, SWPC lists 134. **The misses are near-threshold** (true M1.1–M1.3), two beside eclipse-season
data gaps. **Reported as label noise; labels unchanged.**

## 2026-09-21 — AUDIT 2018-01-01 → 2020-12-31 (report only; `audit_2018_2020.py`)

**BUG count: 0.** Every SWPC M1+ event (K2) is accounted for:

| start | K2 class (reported, obs) | region | trace | reason |
|---|---|---|---|---|
| 2018-02-07 13:31 | M1.2 (C8.1, G15) | 12699 → HARP 7237 | 24 raw → 21 QUALITY==0 → 0 within ±45° | HARP outside ±45° |
| 2019-05-06 05:04 | M1.4 (C9.9, G15) | 12740 → HARP 7357 | 24 → 22 → 0 | HARP outside ±45° |
| 2019-05-06 13:35 | M1.0 (C7.3, G15) | 12740 → HARP 7357 | 24 → 22 → 0 | HARP outside ±45° |
| 2020-05-29 07:13 | M1.1 (G16) | none | — | no region; 2020 excluded (L) |
| 2020-11-29 12:34 | M4.4 (G16) | none | — | no region; 2020 excluded (L) |

The zero-positive years 2018–2020 are real consequences of the filters, not a pipeline fault.

**GOES M1+ peaks over the 3 years** (1,096 days, 99.5% coverage): 6 peaks, 5 matched to SWPC within ±30 min.
Unmatched: **2019-05-09 05:51**, GOES true 1.03e-5 (M1.0). SWPC lists the **same flare, same minute** as
C6.7 from **GOES-15** = 9.57e-6 true — just below M1. Explanation (me): **inter-satellite calibration**, not
a missed flare. The GOES check uses GOES-16 (science primary from 2017-02-07); SWPC reported from GOES-15.
NCEI readme Table 2 gives the XRS-B ratio GOES-15/GOES-16 = **0.923**; 9.57e-6 / 0.923 ≈ 1.04e-5.

**Caveat raised for the user (no change made):** K2's ÷0.7 removes SWPC's scaling factor but not the
~8% GOES-15/GOES-16 calibration difference. For 2017-02 → 2019-11, SWPC's GOES-15-based classes read ~8%
low relative to GOES-16. Effect limited to near-threshold flares; in this window it touches only the one
event above.
Refactor: the GOES peak detector moved into `goes_xrs.peaks()` (shared by `completeness_check.py` and
the audit); the completeness check reproduces 140 / 134 / 6 after the move.

## 2026-09-21 — TRAINING AUTHORISED  (decided by: user)

**"Training authorised by me on 2026-09-21; research plan not yet signed at this point."**

**Residual calibration difference (recorded, user):** a GOES-15 vs GOES-16 calibration difference
(~8%; NCEI XRS-B ratio GOES-15/GOES-16 = 0.923) **remains after K2**. It affects **near-threshold events
only** and is **not corrected**.

**Staged plan (user).** Stop and report at each CHECKPOINT; continue only on approval; commit after each
stage. Labels = K2. Primary test years = 2021, 2023, 2024 (2022 sensitivity only; 2020 excluded).
- STAGE 2 gate (dev 2010–2019, single-region primary subset) → CHECKPOINT 2 (test years not touched)
- STAGE 3 dev cohort → CHECKPOINT 3
- STAGE 4 primary models on dev; write `frozen/frozen_spec.json`, hash here → CHECKPOINT 4
- STAGE 5 test, run once, only after approval of CHECKPOINT 4 → CHECKPOINT 5 (results table only)

**Scaling (user; supersedes the StandardScaler in amended decision S):** follow B&C (2015) §5 —
"we subtract from every feature its median value and divide by its standard deviation."
Median and standard deviation are **fitted inside each training fold only**.

## 2026-09-21 — STAGE 2 RESULTS: gate (dev only) — CHECKPOINT 2

`stage2_gate.py`. Dev = train+val HARPs of `frozen/split.csv`, rows 2010–2019 (2020 excluded). **Test HARPs
never loaded** (asserted in code: no test HARP, no row after 2019).
- **Unscorable rows (implementation choice, me):** 21 dev hourly rows (1 positive) lack MEANPOT and SHRGT45
  together; an SVM cannot score a missing input and imputation is ruled out, so these rows get **no gate
  score** — excluded from training and metrics, and cannot alarm. (Test has 34 such rows, 0 positive;
  the same rule will apply there.)
- Features: the 10 of decision Q. Training rows: single-region, thinned to TAI {4,10,16,22}.
  Scaling: B&C §5 median / standard deviation, per training fold. SVM: RBF, C=4, γ=0.075, tol=1e-8,
  class weight positive:negative = 2.0:1.0. No tuning.
- Folds: 5, grouped by HARPNUM, stratified by 3 HARP strata **from K2 labels**, seed 20260921; built by
  shuffling each stratum and dealing HARPs round-robin. HARPs per fold 245/244/243/243/243; single-region
  positive HARPs per fold 18/17/17/17/17. Grouping asserted (no HARP in two folds).
- Fits: 16,705–17,127 training rows per fold (443–499 positive), 909–1,023 support vectors, ~1 s each;
  **total 2.8 s** (limit 3 h). **Rerun reproduces the out-of-fold scores byte-for-byte.**
- Score = SVM decision function, every hourly dev row out-of-fold (115,147 primary-subset rows).
- **Threshold = −0.992496** (max TSS on pooled out-of-fold hourly scores, primary subset).

Primary subset, hourly, at the pooled threshold:

| fold | rows | pos rows | HARPs | pos HARPs | TSS | HSS | TPR | FPR | FAR | own optimal threshold | TSS at own optimum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 24,586 | 754 | 209 | 18 | 0.788 | 0.473 | 0.837 | 0.049 | 0.648 | −0.9920 | 0.788 |
| 1 | 22,197 | 739 | 193 | 17 | 0.785 | 0.531 | 0.825 | 0.040 | 0.586 | −0.9800 | 0.787 |
| 2 | 22,343 | 479 | 191 | 17 | 0.662 | 0.381 | 0.702 | 0.040 | 0.720 | −0.9940 | 0.665 |
| 3 | 22,421 | 505 | 195 | 17 | 0.392 | 0.329 | 0.414 | 0.022 | 0.701 | −1.0057 | 0.416 |
| 4 | 23,600 | 694 | 198 | 17 | 0.663 | 0.392 | 0.715 | 0.052 | 0.705 | −0.9962 | 0.665 |
| **pooled** | **115,147** | **3,171** | **986** | **86** | **0.679** | **0.434** | **0.720** | **0.041** | **0.667** | −0.9925 | 0.679 |

Artefacts (in `data/`, not tracked): `data/stage2/oof_scores_dev.csv`, `stage2_metrics.csv`,
`stage2_result.json`; fold models `data/stage2/models/fold{0..4}.joblib`, SHA-256:
fold0 `d283c18bfe242518d0389c33c2e94bfe25405b0bc9ebd3f42030592ec09ee00a`,
fold1 `1dbc5a7908903d4cb9d9c03d14e3c51945b2712333a1b2dbcd556779b7769c20`,
fold2 `9e6f233705d9490f830b439a5debd215dc856f3879fd51e142b7f7a8df164d7c`,
fold3 `7aeae7f67c858889c249089e7f0af54832490e190e158e4b731cfb36ac87970c`,
fold4 `49e7c9597746e1398990b13c65a311aa8f16de12780900878cc0b7cd91ac8f48`.
**Test years not touched.** Awaiting approval of CHECKPOINT 2.

### CHECKPOINT 2 approved (user, 2026-09-21)
- **Missing-feature rule adopted as the user's decision:** rows with any gate feature missing are
  **unscorable** — excluded from alarms and metrics, counted and reported (dev 21, test 34).
- **Dev TSS is mildly optimistic:** the threshold was chosen on the same pooled out-of-fold scores it is
  evaluated on. **The test TSS is the unbiased estimate.**

## 2026-09-21 — BUG FOUND AND FIXED (me): month-boundary duplicate rows

Found while building the Stage 3 cohort (a one-to-one merge assert failed).
**Cause:** JSOC record-set ranges `A-B` include both ends, so each monthly query
`[1st 00:00 TAI – next 1st 00:00 TAI]` also returned the next month's 00:00 TAI record, which the next
chunk fetched again. **Extent:** 1,488 duplicate raw rows of 1,074,130 (0.14%); **393 duplicate labelled rows**
of 255,292 (0.15%), 21 positive. Every duplicate is the 00:00 TAI record on the 1st of a month; **all 393 pairs
were identical in every column** (labels agreed because each chunk's flare window was padded), so no value
was wrong — rows were counted twice.
**Fix:** `run_all.py` drops the second copy when concatenating, after **asserting the copies are identical**.
Raw chunk files are untouched. Result verified equal to the old file with duplicates removed.
- Labelled: **255,292 → 254,899 rows**, 0 duplicates. **New SHA-256:**
  `62a0e4ccffe8b1fc4dacd2a0ba80570bf56018540d57367c16eb37337380ffeb`
- Raw combined: 1,074,130 → 1,072,642. **New SHA-256:**
  `be7c7d44b33b13a4620e4b98d23a217fac8e87597360b6ed548cf53f4faf8fa3`
- **`frozen/split.csv` unaffected** (the HARP set is unchanged; split is per HARP).
- Earlier row-count tables in this log (from the first full summary through K2 and L2) include these
  duplicates; they are overstated by ≤ 0.15% of rows. Positive-HARP counts are unaffected (a duplicate
  never introduces a new HARP).

**Stage 2 rerun on the corrected file** (deterministic, 2.8 s): **threshold unchanged (−0.992496); fold
models bit-for-bit identical to the approved ones** (training uses TAI {4,10,16,22}, never hour 00);
fold assignment unchanged. Metrics change only through the removed duplicate rows: 195 fewer primary-
subset rows (3 positive); per-fold TSS change ≤ 0.0016; **pooled TSS 0.6789 → 0.6793**, HSS +0.0003,
FAR −0.0003; positive HARPs unchanged. Approved CHECKPOINT 2 results otherwise stand.

### Fold 3 detail (report only, user request; K2, primary subset, OOF, threshold −0.992496)
8 of 17 positive HARPs detected. Detected (max OOF score on positive rows): 3291 (2.941), 4941 (1.331),
753 (0.848), 5956 (−0.356), 2636 (−0.863), 2635 (−0.872), 54 (−0.939), 4231 (−0.974). Not detected:
902 (−0.996; 67 positive rows), 1990 (−0.997), 4760 (−0.999), 1464 (−1.004), 1558 (−1.005), 3344 (−1.005),
6972 (−1.024), 2887 (−1.073), 3258 (−1.270; alarmed at other times, max over all rows 1.728).
Six of the nine misses lie within 0.013 of the threshold.

## 2026-09-21 — STAGE 3 RESULTS: dev alarm cohort — CHECKPOINT 3

`cohort.py` (rules; reused unchanged for test in Stage 5) + `stage3_cohort.py`. Dev 2010–2019, primary subset,
Stage 2 out-of-fold scores, threshold −0.992496. Implementation details fixed before results (me):
episode = alarm hours of one HARP exactly 1 h apart (any gap ends it); eligible = onset row labelled,
`history_incomplete` False, >= 18 of 24 points in (t−24h, t] with USFLUX and TOTUSJH present; first eligible
episode per HARP; history via existing `n_*_prev_48h` ([t−48h, t) ≡ (t−48h, t] here — t is always hh:59:2x
UTC, flare starts are whole minutes); trend = least-squares slope vs hours / window mean; delayed = false
alarm with >= 1 M1+ from the HARP's region in (t+24h, t+48h] and that window free of label-missing days.

- Alarm hours: 6,836; **episodes: 1,311 in 220 HARPs**.
- Exclusions while searching each HARP's first eligible episode: **231 episodes skipped, all for
  "trend window < 18 points"**; 0 for `history_incomplete`; 0 label-missing.
- **41 HARPs** alarmed but had **no eligible episode** (all: trend window < 18 points).

| | regions |
|---|---:|
| **cohort (one episode per region)** | **179** |
| true alarms | **25** |
| false alarms | **154** |
| delayed (exploratory; subset of false, complete follow-up) | **16** |
| false with a flare in (t+24h, t+48h] but incomplete follow-up | 0 |

Diagnostics (me, report only):
- **Episode fragmentation by the 06/18 TAI gap.** Episode length median 4 h, max **11 h**, 375 single-hour
  episodes; median 3 episodes per HARP (max 23). QUALITY == 0 removes almost all 06:00 and 18:00 TAI records, so
  the "exactly 1 h apart" rule **breaks every alarm run at least every 12 h**. For the 67 regions whose chosen
  episode is not their first, the "onset" may be a restart after a 06/18 gap rather than a true onset.
  Whether a single systematic missing hour should break an episode is a user decision — **not changed**.
- **Why true alarms are few:** 60 HARPs have >= 1 detected positive hour; 55 are in the cohort; for **30** of
  them the first eligible episode began > 24 h before the flare, so it is a false alarm by definition.
- Selection: onset is at a median 48 h after the HARP's first labelled row (the 24-h trend window and the
  18-point rule push onsets later).

Artefacts: `data/stage3/cohort_dev.csv`, `exclusions_dev.csv`, `episodes_dev.csv`.
**Test years not touched.** Awaiting approval of CHECKPOINT 3.

## 2026-09-21 — Checkpoint 3 decisions T1, T2, T3  (decided by: user)
**Made after seeing the cohort sizes, before any trend or model result.**
Note (me): the Stage 3 cohort file contains per-episode trend slopes (computed to apply the 18-point rule),
but **no trend comparison between true and false alarms was computed, printed or viewed**, and no cohort
model has been fitted.

**T1. Episode merging.** Consecutive alarm hours stay in one episode across **up to 3 consecutive
missing/unscorable hours**. An episode ends only at a **scored hour below threshold**, or at a **gap of more
than 3 missing hours**. Reason (user): missing ≠ below threshold; the 06/18 TAI QUALITY gap fragments episodes.
Implementation (me): "missing/unscorable" = any hour with no primary-subset score for that HARP (no SHARP
record, removed by a filter, unscorable, or a multi-region hour). Walking a HARP's scored hours in time order,
a new episode starts at an alarm hour if the previous scored hour was below threshold, or if the previous
scored hour is more than 4 h earlier (> 3 missing hours between).

**T2. Unit = all eligible alarm episodes** (not first-per-region). Each episode is weighted
**1 / (number of eligible episodes in its HARP)**, so each region contributes equally. Grouped CV and the
bootstrap stay grouped by HARP. **Sensitivity: first-episode-per-region.**

**T3. The 18-of-24 trend rule is unchanged.**

Also requested: the Bobra & Couvidat replication check (skipped so far) — **protocol report first, then stop**.

## 2026-09-21 — REVISED STAGE 3 RESULTS (T1, T2, T3) — revised CHECKPOINT 3

Rebuilt with T1 merging and T2 unit; T3 unchanged. Same threshold (−0.992496), same OOF scores.
- Alarm hours 6,836; **episodes (T1): 697 in 220 HARPs** (was 1,311); episode length median 2 alarm hours,
  max 151.
- Exclusions: **197 episodes** "trend window < 18 points"; 0 `history_incomplete`; 0 label-missing.
  **51 HARPs** alarmed with no eligible episode (was 41).

| cohort | episodes | true | false | delayed | regions | regions with >= 1 true episode | region-weighted true / false / delayed |
|---|---:|---:|---:|---:|---:|---:|---|
| **PRIMARY (T2: all eligible episodes, weight 1/episodes-in-HARP)** | **500** | **83** | **417** | **39** | **169** | **33** | **19.53 / 149.47 / 11.09** (sum 169) |
| SENSITIVITY: first eligible episode per region | 169 | 20 | 149 | 13 | 169 | 20 | 20 / 149 / 13 |

**The 55 flaring regions** (previous cohort, >= 1 detected positive hour): **33 now contribute >= 1
true-alarm episode**; 16 are in the cohort with only false episodes; **6 are no longer in the cohort**
(trend window < 18 points).
Mechanism (me): 10 regions of the previous cohort lost eligibility and none gained it. Under T1, a later
fragment that was eligible on its own is absorbed into an episode whose (earlier) onset fails the 18-of-24
rule, which T3 keeps. The first-per-region sensitivity cohort now has 20 true alarms (previous cohort: 25)
for the same reason — merged onsets are earlier, further from the flare.
Artefacts replaced: `data/stage3/cohort_dev.csv` (now all eligible episodes, with `weight`,
`first_eligible`), `exclusions_dev.csv`, `episodes_dev.csv`.
**No trend or model result computed or viewed. Test years not touched.**

## 2026-09-21 — PROPOSED protocol: Bobra & Couvidat replication check (me; awaiting user approval; NOT run)

**Comparator, verified in the paper:** B&C report two parameter sets. **Table 2: C1/C2 = 2.0, operational
case, 13 features → TSS 0.610 ± 0.048.** Table 3: C1/C2 = 15.0 (chosen to maximise TSS) → 0.76 operational
(their conclusion's figure). **Our gate uses C1/C2 = 2.0, so the like-for-like comparator is Table 2's
0.610 ± 0.048,** not 0.76.

**Our quantity:** gate TSS, hour-level, primary subset —
(a) dev pooled out-of-fold at the frozen threshold (0.6793; mildly optimistic, noted at checkpoint 2);
(b) test, Stage 5, 2021/2023/2024, at the frozen threshold (the unbiased figure).
Optional, if approved: TSS at SVM decision value 0 (B&C classify by the sign of the decision function;
we use a max-TSS threshold), computed on the same dev OOF scores — the closest analogue of their rule.

**Pre-stated framing:** the comparison is **descriptive, not pass/fail** — the protocols differ in ways
that move TSS in both directions. Reported alongside our number:

| | Bobra & Couvidat (2015) | this study |
|---|---|---|
| features | 13 | 10 (TOTBSQ, TOTFZ, EPSZ unavailable [corrected 2026-09-22: not SHARP keywords; available in `cgem.lorentz`]) |
| QUALITY | discard > 65536 | keep == 0 (stricter; drops 06/18 TAI) |
| longitude | flares within ±68° of central meridian | HARP |LON_FWT| <= 45° |
| samples | 1 per flare (24 h before GOES peak) + random quiet times | every hourly row (training thinned 6-hourly) |
| class ratio | N/P fixed 16.5 (train and test) | natural (35.2 primary, thinned) |
| split | random 70/30 of examples — same region can be in train and test | grouped by HARP; chronological test |
| threshold | sign of decision function | max TSS on pooled OOF |
| scaling | median / std | median / std (same) |
| flare scale / catalogue | operational scale; NGDC GOES catalogue | true irradiance (K2); SWPC originals |
| period | 2010-05 → 2014-05 | dev 2010–2019; test 2021, 2023, 2024 |
| C1/C2 | 2.0 (Table 2) | 2.0 |
The random 70/30 split lets one region's samples fall on both sides, which tends to inflate B&C's TSS;
our stricter QUALITY and ±45° cut change the population. Neither direction is assumed in advance.
**Stopped: awaiting approval of the protocol and of revised CHECKPOINT 3.**

## 2026-09-21 — DIAGNOSTIC ABLATION, pre-declared as diagnostic  (decided by: user)
Dev 2010–2019 only. **Does not change the primary pipeline. Test years untouched.** Same SVM settings and the
same 10 features throughout. Baseline = current Stage 2 gate (pooled OOF TSS 0.679). Change ONE factor per run;
report TSS, TPR, FPR; single table; no interpretation.
- **D1** threshold = SVM decision value 0 (B&C rule) instead of max-TSS
- **D2** K labels (old ×0.7 scale, file `85b88518…`) instead of K2
- **D3** B&C's longitude limit instead of ±45°, rebuilt from raw
- **D4** B&C's positive/negative sample definition instead of all hourly rows
- **D5** random row-level split instead of HARP-grouped
- **D6** D1–D5 together ("B&C-like pipeline")
Each change is to be traced to a quoted B&C sentence.

### DIAGNOSTIC ABLATION — RESULTS (dev 2010–2019 only; test HARPs never loaded; primary pipeline unchanged)
`diag_ablation.py`, `diag_build.py` → `data/diag/ablation.csv`. Primary subset (single-region), 10 features, same
SVM throughout. Folds held fixed from Stage 2; HARPs that exist only in the ±68° variants dealt into folds by the
same stratified seeded procedure. Unscorable rows excluded (user rule). All TSS are pooled out-of-fold.

| run | source in B&C (2015) | TSS | TPR | FPR | threshold | eval rows | eval positives | pos. HARPs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (Stage 2) | — | 0.6793 | 0.7200 | 0.0407 | −0.9925 | 114,952 | 3,168 | 86 |
| D1 threshold = decision value 0 | no threshold selection described; scikit-learn `SVC` used (p.16) — **inferred**, not stated | 0.3354 | 0.3453 | 0.0099 | 0 | 114,952 | 3,168 | 86 |
| D2 K labels (old scale, file `85b88518…`) | flares from NGDC GOES catalogues, operational scale (p.6) | 0.6773 | 0.7189 | 0.0416 | −0.9999 | 114,952 | 2,440 | 64 |
| D3 longitude ±68° | ARs outside ±68° of central meridian rejected (p.6, p.10) | 0.6456 | 0.6907 | 0.0451 | −0.9979 | 160,223 | 4,821 | 107 |
| D4 B&C samples | positive sample 24 h before GOES peak; random quiet times; 303 pos / 5,000 neg (p.7) | 0.8119 | 0.8697 | 0.0578 | −0.9888 | 4,165 | 238 | 71 |
| D5 random row-level split | examples randomly divided 70/30 (p.21) | 0.7901 | 0.8318 | 0.0417 | −1.0010 | 114,952 | 3,168 | 86 |
| D6 all of D1–D5 | all of the above | 0.6865 | 0.6992 | 0.0128 | 0 | 4,655 | 266 | 74 |

Notes (me, factual only):
- **Baseline reproduced** through the ablation code: TSS 0.6793, identical to Stage 2.
- **Scale switch validated:** `FLARE_SCALE=K` rebuild at ±45° reproduces file `85b88518…` (dev rows, deduplicated)
  in every column except `history_incomplete` (183 rows; the GOES empty-day table is at K2 thresholds; not a gate input).
- D4: B&C's sample definition includes the class ratio (303 positives, 5,000 random negatives), so D4 changes the
  sample construction and N/P = 16.5 together — inseparable as specified. 1,138 K2 M1+ flares in the window;
  238 have a single-region row within 30 min of peak − 24 h (887 do not; 13 flares share a row with another).
  Trained on the sampled rows (no 6-hourly thinning; the sample definition replaces it).
- D6 = K labels + ±68° + D4 samples + random row split + threshold 0. K flare list: 753 M1+ in the window, 266 sampled.
- **Bug found and fixed before reporting (me):** D6's sample builder first drew positives from the K2 flare list
  while using K labels; corrected to the K list. D1–D5 were unaffected and are unchanged by the fix.
- Diagnostic code paths are off by default: `FLARE_SCALE` defaults to K2, `LON_LIMIT` to 45, and `build_dataset.py`
  refuses to write diagnostic settings into the primary `data/` files. A default rebuild of 2014-01 is
  byte-identical to the primary file.

## 2026-09-21 — DIAGNOSTIC: uncertainty for the ablation  (decided by: user; dev only; diagnostic)
1. Verify the comparator for D6: what B&C Table 2's ± represents (sd over how many runs, what varied) and which
   threshold rule produced it; say so if unclear.
2. Baseline and D1–D6 repeated with 20 fold seeds (region-grouped for all except D5, which keeps its random split);
   report mean, sd, min, max TSS.
3. Baseline and D6: region-level bootstrap 95% CI on TSS (1,000 resamples of HARPs) at fixed fold assignment.
4. D2 vs baseline: besides TSS, how many rows, positive HARPs and alarm episodes differ.
Table only, no interpretation. Test years untouched.

### RESULTS — ablation uncertainty (dev only; diagnostic; test years untouched)

**1. Comparator (B&C 2015, verified in the paper).**
- **What the ± is:** the mean and standard deviation over **1,000 repetitions** of training and testing (p.28:
  they "repeat the training and testing phases 1000 times"). **What varied:** the random 70/30 split of
  *examples* (ratio held fixed) and the SVM's random initialisation (p.28). Examples, not regions, were split.
- **Table 2 = C1/C2 = 2.0** (p.21), parameters "selected to achieve the highest HSS2" (Table 2 caption, p.34);
  operational TSS 0.610 ± 0.048. Table 3 (C1/C2 = 15.0, selected for highest TSS) gives 0.76 operational.
- **Threshold rule: not stated.** No threshold selection is described; classification by the default decision
  boundary of scikit-learn's `SVC` is an inference, not a statement in the paper. **Unclear.**
- **Also unclear:** whether the "selected to achieve the highest HSS2" parameter choice was made on data separate
  from the reported test splits. Not stated.
- Consequence for D6 (fact, not interpretation): B&C's ± is a spread over random example-level splits, so the
  closest analogue here is the seed spread of D5/D6, which also use random row-level splits (5-fold, 20 seeds,
  versus 70/30, 1,000 repetitions).

**2. TSS over 20 fold seeds** (seeds 20260921 + 0…19; seed 0 = the Stage 2 folds and reproduces the ablation
table exactly). Region-grouped folds except D5 and D6 (random row split; D6 includes D5's split by definition).
D4/D6 samples fixed; only folds vary.

| run | seed 0 | mean | sd | min | max |
|---|---:|---:|---:|---:|---:|
| baseline | 0.6793 | 0.6760 | 0.0101 | 0.6554 | 0.6923 |
| D1 threshold 0 | 0.3354 | 0.3993 | 0.0325 | 0.3354 | 0.4435 |
| D2 K labels | 0.6773 | 0.6890 | 0.0166 | 0.6542 | 0.7112 |
| D3 ±68° | 0.6456 | 0.6658 | 0.0092 | 0.6456 | 0.6797 |
| D4 B&C samples | 0.8119 | 0.8120 | 0.0075 | 0.7945 | 0.8266 |
| D5 random row split | 0.7901 | 0.7912 | 0.0023 | 0.7869 | 0.7953 |
| D6 all of D1–D5 | 0.6865 | 0.6929 | 0.0056 | 0.6839 | 0.7057 |

**3. Region-level bootstrap** (1,000 resamples of HARPs, seed-0 folds, fixed threshold; 0 resamples lacked a class):

| run | TSS | 95% CI | threshold | HARPs |
|---|---:|---|---:|---:|
| baseline | 0.6793 | [0.5863, 0.7484] | −0.9925 | 986 |
| D6 | 0.6865 | [0.5624, 0.7827] | 0 | 942 |

**4. D2 (K labels) vs baseline (K2 labels), seed-0 folds**

| quantity | baseline (K2) | D2 (K) | difference |
|---|---:|---:|---|
| evaluation rows | 114,952 | 114,952 | identical row keys |
| rows with a different label | | | **728** (all positive under K2 only; 0 positive under K only) |
| positive HARPs | 86 | 64 | 64 in both; **22 baseline only**; 0 D2 only |
| alarm episodes (T1 rule, each run's own threshold) | 697 | 918 | **146 identical**; 551 baseline only; 772 D2 only |
| threshold | −0.9925 | −0.9999 | |
| TSS | 0.6793 | 0.6773 | |

## 2026-09-21 — Decisions on the ablation, the replication protocol, and T4  (decided by: user)

**1. Ablation uncertainty — accepted.** Recorded wording (user):
"B&C Table 2 TSS (0.610) lies within the region-bootstrap 95% CI of our B&C-style reproduction D6 (0.687,
[0.562, 0.783]). Compatible; not a formal test of agreement. B&C's threshold rule and whether their parameter
selection used held-out data are not stated. Their ± (sd over 1,000 random example-level splits) is not directly
comparable to our seed sd. Random example-level splitting (D5) scored higher than region-grouped (baseline) in
all 20 seeds (0.787–0.795 vs 0.655–0.692); cause not decomposed. K vs K2: similar TSS but different positive
HARPs (64 vs 86) and alarm episodes."
**D6 keeps D5's random split — correct; it is the B&C-like combination.**
(Checked by me: D5 > baseline in every one of the 20 seeds.)

**2. Replication protocol — approved as proposed.** Addition: **in Stage 5, the gate test TSS is reported with a
region-level bootstrap 95% CI (1,000 resamples), not a seed sd.**

**3. Revised Checkpoint 3 approved, with one change — T4.**
**T4 — made after seeing cohort sizes, before any trend comparison or model result.**
The episode alarm time **t = the first hour within the episode whose (t−24h, t] trend window has >= 18 of 24
points** (first evaluable hour). **Labels, history and trends are all measured relative to this t. Episodes with
no evaluable hour are excluded.** Reason (user): T1 merging moved onsets before trends are measurable, excluding
whole episodes whose later hours were evaluable. **T1, T2, T3 unchanged.**
Implementation (me): candidate hours for t are the episode's alarm hours in time order (missing hours inside an
episode have no row and cannot be t). The `history_incomplete` rule (D) is then applied at that t: if it is
True the episode is excluded (reason "history_incomplete at t"); t is not moved further.

## 2026-09-21 — STAGE 3b RESULTS: dev cohort under T1–T4 — CHECKPOINT 3b
Same OOF scores and threshold (−0.992496). 697 episodes (T1) in 220 HARPs; 6,836 alarm hours.
- **Exclusions:** **150 episodes** "no evaluable hour" (trend window < 18 points at every alarm hour of the episode);
  0 `history_incomplete at t`; 0 label-missing. **40 HARPs** alarmed with no eligible episode.
- **T4 shift:** t equals the episode onset for 500 of 547 eligible episodes (median shift 0 h) — these are the 500
  episodes of the T1–T3 cohort; the other **47 are recovered** by T4.

| cohort | episodes | true | false | delayed | regions | regions with >= 1 true | region-weighted true / false / delayed |
|---|---:|---:|---:|---:|---:|---:|---|
| **PRIMARY (T1–T4, all eligible episodes, weight 1/episodes-in-HARP)** | **547** | **98** | **449** | **47** | **180** | **41** | **24.13 / 155.87 / 13.04** (sum 180) |
| SENSITIVITY: first eligible episode per region | 180 | 25 | 155 | 16 | 180 | 25 | 25 / 155 / 16 |

- **The 55 previously listed flaring regions:** **41 contribute >= 1 true-alarm episode**; 14 only false; 0 missing
  from the cohort.
- **All 86 dev positive HARPs (primary subset):** **41 contribute >= 1 true-alarm episode**; 21 are in the cohort
  with only false episodes; 24 are not in the cohort — **16 never alarmed**, 8 alarmed but had no eligible episode.
Artefacts replaced: `data/stage3/cohort_dev.csv` (adds `episode_onset`, `hours_onset_to_t`), `exclusions_dev.csv`,
`episodes_dev.csv`. **No trend comparison computed or viewed; no model fitted. Test years untouched.**

## 2026-09-21 — STAGE 4 ON HOLD; full-fidelity B&C reproduction D7  (decided by: user; diagnostic, dev data only)
- **Stage 4 is on hold until the user approves.**
- **Step 1:** protocol audit table from the paper (location for each item), each item marked MATCHABLE /
  NOT MATCHABLE (why) / NOT STATED IN PAPER.
- **Step 2 — D7 "closest possible reproduction":** match every MATCHABLE item (their period, QUALITY rule rebuilt
  from raw, longitude limit, old K scale, sample definitions and N/P, random 70/30 split by example, 1,000 repeats),
  with the 10 available features; NOT STATED items take the most literal reading, listed as assumptions. Report mean
  ± sd TSS over 1,000 repeats (comparable to their 0.610 ± 0.048), min/max, TPR, FPR, positive/negative counts.
- **Step 3 — D7b:** our own pipeline (baseline) restricted to the same period, with a region-bootstrap 95% CI.
Table only, no interpretation.

### D7 Step 1 — B&C (2015) protocol audit (me; paraphrased with page references, not quoted in full)

| item | what the paper says (page) | status for D7 |
|---|---|---|
| data period | SHARP data and flares May 2010 – May 2014 (pp.6, 7) | MATCHABLE — end day not stated; **assumed 2010-05-01 → 2014-05-31** |
| patch type / AR definition | SHARP patches from the automatic detection algorithm; may merge several NOAA ARs into one (pp.7, 9) | MATCHABLE (HARPs) |
| multi-region handling | not described (only that patches can merge NOAA ARs, p.9) | NOT STATED — **assumed ANY rule**: a flare in any NOAA AR of the patch counts for the patch |
| flare–patch association | flares located via NGDC catalogue (p.6); mapping of flare to patch not described | NOT STATED — **assumed via NOAA AR number in `NOAA_ARS`** |
| longitude limit | flares within ±68° of central meridian (p.6); ARs outside ±68° rejected (p.10) | PARTLY MATCHABLE — AR limit applied as \|LON_FWT\| ≤ 68 at the sample time; the flare-location limit is **approximated** by the patch's LON_FWT at the record nearest the flare peak (SWPC XRA lines carry no flare location) |
| QUALITY rule | SHARP entries with QUALITY > 65536 (0x10000) discarded (p.23) | MATCHABLE — rebuilt from raw: keep QUALITY ≤ 65536 |
| flare catalogue | NGDC GOES X-ray flare catalogues (p.6) | NOT MATCHABLE — we use SWPC original event reports (the NGDC lists derive from the same SWPC reports); regions required (NGDC entries with locations, p.6) |
| class scale | GOES operational scale of the time (catalogue, p.6) | MATCHABLE — K (old ×0.7) scale |
| positive sample | sample time exactly 24 h before the GOES peak; every flare counted separately, repeated flares of one AR included (pp.6–7) | MATCHABLE with one approximation — nearest **hourly** record within ±30 min of peak − 24 h (our cache is hourly; B&C used 12-min records, p.7) |
| negative sample | flare-quiet sample times chosen randomly; operational case: AR does not flare within 24 h after the sample time (pp.6–7) | MATCHABLE — random records whose patch has no M1+ in (t, t+24h]; **assumed uniform over eligible records, without replacement, drawn once** |
| number / N/P | 303 positives, 5,000 random negatives (p.7); N/P = 16.5 in training and testing (p.21) | MATCHABLE — N = round(16.5 × P) |
| features | 13 highest-F-score of Table 1 (p.24) | NOT MATCHABLE — 10 of 13 (TOTBSQ, TOTFZ, EPSZ not keywords [corrected 2026-09-22: not SHARP keywords; available in `cgem.lorentz`]) |
| scaling | subtract median, divide by standard deviation (p.23) | MATCHABLE — **which data the median/sd come from is not stated; assumed the whole catalogue, before splitting** (literal reading of a pre-processing step) |
| SVM kernel, parameters | RBF; C = 4, γ = 0.075, tol 1e-8 (pp.15, 21) | MATCHABLE |
| C1/C2 | 2.0 for Table 2 (p.21) | MATCHABLE — **which class carries C is not stated; assumed C2 = C = 4 (negatives), C1 = 8** (same convention as our gate) |
| threshold rule | not described | NOT STATED — **assumed the SVC default (decision value 0)** |
| train/test split | examples randomly divided 30% test / 70% train, ratio always kept (pp.21, 28); N/P 16.5 in both | MATCHABLE — random, by example, **stratified by class** so both keep N/P |
| repeats | 1,000 repetitions; means and sds in Tables 2–3 (p.28) | MATCHABLE — 1,000 |
| metric | TSS = TP/(TP+FN) − FP/(FP+TN) (eq. 17, p.19) | MATCHABLE |
| missing data | not described | NOT STATED — **assumed: examples with any missing feature dropped before sampling** |
| NOAA mapping for negatives | not described | NOT STATED — **assumed: patches with a NOAA number only** (otherwise "does not flare" cannot be determined) |

### D7 Step 2 and D7b Step 3 — RESULTS (diagnostic; dev period only; test years untouched)
`diag_d7.py` → `data/diag/d7_repeats.csv`. Built from raw chunk files with the audit-table choices and assumptions.

**D7 construction counts**
- Raw rows 2010-05 … 2014-06: 379,600 → QUALITY ≤ 65536: 343,198 → |LON_FWT| ≤ 68: 252,052 → features present and
  NOAA-mapped: 140,847 (eligible rows restricted to 2010-05-01 … 2014-05-31 for sampling).
- SWPC M1+ flares, K scale, with a region: 455. Used as positives: **272** (269 distinct records; 3 records serve two
  flares each, one example per flare as in B&C). Not used: 121 flare-location proxy (patch |LON| > 68 or no record at
  the peak); 61 no patch record within 30 min of peak − 24 h passing the filters; 1 sample time outside the period;
  0 without a peak time; 0 region in no patch.
- Negative pool (eligible records, no M1+ from the patch's regions in (t, t+24h]): 132,939; drawn once:
  **N = 4,488** (N/P = 16.50).
- Distinct patches: 90 among positives, 761 among negatives.

| run | TSS | sd | min | max | TPR | FPR | P | N | uncertainty |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **B&C (2015) Table 2, operational** | **0.610** | 0.048 | — | — | — | — | 303 | 5,000 | sd over 1,000 random 70/30 splits |
| **D7 closest reproduction** | **0.5267** | **0.0500** | 0.3562 | 0.6969 | 0.5399 ± 0.0505 | 0.0132 ± 0.0032 | 272 | 4,488 | sd over 1,000 random 70/30 splits (stratified; ~82 pos / 1,346 neg per test set) |
| **D7b our baseline, same period** (2010-05-01 … 2014-05-31) | **0.5861** | — | — | — | 0.6318 | 0.0457 | 57 pos HARPs, 1,863 pos rows | 71,023 rows, 613 HARPs | region bootstrap 95% CI **[0.4665, 0.6800]**, 1,000 resamples |

D7b: Stage 2 baseline machinery (Stage 2 fold map, 6-hourly thinned single-region training, hourly OOF evaluation) on
rows in the period only; the max-TSS threshold (−0.9918) is re-chosen on this period's OOF scores.
D7 assumptions in force (from the audit table): end date 2014-05-31; ANY rule; flare→patch via NOAA number; flare-
location proxy; nearest hourly record (±30 min) instead of 12-min; negatives uniform, without replacement, drawn once;
scaling on the whole catalogue; C2 = C = 4, C1 = 8; threshold = decision value 0; stratified split; examples with
missing features dropped; NOAA-mapped patches only; no missing-SWPC-day rule (B&C have none).
**Stage 4 remains on hold.**

## 2026-09-21 — DIAGNOSTIC D7t, pre-declared  (decided by: user; dev only)
Identical to D7, except **the threshold is chosen within each 70/30 split by max TSS on the TRAINING 70% only**,
then applied to the 30% test. Report mean ± sd, min, max TSS over 1,000 repeats. Table only. **Stage 4 stays on hold.**
Note (me, factual): the training-set decision values used to choose the threshold are in-sample (the SVM is fitted
on those same examples) — as specified.

### D7t — RESULTS (diagnostic; dev period only; test years untouched)
Same catalogue (P 272, N 4,488) and the same 1,000 splits as D7 — the rerun reproduces `d7_repeats.csv` byte-for-byte.
Output: `data/diag/d7t_repeats.csv`.

| run | threshold rule | TSS mean | sd | min | max | TPR | FPR | threshold |
|---|---|---:|---:|---:|---:|---:|---:|---|
| B&C (2015) Table 2 | not stated | 0.610 | 0.048 | — | — | — | — | — |
| D7 | decision value 0 (assumed) | 0.5267 | 0.0500 | 0.3562 | 0.6969 | 0.5399 ± 0.0505 | 0.0132 ± 0.0032 | 0 |
| **D7t** | **max TSS on the training 70% (in-sample), applied to the 30%** | **0.7065** | **0.0401** | **0.5680** | **0.8189** | 0.7843 ± 0.0427 | 0.0778 ± 0.0094 | mean −0.9926 (−1.0241 … −0.8920) |
**Stage 4 remains on hold.**

## 2026-09-21 — Replication conclusion  (decided by: user)
"Closest reproduction of B&C 2015 (D7): TSS 0.527 ± 0.050 with decision value 0; D7t: 0.707 ± 0.040 with threshold
learned on the training 70%. B&C's reported 0.610 ± 0.048 lies between these; their threshold rule is not stated.
Replication diagnostics complete; no changes to the primary pipeline."

## 2026-09-21 — STAGE 4 hold released  (decided by: user)
Specification (user): Logistic **A** = gate score + n_C + n_M + n_X; **B** = A + USFLUX and TOTUSJH relative 24h slopes.
`LogisticRegression`, L2, **C = 1.0, no tuning**; inputs standardised inside each training fold; episode weights
1/(eligible episodes in HARP). Grouped 5-fold CV by HARP on the dev cohort, seed 20260921. Report weighted log-loss and
AUC for A and B (per fold and pooled) and a region-bootstrap 95% CI on log-loss(A) − log-loss(B), 1,000 HARP resamples.
Supporting: score-matched pairs (caliper fixed before looking at trends). Exploratory: delayed vs true, descriptive
only. Also the first-episode sensitivity cohort. Write `frozen/frozen_spec.json`, hash it here. Stop at CHECKPOINT 4.

### Stage 4 implementation details — PRE-REGISTERED by me, BEFORE any trend or model result
1. **Folds:** the cohort's HARPs are split into 2 strata (>= 1 true-alarm episode / none), each shuffled with seed
   20260921 and dealt round-robin into 5 folds. Every episode of a HARP is in its HARP's fold.
2. **Standardisation:** mean / sd of each input, fitted on the training folds only (`StandardScaler`).
3. **Fit:** `LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=10000)`, `sample_weight` = episode weight.
4. **Metrics:** out-of-fold predicted probabilities. **Weighted log-loss** = Σ wᵢ·ℓᵢ / Σ wᵢ; **weighted AUC** =
   ROC AUC with `sample_weight`. Per fold (on that fold's held-out episodes) and pooled (all OOF predictions).
5. **Primary contrast:** Δ = log-loss(A) − log-loss(B) on the pooled OOF predictions (positive Δ = B better).
   **Bootstrap:** 1,000 resamples of HARPs with replacement (seed 20260921); predictions held fixed (no refit);
   weighted Δ recomputed per resample; percentile 95% CI.
6. **Score-matched pairs (supporting):** each true-alarm episode is matched 1:1, greedy nearest neighbour on the **gate
   score**, without replacement, to a false-alarm episode **from a different HARP**; true episodes processed in a seeded
   random order. **Caliper = 0.2 × SD of the gate score over the dev cohort's episodes** (computed from gate scores
   only). Reported: number of pairs, unmatched true episodes, max |score difference|; for each slope, mean and median
   of the paired difference (true − false) with a 95% bootstrap CI resampling pairs **clustered by the true episode's
   HARP** (1,000 resamples).
7. **Delayed vs true (exploratory, descriptive only):** weighted mean and median of gate score, n_C, n_M, n_X and the two
   slopes for true, delayed and other-false episodes; counts; no test statistic.
8. **First-episode sensitivity:** items 1–5 repeated on the first-eligible-episode cohort (weights 1).
9. **Stage 5 prediction rule for A and B (proposed; flagged for approval at CHECKPOINT 4):** by analogy with N2, test
   probabilities = mean of the 5 fold models' predicted probabilities; no refit on the full dev cohort.

## 2026-09-21 — STAGE 4 RESULTS (dev only) — CHECKPOINT 4
`stage4_models.py` (pre-registered details above). Rerun reproduces the out-of-fold cohort predictions byte-for-byte.
Test HARPs and years never loaded (asserted).

**PRIMARY cohort** (T1–T4; 547 episodes, 98 true; 180 HARPs, 41 with a true episode; weighted true 24.13 of 180):

| fold | episodes | true | HARPs | true HARPs | log-loss A | log-loss B | AUC A | AUC B | Δ = A − B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 97 | 14 | 37 | 9 | 0.3377 | 0.3056 | 0.8209 | 0.8693 | 0.0320 |
| 1 | 93 | 17 | 36 | 8 | 0.2906 | 0.3228 | 0.8813 | 0.7956 | −0.0322 |
| 2 | 110 | 21 | 36 | 8 | 0.3924 | 0.3933 | 0.5884 | 0.6094 | −0.0009 |
| 3 | 132 | 30 | 36 | 8 | 0.3897 | 0.3573 | 0.6683 | 0.8178 | 0.0324 |
| 4 | 115 | 16 | 35 | 8 | 0.2551 | 0.2661 | 0.8841 | 0.7708 | −0.0110 |
| **pooled** | **547** | **98** | **180** | **41** | **0.3336** | **0.3293** | **0.7432** | **0.7695** | **0.0043** |

**Δ log-loss (A − B), pooled: 0.0043; HARP-bootstrap 95% CI [−0.0114, 0.0253]** (1,000 resamples).

**SENSITIVITY — first eligible episode per region** (180 episodes, 25 true, 180 HARPs):

| fold | episodes | true | log-loss A | log-loss B | AUC A | AUC B | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 36 | 5 | 0.3352 | 0.3674 | 0.7548 | 0.6903 | −0.0322 |
| 1 | 36 | 5 | 0.3844 | 0.3440 | 0.6581 | 0.8129 | 0.0404 |
| 2 | 36 | 5 | 0.3626 | 0.3273 | 0.7032 | 0.8258 | 0.0352 |
| 3 | 36 | 5 | 0.6270 | 0.6553 | 0.4839 | 0.4903 | −0.0283 |
| 4 | 36 | 5 | 0.3008 | 0.2690 | 0.8000 | 0.8516 | 0.0317 |
| **pooled** | **180** | **25** | **0.4020** | **0.3926** | **0.6521** | **0.7272** | **0.0094** |

**Δ pooled 0.0094; HARP-bootstrap 95% CI [−0.0162, 0.0435].**

**Score-matched pairs (supporting):** caliper **0.0747** (0.2 × SD of gate score over 547 episodes, fixed from scores
only before trends were examined); **83 pairs** from 98 true episodes (15 unmatched); max |score difference| 0.0733;
35 true HARPs. Paired difference (true − false), 95% CI clustered by true HARP (1,000 resamples):
- rel. slope USFLUX: mean 2.832e-3, median 1.858e-3, CI [−4.238e-3, 1.037e-2]
- rel. slope TOTUSJH: mean 3.294e-3, median 2.777e-3, CI [−3.848e-3, 1.188e-2]

**Exploratory, descriptive only** — weighted mean [median]:

| group | episodes | HARPs | weight | gate score | n_C | n_M | n_X | rel. slope USFLUX | rel. slope TOTUSJH |
|---|---:|---:|---:|---|---|---|---|---|---|
| true | 98 | 41 | 24.13 | −0.331 [−0.81] | 5.23 [4] | 1.46 [0] | 0.134 [0] | 0.0131 [0.00245] | 0.0164 [0.00218] |
| delayed | 47 | 26 | 13.04 | −0.724 [−0.936] | 4.37 [2] | 1.13 [0] | 0.115 [0] | 0.0129 [0.00497] | 0.0158 [0.00655] |
| other false | 402 | 160 | 142.83 | −0.916 [−0.973] | 2.10 [1] | 0.157 [0] | 0.00933 [0] | 0.00948 [0.000401] | 0.0109 [0.000123] |

**Frozen specification:** `frozen/frozen_spec.json` (tracked),
**SHA-256 `598be4fa9dc21eb309f9a3e89162f4d62e3c7d2e3c631ff1e119b79a7f964632`**. It fixes the labelled-file and split
hashes, gate features / scaling / SVM / threshold (−0.992496) / fold-model hashes, cohort rules T1–T4 (with the
`cohort.py` hash), models A and B, the caliper, the seeds, and the Stage 5 metrics.
**Awaiting approval.** Open item for approval: pre-registered item 9 — Stage 5 predictions for A and B = mean of the
5 fold models' probabilities, no refit.
**Test years untouched.**

## 2026-09-21 — CHECKPOINT 4 approved; Stage 5 prediction rule approved  (decided by: user)
**Approved: models A and B score the test set with the mean of the 5 fold models' predicted probabilities; no refit.**
Marked in `frozen/frozen_spec.json` (only the `models.test_prediction` field changed; `git diff` shows one line).
**New SHA-256 of `frozen/frozen_spec.json`: `1d20506849930dd52f7f77333f44e4f458a65d9946cb0007a1c603816785368d`**
(supersedes `598be4fa…`). No other changes to the frozen spec.

### Stage 5 execution details fixed BEFORE the test run (me; where the spec is silent)
- **Integrity check first:** the script recomputes every hash in `frozen_spec.json` (labelled file, split, gate fold
  models, `cohort.py`, A/B fold models) and stops if any differs.
- **Gate evaluation population:** scorable rows of test HARPs in the stated years; hour level = every row; **region level
  = one contingency entry per HARP: positive if >= 1 positive row, alarmed if >= 1 alarm hour** in that period/subset.
  TSS, HSS, FAR at both levels; hour- and region-level TSS with a HARP-bootstrap 95% CI, 1,000 resamples; TSS at
  decision value 0 at both levels.
- **Matched pairs:** the **frozen dev caliper 0.0747** (the Stage 4 spec said "caliper fixed on dev"; `frozen_spec.json`
  records the value), same matching procedure.
- **Primary Δ bootstrap: 10,000 HARP resamples** (as in `frozen_spec.json`); seed 20260921 throughout.
- **Robustness subsets (≤ 2 regions, all HARPs):** the gate's fold models score those rows (no refit); the cohort is
  built with T1–T4 from alarms in that subset's rows; models A and B (fold models, no refit) score it.
- **Run once:** the code is first exercised end-to-end on a DEV-period stand-in (2014, dev HARPs; outputs discarded, not
  test data) to remove coding errors; then the test run is executed exactly once.
- **Recorded before the test run (me):** cohort alarms/episodes are restricted to rows in the evaluation years; the
  24-h trend window at t uses every labelled row of the HARP, so an alarm early in an evaluation year can use SHARP
  features from the end of an excluded year (e.g. 2022-12-31 for a 2023-01-01 alarm). Features only — never labels —
  come from outside the evaluation years.
- **Dry run completed** (`stage5_test.py dryrun`: dev HARPs, 2013–2014, outputs in /tmp, discarded): every code path
  ran without error. Its numbers are a code check, not results.

## 2026-09-21 — STAGE 5 RESULTS: held-out test, run ONCE — CHECKPOINT 5 (results tables only, no interpretation)

`stage5_test.py test`: single execution, exit 0. **Every hash in `frozen/frozen_spec.json` verified before scoring.** Test HARPs 801; rows 2021–2024: 101,766; **unscorable 34 (0 positive), excluded**. Gate threshold −0.992496 (frozen); gate score = mean of the 5 fold models' decision values; A/B probabilities = mean of the 5 fold models; no refit.

### Gate (hour level = rows; region level = one entry per HARP; TSS CI = HARP bootstrap, 1,000 resamples)

| period | subset | level | threshold | N | positives | TSS | TSS 95% CI | HSS | FAR | TPR | FPR |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| primary 2021/2023/2024 | single | hour | frozen −0.9925 | 53,356 | 1,976 | **0.5467** | [0.4120, 0.6598] | 0.3670 | 0.7021 | 0.6012 | 0.0545 |
| primary 2021/2023/2024 | single | hour | 0 | 53,356 | 1,976 | **0.3227** | [0.1994, 0.4338] | 0.3536 | 0.5832 | 0.3411 | 0.0184 |
| primary 2021/2023/2024 | single | region | frozen −0.9925 | 450 | 55 | **0.7284** | [0.6301, 0.8198] | 0.5236 | 0.5429 | 0.8727 | 0.1443 |
| primary 2021/2023/2024 | single | region | 0 | 450 | 55 | **0.4757** | [0.3390, 0.6101] | 0.5746 | 0.1818 | 0.4909 | 0.0152 |
| primary 2021/2023/2024 | <=2 | hour | frozen −0.9925 | 64,642 | 3,401 | **0.6089** | [0.5150, 0.6945] | 0.4233 | 0.6483 | 0.6783 | 0.0694 |
| primary 2021/2023/2024 | <=2 | hour | 0 | 64,642 | 3,401 | **0.3966** | [0.2806, 0.4968] | 0.4267 | 0.5057 | 0.4205 | 0.0239 |
| primary 2021/2023/2024 | <=2 | region | frozen −0.9925 | 528 | 87 | **0.7288** | [0.6591, 0.7950] | 0.5606 | 0.4868 | 0.8966 | 0.1678 |
| primary 2021/2023/2024 | <=2 | region | 0 | 528 | 87 | **0.4876** | [0.3818, 0.5932] | 0.5815 | 0.1538 | 0.5057 | 0.0181 |
| primary 2021/2023/2024 | all | hour | frozen −0.9925 | 77,085 | 6,955 | **0.6452** | [0.5829, 0.6986] | 0.4519 | 0.6087 | 0.7629 | 0.1177 |
| primary 2021/2023/2024 | all | hour | 0 | 77,085 | 6,955 | **0.4936** | [0.4066, 0.5660] | 0.4912 | 0.4657 | 0.5403 | 0.0467 |
| primary 2021/2023/2024 | all | region | frozen −0.9925 | 605 | 142 | **0.7266** | [0.6743, 0.7800] | 0.6029 | 0.4159 | 0.9296 | 0.2030 |
| primary 2021/2023/2024 | all | region | 0 | 605 | 142 | **0.6063** | [0.5285, 0.6873] | 0.6629 | 0.1495 | 0.6408 | 0.0346 |
| sensitivity incl. 2022 | single | hour | frozen −0.9925 | 71,862 | 2,381 | **0.5224** | [0.4115, 0.6256] | 0.3347 | 0.7331 | 0.5766 | 0.0543 |
| sensitivity incl. 2022 | single | hour | 0 | 71,862 | 2,381 | **0.2753** | [0.1582, 0.3900] | 0.3089 | 0.6233 | 0.2919 | 0.0166 |
| sensitivity incl. 2022 | single | region | frozen −0.9925 | 605 | 71 | **0.6812** | [0.5841, 0.7621] | 0.4813 | 0.5755 | 0.8310 | 0.1498 |
| sensitivity incl. 2022 | single | region | 0 | 605 | 71 | **0.4179** | [0.3015, 0.5368] | 0.5116 | 0.2439 | 0.4366 | 0.0187 |
| sensitivity incl. 2022 | <=2 | hour | frozen −0.9925 | 86,824 | 4,034 | **0.5942** | [0.5091, 0.6642] | 0.3916 | 0.6821 | 0.6636 | 0.0694 |
| sensitivity incl. 2022 | <=2 | hour | 0 | 86,824 | 4,034 | **0.3667** | [0.2669, 0.4579] | 0.3979 | 0.5347 | 0.3884 | 0.0218 |
| sensitivity incl. 2022 | <=2 | region | frozen −0.9925 | 709 | 110 | **0.7008** | [0.6330, 0.7669] | 0.5268 | 0.5176 | 0.8727 | 0.1720 |
| sensitivity incl. 2022 | <=2 | region | 0 | 709 | 110 | **0.4783** | [0.3880, 0.5717] | 0.5666 | 0.1912 | 0.5000 | 0.0217 |
| sensitivity incl. 2022 | all | hour | frozen −0.9925 | 101,732 | 7,972 | **0.6446** | [0.5875, 0.6994] | 0.4335 | 0.6338 | 0.7559 | 0.1113 |
| sensitivity incl. 2022 | all | hour | 0 | 101,732 | 7,972 | **0.4828** | [0.4009, 0.5543] | 0.4776 | 0.4871 | 0.5252 | 0.0424 |
| sensitivity incl. 2022 | all | region | frozen −0.9925 | 801 | 172 | **0.7077** | [0.6555, 0.7581] | 0.5704 | 0.4510 | 0.9128 | 0.2051 |
| sensitivity incl. 2022 | all | region | 0 | 801 | 172 | **0.5913** | [0.5212, 0.6615] | 0.6474 | 0.1756 | 0.6279 | 0.0366 |

### Test cohort sizes (rules T1–T4)

| period | subset | episodes (T1) | alarm HARPs | excluded (no evaluable hour) | eligible episodes | true | false | delayed | regions | regions with true | region-weighted true |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary 2021/2023/2024 | single | 367 | 105 | 54 | 313 | 45 | 268 | 26 | 98 | 28 | 14.46 |
| primary 2021/2023/2024 | <=2 | 563 | 152 | 87 | 476 | 81 | 395 | 53 | 139 | 43 | 22.46 |
| primary 2021/2023/2024 | all | 971 | 226 | 126 | 845 | 180 | 665 | 92 | 212 | 86 | 45.89 |
| sensitivity incl. 2022 | single | 486 | 139 | 72 | 414 | 62 | 352 | 36 | 128 | 37 | 18.51 |
| sensitivity incl. 2022 | <=2 | 745 | 199 | 117 | 628 | 109 | 519 | 68 | 182 | 56 | 28.86 |
| sensitivity incl. 2022 | all | 1197 | 286 | 162 | 1035 | 215 | 820 | 113 | 267 | 102 | 54.28 |

All exclusions were "no evaluable hour"; none for `history_incomplete at t` or label-missing.

### Models A vs B (weighted; Δ = log-loss(A) − log-loss(B); CI = HARP bootstrap, 10,000 resamples)

| period | subset | cohort | episodes | true | HARPs | true HARPs | log-loss A | log-loss B | **Δ** | **Δ 95% CI** | AUC A | AUC B |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| primary 2021/2023/2024 | single | all eligible (T2) | 313 | 45 | 98 | 28 | 0.3686 | 0.3737 | **-0.0051** | **[-0.0201, 0.0094]** | 0.8111 | 0.7974 |
| primary 2021/2023/2024 | single | first episode per region | 98 | 13 | 98 | 13 | 0.4066 | 0.4091 | -0.0025 | [-0.0265, 0.0210] | 0.7593 | 0.7330 |
| primary 2021/2023/2024 | <=2 | all eligible (T2) | 476 | 81 | 139 | 43 | 0.3747 | 0.3814 | -0.0067 | [-0.0182, 0.0049] | 0.8089 | 0.7829 |
| primary 2021/2023/2024 | <=2 | first episode per region | 139 | 19 | 139 | 19 | 0.4022 | 0.4044 | -0.0022 | [-0.0200, 0.0152] | 0.7618 | 0.7276 |
| primary 2021/2023/2024 | all | all eligible (T2) | 845 | 180 | 212 | 86 | 0.4250 | 0.4260 | -0.0010 | [-0.0101, 0.0078] | 0.8083 | 0.8103 |
| primary 2021/2023/2024 | all | first episode per region | 212 | 45 | 212 | 45 | 0.4841 | 0.4819 | 0.0022 | [-0.0118, 0.0157] | 0.7599 | 0.7561 |
| sensitivity incl. 2022 | single | all eligible (T2) | 414 | 62 | 128 | 37 | 0.3726 | 0.3741 | -0.0015 | [-0.0159, 0.0133] | 0.7994 | 0.7686 |
| sensitivity incl. 2022 | single | first episode per region | 128 | 18 | 128 | 18 | 0.4270 | 0.4216 | 0.0054 | [-0.0199, 0.0336] | 0.7247 | 0.6879 |
| sensitivity incl. 2022 | <=2 | all eligible (T2) | 628 | 109 | 182 | 56 | 0.3864 | 0.3899 | -0.0035 | [-0.0149, 0.0079] | 0.7986 | 0.7664 |
| sensitivity incl. 2022 | <=2 | first episode per region | 182 | 27 | 182 | 27 | 0.4487 | 0.4462 | 0.0026 | [-0.0174, 0.0244] | 0.7075 | 0.6724 |
| sensitivity incl. 2022 | all | all eligible (T2) | 1035 | 215 | 267 | 102 | 0.4278 | 0.4277 | 0.0001 | [-0.0085, 0.0088] | 0.7981 | 0.7955 |
| sensitivity incl. 2022 | all | first episode per region | 267 | 54 | 267 | 54 | 0.4992 | 0.4942 | 0.0050 | [-0.0102, 0.0210] | 0.7267 | 0.7239 |

Primary analysis = first row (primary years, single-region, all eligible episodes).

### Score-matched pairs (primary, single-region; frozen dev caliper 0.0747)

41 pairs from 45 true episodes (4 unmatched); max |score difference| 0.0469; 26 true HARPs.

| slope | mean paired difference (true − false) | median | 95% CI (mean; clustered by true HARP, 1,000) |
|---|---:|---:|---|
| rel_slope_usflux | 0.002191 | 0.002213 | [-0.003941, 0.007951] |
| rel_slope_totusjh | 0.002309 | -0.0006981 | [-0.003397, 0.00864] |

### Delayed vs true (primary, single-region; descriptive only; weighted mean, [median] for slopes)

| group | episodes | HARPs | weight | gate score | n_C | n_M | n_X | rel. slope USFLUX | rel. slope TOTUSJH |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| true | 45 | 28 | 14.46 | -0.342 | 5.22 | 0.613 | 0.207 | 0.0077 [0.00259] | 0.0114 [0.00205] |
| delayed | 26 | 20 | 8.11 | -0.661 | 2.47 | 0.452 | 0.0411 | 0.0243 [0.00867] | 0.0283 [0.00666] |
| other false | 242 | 87 | 75.42 | -0.875 | 1.97 | 0.243 | 0.0155 | 0.0119 [0.00311] | 0.013 [0.00199] |

### Output files (data/stage5/, SHA-256)

- `data/stage5/cohort_sizes.csv` `8ef8337d837f71ac4acfa356beff11ebbcc06b834150438f143fbbd8dde480c5`
- `data/stage5/cohort_test_primary.csv` `49fe435c24264c291b010a223519ebad4b1237a08d85976b68b3ef945a86c083`
- `data/stage5/delayed_descriptive.csv` `78bd507ac06a07d86c00a34387cf8f14c75edf4192b725e475aa7665ea60ccfa`
- `data/stage5/gate_gate.csv` `5e88db8d7075302ebdd55ccb8088485fcd00a1e4893bc92fbaa028cf214c2054`
- `data/stage5/matched_pairs_test.csv` `15acc54d50bd58cd3eef08091f72ef3c1ffc397a36d96563325487ef364e8aa4`
- `data/stage5/models_b.csv` `77cd1e0db0f2e7eacf04f785c7c6761e212efd63f055582931a7b72363b52e6b`
- `data/stage5/pairs_summary.csv` `d0dd9b6c9d1daeadee50866b1c53ea56749ca796ea251653a456962832d00cbf`
- `stage5_test.log` (console output) is tracked in git.

## 2026-09-21 — PRIMARY RESULT FINAL; next phase  (decided by: user)
**The primary result (Stage 5, CHECKPOINT 5) stays unchanged and is recorded as FINAL.**
**No new analysis is to be run on 2021–2024.**

**Step A (dev only, exploratory):** within the dev cohort, logistic models with (i) gate score only, (ii) C/M/X history
only, (iii) score + history; same CV, weights and regularisation as Stage 4; weighted log-loss and AUC; table only.
(Note (me): (iii) has the same inputs as model A, so it reproduces Stage 4's A.)

### Step B — PRE-REGISTERED 2026-09-21, before R has been computed anywhere  (decided by: user; details marked)
- **Feature R** = hours since the region's most recent **C1+ flare (K2 scale)** before t, **capped at 48 h** (R = 48 if
  none in the window); used as **log(1 + R)**.
  Details (me, fixing the literal reading): "region" = the NOAA regions in the HARP's `NOAA_ARS` at t (ANY rule, as for
  labels and history); flare time = **start time** (as for labels and history); "before t" = start in **(t − 48 h, t)**;
  R = (t − start of the most recent such flare) in hours, else 48; C1+ = harmonised K2 flux >= 1e-6; SWPC originals.
- **Hypothesis: model C = A + log(1 + R) beats A.** Model C: same estimator, standardisation, weights, CV and seeds as A.
  "Beats" = weighted log-loss(A) − log-loss(C) > 0, with a HARP-bootstrap 95% CI (same procedure as the primary).
- **Operating point, fixed on dev:** report the false-alarm count for A vs C at the dev threshold that gives C the same
  true-alarm rate as A.
  **For confirmation (me): A's own operating threshold τ_A is not specified.** Proposed: τ_A = the threshold maximising
  weighted TSS on A's dev out-of-fold probabilities (the same rule used for the gate); τ_C = the threshold on C's dev
  out-of-fold probabilities giving the same weighted true-alarm rate (TPR) as A at τ_A; report false alarms (episodes
  and region-weighted) at τ_A and τ_C. Both thresholds fixed on dev.
- **Evaluation set:** not yet specified — 2021–2024 is closed (above); the candidate is the fresh confirmation set of
  Step C. **Nothing in Step B is computed until the user confirms τ_A and the evaluation set.**

**Step C (report only; fetch nothing):** feasibility of a fresh confirmation set 2025-01-01 → latest available: SHARP
keyword availability, SWPC report coverage, and whether SWPC 4-digit Reg# → +10000 still holds past region 14000
(verify against SHARP NOAA_ARS).

### STEP A — RESULTS (dev only, exploratory; table only)
`stepA_dev.py` (reuses `stage4_models.cv`; `stage4_models.py` given a main guard and verified to reproduce its outputs
byte-for-byte; all 10 frozen A/B fold models still match their frozen hashes; Step A saves no models).

| cohort | model | episodes | true | weighted log-loss | weighted AUC |
|---|---|---:|---:|---:|---:|
| primary (all eligible, region-weighted) | (i) gate score only | 547 | 98 | 0.3260 | 0.7403 |
| primary (all eligible, region-weighted) | (ii) history only (n_C, n_M, n_X) | 547 | 98 | 0.3764 | 0.7260 |
| primary (all eligible, region-weighted) | (iii) score + history (= A) | 547 | 98 | 0.3336 | 0.7432 |
| first eligible episode per region | (i) gate score only | 180 | 25 | 0.3182 | 0.7551 |
| first eligible episode per region | (ii) history only | 180 | 25 | 0.4552 | 0.6658 |
| first eligible episode per region | (iii) score + history (= A) | 180 | 25 | 0.4020 | 0.6521 |
Per-fold log-losses in `data/stage4/stepA_dev.csv`. (iii) reproduces Stage 4's model A exactly.

### STEP C — feasibility of a confirmation set 2025-01-01 → latest (report only; nothing fetched)
Checked with metadata only: JSOC series description, NCEI directory listings (names/dates), and the local cache.

| item | finding | status |
|---|---|---|
| SHARP keywords, `hmi.sharp_cea_720s` | series live on JSOC (prime keys HARPNUM, T_REC); latest T_REC **not checked** — requires a record query | **unverified** without a (one-record, keyword-only) query |
| SWPC daily event reports (NCEI) | 2025: all 12 month directories; 2026: through **2026-09-20**; spot-checked months complete (2025-01, -02, -03, -06; 2026-01, -08) **except 2025-12: files for the 1st–29th only (12-30 and 12-31 absent)** | available; 2 missing days → the label-missing rule (C) would apply |
| GOES XRS 1-min science (empty-day rule) | GOES-18: 2022–2026; GOES-19: 2024–2026; GOES-16: to 2025 | available; Table 11 lists **GOES-18 primary / GOES-19 secondary from 2025-04-07** (already transcribed) |
| SWPC Reg# → +10000 past region 14000 | local cache ends 2025-01-02; highest region seen: SWPC 13947 (Reg# 3947), SHARP `NOAA_ARS` 13960 — **region 14000 is not in the cache** | **unverified** — needs SWPC reports and SHARP `NOAA_ARS` from after ~14000 was assigned |
| flare scale 2025+ | XRA from GOES-18/19 = true scale; `swpc.py` already treats G16–G19 as true scale (K2: used as reported) | consistent, no change needed |
Proposed minimal checks, **not run** (each a fetch, awaiting approval): (1) one keyword-only JSOC query for the latest
`hmi.sharp_cea_720s` T_REC; (2) SWPC reports for a few days around the first region ≥ 14000 plus a keyword-only SHARP
`NOAA_ARS` query for the same days, to confirm the Reg# rule. **No analysis run on 2021–2024.**

## 2026-09-21 — Confirmation-set decisions  (decided by: user; before any 2025+ data is fetched or R is computed)
1. **τ_A approved:** the threshold maximising TSS on A's dev out-of-fold predictions.
2. **Confirmation set = 2025-01-01 → the latest date with SHARP + SWPC + GOES coverage.** The end date is determined
   from check 1 below and **frozen in this log BEFORE fetching**. Identical rules: K2 scale; CHECK 5 per calendar year
   (>= 90% rule; failing years excluded); missing-day and empty-day rules; frozen gate and threshold; cohort rules
   T1–T4; single-region primary.
3. **Pre-registered confirmatory tests on the 2025+ set:**
   (a) **Replication of the primary:** log-loss(A) − log-loss(B), region-bootstrap 95% CI, 10,000 HARP resamples.
   (b) **Step B:** log-loss(A) − log-loss(C), same CI; plus the false-alarm count for A vs C at τ_A's dev true-alarm rate.
   **Models A, B, C are trained on dev only (2010–2019) and frozen before 2025+ is scored.**
4. **Step A recorded as exploratory:** on dev, the gate score alone had the lowest log-loss; adding the C/M/X counts
   did not improve it.
5. **Approved: the two keyword-only checks** (latest SHARP T_REC; SWPC Reg# convention around the first region >= 14000
   vs SHARP NOAA_ARS). Report, then stop.
**No 2025+ data is fetched until the user approves the frozen end date and the check results.**

### CHECK RESULTS — confirmation-set feasibility (keyword-only; approved checks)
**Check 1 — coverage end dates**
- **SHARP (`hmi.sharp_cea_720s`):** latest T_REC = **2026-08-17 00:00:00 TAI**. Found by keyword-only queries (T_REC,
  HARPNUM): daily sampling finds no records 2026-08-25 → 09-22 and the latest at 08-17 00:00; an hourly query of
  08-17 → 08-25 returns only the 08-17 00:00 slot (20 records).
- **SWPC daily reports (NCEI):** through **2026-09-20**; archive lacks **2025-12-30 and 2025-12-31** (the missing-day rule applies).
- **GOES XRS 1-min science:** GOES-18 and GOES-19 through **2026-09-20** (latest daily files d20260920).
- **Limiting source: SHARP.**

**Check 2 — SWPC Reg# convention past region 14000** (SWPC reports 2025-02-18 → 02-24 downloaded into the cache; SHARP
`NOAA_ARS` keyword query, same days, hourly)
- SHARP: region 14000 first appears 2025-02-20 (daily sampling); neighbours 13995–14005 first appear 02-12 → 02-22.
  Region 14001 already appears on 2025-02-08, merged with 13989 in HARP 12732 — consistent with `NOAA_ARS` being
  filled retroactively once NOAA assigns a number (noted, no action).
- SWPC prints the crossing as **4-digit "4000", "4001"**; +10000 → 14000, 14001, both present in SHARP.
- XRA events parsed in these 7 days: 66, 63 with a region; **their converted regions (13990, 13991, 13992, 13996, 13997,
  13998, 14000, 14001) all appear in SHARP `NOAA_ARS`.**
- **Region column of every XRA and FLA line: 95 of 95 are 4-digit.** The 5-digit values and six unmatched 4-digit
  values found by a broad last-token scan (1100, 1700, 2000, 2500, 3200, 3600, 14000, 23000) are all **RBR radio-burst
  fluxes**, not regions; the parser reads XRA lines only, so they cannot reach labels.
- **Result: the rule Reg# < 10000 → +10000 holds past region 14000.** (It would fail at region 20000; not reached.)

**PROPOSED frozen end date (me; awaiting user approval — NOT yet frozen, nothing fetched beyond the checks):**
confirmation set = **T_REC from 2025-01-01 00:00 TAI up to but not including 2026-08-17 00:00 TAI** (last full SHARP day
2026-08-16). SWPC and GOES cover every 24-h label window and 48-h history window in that span (SWPC to 2026-09-20; the
history window at the start uses 2024-12-30/31 reports, already cached). The JSOC query will use an end of
2026-08-16_23:00_TAI, because JSOC ranges include both ends (see the month-boundary duplicate fix). Calendar years for
CHECK 5: 2025 (full) and 2026 (2026-01-01 → 2026-08-16, partial).

## 2026-09-21 — CONFIRMATION SET FROZEN  (decided by: user; recorded before any 2025+ fetch beyond the checks)
**Confirmation set = T_REC 2025-01-01 00:00 TAI → 2026-08-16 23:00 TAI.** The JSOC query end is inclusive at 23:00, to
avoid boundary duplicates. Approved by the user; frozen from this entry.

**`NOAA_ARS` (user):** SHARP `NOAA_ARS` appears to be filled retroactively. It is used **only for flare–region
linking** (labels, history, the single-region/mapping status that defines subsets), **never as a model input**.
(The gate uses the 10 SHARP features; models A/B/C use the gate score, n_C/n_M/n_X, and trends/R.)

**STEP 1 (data only; no gate scoring, no cohort, no R):** fetch SHARP keywords (original set + the 10 extras) in
resumable monthly chunks with the same record-set pattern and a boundary-duplicate check; fetch SWPC reports and GOES
XRS for the period (+48 h before, +24 h after where available); build labels with identical rules (K2, missing-day,
empty-day, history_incomplete, region_group); run CHECKS 1–5, CHECK 5 per calendar year (2025; 2026 partial) with the
90% rule, excluding failing years per L; report per year and hash the new raw and labelled files. STOP after Step 1.

## 2026-09-21 — CONFIRMATION SET, STEP 1 RESULTS (data only; no gate scoring, no cohort, no R)

**Fetched / built**
- SWPC daily reports 2024-12-29 → 2026-08-18 (593 files for 2025–2026). **404 days: 2025-12-30, 2025-12-31** (added to
  `_missing_days.txt`; rule C → label-missing and history-incomplete). **Empty-report days in 2025–2026: 0.**
- **GOES XRS: not fetched.** GOES is read only to classify empty-report days (rules E, H, I); a 404 day is missing
  without a GOES check (rule C). With zero empty-report days no rule reads GOES in this period. The empty-day table is
  unchanged. (Deviation from the instruction's "fetch GOES XRS", stated here; available on request.)
- SHARP extras (`fetch_extra.py 2025-01-01 2026-08-17`): 20/20 chunks. SHARP keywords + labels (`run_all.py`), 20 monthly
  chunks, same record-set pattern; **final chunk queried to 2026.08.16_23:00_TAI** via `JSOC_END_OVERRIDE` (applied only to
  the chunk whose end is 2026-08-17). **Boundary-duplicate check:** 282 raw / 76 labelled duplicate rows, all identical
  copies, dropped.
- Code changes (defaults unchanged; a default 2014-01 rebuild is byte-identical): `JSOC_END_OVERRIDE` in
  `build_dataset.py` / `fetch_extra.py`; `CHUNK_RANGE` in `chunks.py`; GOES-19 added to `goes_xrs.BASE`; `join_report.py`
  derives years and output file from the chunk range (the 2010–2024 table is never overwritten); CHECK 1 now uses the
  first X flare with >= 1 labelled row in its 24-h window (see below).

**CHECKS on the confirmation set: 1 PASS, 2 PASS, 3 descriptive, 4 PASS, 5 PASS.**
- CHECK 1 first **failed on event selection, not labels**: it took the first X flare of the padded flare list
  (X1.5, 2024-12-30), whose 24-h window precedes every confirmation row, so "all 0 rows labelled 1" was false. Fixed to
  the first X flare with a labelled row in [t0−24h, t0): X2.0, 2025-02-23 19:22, NOAA 14001 → HARP 12755; **12 of 12 rows
  in [t0−24h, t0) labelled 1**. The same fix on 2014-01 selects the original event (X1.2, HARP 3563; 21/21) — unchanged.
- CHECK 2: median USFLUX positive/negative 6.42×, TOTUSJH 7.15×.
- CHECK 3: 49,935 rows, 402 HARPs, 68 with a positive row.
- CHECK 4: missing-mapping rows median USFLUX 0.026× mapped; 1.0% above the mapped median.
- **CHECK 5 per calendar year (>= 90%): 2025 — 356 M1+, 21 unknown region, 94.1% usable → USABLE; 2026 (to 08-16) —
  205 M1+, 7 unknown, 96.6% → USABLE. No year excluded.** %in_SHARP 100% / 99.5%; dups 1 / 0.

**Exclusions by reason** (UTC year; sequential as in the pipeline)

| year | raw rows | QUALITY != 0 | \|LON\| > 45 | mapping missing | label-missing day | → labelled | history_incomplete (kept) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024* | 15 | 0 | 4 | 1 | 0 | 6 | 0 |
| 2025 | 140,567 | 15,653 | 29,094 | 38,541 | 320 | 32,830 | 0 |
| 2026 | 70,474 | 8,091 | 14,482 | 18,536 | 0 | 17,099 | 237 |

**Per year by region subset** — rows / positive rows / HARPs / positive HARPs

| year | single (primary) | <= 2 | all |
|---|---|---|---|
| 2024* | 2 / 0 / 2 / 0 | 4 / 0 / 4 / 0 | 6 / 1 / 6 / 1 |
| 2025 | 21,303 / 390 / 185 / 12 | 27,770 / 1,073 / 232 / 28 | 32,830 / 1,843 / 267 / 46 |
| 2026 | 12,398 / 468 / 104 / 11 | 14,930 / 636 / 122 / 17 | 17,099 / 847 / 137 / 22 |

Distinct positive HARPs over 2025 + 2026 (single / <= 2 / all): **23 45 68**.

**\* Overlap with the 2021–2024 test data (flagged for the user; nothing excluded yet).** The frozen start, 2025-01-01
00:00 TAI, is **2024-12-31 23:59:23 UTC**, and the 2024-12 chunk of the 2010–2024 dataset already contains that slot
(JSOC ranges include both ends). **15 raw / 6 labelled rows are in both files** — identical in every column. They are the
"2024" rows above. **6 HARPs** appear in both 2021–2024 and the confirmation set: all 6 have the overlapping slot, and the same 6 also have
2025 rows (6 of the 267 HARPs with 2025 rows); none of the 137 HARPs with 2026 rows is in 2021–2024.

**Hashes (SHA-256)**
- `data/raw_sharp_20250101_20260817.csv` `d6dc70b837fe0716e3ef0d31b735e70bb2a5c2e5a6ec7633c3412c0e05c779c2`
- `data/labelled_20250101_20260817.csv` `1f6673956db3599616fe4d04fbd14b285a383737156a49d393f6c5d617c49263`
**Stopped after Step 1.** No gate scoring, no cohort, no R.

## 2026-09-21 — DIAGNOSTIC D8, pre-declared  (decided by: user; dev period only; primary result untouched)
Identical to D7 (B&C period May 2010 – May 2014, their sample definition, N/P 16.5, random 70/30, 1,000 repeats,
QUALITY <= 65536, ±68°, 10 features, median/std scaling, C = 4, γ = 0.075, tol = 1e-8), **but C1/C2 = 15.0 and decision
value 0 (B&C Table 3 setting).** Then ONE comparison table, operational case, mean ± sd over 1,000 repeats: rows TSS,
recall, precision, FPR, accuracy; columns B&C Table 2 | D7 | B&C Table 3 | D8. Table only.

### D8 — RESULTS and the D7/D8 vs B&C comparison (diagnostic; dev period only; primary result untouched)
B&C values were checked against the paper before use: **all ten user-supplied operational values match** Table 2
(p.34) and Table 3 (p.35). FPR is not reported by B&C; it is taken as 1 − recall(negative), with the same sd.
D7 was rerun with full confusion counts (`diag_d7.py --d8`) and **reproduces its saved TSS exactly**. D8 = D7 with
class weight positive:negative = 15.0 (decision value 0). Same catalogue (P 272, N 4,488) and the same 1,000 splits.
No split had zero positive predictions. Per-split counts in `data/diag/d7_counts.csv`, `d8_counts.csv`.

**Operational case, mean ± sd over 1,000 repeats**

| metric | B&C Table 2 (C1/C2 = 2) | our D7 (C1/C2 = 2) | B&C Table 3 (C1/C2 = 15) | our D8 (C1/C2 = 15) |
|---|---|---|---|---|
| TSS | 0.610 ± 0.048 | 0.527 ± 0.050 | 0.761 ± 0.039 | 0.716 ± 0.040 |
| recall | 0.627 ± 0.049 | 0.540 ± 0.051 | 0.832 ± 0.042 | 0.805 ± 0.042 |
| precision | 0.690 ± 0.049 | 0.717 ± 0.050 | 0.417 ± 0.037 | 0.356 ± 0.022 |
| FPR | 0.017 ± 0.004 | 0.013 ± 0.003 | 0.071 ± 0.008 | 0.089 ± 0.009 |
| accuracy | 0.962 ± 0.004 | 0.961 ± 0.004 | 0.924 ± 0.007 | 0.905 ± 0.008 |

## 2026-09-21 — Confirmation set PAUSED; decisions on overlap and subset  (decided by: user)
- **The 2025+ confirmation work is PAUSED.**
- **The 6 HARPs that also appear in 2021–2024 are excluded** from the confirmation set (this removes the 6 overlapping
  labelled rows of the 2025-01-01 00:00 TAI slot along with those HARPs' 2025 rows).
- **The <= 2-region fallback applies** to the confirmation set (single-region has 23 positive HARPs over 2025–2026,
  below the fallback's 40).
- Note (me): not yet applied to any file — the confirmation labelled file (`1f667395…`) is unchanged; the exclusion and
  subset choice will be applied when the work resumes.

## 2026-09-21 — D8 replication conclusion (me, record-keeping)
The user's message refers to a "D8 replication conclusion". The D8 results table is recorded above; **no conclusion
wording for D8 has been provided by the user**, so none is recorded here. To be added verbatim when supplied.

## 2026-09-21 — EUV/UV PILOT — exploratory, dev data only (2010–2019)  (decided by: user)
**Exploratory.** Dev data only; **2021–2024 and 2025+ data are not touched.**
- **STEP 1 — BADPIT specification from the paper (arXiv:2604.26036) only; code unavailable.** Extract the algorithm
  with page references (instrument/channel, cadence, baseline, thresholds (3σ and power-law), spatial rule (> 3 connected
  pixels), temporal rule (> 5 consecutive frames), saturation flag (> 12,000 DN), PIL mask (±150 G, 16 px dilation), AR
  mask (30 G), alignment/registration); list every unstated detail with one proposed choice each, marked for user
  approval; check for an archived official copy of the code (Zenodo, Software Heritage, arXiv ancillary files) and use
  no unofficial copies; identify BADPIT's 2 active regions and time windows. **CHECKPOINT 1; no downloads.**
- **STEP 2** (after CHECKPOINT 1 approval): 3 dev alarm episodes from the frozen dev cohort (1 true, 1 false, 1 delayed;
  gate scores within the caliper; |LON| <= 30° if possible); SHARP CEA Br at t and AIA cutouts over the HARP box for
  (t−24h, t] in BADPIT's channel at 12-min cadence via JSOC export (cutout mode); report size and wall time; save to
  `data/euv_pilot/` (untracked) with hashes.
- **STEP 3:** PIL mask from Br by BADPIT's rule, mapped onto the AIA frame (level 1.5 if needed; time offset/rotation);
  one overlay PNG per episode.
- **STEP 4:** per AIA frame, fraction of PIL-mask pixels above a TRAILING 3σ baseline (earlier frames only), and the same
  for the HARP box; plots vs time; frames during a GOES flare in progress flagged and excluded.
- **CHECKPOINT 2 (final): GO/NO-GO facts only**; no interpretation of true vs false (n = 3).
- JSOC export email: the message gives "YOUR_EMAIL" — a placeholder. **A registered JSOC address is needed before
  Step 2**; none is assumed.

## 2026-09-21 — EUV PILOT STEP 1: BADPIT specification (paper only) — CHECKPOINT 1
Source: André-Hoffmann, Korsós, Nindos, Patsourakos, Georgoulis & Erdélyi, "Brightenings AnD Polarity Inversion
Tracking (BADPIT) method…", arXiv:2604.26036 (22 pp., SOLA manuscript dated 26 June 2026). Page numbers are the
manuscript's. Content paraphrased with page references (not quoted at length).

### Official code
The paper links a GitHub repository for BADPIT and its desaturation tool (p.7, footnote 2:
`github.com/aandre-hoffmann/BADPIT`). **Checked 2026-09-21: the URL returns HTTP 404; Software Heritage has no archived
origin for it; Zenodo has no record matching "BADPIT"; the arXiv abstract page lists no ancillary files.**
**No official copy is available; no code of any kind was downloaded or used.**

### Specification table

| item | what the paper states (page) |
|---|---|
| magnetic data | **HMI line-of-sight magnetogram cutouts**, 0.5″/px, 12-min cadence (pp.4–5, Table 1); LoS is used because ARs are restricted to ±45° central-meridian distance (pp.4, 11) |
| EUV/UV data | AIA **Level 1.5**, co-aligned, cutouts via the JSOC export service following P. Young's procedure (p.4); 94, 131, 171, 193, 1600 Å (p.4) |
| channel used for the analysis | **94 Å** (p.13), chosen because TBs concentrate at the PIL there and the power-law TBs appear most consistently |
| AIA cadence | **12 s** (24 s for 1600 Å) (Table 1, p.5) |
| pre-processing | exposure-time normalisation → DN/s (p.4) |
| saturation | saturation = ≥ 16,000 DN; **pixels > 12,000 DN are flagged** (conservative, following Schwartz et al. 2015), together with saturation trails (detector y-axis streaks) and diffraction arms (along the PSF axes at ±40°, ±50°); flagged pixels are **replaced by linear interpolation in time, with a sinusoidal component added** so the corrected points do not trigger detection (pp.6–7) |
| candidate pixels | intensity peaks in each pixel's light curve over the field of view (p.8) |
| spatial rule | patch larger than **3 contiguous pixels** (> 5.67×10⁵ km²) (p.8) |
| temporal rule | persists for **more than five consecutive frames** (at least one minute at 12 s) (p.8) |
| 3σ threshold | per pixel, from the Gaussian distribution of that pixel's intensities **over the full observation period** (pp.8–9); the paper notes this makes it not directly usable for near-real-time monitoring (p.9) |
| power-law threshold | one global threshold per AR and channel, from the AR's intensity histogram over the whole period: the intensity where the histogram departs from a fitted power law y = a x^(−α) at high intensity, identified **qualitatively** from the residuals (increased spread or a high-intensity rollover) (pp.9–10); values in Table 2 (p.11) |
| PIL area (PIA) | two masks where \|B_LoS\| > **150 G** (one per polarity), each **dilated by 16 HMI pixels (8″)**; their overlap = PIA (p.12); following Schrijver (2007) |
| AR mask | \|B\| > **30 G**, chosen empirically to separate AR from quiet-Sun fields; applied to the AIA data (p.12) |
| magnetogram timing | Fig. 6 shows masks on an HMI magnetogram **averaged over 3 hours** (p.12) |
| counting | TBs counted per **1-hour** interval over the 24-hour window (pp.14–16) |
| alignment | data described as co-aligned Level 1.5 (p.4); **no registration or HMI→AIA mapping procedure described** |

### Unstated details — one proposed choice each, **for the user's approval** (none acted on)

| # | unstated detail | proposed choice |
|---|---|---|
| U1 | 3σ threshold form (μ + 3σ? Gaussian fit or sample moments?) | per-pixel **mean + 3 × sample SD** |
| U2 | contiguity of "> 3 contiguous pixels" | **8-connectivity; >= 4 pixels** |
| U3 | what must persist "> 5 consecutive frames" (a pixel, or a patch that moves) | a patch whose pixels **overlap by >= 1 pixel between consecutive frames**, for **>= 6 frames** |
| U4 | desaturation sinusoid (amplitude, period) and the geometry used to flag trails and diffraction arms | **do not interpolate**: exclude pixels > 12,000 DN, and flag the frame if any pixel in the HARP box exceeds 12,000 DN |
| U5 | power-law fit range and the deviation point (qualitative in the paper) | **not used in the pilot** (Step 4 uses a trailing 3σ only); if needed later: fit between the median and 99th percentile, deviation = first bin above the range with residual > 3 × residual RMS |
| U6 | dilation structuring element for 16 px | **disk of radius 16 px** |
| U7 | single magnetogram vs a 3-hour average for the masks | **the single magnetic record at t** (as in the pilot brief) |
| U8 | HMI→AIA mapping | reproject the mask with the WCS headers (`reproject`), after **differential rotation** from the magnetogram time to each AIA frame time; AIA registered to level 1.5 with `aiapy` |
| U9 | how the 30 G AR mask is applied ("through visual inspection") | not used in the pilot: the **HARP box** is used as the region (as in the brief) |
| U10 | cutout tracking (fixed box vs following rotation) | JSOC cutouts **tracked** with solar rotation, centred on the HARP at t |

### Differences between the pilot brief and BADPIT (flagged, not resolved — the user's call)
1. **Magnetic data:** the brief uses **SHARP CEA Br**; BADPIT uses **HMI LoS** magnetogram cutouts at 0.5″/px. The 150 G / 30 G
   thresholds and the 16-px dilation were set on LoS data.
2. **Cadence:** the brief uses AIA at **12 min**; BADPIT uses **12 s**. "> 5 consecutive frames" means ~1 minute at 12 s but
   ~1 hour at 12 min, and the per-pixel intensity distributions differ. At 12 s, a 24-hour window is ~7,200 frames per
   channel per episode (60× the 12-min volume).
3. **Baseline:** the brief's trailing 3σ baseline is causal; BADPIT's 3σ uses the full period, including frames after t.
4. **Channel:** BADPIT's analysis channel is 94 Å (the brief says "BADPIT's channel").

### BADPIT's 2 active regions (for later validation)

| NOAA AR | role | window (UT) | position | period in this project |
|---|---|---|---|---|
| 11429 | flaring (C, M; two X flares starting just after the window) | 2012-03-06T00:00 → 2012-03-07T00:00 | N17E27 at 03-06 00:00 | **dev (2010–2019)** |
| 13186 | non-flaring (no ≥ C1 in the window or ±48 h) | 2023-01-16T00:00 → 2023-01-17T00:00 | N25W15 at 01-16 18:58 | **2023 — inside the 2021–2024 test years** |
**Conflict:** validating against AR 13186 would read 2023 data, which the pilot instruction forbids. AR 11429 is usable.
Also: AR 11429 lies at ~E27 at the start of its window, i.e. inside ±30°.
**No downloads made. Stopped at CHECKPOINT 1.**

## 2026-09-21 — EUV PILOT decisions, part 1  (decided by: user; recorded BEFORE any EUV download)
**Exploratory; dev data (2010–2019) only for all EUV development.**
- **D8 conclusion (user, verbatim):** "Same-period reproduction with C1/C2 = 15: D8 TSS 0.716 ± 0.040 vs B&C Table 3
  0.761 ± 0.039, with the same recall/precision trade-off; together with D7 (0.527 vs 0.610), our reproduction is
  consistently 0.05–0.08 lower, plausibly from 3 unavailable features [corrected 2026-09-22: available in `cgem.lorentz`], catalogue, and flare-location differences."
- **JSOC export email:** provided by the user for JSOC export requests.
- **U1–U10 approved as proposed.**
- **BADPIT power-law threshold dropped** (not algorithmic); **3σ only.**
- **Magnetic data for PIL masks: line-of-sight, as BADPIT.** The user asked to confirm that `hmi.sharp_720s` has a LoS
  magnetogram segment — answered below.
- **The user's message was cut off** after that sentence; the remaining decisions are not yet received. No EUV download
  until they are.
- **Answer (me): `hmi.sharp_720s` has a line-of-sight `magnetogram` segment — provisional.** The JSOC metadata call
  (`drms` `info`) failed server-side on 2026-09-21 ("No space left on device" in JSOC's database). The failed query
  itself, returned in the error, lists the series' segment columns: `magnetogram` is segment 0 (`magnetogram_bzero`,
  `magnetogram_bscale`), followed by `bitmap`, `dopplergram`, `continuum` and the inversion segments (`field`,
  `inclination`, `azimuth`, …). To be confirmed with a clean metadata call once JSOC recovers.
  **JSOC was returning database disk-full errors at this time** — relevant to export feasibility.

## 2026-09-21 — EUV PILOT decisions, part 2  (decided by: user; recorded BEFORE any EUV download)
1. **Primary EUV measure = "PIL-localised EUV variability" at 12-min cadence** (not BADPIT's 12-s transient detection).
   For (t−24h, t]: AIA **94 Å** cutouts (**1600 Å secondary**) covering the HARP; PIL-area mask from the
   **`hmi.sharp_720s` LoS magnetogram at t** (±150 G, 16 px dilation; 30 G AR mask), mapped to the AIA frames with
   differential rotation. Per episode: mean intensity and the SD of the **detrended** intensity, inside the PIL mask and
   in the whole HARP box; frames during a GOES flare already in progress excluded; **>= 80% of frames required**.
   **Primary feature = PIL variability / whole-HARP variability.** Described as **"motivated by BADPIT and Leka et al."**,
   not as BADPIT.
2. **Cadence cost test:** in the pilot, **also run 12 s over (t−6h, t]** on the same 3 episodes, **process-and-delete**
   (keep only per-frame results and overlays). Record download time, size and processing time per episode for both
   cadences, and projected totals for **547 dev + ~400 2025+ episodes**. **The full-study cadence will be chosen on cost
   only, before any true-vs-false comparison.**
3. **Baseline: trailing (past frames only) for everything used in forecasting.** BADPIT's whole-window baseline only
   for the validation reproduction.
4. **AR 13186 (2023-01-16): exception allowed for method validation only** (reproducing BADPIT's flaring vs quiescent TB
   counts at 12 s). Reason (user): 2021–2024 was reserved for the magnetic test, which is complete; the EUV
   confirmatory test will use 2025+. **No alarms, labels or hypotheses from 2021–2024 are used.** The validation
   reproduction can wait until after the pilot.
5. **AARP (NWRA AIA Active Region Patches): metadata check only** — date coverage, times, channels, file sizes.
6. **JSOC outage:** confirm the LoS segment with a clean metadata call when JSOC recovers. **If exports fail, wait and
   retry; do not switch data sources without asking.**
**Pilot:** 3 dev episodes (1 true, 1 false, 1 delayed; gate scores within the caliper; |LON| <= 30° if possible).
Deliver overlays (for the user's visual alignment check), time series and the cost table. **No true-vs-false
conclusions. Stop at CHECKPOINT 2.**

### Pilot implementation details fixed by me before any download — **for the user's approval**
- **P1 detrending:** for each mask (PIL, whole HARP box), the per-frame **mean** intensity series over (t−24h, t] minus
  its least-squares **linear** fit; variability = SD of the residuals. Primary feature = SD(PIL) / SD(HARP box).
- **P2 "flare already in progress":** a frame is excluded if its time lies inside the begin–end interval of **any SWPC
  XRA event of class >= C1.0 (K2 true scale), from any region** (GOES is disk-integrated).
- **P3 12-s cost test:** **94 Å only** (the primary channel); 1600 Å only at 12 min.
- **P4 AIA processing:** `aia.lev1_euv_12s` / `aia.lev1_uv_24s` exported as cutouts, registered to level 1.5 with
  `aiapy`, exposure-normalised (DN/s); pixels > 12,000 DN excluded and the frame flagged (U4).
- **P5 pilot metric (Step 4 of the pilot brief):** per frame, the fraction of mask pixels above a **trailing** per-pixel
  mean + 3 SD computed from **earlier frames only** (U1); needs >= 12 earlier frames before it is reported.
- **P6 episode choice:** from the frozen dev cohort, candidate triples (one true, one false, one delayed) whose gate
  scores lie within the caliper (0.0747) of each other and whose |LON_FWT| <= 30° at t; among them, the triple with the
  smallest gate-score spread, ties broken by earliest t. Chosen **before** any EUV data is seen.

### EUV pilot — pre-download results (me)
**Pilot episodes chosen by rule P6 (before any EUV data):** |LON_FWT| <= 30° at t: 62 true, 29 delayed, 296 other-false
episodes eligible. Smallest gate-score spread, three different HARPs (`data/euv_pilot_episodes.csv`):

| role | HARP | NOAA AR | t (UTC) | gate score | LON_FWT | LAT_FWT |
|---|---:|---:|---|---:|---:|---:|
| true | 4231 | 12089 | 2014-06-12 12:59:25 | −0.9917 | −9.3° | 17.5° |
| delayed | 6975 | 12645 | 2017-03-31 06:59:23 | −0.9917 | −11.4° | −9.9° |
| false | 3248 | 11856 | 2013-10-08 11:59:25 | −0.9917 | 2.2° | 8.3° |
Score spread 0.0001 (caliper 0.0747). Why these: the rule's minimum spread; all three are within 12° of disk centre.

**AARP metadata check (decision 5; no data downloaded).** Sources: data.gov record "NWRA AIA Active Region Patches
(AARP) Database"; SDAC directory listing `umbra.nascom.nasa.gov/contributed/AIA_AARPS/`; Dissauer et al. 2023, ApJ
(arXiv:2212.11251).
- **Coverage: 2010-06 → 2018-12** (103 month directories). **No 2019; no 2025+.**
- **Sampling:** daily, **11 images at 72-s cadence (13 min) per channel, centred at 15:48, 16:48, … 21:48 UT** (7 samples a
  day, one hour apart). Only that 6-hour daytime window is covered each day.
- **Channels:** 94, 131, 171, 193, 211, 304, 335, 1600 Å (1700 Å omitted).
- **Boxes:** HARP-based, with extended bounding boxes for coronal loops; full spatial sampling kept.
- **Files:** one FITS per AARP per day per channel (e.g. `2014.03.01_15:48:00_7h@1h_AARP3766_94.fits`), **58–90 MB each**
  in 2014-03; total ~9 TB; last updated 2026-09-08.
- Facts relevant to the brief: AARP cannot supply (t−24h, t] at 12-min cadence (daily 6-h window only), does not cover
  2019 or 2025+, and its cadence within a sample is 72 s.

**JSOC outage (decision 6):** the metadata call failed again with the same database disk-full error; per the decision,
waiting and retrying (no source switch).

### EUV pilot — approvals and amendments  (decided by: user)
- **P1, P3, P5, P6 approved.**
- **P2 amended:** a frame is excluded if it falls within the begin–end interval of **(a) any C1+ SWPC event attributed to the
  same NOAA region(s) as the HARP**, or **(b) any M1+ event from any region** (K2 true scale). **Report per episode how many
  frames each rule removes.**
- **P4 approved with clarification:** the **12,000 DN saturation cut applies to raw DN, before exposure normalisation.**
- **AARP: not used** (no 2019 or 2025+ coverage; 6 h/day only).
- Continue waiting on JSOC per decision 6; when it recovers: confirm the LoS segment, run the pilot, stop at CHECKPOINT 2.

### EUV pilot — preparation while JSOC is down (me)
- `swpc.py` now also parses each event's **end** time (needed for P2); labels verified **byte-identical** for 2014-01 and
  2024-05 chunks after the change.
- JSOC `im_patch` documentation (read from jsoc.stanford.edu): patches are **tracked by default** (`-t` disables tracking),
  no reprojection is done (plain cutout in original pixels) → U10 = tracked cutouts; level 1.5 via `aiapy` (P4).
- `euv_pilot.py` written; its pure-logic parts pass a self-test on synthetic data (PIL mask incl. a no-overlap case,
  P2 counts per rule, P5 trailing 3σ, P1 detrended SD, P4 saturation before normalisation).
- **JSOC export address:** JSOC's registration check returned "invalid or not registered" for the address the user
  supplied. This may be genuine or an effect of the outage (the check uses the same failing JSOC services). Registering
  the address is the user's action (JSOC sends a confirmation email); not done by me.

## 2026-09-21 — EUV PILOT DOWNLOAD decisions  (decided by: user; recorded BEFORE downloading)
**Scope: the 3 pilot episodes only** (HARP 4231, 6975, 3248; t as recorded).
**Items per episode:**
1. `hmi.sharp_720s` LoS **magnetogram** at the record nearest <= t (TAI), plus **bitmap**.
2. AIA **94 Å**, 12-min cadence, (t−24h, t], cutout around the HARP, tracked.
3. AIA **1600 Å**, 12-min cadence, (t−24h, t], cutout, tracked.
4. AIA **94 Å, 12-s cadence, (t−6h, t]**, cutout, tracked — cost test; process-and-delete allowed (per-frame results and
   overlays kept).
**Source rules:**
- Primary: **JSOC export** (drms, the email on record), method url, protocol FITS; AIA via **im_patch** cutouts, box = HARP
  bounding box + **50″ margin**, tracking on, reference time t. Keep the retry loop; start as soon as JSOC responds.
- **Fallback, AIA items 2–3 ONLY:** if JSOC is still failing **12 hours from this entry** (entry time 2026-09-21 22:43:34 IST; deadline
  **2026-09-22 10:43:34 IST**), fetch level-1 full-disk AIA via SunPy Fido from a VSO provider (e.g. SDAC), crop locally to the same box,
  delete the full-disk files; record the provider per file. **Not for item 4, not for HMI item 1 (JSOC only).**
- Never mix sources within one episode's item without recording it.
**Download discipline:** resumable (skip present and verified files); `data/euv_pilot/<HARP>/<item>/` (untracked);
manifest CSV (file, T_OBS, wavelength, exposure, source, size, SHA-256); checker (count vs expected — 12 min ~120, 12 s
~1,800 —, wavelength, time coverage, cutout contains the HARP box, gaps listed); wall time and bytes per item and episode.
**After download:** run the pilot (P1–P6 as approved; P2 amended; P4 raw-DN cut): overlays, time series, cost table with
projected totals for 547 dev + ~400 2025+ episodes. **No true-vs-false conclusions. Stop at CHECKPOINT 2.**

Notes (me):
- "Record nearest <= t (TAI)": each episode's t is the UTC form (hh:59:2x) of an hourly T_REC at hh+1:00:00 TAI, so the
  record at t is the episode row's own T_REC.
- **Gap in the fallback rule:** it triggers on "JSOC still failing". JSOC's registration check currently rejects the export
  address. If JSOC recovers but exports fail because the address is unregistered, that is not "JSOC failing"; **I will
  stop and ask** rather than use the fallback.
- `euv_download.py` written (JSOC path only; the approved AIA fallback is not implemented yet): resumable (skips items whose
  manifest files verify by SHA-256), manifest (`data/euv_pilot/manifest.csv`: file, T_OBS, wavelength, exposure, source,
  size, SHA-256), per-item download log (files, bytes, wall time, JSOC request id). HMI record = the episode row's own
  T_REC (4231: 2014.06.12_13:00:00_TAI; 6975: 2017.03.31_07:00:00_TAI; 3248: 2013.10.08_12:00:00_TAI).
  The AIA box is computed from item 1's WCS, so AIA items run only after item 1.
- The JSOC retry loop now runs until JSOC answers or the fallback deadline (2026-09-22 10:43:34 IST).
- **Open question raised with the user (fallback geometry):** the approved fallback crops to "the same box" (HARP bounding
  box + 50″). That box comes from JSOC (the item-1 WCS or the patch-extent keywords, never fetched). If JSOC stays down,
  the box cannot be computed; the cache holds only the HARP's flux-weighted centre. Not resolved by me.

### 2026-09-22 08:05 IST — JSOC recovered; export address unregistered (decided by: me)
- JSOC `info('hmi.sharp_720s')` succeeded at 2026-09-22 08:05:21 IST. The segment `magnetogram` (int, Gauss, "magnetogram") is confirmed as the LoS field; the provisional confirmation is now final. `bitmap` is confirmed too.
- With JSOC up, `drms.Client(email='YOUR_EMAIL_HERE')` still returns "Email address is invalid or not registered". Exports cannot run.
- The fallback (items 2–3 only) covers "JSOC failing". It does not cover an unregistered address, and JSOC is no longer failing. So no fallback is used and no download has started. Waiting for the user to register the address (http://jsoc.stanford.edu/ajax/register_email.html) or supply a registered one.

### 2026-09-22 — JSOC parallel-export limit (fact, measured; recorded by: me)
- Three small exports (item-1 bitmaps, data already held) were submitted back to back. The first was accepted (JSOC_20260922_000476). The others got status 7: "User YOUR_EMAIL_HERE has 1 pending export requests (JSOC_20260922_000476); please wait until at least one request has completed before submitting a new one."
- So JSOC allows N = 1 pending export per registered address. The cost projections use N = 1 as the allowed value.

### 2026-09-22 — AIA pilot processing: implementation notes (decided by: me; **for the user's approval at Checkpoint 2**)
- **Level 1.5 on cutouts:** `aiapy.calibrate.register` refuses non-full-disk input ("Input must be a full disk image"). Its pixel operation is `Map.rotate(scale = cdelt/0.6", order=3)`, i.e. rotate to solar north and rescale to 0.6"/px. The surrounding recentre/crop is specific to full-disk images. I apply that same rotate/rescale to each cutout (euv_run.register_cutout), with missing = NaN.
- **Frame quality:** some frames are not covered by P1–P6. There is one zero-exposure frame per episode per channel at ~20:59 UTC (QUALITY 0x10000), and HARP 6975 has frames with QUALITY 0x40000/0x60000 on 2017-03-30 14:59–16:35 UTC (SDO eclipse season). Default: **frames with QUALITY != 0 are excluded**, counted separately (`excl_quality`). Zero-exposure frames cannot be normalised in any case.
- **P5 with moving masks:** the masks are reprojected per frame (differential rotation), so the trailing 3σ fraction for frame i uses frame i's mask. The baseline uses earlier valid frames only; P2- and quality-excluded frames give no metric and do not enter the baseline.
- **Flare events for P2:** SWPC events with begin in [t−2 d, t], so events that start before the window and end inside it are included.

### 2026-09-22 — Checkpoint 2 approvals and design fix (decided by: user)
- **Approved:** registration on cutouts (aiapy's register pixel operation applied to cutouts), exclusion of frames with QUALITY != 0, and the baseline rule (per-frame mask; excluded frames not in the baseline).
- **Optional:** apply `aiapy.update_pointing` before registration if it runs without JSOC DB issues; otherwise note it.
- **Design fix before any scaling.** The user decided this **from method reasoning, not from pilot values**.
  - The ratio SD(PIL)/SD(box) is replaced as the primary feature by **CV_PIL − CV_ctrl**.
  - CV = SD of the detrended mean-intensity series / mean intensity, over (t−24h, t].
  - ctrl = a same-area control mask inside the AR mask (30 G) and outside the dilated PIL, chosen by a fixed rule.
  - CV_PIL, CV_ctrl and CV_box are also reported. The 3 pilot episodes are recomputed with the new definition (facts only).
- **Full-study download plan: proposal only, not started.** Group dev episodes by HARP, with one export per HARP covering the union of its (t−24h, t] windows. Report the number of requests and the projected time at N = 1, for 94 Å only and for 94 + 1600 Å.
- Finish item 4, deliver the cost table, then stop.

### 2026-09-22 — Control-mask rule and CV details (decided by: me, before computing any CV)
- **Control mask (HMI grid at t):**
  - Candidates are the pixels with |B| > 30 G that are NOT in the dilated PIL mask.
  - Distance = Euclidean distance (px) to the nearest PIL-mask pixel (`scipy.ndimage.distance_transform_edt`).
  - ctrl = the n_PIL candidates with the largest distance, where n_PIL is the number of PIL-mask pixels.
  - Ties are broken by a fixed random permutation (numpy RandomState seed 0) applied before a stable sort.
  - If there are fewer than n_PIL candidates, all are used and the episode is flagged (`ctrl_short`).
  - ctrl is reprojected onto each AIA frame exactly as the PIL mask is.
- **CV:** for each mask, CV = detrended_sd(mean series over valid frames) / mean(mean series over the same frames). Valid frames are the same as for the other features (not P2-excluded, QUALITY == 0).

### 2026-09-22 — update_pointing applied; ctrl mask observations (recorded by: me)
- `aiapy.calibrate.update_pointing` runs on the cutouts. It shifts CRPIX by X0_MP_new − X0_MP_old and uses the pointing table `aia.master_pointing3h` from a JSOC keyword query. It is applied to every frame before registration (`pointing_updated` counts frames), and all frames in items 2–3 were updated. `ratio_old` changed by < 1% as a result.
- Ctrl mask facts: under the fixed rule it is spatially scattered (small >30 G plage/network patches far from the PIL, often near the patch edges). For HARP 6975 there are fewer candidates than PIL pixels (26,688 < 33,031), so `ctrl_short` = True and all candidates are used. The rule is not changed.

### 2026-09-22 — Item 4 paused (decided by: user)
- The user paused item 4 to find a faster download method. Files average 0.14 MB and arrive at ~7–8 s each (per-file HTTP overhead, not bandwidth).
- State at pause: HARP 4231 has 191 of 1,800 files from finished request JSOC_20260922_000545; partial `.part` files were removed. Nothing is processed yet and no raw files are deleted. HARPs 6975 and 3248 have not been requested.
- Resume with `JSOC_REQUEST_ID=JSOC_20260922_000545 python euv_run.py item4 4231`, which skips files already present. Items 1–3 and the pilot results are complete.

## 2026-09-22 — Reproduction improvement for D7 (decided by: user; DIAGNOSTIC ONLY)
- **The main gate stays at 10 features.** This work is diagnostic only. It does not change the frozen spec, the gate or the Stage 5 FINAL result.
- Scope, report only, no downloads:
  1. Exact formulas, units, pixel masks and constants for TOTBSQ, TOTFZ and EPSZ, from Bobra et al. 2014 (Sol. Phys. 289, 3549) and B&C 2015, quoted with pages.
  2. A cost estimate for the hmi.sharp_cea_720s vector segments (Br, Bp, Bt, plus bitmap/conf_disambig as needed) for exactly the D7 sample records (272 pos + 4,488 neg): records, size, requests, projected time at N = 1.
  3. A validation plan: compare our computed values with SWAN-SF's TOTBSQ, TOTFZ and EPSZ for matching HARP/time, with an agreement metric, before using them.
  4. A catalogue check (metadata only): does the NGDC/NCEI GOES XRS flare report for May 2010 – May 2014 carry flare location and NOAA region, and how many of the 121 location-proxy losses would it recover?
- Report 1–4, then stop.

### D7 reproduction improvement — results 1 and 4 (recorded by: me; diagnostic; dev period only)
**1. Definitions of TOTBSQ, TOTFZ, EPSZ.** Page numbers are arXiv pages; journal pages differ.
- **Bobra et al. 2014** (arXiv:1404.1879, Table 3, p. 8) lists 16 parameters. **TOTBSQ, TOTFZ and EPSZ are not among them**, and no Lorentz-force formula appears in the paper. It does define the pixel mask for all SHARP parameters (p. 7): pixels "within the HARP (bitmap ≥ 33)" and above the high-confidence disambiguation threshold (≈ 150 G, conf_disambig = 90). The count of contributing pixels is keyword CMASK.
- **B&C 2015** (arXiv:1411.1405, Table 1, p. 12) gives proportionalities only, with no constants or units:
  - TOTBSQ: F ∝ ΣB²
  - TOTFZ: F_z ∝ Σ(B_x² + B_y² − B_z²) dA
  - EPSZ: δF_z ∝ Σ(B_x² + B_y² − B_z²) / ΣB²

  B&C p. 8 says seven Lorentz parameters are "adapted from Fisher et al. (2012)". B&C p. 8 (Fig. 1 panels 7–8) says each parameter uses one of two masks; the non-R masks are HARP ∩ high-confidence.
- **Official JSOC series `cgem.lorentz`** ("Lorentz force computed from hmi.sharp_cea_720s", prime keys HARPNUM, T_REC, 12-min cadence, 2010-05-01 → 2026-08-18). Its keyword definitions (jsoc_info) give the constants and units:
  - TOTBSQ [G²] = Σ B², all pixels; TOTBSQ1 = strong pixels only.
  - TOTFZ [10²⁰ dyne] = Σ (B_h² − B_r²)·AREA/(8π), all pixels; TOTFZ1 = within the bitmap mask.
  - EPSZ [none] = Σ(B_h² − B_r²)/ΣB², all pixels; EPSZ1 = within the bitmap mask.
  - MASKNAME = conf_disambig, MASKTHRS = 61 (e.g. HARP 4231, 2014-06-12).
  - **hmi.sharp_cea_720s has no TOTBSQ/TOTFZ/EPSZ keywords.**
- **Not stated in either paper:** which variant B&C used (all pixels or masked), and the exact per-pixel AREA. The official SHARP/CGEM pipeline source would settle both; it has not been read (only official copies may be used).

**4. NCEI GOES XRS report (goes-xrs-report_2010…2014.txt; fixed-width catalogue text, ~1 MB).**
- Location (e.g. S12W47, cols 29–34) and NOAA region (cols 81–85) fields exist, but location is often blank.
  - Rows with a location: 2010 204/1,256; **2011 0/2,171**; 2012 840/2,037; 2013 849/2,051; 2014 1,213/2,258.
  - M/X rows with a location: 15/23, **0/119**, 93/130, 72/111, 151/221.
- The 121 D7 location-proxy losses (`data/diag/d7_location_proxy_losses.csv`):
  - 119 match a report row (same date, start hhmm), and 52 of those have a location: 19 with |lon| ≤ 68 and 33 with |lon| > 68.
  - Of the 19, **8 have a qualifying patch record within 30 min of peak − 24 h**, so **8 of 121 would be recovered as positives.**
  - By year (with location / |lon| ≤ 68): 2010 2/0, 2011 0/0, 2012 22/7, 2013 10/5, 2014 18/7.
- Not computed: flares the proxy wrongly *included* (true location > 68°) would need the same report. Out of scope.
- Files: `diag_d7_catalogue.py`, `data/diag/d7_location_proxy_catalogue.csv`, `data/diag/d7_sample_records.csv` (the D7 sample rebuilt from diag_d7.py's seeded code: 272 pos + 4,488 neg, 4,757 distinct records, 763 HARPs).

## 2026-09-22 — CORRECTION and reproduction decisions (decided by: user)
**Correction:** TOTBSQ, TOTFZ and EPSZ are **not SHARP keywords** (hmi.sharp_cea_720s / hmi.sharp_720s), but they **are available as keywords in the JSOC series `cgem.lorentz`**. Earlier wording ("unavailable", "not a JSOC keyword", "not keywords") is annotated in place with this date. **The main gate stays at 10 features.**
- **Step 2 (vector-segment size estimate) is cancelled.** It is not needed. The partial script `diag_d7_vector_cost.py` is kept for the record; it produced no result.
- **Reproduction fix 1 uses `cgem.lorentz` keyword queries** for the 4,757 D7 records, with no image downloads. Pre-registered:
  - **R4a (primary) = masked variant** (TOTBSQ1, TOTFZ1, EPSZ1).
  - **R4b (sensitivity) = all-pixel variant** (TOTBSQ, TOTFZ, EPSZ).
  - **Unstated in B&C:** their exact variant, and their mask threshold (SHARP convention conf_disambig = 90, Bobra et al. 2014 p. 7, vs cgem MASKTHRS = 61).
- **SWAN-SF:** the full SWAN.tar.gz (735 MB, Harvard Dataverse file 3642432) is approved **for validation only**. It goes to data/swansf/ (untracked).
  - **Pre-registered pass rule:** Spearman ρ ≥ 0.95 **and** median |relative difference| ≤ 10% between `cgem.lorentz` (each variant) and SWAN-SF, for matching HARP/T_REC.
  - Report which variant matches SWAN-SF better.
- **R2 includes the NGDC catalogue fix** (8 recovered flares), as planned.
- **Step 0:** Ahmed et al. 2013 sample definitions; our HARP/AR count for May 2010 – May 2014 vs B&C's 2,071.
- Then report, and **wait for the user's OK before R1–R4.** Note: R1 and R3 are not defined in this repository or this session's messages; only R2 (catalogue fix included) and R4a/R4b (above) are specified.

### Step 0 — results (recorded by: me)
- **Ahmed et al. 2013** (Sol. Phys. 283, 157): full text not read. It is paywalled (Springer), and the only other copy found is on ResearchGate (unofficial). The definitions below are **as B&C 2015 report them (arXiv pp. 6–7)**:
  - **Operational:** positive = the AR flares within 24 h after the sample time; negative = it does not flare within 24 h after.
  - **Segmented:** same positive; negative = no flare within ±48 h of the sample time.
  - Positive sample time = exactly 24 h before the GOES peak; negative sample times random.
  - B&C also note that Ahmed et al. include C-class flares (p. 21).
- **HARP/AR count, 2010-05-01 … 2014-05-31** (our hourly hmi.sharp_cea_720s keyword cache):
  - 2,322 distinct HARPs, 801 of them with ≥ 1 NOAA number; 1,006 distinct NOAA ARs.
  - B&C: "the SHARP database contains 2,071 ARs and 1.5 million active region patches" (arXiv p. 8).
  - Their end date and their definition of "AR" (HARP or NOAA region) are not stated.

### SWAN-SF validation — RESULTS (pre-registered rule; recorded by: me; diagnostic)
- **Inputs:**
  - SWAN.tar.gz (Harvard Dataverse file 3642432), 735,206,766 B, **MD5 379da8ba2920a82c81d1c4d3293fc709 = published**. It was re-downloaded from scratch in 8 byte ranges; the earlier partial copy was discarded.
  - `cgem.lorentz` keyword query for the 4,757 distinct D7 records (`diag_d7_cgem.py` → `data/diag/d7_cgem_lorentz.csv`): 4,757 found, 4,579 with all six values; MASKNAME = conf_disambig and MASKTHRS = 61 on every record.
- **Matching:** SWAN-SF Timestamp = T_REC without "_TAI". All 763 D7 HARPs are in SWAN-SF, and 4,757 records matched. cgem TOTFZ was converted from 10²⁰ dyne to dyne.
- **Rule:** PASS iff Spearman ρ ≥ 0.95 AND median |rel diff| ≤ 10%, with rel diff = (cgem − SWAN)/|SWAN|.

| variant | param | n | Spearman ρ | median \|rel diff\| | median ratio cgem/SWAN | PASS |
|---|---|---:|---:|---:|---:|---|
| R4a masked | TOTBSQ | 4,639 | 0.9889 | 0.1310 | 1.1182 | no |
| R4a masked | TOTFZ | 4,639 | 0.9775 | 0.9537 | 0.0463 | no |
| R4a masked | EPSZ | 4,639 | 0.9852 | 0.0300 | 1.0148 | **yes** |
| R4b all-pixel | TOTBSQ | 4,579 | 0.9625 | 0.7569 | 1.7569 | no |
| R4b all-pixel | TOTFZ | 4,579 | 0.8652 | 0.9719 | 0.0281 | no |
| R4b all-pixel | EPSZ | 4,579 | 0.3391 | 0.5909 | 0.4099 | no |

- **Which variant matches SWAN-SF better:** the **masked variant (R4a)**, which has the higher ρ and the lower median |rel diff| for all three parameters.
- **Under the rule:** 1 of 6 passes (R4a EPSZ).
- **Disclosure:** before the validation ran, but after the rule was fixed, I inspected one record (HARP 4201, 2014-06-02 19:24 TAI, not a D7 HARP) to check timestamp format and units.
- Files: `diag_swansf_validate.py`, `data/diag/swansf_validation.csv`. SWAN.tar.gz is kept in data/swansf/ (untracked).

## 2026-09-22 — Reproduction runs R1–R4 defined (decided by: user; DIAGNOSTIC; main pipeline and gate unchanged)
- Cumulative runs. Each uses all 1,000 random stratified 70/30 splits, with both C1/C2 = 2 (Table 2 setting) and C1/C2 = 15 (Table 3 setting). Report TSS, recall, precision and FPR as mean ± sd, and whether mean TSS lands in the **pre-registered target: Table 2 0.562–0.658; Table 3 0.722–0.800.**
  - **R1** = D7/D8 with the exact 12-min SHARP record at each sample time (keywords only).
  - **R2** = R1 + NGDC catalogue (flare locations; 8 recovered flares under D7 logic).
  - **R3 = skipped.** Step 0 found that B&C's operational definition (as they report Ahmed et al. 2013) matches D7's.
  - **R4 (primary)** = R2 + TOTBSQ, TOTFZ, EPSZ from SWAN-SF (13 features).
  - **R4-cgem (sensitivity)** = R2 + the 3 features from cgem.lorentz, masked variant. Label: "failed pre-registered magnitude validation (TOTBSQ, TOTFZ); ρ ≥ 0.978".
- **Validation outcome recorded as-is:** the pre-registered rule passed only for masked EPSZ, and the rule is not changed. Likely causes, **hypotheses, not verified**: mask threshold (cgem MASKTHRS 61 vs SHARP convention 90), and a unit or constant difference for TOTFZ (median ratio cgem/SWAN ≈ 0.046).
- **Region count recorded:** 2,322 HARPs (ours, 2010-05-01 … 2014-05-31) vs B&C's 2,071. B&C's counting unit and end date are unstated.
- Table only.

### R1–R4 implementation details (decided by: me, before running)
- **R1 positive sample record:** for each SWPC M1+ flare (K scale, with a region), the T_REC on the 12-min grid nearest to (GOES peak − 24 h, converted to TAI), so |Δ| ≤ 6 min.
  - It is fetched by keyword query from hmi.sharp_cea_720s, for the patches containing the flare's region, tried in HARPNUM order (as in D7).
  - If that exact record is missing or fails a filter (QUALITY ≤ 65536, |LON_FWT| ≤ 68, 10 features present, region in NOAA_ARS), that patch gives no positive. There is no fallback to neighbouring records.
  - The location proxy uses the patch's 12-min record nearest the peak (|LON_FWT| ≤ 68).
- **R1 negatives:** the D7 construction is unchanged. The hourly eligible records are themselves exact 12-min SHARP records at their own sample times. The pool excludes the positive records (HARP, T_REC) and records with M1+ in (t, t+24h]. N = round(16.5·P), drawn once with the D7 seed.
- **R2:** a flare that fails the location proxy is admitted if the NCEI GOES XRS report (matched on date and start hhmm) gives a location with |lon| ≤ 68. It still needs a qualifying R1 sample record. No flare is removed by R2. The number recovered under R1 logic is reported (it may differ from 8).
- **R4 / R4-cgem:** an example needs all 13 features at its (HARP, T_REC); examples without them are dropped **before sampling**, for positives and the negative pool alike (the D7 missing-data assumption). This changes P and N relative to R2, and both are reported. SWAN-SF is matched on HARP + T_REC. cgem.lorentz values come from keyword queries (TOTBSQ1, TOTFZ1, EPSZ1).
- Everything else is D7/D8: median/SD scaling on the whole catalogue, RBF C = 4, γ = 0.075, tol = 1e-8, class weight positive:negative = 2 or 15, decision value 0, split seeds SEED + i.

### R1–R4 — RESULTS (diagnostic; dev period only; main pipeline and gate unchanged; table only)
`diag_r.py` → `data/diag/r_runs.csv`. 1,000 random stratified 70/30 splits per row; mean ± sd. The pre-registered TSS targets are Table 2 0.562–0.658 and Table 3 0.722–0.800. Flares in the period with a peak: 454. NCEI-location admissions in R2: 8. No split had undefined precision.
Implementation note (me): the cgem.lorentz query for the negative pool used one hourly range query per HARP. The first attempt, which listed hourly T_RECs, failed with HTTP 414 before any result was computed.

| run | C1/C2 | P | N | neg pool | TSS | recall | precision | FPR | TSS in target |
|---|---:|---:|---:|---:|---|---|---|---|---|
| R1 | 2 | 283 | 4,670 | 132,978 | 0.515 ± 0.049 | 0.531 ± 0.050 | 0.677 ± 0.048 | 0.016 ± 0.003 | no |
| R1 | 15 | 283 | 4,670 | 132,978 | 0.706 ± 0.040 | 0.797 ± 0.042 | 0.347 ± 0.023 | 0.092 ± 0.010 | no |
| R2 | 2 | 291 | 4,802 | 132,978 | 0.520 ± 0.049 | 0.536 ± 0.049 | 0.679 ± 0.052 | 0.016 ± 0.004 | no |
| R2 | 15 | 291 | 4,802 | 132,978 | 0.708 ± 0.038 | 0.801 ± 0.041 | 0.344 ± 0.023 | 0.093 ± 0.010 | no |
| R4 (SWAN-SF, primary) | 2 | 291 | 4,802 | 132,965 | 0.530 ± 0.051 | 0.541 ± 0.051 | 0.756 ± 0.049 | 0.011 ± 0.003 | no |
| R4 (SWAN-SF, primary) | 15 | 291 | 4,802 | 132,965 | 0.695 ± 0.039 | 0.779 ± 0.042 | 0.360 ± 0.025 | 0.084 ± 0.010 | no |
| R4-cgem (masked; failed pre-registered magnitude validation TOTBSQ, TOTFZ; ρ ≥ 0.978) | 2 | 276 | 4,554 | 129,826 | 0.507 ± 0.050 | 0.519 ± 0.051 | 0.730 ± 0.054 | 0.012 ± 0.003 | no |
| R4-cgem (same label) | 15 | 276 | 4,554 | 129,826 | 0.695 ± 0.042 | 0.777 ± 0.044 | 0.366 ± 0.025 | 0.082 ± 0.009 | no |

## 2026-09-22 — Item 4 resumed; 12-s cadence check pre-declared (decided by: user; pilot only; facts only)
- Finish item 4 (94 Å, 12 s, (t−6h, t]) for HARPs 4231, 6975 and 3248, resuming from files on disk, one file at a time with retries. Keep per-frame derived results; process-and-delete is OK.
- **Cadence check (pre-declared):** for each episode over (t−6h, t], compute CV_PIL, CV_ctrl (pixel-count-matched control, 20 draws) and CV_PIL − CV_ctrl:
  - (a) from all 12-s frames;
  - (b) from only the frames at the 12-min slots.
  Report both side by side, with frame counts, gaps, download time and size. No true-vs-false conclusions (n = 3).
- Also requested: "the AIA synoptic check and Path A as specified earlier".
- **Open (me):** "AIA synoptic check", "Path A" and the "pixel-count-matched control, 20 draws" are **not defined** in decisions.md or in this session's messages. The recorded ctrl rule (2026-09-22) is deterministic (the farthest AR-mask pixels, seed-0 tie-break), not 20 random draws.
  - None of the three is run until the user supplies the definitions.
  - Raw item-4 files are **kept, not processed or deleted**, until the metric is defined.

## 2026-09-22 — Definitions D-CTRL, SYNOPTIC CHECK, PATH A, item-4 cadence check (decided by: user; recorded VERBATIM before running anything)

> D-CTRL — pixel-count-matched random control (replaces the "farthest pixels" rule
> as primary; keep the deterministic rule as a reported secondary):
> - Candidate set: HARP bitmap region ∩ AR mask (|B_LoS| ≥ 30 G) ∩ OUTSIDE the dilated
>   PIL mask, defined on the LoS magnetogram at t.
> - Draws: 20 draws, seeds 0–19, uniform random WITHOUT replacement.
>   n = min(n_PIL, n_candidates). If n_candidates < n_PIL, also subsample the PIL mask
>   to n pixels (same seed), so both sides always have equal pixel counts.
>   Flag ctrl_short when this happens.
> - Pixels are drawn once in the magnetogram frame at t, then mapped to every AIA frame
>   with the same reprojection/differential rotation as the full masks.
> - Per draw: build the mean-intensity time series over (t−24h, t] for the PIL sample
>   and the control sample (valid frames only; exclusion rules P2/P4/QUALITY as
>   approved); remove a least-squares linear trend; CV = SD(residuals) / mean(series).
> - Combine: mean of the per-draw CVs (report the SD across draws too).
> - Primary feature: ΔCV = CV_PIL − CV_ctrl. Also report CV_PIL, CV_ctrl, CV_box.
>
> SYNOPTIC CHECK — report only, no bulk download:
> - AIA synoptic data (level 1.5, ~1024², ~2-min cadence): URL, format, coverage
>   2010→2026, 94 Å and 1600 Å availability, file size, any usage/rate policy.
> - Test: download 20 files with 4–8 parallel connections; report throughput.
> - If available: rerun the 3 pilot episodes with synoptic frames at the 12-min slots,
>   same masks mapped to the synoptic frame, D-CTRL metric; side by side with the
>   cutout results; overlays; time and size.
> - Also: SDAC/VSO full-res full-disk AIA via SunPy Fido — same 20-file parallel
>   throughput test. And count UNIQUE 12-min timestamps in the union of all 547 dev
>   alarm windows. Project total time/GB for (a) JSOC cutouts grouped by HARP, N = 1,
>   (b) synoptic, (c) SDAC full-res crop-and-delete; 94 Å only and 94 + 1600 Å.
> - Never use more than one JSOC account.
>
> PATH A — "phantom false alarms" (no downloads; descriptive, not a test of the
> primary result):
> - Using archived HEK-based labels (data/labels_hek/) and final SWPC K2 labels, with
>   the same frozen 10-feature gate scores and threshold:
>   1. Gate TSS, FAR, precision under HEK vs SWPC labels, hour and region level,
>      region-bootstrap 95% CI — for 2021–2024 and 2010–2019 separately.
>   2. Count alarm episodes (T1–T4 rules) labelled FALSE under HEK but TRUE under
>      SWPC ("phantom false alarms"), per year and as % of HEK false alarms.
>   3. Separate the two causes: also compare HEK vs SWPC on the SAME scale (K),
>      so region-number loss is separated from the ×0.7 scale change.
> - Literature check: any published report of HEK SWPC events with
>   ar_noaanum = 0 after ~2020, and any paper quantifying its effect on flare-forecast
>   verification. Links only.
>
> Item 4 cadence check (after the download finishes): for each pilot episode over
> (t−6h, t], compute ΔCV (D-CTRL, 6 h window) from (a) all 12 s frames and (b) only
> the 12-min-slot frames. Side by side, facts only. Raw 12 s files may be deleted
> after this.
>
> Run order: synoptic check and Path A now (they don't need JSOC); cadence check
> when item 4 finishes. Report each when done.

Notes (me, recorded before running):
- **Path A uses 2021–2024.** The standing rule (2026-09-21, "PRIMARY RESULT FINAL") is "No new analysis is to be run on 2021–2024". Path A is the user's explicit, descriptive exception. It does not alter or retest the FINAL primary result.
- The **"AR mask (|B_LoS| ≥ 30 G)"** here uses ≥; the earlier pilot code used > 30 G. D-CTRL follows the ≥ given here.

### D-CTRL / synoptic / cadence — implementation details (decided by: me, BEFORE any D-CTRL value is computed)
- **HARP bitmap region** = `hmi.sharp_720s` bitmap ≥ 33. Observed values are 1, 2, 33 and 34; ≥ 33 = inside the HARP, as in Bobra et al. 2014 p. 7. AR mask = |B_LoS| ≥ 30 G.
- **Draws:** for seed s, the control sample is `RandomState(s).choice(candidates, n, replace=False)`. When ctrl_short, the PIL sample is a separate `RandomState(s).choice(PIL, n, replace=False)`; otherwise the PIL sample is the full PIL mask (n = n_PIL).
- **Mapping to AIA (all masks in the D-CTRL runs, including the full PIL, box and deterministic ctrl):** each HMI pixel centre is mapped forward to the AIA frame (WCS, with `propagate_with_solar_surface` from the magnetogram time to the frame time) and assigned to the AIA pixel it falls in (nearest). A mask's frame mean is the mean over its HMI pixels of the AIA value at their mapped pixels. Pixels mapping outside the frame or onto NaN are ignored.
  - Reason: bilinear reprojection thresholded at 0.5 (used for the earlier pilot numbers) drops most isolated single-pixel samples, so the sample sizes would no longer be equal. Forward mapping keeps every sampled HMI pixel.
  - The earlier pilot results stay as recorded; the D-CTRL numbers use this mapping.
- **Box** = all pixels of the SHARP patch (U9, unchanged).
- **Valid frames:** P2 (amended), QUALITY == 0 and the P4 saturation rule, as approved. For **synoptic** frames (4×4-averaged level 1.5, values = DN per original pixel), the 12,000 DN cut is applied to the averaged pixel values. It cannot be applied per raw pixel, so this is a stated deviation. Synoptic frames are already level 1.5, so no update_pointing or registration is applied to them.
- **Cadence check (b):** the 12-s frames whose T_OBS lies within ±6 s of the 12-min slots t − 6 h + 12 min … t. **Synoptic:** the file at each 12-min slot, `AIAYYYYMMDD_HHMM_{0094,1600}.fits`, with HHMM = the slot rounded to the 2-min grid.

### SDAC/VSO full-res throughput test — not completed (recorded by: me)
- **SDAC is not an AIA full-resolution provider.** `Fido.search` for AIA 94 Å (2014-06-12 00:00–00:05) with Provider = SDAC returned 0 rows. Without a provider filter, VSO lists **only JSOC** (64.6 MiB per level-1 full-disk file). SDAC's `umbra.nascom.nasa.gov/sdo/aia/` holds only a few 2010–2012 event bundles.
- The 20-file test via VSO→JSOC (6 connections) was started, delivered 0 files in ~25 min, and was **stopped**. VSO stages JSOC data under VSO's own JSOC access, which conflicts with "Never use more than one JSOC account". No file was received.
- Path (c) "SDAC full-res crop-and-delete" therefore has no measured throughput.

### PATH A — RESULTS (descriptive; not a test of the FINAL primary result; recorded by: me)
`diag_patha.py` → `data/diag/patha_gate.csv`, `patha_episodes.csv`, `patha_phantom_*.csv`.
- **Setup:** primary subset (single-region), frozen gate and threshold −0.992496.
  - All 254,899 K2 rows have HEK and SWPC-K labels (month-boundary duplicates removed from both).
  - Dev uses the frozen OOF scores; 2021–2024 uses the mean of the frozen fold models, including 2022 as in the sensitivity analysis.
  - Reproduction checks: dev K2 hour TSS 0.6793 = Stage 2; 2021–2024 K2 hour TSS 0.5224 and 414 episodes = Stage 5's sensitivity row.
- **Label sets:**
  - HEK = archived HEK/SWPC labels, classes as reported.
  - K = SWPC originals, old scale (file 85b88518…).
  - K2 = final.
- **Same-scale pairs:** 2010–2019 HEK vs K; 2021–2024 HEK vs K2 (HEK carries GOES-16 fluxes as reported).

**1. Gate under each label set** (TSS 95% CI = HARP bootstrap, 1,000; precision = 1 − FAR)

| period | labels | level | positives | N | TSS [95% CI] | FAR | precision |
|---|---|---|---:|---:|---|---:|---:|
| 2010–2019 | HEK | hour | 2,444 | 114,952 | 0.725 [0.642, 0.796] | 0.725 | 0.275 |
| 2010–2019 | K | hour | 2,440 | 114,952 | 0.722 [0.636, 0.792] | 0.727 | 0.273 |
| 2010–2019 | K2 | hour | 3,168 | 114,952 | 0.679 [0.586, 0.748] | 0.666 | 0.334 |
| 2010–2019 | HEK | region | 64 | 986 | 0.680 [0.591, 0.766] | 0.750 | 0.250 |
| 2010–2019 | K | region | 64 | 986 | 0.664 [0.570, 0.750] | 0.755 | 0.245 |
| 2010–2019 | K2 | region | 86 | 986 | 0.647 [0.557, 0.726] | 0.682 | 0.318 |
| 2021–2024 | HEK | hour | 1,299 | 71,862 | 0.579 [0.401, 0.720] | 0.838 | 0.162 |
| 2021–2024 | K | hour | 1,465 | 71,862 | 0.553 [0.417, 0.679] | 0.825 | 0.175 |
| 2021–2024 | K2 | hour | 2,381 | 71,862 | 0.522 [0.412, 0.626] | 0.733 | 0.267 |
| 2021–2024 | HEK | region | 38 | 605 | 0.682 [0.552, 0.785] | 0.763 | 0.237 |
| 2021–2024 | K | region | 45 | 605 | 0.736 [0.641, 0.815] | 0.705 | 0.295 |
| 2021–2024 | K2 | region | 71 | 605 | 0.681 [0.584, 0.762] | 0.576 | 0.425 |

**2–3. Episodes (T1–T4 under K2; 961 = 547 dev + 414 test, relabelled at t).** "Phantom" = false under the first set, true under the second; "reverse" = the opposite.

| comparison | 2010–2019 phantom / HEK-or-K false | 2021–2024 phantom / false | all | reverse (all) |
|---|---|---|---|---|
| HEK → K2 (both causes) | 18 / 466 | 34 / 386 (8.8%) | 52 / 852 (6.1%) | 1 |
| HEK → K (dev: same scale) | **0** / 466 | 20 / 386 | 20 / 852 (2.3%) | 14 |
| K → K2 (scale change only) | 19 / 468 | 26 / 378 | 45 / 846 (5.3%) | 0 |

- **Per year, HEK → K2 phantom:** 2011 3, 2014 4, 2015 8, 2017 3, 2021 2, **2022 15**, **2023 17**, 2024 0, other years 0.
- **Same-scale view:** 2010–2019 HEK vs K = 0 phantom, so there is no region-loss effect in the dev years. 2021–2024 HEK vs K2 (same scale) = 34 phantom (2021 2, 2022 15, 2023 17, 2024 0).
- **Literature (links only; not read in full):** arXiv:2512.13417 "Defects and Inconsistencies in Solar Flare Data Sources: Implications for Machine Learning Forecasting"; Angryk et al. 2020, Sci. Data (SWAN-SF); NCEI "GOES Flare Report ReadMe" (Lucas & Machol, 2025); arXiv:2608.04537. **No source found that specifically reports HEK ar_noaanum = 0 after ~2020 [unverified whether 2512.13417 does].**

### 2026-09-22 — Download-speed tests (decided by: user; method only, same data)
- **HARP 6975 item 4** is requested with JSOC `method="url-tar"`: one archive per request, unpacked into the item folder, tar deleted. The data, box, tracking and t_ref are unchanged; only the delivery method differs.
- **HARP 4231** continues per file from finished request JSOC_20260922_000545 (886 of 1,800 at the switch). The log now records `prep_s` (submit → ready) and `download_s` separately.
- **Synoptic** downloads use 6 parallel connections, written to .tmp and renamed. One truncated synoptic file left by the stopped sequential run was found (FITS size check) and removed.
- **HARP 3248 item 4:** requested after 6975's export has finished (one pending export per address), with whichever method measured faster (operational choice, stated when made).

## 2026-09-22 — Path A follow-up (decided by: user; frozen files and the main result unchanged)
**Prior work (user, recorded verbatim):** "Prior work = Hu, Jin, Verma, Liu, Manchester, Zhao, Gombosi & Chen, arXiv:2512.13417v3 (2026). They report >3,000 post-2022 SunPy-HEK GOES flares with AR=0 (p.9) and the SWPC x0.7 scaling (Fig.4). They do not quantify the HEK AR=0 effect on alarm FAR. Path A = independent confirmation + FAR quantification, not a discovery."
Requested:
- (2) 95% CIs for FAR and precision, HEK vs K2, 2021–24, hourly and region level: 2,000 bootstrap resamples by HARP, seed 0, plus the CI of the difference (HEK − K2) from the same resamples.
- (3) The 34 phantom alarms → `data/pathA/phantoms_2021_24.csv`.
- (4) An evidence pack for 3 phantoms from 2023 → `data/pathA/evidence/`.
- (5) Numbers only.

## 2026-09-22 — Prior-work check completed: Hu et al. 2026 read in full (recorded by: Claude chat, on user request; no analysis changed)
Source: Hu, Jin, Verma, Liu, Manchester, Zhao, Gombosi & Chen, "Defects and Inconsistencies in Solar Flare Data Sources: Implications for Machine Learning Forecasting", arXiv:2512.13417v3 (June 2026). Main text pp. 1–33 read; appendix tables only skimmed.
- **Already published (not ours):** SunPy-HEK GOES list has >3,000 post-2022 flares with AR = 0; authors say not to use it for research, especially GOES-R era (p. 9). SWPC ×0.7 scaling, ratio 0.7 before Dec 2019 then 1 (pp. 10–11, Fig. 4).
- **Their Section 4 (ML effect)** compares SWPC-FTP vs NCEI Science-Quality labels, and NRT vs definitive SHARPs (LSTM + logistic regression/PCA; train 2010-05-01 → 2019-12-31; test 2020–2024; M/X vs A/B, C excluded; 30 bootstrap models). It does **not** test HEK labels. No HEK effect on skill or FAR is reported in the main text.
- **Their recommendations (Section 5, Table 11):** for AR-based ML, SWPC-FTP labels are the most direct source; the pre-GOES-R scaling must be documented/corrected; definitive SHARPs preferred for retrospective benchmarks; SunPy-HEK must be independently validated before training/evaluation. Our existing design (SWPC originals, K2 = ÷0.7 correction, definitive SHARPs) already follows these. No design change.
- **Consequence for Path A framing:** independent confirmation of a published defect + first alarm-level quantification of its effect on FAR (as far as checked). Hu et al. must be cited. Open caveat: appendix tables not read line by line.

### Path A follow-up — RESULTS (numbers only; recorded by: me)
`diag_patha2.py`. 2021–2024 test HARPs, single-region, frozen gate and threshold. 5,145 alarm hours; 139 alarmed regions of 605. 2,000 HARP resamples, seed 0; all 2,000 were usable.

| level | quantity | HEK | K2 | HEK − K2 |
|---|---|---|---|---|
| hour | FAR | 0.8383 [0.7599, 0.9112] | 0.7331 [0.6609, 0.8040] | 0.1052 [0.0662, 0.1466] |
| hour | precision | 0.1617 [0.0888, 0.2401] | 0.2669 [0.1960, 0.3391] | −0.1052 [−0.1466, −0.0662] |
| region | FAR | 0.7626 [0.6905, 0.8288] | 0.5755 [0.4937, 0.6593] | 0.1871 [0.1224, 0.2517] |
| region | precision | 0.2374 [0.1712, 0.3095] | 0.4245 [0.3407, 0.5063] | −0.1871 [−0.2517, −0.1224] |

- **Phantom list:** `data/pathA/phantoms_2021_24.csv`, 34 alarms (2021: 2, 2022: 15, 2023: 17) in 20 HARPs.
- **HEK match** (SWPC-reported events within ±10 min of the first SWPC K2 M1+ start in (t, t+24h]): ar_noaanum = 0 for 27 phantoms, "0;0" (two HEK events) for 3, and no HEK event for 4 (HARP 9699 2023-06-22; HARP 10430 ×3, 2023-11-28 and 2023-12-01).
- **Evidence pack** (`data/pathA/evidence/`, the first 3 phantoms of 2023):
  - HARP 8942 2023-01-08 09:59 (SWPC M2.1, reg 3181; HEK ar_noaanum 0, hpc_x 0, hgs_x/y 0).
  - HARP 9121 2023-02-25 16:59 (SWPC M6.3, reg 3229; HEK ar 0).
  - HARP 9182 2023-03-05 11:59 (SWPC M1.0, reg 3242; 2 HEK M1.0 events, both ar 0).
  - Each folder has `hek_record.csv` (165 fields incl. hpc/hgs/hgc/hrc/event_coord), `swpc_report_line.txt` (the NCEI original XRA line) and `sharp_record_at_alarm.csv` (raw SHARP row at the alarm T_REC).

### Path A consistency checks — RESULTS (numbers only; recorded by: me)
`diag_patha3.py`. Descriptive; frozen files and the main result unchanged.

**1. Region flips.** 139 alarmed regions of 605; **26 flip** (HEK false → K2 true); the 34 phantom episodes span 20 HARPs. No flipping region has a single HEK-positive row. `data/pathA/region_flips_2021_24.csv`.

| reason | regions |
|---|---:|
| phantom episode (first evaluable hour) | 15 |
| later alarm hour, K2-positive, not an episode t | 7 |
| K2-positive rows only outside alarm hours | 4 |

The 4 with no K2-positive alarm hour: HARPs 9590, 9643, 9822, 10527. The 7 "later alarm hour": 8878, 8968, 9133, 9137, 9632, 9762, 10312. (The region level counts a region positive if **any** row is positive and alarmed if **any** hour alarms, so it does not require the positive row to be an alarm hour.)

**2. FAR / precision by test-year set** (2,000 HARP resamples, seed 0; the 2021–2024 table above is unchanged)

| years | level | FAR HEK | FAR K2 | FAR HEK − K2 | precision HEK | precision K2 |
|---|---|---|---|---|---|---|
| primary 2021/2023/2024 (3,988 alarm hours, 105 alarmed regions) | hour | 0.8007 [0.7110, 0.8878] | 0.7021 [0.6186, 0.7833] | 0.0985 [0.0573, 0.1499] | 0.1993 [0.1122, 0.2890] | 0.2979 [0.2167, 0.3814] |
| primary 2021/2023/2024 | region | 0.7238 [0.6344, 0.8058] | 0.5429 [0.4414, 0.6337] | 0.1810 [0.1122, 0.2589] | 0.2762 [0.1942, 0.3656] | 0.4571 [0.3663, 0.5586] |
| 2022 only (1,157 alarm hours, 34 alarmed regions) | hour | 0.9680 [0.9230, 1.0000] | 0.8401 [0.7331, 0.9223] | 0.1279 [0.0519, 0.2241] | 0.0320 [0.0000, 0.0770] | 0.1599 [0.0777, 0.2669] |
| 2022 only | region | 0.8824 [0.7692, 0.9744] | 0.6765 [0.5161, 0.8333] | 0.2059 [0.0811, 0.3448] | 0.1176 [0.0256, 0.2308] | 0.3235 [0.1667, 0.4839] |

**3. HEK M1+ events with ar_noaanum ≤ 0 or missing, per year** (all HEK/SWPC M1+ events, classes as reported, no scale conversion; `data/pathA/hek_ar_zero_by_year.csv`)

| year | HEK M1+ | AR = 0 or missing | fraction |
|---|---:|---:|---:|
| 2019 | 0 | 0 | — |
| 2020 | 2 | 2 | 1.000 |
| 2021 | 31 | 14 | 0.452 |
| 2022 | 195 | 173 | 0.887 |
| 2023 | 334 | 284 | 0.850 |
| 2024 | 949 | 72 | 0.076 |

**4. The 4 "no HEK event" phantoms** (HARP 9699 2023-06-22; HARP 10430 2023-11-28 and ×2 2023-12-01). Re-searched HEK (FRM = SWPC) within ±60 min of both the SWPC start and the SWPC peak: **no HEK event found in any of the 8 searches.** `data/pathA/no_hek_phantoms_pm60min.csv`.

**5.** The staged entry "Prior-work check completed: Hu et al. 2026 read in full" was already in `decisions.md` and went into commit `2ba51d3` unchanged (verified with `git log -S`). No re-commit was needed.

## 2026-09-23 — COMBINED EUV TEST (decided by: user; replaces all earlier EUV test prompts from Claude chat)
**Rules in force:** no true-vs-false comparison of ΔCV anywhere; frozen files and the main result unchanged; one JSOC export pending at a time, the user's account only; all rules recorded here **before** running; numbers only; **STOP before the full-study download.**

### PHASE 0 — prior work (source: Claude chat, verified from PDFs; recorded as given)
- Kniezewski, Mason, Uritsky & Garland 2024, ApJL 977:L29 — 3-min, 6 h, limb loops, 131/171/193/304 Å, 53 flares ≥ C5 vs 30 flare-quiet ARs.
- Dissauer, Leka & Wagner 2023, ApJ 942:83 — AARPs; full resolution; 72-s bursts; AEC images avoided; criticises spatial binning.
- Zhong, Kolotkov & Nakariakov, arXiv:2602.18133 — 12-s full-res cutouts; 0.9–10 mHz.
- Nishizuka et al. 2018, ApJ — DeFN; 1-h cadence.
- Galvez et al. 2019, ApJS — SDOML, built from AIA synoptic 1024×1024, 2.4″/px, 2-min.

### Download set-up (rules)
- **JSOC:** `url-tar` for all exports. **Overlap test:** once an export reports complete, submit the next while the previous tar downloads; if JSOC rejects it as a second pending export, revert to sequential and log the exact response.
- **Synoptic:** 12 connections; log files/s and errors every 500 files; on any error or throttling drop to 6 and log it.
- **Disk:** free space at start **666 GB** (data/euv_pilot currently 1.7 GB). **Crop-on-download** for synoptic: after each full-disk frame, save the patch for every HARP needed at that time (HARP box + D-CTRL margin), then delete the full-disk file. First verify on the 3 pilot HARPs that cropped-patch ΔCV equals full-disk ΔCV (|diff| < 1e-6). Report MB per 1,000 frames before and after.
- **Shared cross-HARP cache:** not used now (≈7% saving); noted as optional.

### PHASE 1 (no downloads)
1. **Exposure:** confirm every frame (cutout, 12-s, synoptic) is divided by EXPTIME before ΔCV; for synoptic, check header/units and state whether already normalised. **Rule: drop frames with EXPTIME < 50% of that channel's median in the window.** Report frames checked/dropped per pilot HARP and channel, and recompute all pilot ΔCVs (24 h cutout, 24 h synoptic, 6 h 12-s, 6 h 12-min): old vs new.
2. **Offset test:** HARPs 4231, 6975, 3248, existing 12-s 94 Å frames over (t−6h, t]; 12-min subsamples at all 60 offsets (0 s to 11:48 in 12-s steps). Report mean, SD, min, max, and the percentile of the current 12-min value.
3. **Path A leftovers:** HEK ar_noaanum = 0 count and fraction per year 2019–2024 (all M1+); re-search the 4 "no HEK event" phantoms (HARP 9699; 10430 ×3) at ±60 min by start and by peak.

### PHASE 2 — cadence test (synoptic, 94 Å only)
4. **15 dev alarms, random seed 1, stratified 8/7 by label for coverage only.** D-CTRL ΔCV over (t−24h, t] at 2, 3, 6 and 12 min; same masks, same 20 draws, exposure rule; **slot = nearest frame within ± half the cadence; an alarm is valid only if ≥ 90% of slots are filled.**
   - **Decision rule:** reference = 2 min. Choose the **slowest** of {12, 6, 3} with **Spearman ρ ≥ 0.9 AND median |ΔCV − ΔCV_2min| ≤ 0.02**; if none passes, use 2 min. Report ρ with a bootstrap 95% CI (2,000 resamples, seed 0) and state that n = 15.
   - **1600 Å is not re-tested** (validated by the 3-HARP pilot only; stated as a limitation).

### PHASE 3 — synoptic vs cutout (JSOC, 94 Å only)
5. First 10 of the 15 (seed-1 order): 24 h cutouts at 2-min cadence by url-tar.
   - (a) cutout vs synoptic at the chosen cadence. **Rule: synoptic is the full-study source if median |diff| ≤ 0.01 AND Spearman ρ ≥ 0.9, otherwise JSOC cutouts.**
   - (b) cutout-based 2/3/6/12-min agreement as a second opinion on Phase 2.

### PHASE 4 — after the decisions
6. **131 Å** ΔCV at the chosen cadence for the 15 alarms (descriptive only).
7. **Summary table:** each choice (source, cadence, exposure rule, slot rule), its rule, the measured numbers, pass/fail, final decision.
8. **Full-study cost table** for 547 alarms at the chosen source/cadence: files, GB after cropping, estimated hours for 2 channels (and 3 with 131 Å). Wall-clock time per phase.
9. **Commit and STOP.** Wait for the user's go-ahead before the full download.

### Combined EUV test — implementation details (decided by: me, BEFORE running Phases 2–3)
- **Selection (Phase 2):** from the frozen dev cohort `data/stage3/cohort_dev.csv` (547 episodes). 8 with true_alarm = 1 and 7 with true_alarm = 0, via `DataFrame.sample(n, random_state=1)` within each label; the 15 are then ordered by `RandomState(1).permutation`. **Seed-1 order** = that permutation; Phase 3 uses its first 10. The selection is written to `data/euv_cad/alarms.csv` before any EUV value is computed. Labels are used for coverage only, never compared.
- **Masks:** `hmi.sharp_720s` magnetogram + bitmap at each alarm's T_REC, as in item 1. One JSOC export (url-tar) with all 15 record sets comma-separated; if JSOC rejects the multi-set syntax, 15 sequential exports.
- **Exposure rule** (Phase 1 rule 1): applied to every source, including the Phase 2–3 frames.
- **Crop-on-download (synoptic):**
  - Box = the bounding box, in frame pixels, of the HMI patch's edge pixels mapped to that frame (differential rotation to the frame time), padded by **50″** (the item-2/3 cutout margin; 21 synoptic px).
  - The crop is saved as FITS with its header (EXPTIME, QUALITY, T_OBS and WCS kept), then the full-disk file is deleted.
  - Verified first on the 3 pilot HARPs: ΔCV from crops vs full disk, |diff| < 1e-6.
- **Slots (Phase 2):** for cadence c ∈ {2, 3, 6, 12} min, slots = t − 24 h + k·c, k = 1…24h/c. Each slot takes the nearest 2-min synoptic frame within ± c/2. A slot is **filled** if that frame exists and is valid (P2, QUALITY, exposure rule). An alarm is valid at cadence c if ≥ 90% of its slots are filled.
- **Agreement statistics:** Spearman ρ between ΔCV_c and ΔCV_2min over the alarms valid at both. The bootstrap resamples alarms (2,000, seed 0) for the ρ CI. Median |ΔCV_c − ΔCV_2min| is over the same alarms.
- **Phase 3 cutouts:** `aia.lev1_euv_12s[t−24h+2m – t @2m][94]{image}`, im_patch as items 2–3 (HARP box + 50″, tracked, t_ref = t), url-tar. The same D-CTRL, P2, QUALITY and exposure rules apply; pointing update and cutout registration as approved. The cutout-vs-synoptic comparison is at the cadence chosen in Phase 2, on the same slots.

### Combined EUV test — PHASE 1 RESULTS and crop verification (numbers only; recorded by: me)
**1. Exposure.**
- Every source (cutout, 12-s, synoptic) is divided by EXPTIME before ΔCV (`euv_dctrl.frames`; the same code in all paths).
- Synoptic headers carry EXPTIME, with no PIXLUNIT/BUNIT. The synoptic README gives the units as "DN per original 0.6 arc-sec pixel", i.e. **not exposure-normalised**, so the division is required and applied.
- Rule applied: drop frames with EXPTIME < 50% of that channel's median in the window. Channel medians were 2.9007–2.9021 s.
- Frames dropped by the rule (this count overlaps the QUALITY-excluded zero-exposure calibration frame, 1 per 24 h window):
  - 24-h cutout and synoptic: 1 per HARP and channel, except **HARP 4231 cutout 94 Å: 3**.
  - 6-h 12-s 94 Å: **4231: 33**, 6975: 0, 3248: 0.
- ΔCV old → new (`data/euv_pilot/exposure_rule_old_vs_new.csv`). Changes: 4231 cutout 94 −0.1193 → −0.1171 (+0.0022); 4231 12-s (a) 0.2080 → 0.2086 (+0.0006). **All other 16 values are unchanged** at 4 dp.

**2. Offset test** (12-s 94 Å, (t−6h, t], 60 offsets × 30 frames; `data/euv_pilot/offset_test_12s_94.csv`)

| HARP | ΔCV mean | SD | min | max | current (offset 0) | percentile |
|---|---:|---:|---:|---:|---:|---:|
| 4231 | 0.2002 | 0.0609 | 0.1308 | 0.3065 | 0.1497 | 24.2 |
| 6975 | 0.2139 | 0.0178 | 0.1775 | 0.2363 | 0.2322 | 84.2 |
| 3248 | 0.1804 | 0.0133 | 0.1602 | 0.1999 | 0.1980 | 94.2 |

**3. Path A leftovers:** already computed in the consistency checks (commit `fb1fdd4`) with the same definitions: HEK M1+ with ar_noaanum ≤ 0 or missing, 2019–2024; the 4 no-HEK phantoms re-searched at ±60 min by start and by peak (0 of 8 found). Not recomputed.

**Crop-on-download verification** (3 pilot HARPs, 120 synoptic 94 Å frames each): ΔCV from crops = full disk, **|diff| = 0.0** for all 3 (PASS, < 1e-6). **MB per 1,000 frames: full disk 727–752; cropped 141–190.**

**Selection (Phase 2):** 15 alarms in `data/euv_cad/alarms.csv` (seed-1 order). HARPs: 892, 5745, 7115, 1638, 2663, 5692, 5885, 3291, 6975, 5111, 4205, 4321, 3248, 187, 750.

### Combined EUV test — stall and resume (recorded by: me)
- Both downloads stopped at ~02:19 IST (0% CPU until 10:18); the machine most likely slept. Synoptic had reached 7,000/10,800; cutouts 9 of 10 (alarm 7, HARP 5885, tar stalled at 73 MB).
- Fix: `socket.setdefaulttimeout(120)` (urlretrieve had no timeout), partial files removed, both relaunched under `caffeinate -i`. Synoptic resumes (existing crops skipped); HARP 5885 gets a new export (one pending at a time).
- **Wall-clock times for Phases 2–3 exclude the stall** (~8 h); both the rates before the stall and the resumed rates are reported.

### Combined EUV test — PHASE 2 and PHASE 3 RESULTS and DECISIONS (numbers only; recorded by: me, applying the user's pre-registered rules)
**Data.** Synoptic 94 Å 2-min, 15 alarms: 10,631 of 10,800 frames (169 not in the archive; alarm 5, HARP 2663: 119). Cropped on download, 0 errors, 12 connections throughout. JSOC 2-min cutouts, first 10 alarms: 711–720 frames each.
**Validity (≥ 90% of slots filled by a valid frame).** Unfilled slots come mostly from P2 flare exclusion plus QUALITY; alarm 5 from archive gaps. Synoptic at 2 min: valid for 8 of 15. Synoptic 2-min fill 0.736–0.999.

**Phase 2 — cadence (synoptic, reference 2 min; alarms valid at both cadences; bootstrap 2,000, seed 0)**

| cadence | n | Spearman ρ [95% CI] | median \|ΔCV − ΔCV_2min\| | PASS (ρ ≥ 0.9 and ≤ 0.02) |
|---|---:|---|---:|---|
| 3 min | 8 | 0.976 [0.730, 1.000] | 0.0015 | yes |
| 6 min | 8 | 0.952 [0.615, 1.000] | 0.0030 | yes |
| 12 min | 8 | 0.952 [0.615, 1.000] | 0.0077 | yes |

**Decision (rule): cadence = 12 min** (the slowest passing). **n = 8, not 15**, because 7 alarms failed the ≥ 90% fill rule at 2 min. The CI lower bounds are 0.62–0.73.

**Phase 3(b) — cutout second opinion (first 10 alarms; valid at both; n = 5)**

| cadence | n | ρ [95% CI] | median \|diff\| | PASS |
|---|---:|---|---:|---|
| 3 min | 5 | 1.000 [1.000, 1.000] | 0.0030 | yes |
| 6 min | 5 | 0.900 [0.111, 1.000] | 0.0073 | no — ρ is 0.9 exactly for n = 5, computed as 0.8999… (float), so ≥ 0.9 fails by rounding |
| 12 min | 5 | 1.000 [1.000, 1.000] | 0.0174 | yes |

**Phase 3(a) — source (at 12 min, same slots; alarms valid in both; n = 6)**
- Spearman ρ 0.600 [−0.636, 1.000]; median |ΔCV_cut − ΔCV_syn| **0.0183**.
- Rule: synoptic if median ≤ 0.01 AND ρ ≥ 0.9 → **FAIL** → **decision (rule): full-study source = JSOC cutouts.**
- Per alarm (cut vs syn): 5745 0.2372 / 0.2409; 1638 0.0431 / 0.1667; 5885 0.1006 / 0.0727; 3291 0.0919 / 0.1006; 6975 0.1378 / 0.1333; 5111 0.4191 / 0.3708.

**Phase 4 (next):** 131 Å ΔCV at 12 min, 15 alarms, from the chosen source (JSOC cutouts, url-tar, pipelined as in the overlap test). Descriptive only.

### Combined EUV test — PHASE 4 RESULTS, SUMMARY and COST (numbers only; recorded by: me). **STOPPED before any full-study download.**

**6. 131 Å ΔCV at 12 min** (JSOC cutouts, url-tar; descriptive; `data/euv_cad/cv_cutout_131.csv`).
- Valid (≥ 90% filled): 10 of 15.

| order | HARP | fill | valid | ΔCV ± SD(draws) | CV_PIL | CV_ctrl | CV_box |
|---:|---:|---:|---|---|---:|---:|---:|
| 1 | 892 | 0.850 | no | 0.0171 ± 0.0003 | 0.5352 | 0.5181 | 0.4458 |
| 2 | 5745 | 0.908 | yes | 0.3729 ± 0.0047 | 0.7247 | 0.3518 | 0.3515 |
| 3 | 7115 | 0.808 | no | 0.1119 ± 0.0023 | 0.9915 | 0.8797 | 0.8625 |
| 4 | 1638 | 0.950 | yes | 0.0037 ± 0.0003 | 0.0684 | 0.0648 | 0.0559 |
| 5 | 2663 | 0.992 | yes | −0.0089 ± 0.0007 | 0.0484 | 0.0574 | 0.0372 |
| 6 | 5692 | 0.725 | no | 0.0540 ± 0.0044 | 0.6235 | 0.5695 | 0.6834 |
| 7 | 5885 | 0.833 | no | 0.0677 ± 0.0003 | 0.1486 | 0.0809 | 0.0849 |
| 8 | 3291 | 0.992 | yes | 0.0557 ± 0.0006 | 0.1086 | 0.0530 | 0.0532 |
| 9 | 6975 | 0.967 | yes | 0.0696 ± 0.0004 | 0.1228 | 0.0532 | 0.0750 |
| 10 | 5111 | 0.925 | yes | 0.1433 ± 0.0011 | 0.2335 | 0.0902 | 0.0855 |
| 11 | 4205 | 0.992 | yes | 0.0034 ± 0.0006 | 0.0495 | 0.0461 | 0.0244 |
| 12 | 4321 | 0.983 | yes | 0.0196 ± 0.0005 | 0.0686 | 0.0490 | 0.0406 |
| 13 | 3248 | 0.975 | yes | 0.1121 ± 0.0014 | 0.1878 | 0.0757 | 0.0627 |
| 14 | 187 | 0.883 | no | 0.0670 ± 0.0007 | 0.1259 | 0.0589 | 0.0421 |
| 15 | 750 | 0.892 | no | 0.2117 ± 0.0020 | 0.5466 | 0.3349 | 0.3079 |

- 131 Å exports: 15, all 116–120 frames. Median prep 114 s and download 43 s, with one queue outlier each (prep 1,688 s; download 1,797 s). The overlap was kept throughout.

**7. Summary of choices**

| choice | rule (pre-registered) | measured | pass/fail | final decision |
|---|---|---|---|---|
| exposure | drop frames with EXPTIME < 50% of the channel median; divide all frames by EXPTIME | synoptic not pre-normalised (README); drops: 1 per 24 h window (= the QUALITY-flagged 0-s frame), 4231 cutout 94: 3, 4231 12-s: 33; ΔCV changes +0.0022 and +0.0006, the others 0 | applied | rule adopted |
| slot rule | nearest valid frame within ± cadence/2; alarm valid if ≥ 90% filled | 2-min synoptic: 8/15 valid; 12-min 94 synoptic: 11/15 [corrected 2026-09-23: earlier '8/15' was the number valid at BOTH 2 and 12 min, the n of the cadence test]; 12-min 131 cutout: 10/15 | applied | rule adopted (it removes many alarms: fill counts P2-excluded frames as unfilled) |
| cadence | slowest of {12, 6, 3} with ρ ≥ 0.9 and median \|Δ\| ≤ 0.02 vs 2 min | 12 min: ρ 0.952 [0.615, 1.000], median 0.0077, n = 8 | pass | **12 min** |
| cadence (2nd opinion, cutouts) | same rule | 12 min ρ 1.000, median 0.0174, n = 5 (6 min fails by float rounding at ρ = 0.9) | pass at 12 | consistent |
| source | synoptic if median \|diff\| ≤ 0.01 and ρ ≥ 0.9 at the chosen cadence | median 0.0183, ρ 0.600 [−0.636, 1.000], n = 6 | **fail** | **JSOC cutouts** |
| crop-on-download | cropped ΔCV = full-disk ΔCV, \|diff\| < 1e-6 | \|diff\| = 0 on 3 pilot HARPs; 727–758 → 141–245 MB per 1,000 frames | pass | available (synoptic not chosen) |
| JSOC overlap | submit the next export once the previous is complete, during the tar download | never rejected in 25 exports | pass | pipelined exports |
| synoptic connections | 12; drop to 6 on errors/throttling | 0 errors; 2.06 files/s overall | — | stayed at 12 |
| 1600 Å | not re-tested | validated by the 3-HARP pilot only | limitation | stated |

**8. Full-study cost, 547 dev alarms, JSOC cutouts at 12 min, one url-tar export per HARP (union of windows), pipelined** (`data/euv_cad/cost_full_study.csv`)
- Inputs, all measured: 180 requests/channel; 43,030 frames/channel (239 per request); prep = 87 + 0.236 × frames s (fit, n = 24 exports, one 1,688-s queue outlier excluded) → 143 s/request; median tar rate 0.76 MB/s → 68 s/request; MB/frame 94 Å 0.216, 131 Å 0.312. **1600 Å assumed = 94 Å** (not measured at 12 min by url-tar). Processing 0.09 s/frame per episode-frame (547 × 120), 1 core.

| channels | requests | files | GB | download h (pipelined) | download h (sequential) | processing h (1 core) |
|---|---:|---:|---:|---:|---:|---:|
| 94 + 1600 Å | 360 | 86,060 | 18.6 | 14.3 | 21.2 | 3.3 |
| 94 + 1600 + 131 Å | 540 | 129,090 | 32.0 | 21.5 | 31.8 | 4.9 |

JSOC queue outliers (~30 min per request, seen twice in 25) are not in these medians.

**Wall-clock per phase (stall excluded):** Phase 1: 12.4 min. Phase 2: download 88.5 min (10,800 synoptic) + ΔCV 19.1 min. Phase 3: download 70.9 min (10 × 2-min cutouts) + ΔCV 21.4 min. Phase 4: 131 download 55.1 min + ΔCV 5.1 min.

## 2026-09-23 — VALIDITY COUNT TEST (decided by: user; descriptive; no downloads, no ΔCV computed or reported, no rule changes)
Data: the 15 test alarms (synoptic 94 Å, 2-min) and the 10 with 2-min JSOC cutouts (94 Å). The same slot rule as the test (nearest **valid** frame within ± cadence/2; exposure rule; flare-in-progress invalid). Per alarm × cadence (2, 3, 6, 12 min) × source: slots, filled, % filled, valid at 90/80/70%; reason for each empty slot; summary valid counts overall and by label; per-alarm list.

Implementation (decided by: me, before running):
- **Empty-slot reason:** if no frame at all lies within ± cadence/2 → (a) no file in the archive or export. Otherwise every frame in the window is invalid, and the slot takes the reason of the **nearest** frame, with precedence **(b) exposure rule → (c) flare-in-progress (P2 a or b) → (d) QUALITY ≠ 0 → (d) other** (e.g. no mapped pixels).
- Zero-exposure calibration frames fail both (b) and QUALITY; by this precedence they count as (b).
- Flags are recomputed from each alarm's stored per-frame series (t_obs, quality, exptime, box), with P2 re-derived from SWPC (same function and regions as the test). The stored `valid` column must reproduce exactly; this is asserted.

### VALIDITY COUNT TEST — RESULTS (descriptive; counts only; no ΔCV; no rule changes; recorded by: me)
`euv_validity.py` → `data/euv_cad/validity_counts.csv` (per alarm × cadence × source), `validity_summary.csv`, `validity_per_alarm.csv`. The recomputed flags reproduce the test's `valid` column exactly (asserted).
**Correction in the Phase 4 summary:** 12-min synoptic valid = 11/15, not 8/15. The 8 was the number valid at both 2 and 12 min.

**Valid alarms (overall | true | false)**

| source | cadence | ≥ 90% | ≥ 80% | ≥ 70% |
|---|---|---|---|---|
| synoptic (15: 8 true, 7 false) | 2 min | 8 \| 2 \| 6 | 14 \| 7 \| 7 | 15 \| 8 \| 7 |
| synoptic | 3 min | 9 \| 3 \| 6 | 14 \| 7 \| 7 | 15 \| 8 \| 7 |
| synoptic | 6 min | 10 \| 4 \| 6 | 14 \| 7 \| 7 | 15 \| 8 \| 7 |
| synoptic | 12 min | 11 \| 5 \| 6 | 15 \| 8 \| 7 | 15 \| 8 \| 7 |
| cutout (10: 7 true, 3 false) | 2 min | 5 \| 2 \| 3 | 8 \| 5 \| 3 | 10 \| 7 \| 3 |
| cutout | 3 min | 5 \| 2 \| 3 | 9 \| 6 \| 3 | 10 \| 7 \| 3 |
| cutout | 6 min | 6 \| 3 \| 3 | 9 \| 6 \| 3 | 10 \| 7 \| 3 |
| cutout | 12 min | 7 \| 4 \| 3 | 10 \| 7 \| 3 | 10 \| 7 \| 3 |

**Empty slots by reason (totals over alarms)**

| source | cadence | slots | empty | (a) no file | (b) exposure | (c) flare-in-progress | (d) QUALITY ≠ 0 | (d) other |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synoptic | 2 | 10,800 | 1,019 | 169 | 14 | 682 | 154 | 0 |
| synoptic | 3 | 7,200 | 645 | 101 | 4 | 437 | 103 | 0 |
| synoptic | 6 | 3,600 | 276 | 41 | 2 | 184 | 49 | 0 |
| synoptic | 12 | 1,800 | 103 | 19 | 1 | 62 | 21 | 0 |
| cutout | 2 | 7,200 | 737 | 15 | 31 | 580 | 111 | 0 |
| cutout | 3 | 4,800 | 468 | 7 | 22 | 368 | 71 | 0 |
| cutout | 6 | 2,400 | 197 | 0 | 5 | 157 | 35 | 0 |
| cutout | 12 | 1,200 | 69 | 0 | 3 | 53 | 13 | 0 |

**Per alarm** (% filled at 2 min / 12 min; main reason over all cadences):
- **Synoptic:**
  - 1 HARP 892 2011-09-26 04:59 true 84.0/89.2 flare
  - 2 HARP 5745 2015-07-06 18:59 true 89.4/95.8 flare
  - 3 HARP 7115 2017-09-06 09:59 true 80.3/88.3 flare
  - 4 HARP 1638 2012-05-08 22:59 true 96.0/100.0 flare
  - 5 HARP 2663 2013-04-18 19:59 false 83.5/84.2 no file
  - 6 HARP 5692 2015-06-19 12:59 true 73.6/80.8 flare
  - 7 HARP 5885 2015-08-26 09:59 true 84.9/95.0 flare
  - 8 HARP 3291 2013-10-20 20:59 false 99.9/100.0 exposure
  - 9 HARP 6975 2017-04-01 08:59 true 97.4/98.3 flare
  - 10 HARP 5111 2015-01-26 06:59 false 93.8/95.8 flare
  - 11 HARP 4205 2014-06-07 19:59 false 99.9/100.0 exposure
  - 12 HARP 4321 2014-07-10 18:59 false 99.0/100.0 no file
  - 13 HARP 3248 2013-10-08 06:59 false 98.3/99.2 flare
  - 14 HARP 187 2010-09-27 23:59 false 90.1/94.2 QUALITY
  - 15 HARP 750 2011-08-02 16:59 true 88.5/93.3 flare
- **Cutout** (first 10): 83.6/89.2, 89.3/95.8, 79.6/88.3, 95.8/99.2, 99.9/100.0 (exposure), 73.9/81.7, 84.6/93.3, 99.9/100.0 (exposure), 97.4/99.2, 93.8/95.8. The main reason is flare-in-progress for all except orders 5 and 8.

## 2026-09-23 — Flare-followed fraction, alarmed vs non-alarmed, primary test years (requested by: user; descriptive; no model fitting)
- Frozen Stage 5 gate on 2021/2023/2024, single-region (the mean of the 5 frozen fold models, threshold −0.992496), with K2 SWPC labels. The re-scoring reproduces Stage 5 exactly: hour TP 1,188, FP 2,800, FN 788, TN 48,580; TSS 0.5467, FAR 0.7021; region FAR 0.5429.
- CIs: HARP bootstrap, 1,000 resamples, seed 20260921 (the Stage 5 gate scheme). `diag_flare_rate.py` → `data/stage5/flare_rate_by_alarm_primary.csv`. No new analysis of the primary question; the FINAL result is unchanged.

| level | group | n | followed by M1+ in 24 h | fraction [95% CI] |
|---|---|---:|---:|---|
| hour | (a) alarmed | 3,988 | 1,188 | 0.298 [0.223, 0.383] |
| hour | (b) non-alarmed | 49,368 | 788 | 0.016 [0.011, 0.022] |
| hour | (a) − (b) | | | 0.282 [0.205, 0.367] |
| region | (a) alarmed | 105 | 48 | 0.457 [0.370, 0.553] |
| region | (b) non-alarmed | 345 | 7 | 0.020 [0.006, 0.037] |
| region | (a) − (b) | | | 0.437 [0.349, 0.532] |

## 2026-09-23 — Read-only checks on the finished test results (requested by: user; descriptive; no fitting; FINAL result unchanged)
Test 2021/2023/2024, single-region, K2 SWPC. Gate = mean of the 5 frozen fold models (re-scored, no fitting). Cohort = `data/stage5/cohort_test_primary.csv` (313 episodes). Onset = episode_onset (T1 first alarm hour); the label time t (T4) is ≥ onset. `diag_testchecks.py`.

**1. Lead time** (first SWPC K2 M1+ from the HARP's NOAA region(s) with start > onset; no upper bound; catalogue to 2025-01-01 22:18). `data/stage5/lead_time_test_primary.csv`.
- Episodes: 313 = 45 true + 26 delayed + 242 other false.
- 139 had an M1+ from their region after onset (true 45, delayed 26, other false 68). 174 never did (all "other false").
- Lead (h), n = 139: median 45.1, Q1 16.6, Q3 82.0, min 1.7, max 167.4. Within 24 h: 33.8%; 48 h: 51.8%; 72 h: 67.6%.
- Median by group: true 12.4, delayed 37.4, other false 83.2.

**2. Time-linked region metric** (105 alarmed regions of 450). `data/stage5/region_timelinked_test_primary.csv`.
- Existing definition (≥ 1 labelled hour of the region positive): **48/105**.
- Time-linked (an M1+ starts within 24 h after ≥ 1 **alarmed** hour): **39/105**.
- Difference: 9 regions whose positive hours all lie **outside** their alarmed hours. The flare followed a non-alarmed labelled hour, not an alarm.

**3. Label spot-check, 15 false episodes** (random, seed 0; all M1+ on the whole disk in (onset, onset+24h]; region positions = FWT centres of the SHARP containing each region within ±1 h; great-circle distance to the alarmed HARP). `data/stage5/false_alarm_spotcheck.csv`.
- 8 episodes had no M1+ on the disk in the window. 7 episodes had 17 M1+ flares in total, none from the episode's own region.
- 15 flares were from other numbered regions at **35.9–99.3°** from the HARP (none < 15°).
- 2 flares had no SWPC region (2024-08-05 09:49 M1.7 and 17:56 M1.0, around HARP 11640), so their position is unknown.
- **Possible mislabels (< 15°): 0.** The 2 unregioned flares cannot be assessed.

**4. Hourly base rate** (all scorable single-region test rows, alarmed + non-alarmed): **1,976 / 53,356 = 3.70%**. By year: 2021 194/10,920 = 1.78%; 2023 843/21,631 = 3.90%; 2024 939/20,805 = 4.51%.

## 2026-09-23 — Persistence baseline vs frozen gate, test 2021/2023/2024 (requested by: user; descriptive; no fitting; FINAL result unchanged)
- **P** = 1 if an M1+ (K2 SWPC) from the same NOAA region(s) started in (t−24h, t]. Same rows as Stage 5: scorable single-region test rows, n = 53,356; 0 rows have history_incomplete.
- Gate = mean of the 5 frozen fold models, threshold −0.992496. It reproduces Stage 5 (asserted).
- Region level = Stage 5 definition (450 HARPs; alarm if any alarm hour, positive if any positive hour). CI = HARP bootstrap, 1,000, seed 20260921.
- `diag_persistence.py` → `data/stage5/persistence_vs_gate.csv`.

| predictor | level | TP | FP | FN | TN | TSS [95% CI] | TPR | FPR | precision | FAR |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| gate | hour | 1,188 | 2,800 | 788 | 48,580 | 0.5467 [0.4120, 0.6598] | 0.6012 | 0.0545 | 0.2979 | 0.7021 |
| P | hour | 751 | 1,154 | 1,225 | 50,226 | 0.3576 [0.2435, 0.4613] | 0.3801 | 0.0225 | 0.3942 | 0.6058 |
| gate | region | 48 | 57 | 7 | 338 | 0.7284 [0.6301, 0.8198] | 0.8727 | 0.1443 | 0.4571 | 0.5429 |
| P | region | 51 | 7 | 4 | 388 | 0.9096 [0.8337, 0.9740] | 0.9273 | 0.0177 | 0.8793 | 0.1207 |

- **Gate on hours with P = 0** (n = 51,451; 1,225 positive): TPR 0.4816, precision 0.2081 (TP 590, FP 2,245, FN 635, TN 47,981).
- For reference, on P = 1 hours (n = 1,905): TPR 0.7963, precision 0.5186.
- **Definition note:** the Stage 5 region unit is not time-linked. A region with any M1+ from its own region during the period has positive hours (before the flare) and P = 1 hours (after it), so region-level P is positive by construction for such regions.

## 2026-09-23 — DESCRIPTIVE OPERATING POINT (Deshmukh-style; requested by: user) — NOT a pre-registered test
- Read-only, no refit. The FINAL primary result is unchanged.
- **Naming:** the request called "B" gate + history and "A" B + trends. In this project (frozen spec, Stages 4–5) **A = gate score + n_C + n_M + n_X** and **B = A + 24-h relative slopes of USFLUX and TOTUSJH**. Results are labelled by content with the project letters.
- **Rule (decided by: me, before computing):** for each model, τ = the largest dev threshold such that the weighted fraction of TRUE dev episodes with out-of-fold probability ≥ τ is ≥ 0.88.
  - Dev data: `data/stage4/oof_cohort_dev.csv`, 547 episodes, weights 1/n per HARP as in Stage 4.
  - τ is applied unchanged to the frozen test probabilities (`data/stage5/cohort_test_primary.csv`: p_A, p_B = mean of the 5 frozen fold models; primary 2021/2023/2024, single-region, T2 cohort, 313 episodes).
- **Reported (weighted as in Stage 4/5, plus unweighted counts):** % true kept, % false removed, precision before (all episodes) and after (kept episodes). CIs: HARP bootstrap, 10,000 resamples, seed 20260921 (the Stage 5 model scheme). Gate-only baseline = all 313 kept.

### Descriptive operating point — RESULTS (NOT a pre-registered test; numbers only; recorded by: me)
`diag_operating_point.py` → `data/stage5/operating_point_descriptive.csv`. Test = 313 episodes (45 true, 268 false), primary 2021/2023/2024, single-region, T2. Percentages are weighted (1/n per HARP); counts are unweighted. CI = HARP bootstrap, 10,000, seed 20260921.

| model | dev τ (weighted dev true kept) | test kept | true kept (count; weighted % [CI]) | false removed (count; weighted % [CI]) | precision before [CI] | precision after [CI] |
|---|---|---:|---|---|---|---|
| gate only (all kept) | — | 313 | 45/45; 100% | 0/268; 0% | 0.148 [0.094, 0.206] | 0.148 [0.094, 0.206] |
| gate + history (A) | 0.0750 (0.888) | 274 | 45/45; 100.0% [100.0, 100.0] | 39/268; 20.3% [13.1, 28.1] | 0.148 [0.094, 0.206] | 0.179 [0.116, 0.247] |
| A + trends (B) | 0.0701 (0.882) | 198 | 42/45; 95.9% [90.0, 100.0] | 112/268; 41.1% [33.0, 49.2] | 0.148 [0.094, 0.206] | 0.220 [0.143, 0.303] |

## 2026-09-23 — EXPLORATORY DIAGNOSTIC "R-split" — design recorded BEFORE running (requested by: user)
Dev years only. It does **not** touch the 2021–2024 test set, frozen files or FINAL results. Refits are diagnostic only.
**Prediction by Claude chat (verbatim, recorded before running):** "R-D FAR ≈ 0.9; TSS in both variants higher than the chronological test TSS 0.547."

- **Data:** labelled rows 2010-05 → 2017-12 from `data/labelled_20100501_20250101.csv` (all of them dev HARPs). Same filters as the gate (QUALITY == 0, |LON_FWT| ≤ 45°, single-region primary subset), K2 SWPC labels.
- **Model:** the frozen gate specification, refit per split. The same 10 features; SVM RBF C = 4, γ = 0.075, tol 1e-8, class weight positive:negative = 2:1; median/SD scaling on the training rows; training rows = train-HARP rows at TAI hours {4, 10, 16, 22}.
- **Split:** HARPs randomly assigned 70% train / 10% validation / 20% test; seeds 100, 200, …, 1000. All rows of a HARP are in one set.
- **Threshold:** max TSS on the validation set, applied to the test set.
- **Variants:**
  - **R-D:** label = M1+ flare start in (t, t+12h]; evaluated on rows at TAI hours 0, 3, 6, …, 21.
  - **R-24:** label = `flared_M1_next_24h` (as in the main study); evaluated on all hourly rows.
- Reported per seed and as mean/min/max: P, N, TP, FP, FN, TN, base rate, TPR, FPR, TSS, precision, FAR = FP/(TP+FP), accuracy, and the accuracy of "always no flare".
- Comparators:
  - Deshmukh et al. 2022 Table 6 CNN-only means, **as supplied by Claude chat (not verified here)**: FAR 0.894, accuracy 0.934, TPR 0.742, FPR 0.064, TSS 0.678, base rate 0.010.
  - Our chronological Stage 5 hour-level result: FAR 0.702, accuracy 0.933, TPR 0.601, FPR 0.055, TSS 0.547, base rate 0.037.

Implementation details (decided by: me, before running):
- **HARP assignment:** HARPs with ≥ 1 primary-subset row in 2010-05 → 2017-12, sorted by number, permuted by `RandomState(seed)`. The first 70% (rounded down) are train, the next 10% validation, the rest test. Not stratified (random, as specified).
- **R-D label:** computed from the SWPC K2 M1+ list with the same region join (ANY over NOAA_ARS) as the main labels. Rows are already restricted to label windows free of missing days.
- **Training labels:** each variant is trained with its own label, so R-D and R-24 are separate fits.
- **Validation threshold:** chosen on the validation rows at the variant's evaluation spacing (3-hourly for R-D, hourly for R-24).
- **Unscorable rows** (any gate feature missing) are excluded, as in Stage 2.
- Precision and FAR are undefined if TP + FP = 0; that is reported.

### EXPLORATORY DIAGNOSTIC "R-split" — RESULTS (numbers only; recorded by: me)
`diag_rsplit.py` → `data/diag/rsplit_per_seed.csv`, `rsplit_summary.csv`, `data/diag/rsplit.log`.
- Data: 109,362 scorable single-region rows, 927 HARPs, 2010-05 → 2017-12. Positive rows: 24 h 3,168; 12 h 2,009.
- 20 fits (2 variants × 10 seeds). Per seed: ~14,000 training rows and 187 test HARPs. Validation positives: R-D 10–105, R-24 63–541.

**Mean [min, max] over 10 seeds (test set of each split)**

| metric | R-D (12 h, 3-hourly rows) | R-24 (24 h, hourly rows) | Deshmukh 2022 Table 6 CNN-only mean (as supplied, not verified) | our chronological Stage 5, hour level |
|---|---|---|---|---|
| P | 119.7 [65, 166] | 680.1 [357, 961] | — | 1,976 |
| N | 5,866.2 [5,591, 6,036] | 21,154.7 [20,104, 21,787] | — | 51,380 |
| TP / FP / FN / TN (mean) | 78.2 / 201.5 / 41.5 / 5,664.7 | 482.2 / 1,049.9 / 197.9 / 20,104.8 | — | 1,188 / 2,800 / 788 / 48,580 |
| base rate | 0.0200 [0.0111, 0.0281] | 0.0312 [0.0167, 0.0446] | 0.010 | 0.037 |
| TPR | 0.634 [0.494, 0.836] | 0.687 [0.511, 0.852] | 0.742 | 0.601 |
| FPR | 0.035 [0.005, 0.108] | 0.050 [0.021, 0.098] | 0.064 | 0.055 |
| TSS | 0.600 [0.486, 0.794] | 0.637 [0.490, 0.795] | 0.678 | 0.547 |
| precision | 0.337 [0.140, 0.532] | 0.319 [0.199, 0.408] | — | 0.298 |
| FAR | 0.663 [0.468, 0.860] | 0.681 [0.592, 0.801] | 0.894 | 0.702 |
| accuracy | 0.959 [0.884, 0.990] | 0.943 [0.897, 0.969] | 0.934 | 0.933 |
| accuracy "always no flare" | 0.980 [0.972, 0.989] | 0.969 [0.955, 0.983] | — | 0.963 |

**Against the recorded prediction** ("R-D FAR ≈ 0.9; TSS in both variants higher than the chronological test TSS 0.547"):
- R-D mean FAR 0.663; 1 of 10 seeds has FAR ≥ 0.85 (seed 500, 0.860).
- Mean TSS: R-D 0.600, R-24 0.637. Seeds with TSS ≤ 0.547: R-D 4 of 10, R-24 2 of 10.

## 2026-09-23 — AMENDMENT: FULL EUV STUDY, 94 Å ONLY (decided by: user) — recorded BEFORE any full-study download
- **Reason 1:** the validity audit (4c25475) showed flare-in-progress exclusion removed true alarms preferentially (cutouts, 12 min, ≥ 90%: 4/7 true vs 3/3 false kept).
- **Reason 2 (channels):** time constraint (IRIS deadline). **AIA 94 Å ONLY.** The previously planned secondary channels 1600 Å and 131 Å are **DROPPED before any results** (future work). Basis for 94 Å: BADPIT (André-Hoffmann et al., arXiv:2604.26036) — 94 Å most suitable for brightenings in the PIL area; Leka et al. (arXiv:2212.11255) — 94 Å gives the most discriminating parameters.
- **Disclosure:**
  - (a) ΔCV of the 3 pilot HARPs (roles known) was seen before this amendment; n = 3, not used to choose.
  - (b) No ΔCV-by-label has been computed or seen for the 15 test alarms.
  - (c) The flare-frame change was prompted by label-split ELIGIBILITY COUNTS only.
- **Versions:**
  - **PRIMARY:** ΔCV_94 with flare-in-progress frames NOT excluded. Frames are still removed by the existing exposure rule, QUALITY rule and saturation rule P4/U4 (unchanged). Frames removed per rule are reported per version.
  - **SENSITIVITY:** the previously specified flare-excluded ΔCV_94.
  - Both are reported regardless of outcome.
- **Scheduling change:** ΔCV is computed per HARP as soon as its data are downloaded and verified (same calculation, different timing).
- **Plan (user):** step 2 dry run on the 3 pilot HARPs (must pass) → step 3 full download + compute (547 dev episodes) → step 4 count-first fill threshold (counts only) → **STOP**. Step 6 analysis only after the user's go-ahead. No ΔCV summary by label is output before then. The magnetic-trend test and the 2021–2024 test set are not reopened.

**Unchanged rules, quoted verbatim:**
- Exposure (2026-09-23, Phase 1 rule 1): "**Rule: drop frames with EXPTIME < 50% of that channel's median in the window.**"
- QUALITY (2026-09-22): "Default: **frames with QUALITY != 0 are excluded**, counted separately (`excl_quality`)." Approved: "exclusion of frames with QUALITY != 0".
- Saturation U4: "**do not interpolate**: exclude pixels > 12,000 DN, and flag the frame if any pixel in the HARP box exceeds 12,000 DN".
- Saturation P4: "`aia.lev1_euv_12s` / `aia.lev1_uv_24s` exported as cutouts, registered to level 1.5 with `aiapy`, exposure-normalised (DN/s); pixels > 12,000 DN excluded and the frame flagged (U4)." Clarification: "the **12,000 DN saturation cut applies to raw DN, before exposure normalisation.**"
- **Note (me):** P4/U4 removes **pixels**, not frames; a frame containing them is *flagged*, not removed. "Frames removed by the saturation rule" is therefore reported as frames flagged (and pixels excluded), per version.

**Implementation details (decided by: me, before any download):**
- **Episodes:** `data/stage3/cohort_dev.csv` (547 episodes, 180 HARPs; the frozen dev cohort). Stage 4 folds from `data/stage4/oof_cohort_dev.csv` for step 6.
- **HMI masks:** `hmi.sharp_720s` magnetogram + bitmap at each episode's T_REC. Source per step 2a (direct access if it passes, else normal export).
- **One export per HARP:**
  - Record set `aia.lev1_euv_12s[(earliest t) − 24h + 12m – (latest t) @12m][94]{image}`, which covers all its windows, including any gaps between them.
  - im_patch t_ref = the HARP's latest episode t; centre = the patch centre in that episode's magnetogram; width/height = the maximum patch extent over the HARP's episodes + 2 × 50″; tracked; same other settings as the pilot.
  - For single-episode HARPs this is exactly the pilot item-2 specification.
  - `url-tar`; the next export is submitted once the previous one completes (during the tar download); one pending export at a time; the user's account only.
- **Frames per episode:** the HARP's frames with T_OBS in (t − 24h, t]. **Coverage check:** per episode, the fraction of HMI patch pixels that map outside the cutout is logged; episodes with any pixel outside on any valid frame are flagged.
- **ΔCV:** D-CTRL exactly as in the combined test (`euv_dctrl.samples / hmi_to_frame / frame_means / summarise`; pointing update and cutout registration as approved), over all valid frames in the window. Primary: valid = QUALITY == 0 and the exposure rule. Sensitivity: additionally not in progress per P2 (amended).
- **Fill (step 4):** 120 slots t − 24h + k·12 min; a slot is filled if a valid frame (per version) lies within ± 6 min. Candidates 90 / 80 / 70%; unweighted episode counts.
- **Workers:** 8 processes (10 cores − 2). Resumable: FITS files checked by size and header; failed exports retried 3× with backoff, then logged and skipped.
- **Outputs:** `data/euv_full/` only (`dryrun/`, `hmi/`, `aia/<HARP>/`, `series/`, `results/`, `logs/`). Per-episode results are stored without label summaries.

### Step 2a — HMI direct-access benchmark: RESULT and mask-source decision (recorded by: me)
`euv_full.py hmi_check` → `data/euv_full/dryrun/hmi_direct_check.csv`. 3 pilot records via `url_quick` / `as-is`, with headers rebuilt from a keyword query.
- **The user's PASS rule is met:** pixel arrays identical (shape, NaN pattern, max \|diff\| = 0 on finite pixels), bitmaps identical, PIL and AR masks 0 differing pixels, D-CTRL samples identical.
- Time per record: direct 9.3–11.7 s vs logged export 18.4–87.1 s.
- **Extra check (me): WCS not reproducible.** JSOC keyword interfaces (`jsoc_info` rs_list, `show_info`) return keywords at display precision, e.g. CDELT1 0.504362 vs exported 0.504361629, CRPIX1 22.440430 vs 22.4404297. The rebuilt WCS changes the HMI→AIA pixel mapping for 0.009–0.043% of mapped pixels (6 sampled frames per pilot HARP), so ΔCV from direct-access masks cannot equal the exported-mask ΔCV to 1e-6 (the step 2b rule).
- **Decision (me): masks via normal JSOC exports (the user's FAIL branch)** for all episodes, one export per HARP (magnetogram + bitmap at all its episode T_RECs), url-tar. This keeps the full run exactly reproducible; the cost is extra export time. Flagged for the user.
- **Saturation flag (implementation, me):** a frame is flagged if any raw pixel > 12,000 DN lies anywhere in the cutout (HARP box + 50″ margin). Saturated pixels are excluded as before. The pixel cut is unchanged; the flag area includes the margin.

### Addition before the full run: per-HARP HMI export test (decided by: user; recorded before running)
- **Test:** for HMI mask exports (normal export path), ONE export per HARP covering all of that HARP's alarm times, `hmi.sharp_720s[HARP][t1,t2,…]{magnetogram,bitmap}`.
- **Verification:** on the 3 pilot HARPs, the files must be byte-identical in data and header to per-alarm exports, or produce identical PIL/AR masks and identical ΔCV (\|diff\| < 1e-6).
- **Rule:** if it passes, per-HARP HMI exports for the full run; if JSOC rejects it or anything differs, keep per-alarm exports. One pending export at a time.
- **Implementation (me):**
  - The 3 pilot HARPs have 16 dev alarm times: 3248 × 3, 4231 × 4, 6975 × 9.
  - 3 per-HARP exports vs 16 per-alarm exports, all `url-tar`, into `data/euv_full/hmi_test/`.
  - Comparison per file: the data arrays (bytes, including NaN pattern and dtype) and every header card. Cards that can legitimately differ between two export requests of the same record (e.g. an export timestamp) are listed rather than hidden.
  - Byte-identical data + header = PASS. Otherwise the fallback criterion applies: PIL/AR masks and D-CTRL samples identical; ΔCV checked on the 3 pilot episodes with AIA data.
  - Runs after the step 2b dry run (one pending export at a time).

### Step 2b — dry run: PASS (recorded by: me)
`euv_full.py dryrun` → `data/euv_full/dryrun/` (fresh url-tar exports; the pilot files were not reused).
- **Checks:** flare-excluded ΔCV_94 vs the pilot values after the exposure rule: 3248 0.134345 (\|diff\| 5.6e-17); 4231 −0.117111 (2.8e-17); 6975 0.147909 (8.3e-17), all < 1e-6. Single-process = 8-worker results for both versions (exact equality). Frames 120 / 120 / 118 (as in the pilot).
- **Exports:** HMI prep 62–84 s; AIA prep 85–104 s, download 28–73 s; 0 failures. Pipeline wall time 631 s.

### Per-HARP HMI export test — RESULT: PASS by the fallback criterion → per-HARP HMI exports (recorded by: me)
`euv_full.py hmi_test` → `data/euv_full/hmi_test/hmi_per_harp_check.csv`, `timing.csv`. JSOC accepted `hmi.sharp_720s[HARP][t1,…,tn]` (3 exports; 3, 4 and 9 T_RECs).
- **Data arrays:** identical (bytes, dtype, shape) for all 16 records, magnetogram and bitmap.
- **Headers:** byte-identical for 3/16. The other 13 magnetograms differ in exactly two cards:
  - `POLICY` (JSOC's data-use attribution text): blank in the multi-T_REC export, filled in the per-alarm export.
  - `HEADSUM` ("Keyword checksum"), which changes with POLICY.
  - No WCS or data keyword differs. Bitmap headers are identical.
- **Fallback criterion:** PIL/AR masks 0 differing pixels and D-CTRL samples identical, 16/16. ΔCV on the 3 pilot episodes (dry-run AIA frames) with per-HARP vs per-alarm masks: \|diff\| = 0.0 in both versions → **PASS.**
- **Timing:** median prep per export 62.6 s (per HARP, 3–9 records) vs 63.5 s (per alarm, 1 record) → 180 HMI exports instead of 547 in the full run.
- **Decision (rule): per-HARP HMI exports for the full run.**

### Full run — data-availability note (recorded by: me, during the run)
HARP 8 (1 episode, t = 2010-05-04 20:59 UTC): the AIA export failed 3× with JSOC status 4. A keyword query shows `aia.lev1_euv_12s` 94 Å has **no records before 2010-05-13**; the first record is 2010-05-13T00:00:02Z. It is the only dev episode with t < 2010-05-14, so the episode has no AIA data and is listed as missing ("no AIA data"). This is not a pipeline fault.

### Full run, pass 1 — completion and fixes before the resume pass (recorded by: me)
- **Pass 1** (2026-09-23 17:01 → 2026-09-24 05:52, 12.8 h): 180 HMI + 178 AIA exports; 53,852 of 54,165 expected frames; 14.5 GB. Episode results: 535 of 547.
- **12 without a result:**
  - HARP 8, no AIA data before 2010-05-13 (1).
  - HARP 2037, pointing-table query timeout (1).
  - HARP 4610, HMI files present but named by record number (`hmi.sharp_720s.4519292.*`), so the file-finder missed them (1). Headers verified: HARPNUM 4610, T_REC 2014.09.29_16:00.
  - 9 episodes (HARPs 4424, 4900, 4921, 5026, 5298, 5739, 7075): `aiapy.update_pointing` raised TypeError because 10 frames lack `SAT_ROT`. **All 10 have QUALITY = 4** and are excluded by the QUALITY rule anyway.
- **Fixes (implementation, me):**
  - The HMI file-finder falls back to matching the header T_REC.
  - A missing `SAT_ROT` keeps the header pointing, as for a missing pointing-table entry; counted per episode (`frames_no_satrot`, `frames_no_satrot_q_ok`).
  - Neither fix can change any of the 535 existing results: those episodes contain no such frames, and their HMI files were found.
- **4 HARPs below 97% of expected frames:** 2635 and 2636 (513/530), 3258 (344/360), 6206 (698/795). Their episodes were computed. The resume pass re-exports them once to confirm the gaps are in the archive.
- **Resume pass:** `euv_full.py run` again (downloads and existing results skipped).

### Full run — resume pass and STEP 4 COUNT-FIRST THRESHOLD (counts only; no ΔCV read or reported; recorded by: me)
**Resume pass** (05:54 → 06:16): 11 missing episodes computed → **546 of 547 episodes have results.**
- Missing: **HARP 8** (1 episode, 2010-05-04), with no `aia.lev1_euv_12s` data before 2010-05-13; JSOC status 4 again, 3×.
- The 4 short HARPs re-exported under the same JSOC request IDs with the same counts, so their gaps are in the archive: 2635 and 2636 513/530, 3258 344/360, 6206 698/795. HARP 4610 AIA 120/120.
- **Totals:** 180 HMI exports + 183 AIA exports (179 HARPs; 4 repeats); 14.5 GB; pass 1 wall time 12.8 h + resume 0.4 h.

**Frames** (546 episodes, 65,253 frames in their (t−24h, t] windows):
- QUALITY ≠ 0: 1,440.
- Exposure rule: 661.
- Flare-in-progress: 2,180, removed in the SENSITIVITY version only.
- Saturation-flagged frames (pixels > 12,000 DN excluded, frame kept): 321.
- Frames without `SAT_ROT`: 12, all QUALITY = 4.

**Coverage flag:** 26 episodes (14 HARPs) have HMI patch pixels mapping outside the cutout on ≥ 1 valid frame. Maximum fraction outside: median 0.69%, maximum 5.8%; > 1% in 10 episodes, > 10% in none.

**Valid episodes (fill ≥ threshold; unweighted; the denominator includes HARP 8's episode as not valid)**

| threshold | version | valid / 547 | true valid / 98 | false valid / 449 | frac true | frac false | gap (pp) |
|---|---|---:|---:|---:|---:|---:|---:|
| 90% | primary | 530 | 94 | 436 | 0.9592 | 0.9710 | 1.19 |
| 90% | sensitivity | 445 | 63 | 382 | 0.6429 | 0.8508 | **20.79** |
| 80% | primary | 541 | 96 | 445 | 0.9796 | 0.9911 | 1.15 |
| 80% | sensitivity | 528 | 89 | 439 | 0.9082 | 0.9777 | 6.96 |
| 70% | primary | 546 | 97 | 449 | 0.9898 | 1.0000 | 1.02 |
| 70% | sensitivity | 542 | 95 | 447 | 0.9694 | 0.9955 | 2.62 |

**Rule** (highest threshold with gap ≤ 10 pp in BOTH versions): 90% fails (sensitivity 20.79 pp); 80% passes (1.15 and 6.96 pp) → **fill threshold = 80%.**
**Failed / missing HARPs:** HARP 8 only (no AIA data). **STOPPED — awaiting the user's go-ahead for step 6. No ΔCV summary by label has been computed or output.**

## 2026-09-24 — DOCUMENTATION ENTRY: frame-rule check, literature review, design justification, open proposals, Q&A  (recorded by: Claude chat, on user request; documentation only)
**Scope:** no rule, frozen file, result or code was changed. No ΔCV value was read, computed or reported, and nothing was split by label. The only new number (item 1c) is a frame count from `data/euv_full/series/*.csv` (columns `exp_ok`, `flare`, `q_ok`), read-only.
**Sources:** literature quotes were checked in the PDF text on 2026-09-24 unless marked otherwise. Items marked *(2026-09-23 read)* come from Claude chat's PDF reads on 2026-09-23 (project status doc), and were not re-checked today.

### 1. Frame rules: code vs recorded rules (read in `euv_full.py` `compute_episode`, `euv_pilot.py` `flare_excluded`)
**a. How each rule is applied, per frame:**
- **QUALITY:** `q_ok = quality == 0`.
- **Exposure:** the median EXPTIME is taken over QUALITY == 0 frames in the episode's (t−24h, t] window. `exp_ok = exptime >= 0.5 × median`.
- **P2 amended (flare in progress):** the frame's T_OBS falls inside the begin–end interval of either:
  - (a) a C1+ SWPC event (K2) with `noaa_ar` in the HARP's NOAA region(s), or
  - (b) any M1+ event.
  - Events are loaded for [t − 2 d, t].
- **Saturation (P4/U4):** `raw > 12,000 DN` → those pixels are set to NaN before exposure normalisation. The frame is kept, with `sat_flag = True` and the count stored in `sat_px`.
- **Versions:**
  - `valid_primary = q_ok & exp_ok & box.notna()`
  - `valid_sens = valid_primary & ~flare`

**b. Conclusion:** the code matches the recorded rules. Check B of the proposed go-ahead (saturation wording) is already answered by two existing entries:
- the amendment's "Note (me)": P4/U4 removes pixels, not frames;
- step 2a: the flag area includes the 50″ margin.

The only inaccuracy is the phrase "Frames are still removed by … saturation rule P4/U4" in the amendment's PRIMARY bullet. Pixels are removed there; frames are only flagged.

**c. NEW descriptive count: exposure rule vs flare intervals** (546 episodes, 65,253 frames):

| exposure-rule frames | count |
|---|---:|
| total | 661 |
| of which also QUALITY ≠ 0 | 544 |
| of which QUALITY == 0 | 117 |
| inside a P2 flare interval, any QUALITY | 86 |
| inside a P2 flare interval, QUALITY == 0 | 68 |

- The exposure rule removes only 68 QUALITY-good flare-interval frames from the PRIMARY version. For scale, 2,180 frames lie in P2 flare intervals (any QUALITY).
- Background: AIA's Automatic Exposure Control (AEC) shortens exposures during flares. Dissauer et al. 2023 show an example of 2 s → 0.43 s at 193 Å.

### 2. How other studies handle flares inside the analysis window
| study | what they do with flare-contaminated data | sample |
|---|---|---|
| Dissauer, Leka & Wagner 2023, ApJ 942:83 (AARP I) | Flare times **included**; AEC (short-exposure) images **avoided** (72-s sampling): "Avoiding the AEC images allows for times of flares to be included with less dramatic impact to the moment analysis." | 2010-06 → 2018-12, all HARPs |
| Leka, Dissauer, Barnes & Wagner, arXiv:2212.11255 (AARP II) | Flares **not removed**: "Flares occur during the data acquisition … but rarely do their influence persist more than 2 – 3 hr … the linear fits generally all but ignore them." "Perfect storm" outliers "typically occur no more than 0.1% of the time." | same |
| André-Hoffmann et al. 2026, Solar Physics (BADPIT) | Flares **kept**: TBs "include potential subflaring events but also up to C- and M-class flares and does not distinguish them." Pixels > 12,000 DN "replaced by values derived via linear interpolation in time." | 2 ARs, 24 h |
| Jonas et al. 2018 (arXiv:1708.01323) | "we discard data during the flash phase of the flare." Flare history: "prior flaring activity has significant predictive capacity in and of itself." | 4,272 flares ≥ C1.0 (3,836 C, 406 M, 30 X) |
| Kniezewski, Mason, Uritsky & Garland 2024, ApJL 977:L29 (Sec 2.1) | Whole events **selected**: "discounted if a flare of magnitude C5.0 or greater occurred in the same active region within 6 hr." Flares < C5 were allowed inside the window. Quiet cases: ≥ 12 hr with no ≥ C flare, and a 6-hr window with ≥ 3-hr buffers. | 53 flares vs 30 quiet windows |
| Kniezewski, Mason, Emmons, Fitch & Garland, arXiv:2506.14004 (submitted to ApJ; checked on the arXiv HTML page only) | Flares removed if a ≥ C5.0 flare occurred in the same AR within 6 h; quiet = no ≥ C5.0 for 7 h. NLFFF magnetic variability. | 18 flares (6 C/6 M/6 X) |
| Dissauer, Barnes, Leka & Wagner 2025, arXiv:2503.12338 (Sec 2) | Active epoch = pre-flare period "during which no other flaring events above the C1.0 level occur". Activity below C1 is analysed. 2-h windows end 4 min before the GOES start. Flare list = SWPC warehouse. | 3 events |
| Zhong, Kolotkov & Nakariakov, arXiv:2602.18133 (Sec 2.1) | "There should be no other flares at least 3 hours earlier than the start time of the candidates." No class or region threshold stated. | 14 flares in 13 ARs + 1 quiet AR |

**Where this project sits:**
- **PRIMARY** version = the AARP approach: flare frames kept, short-exposure frames removed.
- **SENSITIVITY** version = frame-level removal of flare intervals (the Jonas idea).
- **Model A** already contains flare history (n_C, n_M, n_X, 48 h).

Event-selection designs (Kniezewski, Dissauer 2025, Zhong) are not usable for an alarm-time forecast. They drop regions that flared recently, and here they would drop true alarms preferentially (validity audit 4c25475; step 4 table: the 90% sensitivity rule kept 64% of true vs 85% of false).

### 3. Design choices vs published work (justification)
| choice | this project | published basis |
|---|---|---|
| Question: true vs false among magnetically flagged regions | Alarm vs alarm (both "dangerous") | Alatoom & Nikolaou 2026, Space Weather (10.1029/2026SW005010): the most common FPs "are magnetically complex, historically productive regions … physical readiness does not necessarily translate into imminent eruption." Kniezewski 2024 matched quiet ARs by complexity so results "were not skewed by inherent differences between the types of active regions." |
| Second stage to cut a magnetic model's false alarms | EUV at the PIL, tested as added information over the gate + flare history | Deshmukh, Flyer, van der Sande & Berger (arXiv:2111.10704; published in ApJS as "Decreasing False-alarm Rates in CNN-based Solar Flare Prediction Using SDO/HMI Data"): magnetic-only second stage; "reduces false positives by ≈ 48% without significantly affecting the true positives (reduction by ≈ 12%)". |
| Flare labels | SWPC originals, K2 (÷0.7 for GOES-13/14/15) | Hu et al. 2026, arXiv:2512.13417 (entry 2026-09-22). Dissauer 2025 also uses the SWPC warehouse. |
| Split | Dev 2010–2019, grouped CV; test 2021/2023/2024 | Francisco, Guastavino, Fernandes, Barata & Del Moro, arXiv:2410.16116 (journal version not verified): "5-fold CV done on the period ranging from May 2010 to December 2019", test Jan 2020 → Apr 2023 *(arXiv HTML)*. Chen et al. 2024 review and Wang et al. 2020: results depend on split and years *(2026-09-23 read)*. |
| Magnetic gate | Bobra & Couvidat 2015-style SVM, 10 SHARP features | Bobra & Couvidat 2015, ApJ 798:135 (reproduction entries 2026-09-21/22). |
| Channel | AIA 94 Å only | Leka 2023: "The 94 Å filter data provides the most parameters with discriminating power." BADPIT: "The 94 Å channel proved to be the most suitable channel for the tracking." Francisco 2024: "The 94Å wavelength provides the most discriminative features for flare prediction." |
| Location | PIL mask ±150 G, 16-px dilation, 30 G AR mask | BADPIT PIA (after Schrijver 2007): identical. Dissauer 2025: TBs cluster near strong-gradient PILs before flares *(2026-09-23 read)*. |
| Window | (t − 24 h, t] | BADPIT: 24 h. AARP: hourly bursts over ~6 h. Kniezewski: 6 h. Dissauer 2025: 2 h. Zhong: ≥ 2 h. |
| Cadence | 12 min (12 vs 2 min: ρ 0.952, n = 8; commit 9a56c68) | Physics studies: 12 s (Zhong, Harra 2026, BADPIT), 72 s (AARP), 3 min (Kniezewski). Forecasting: 12 min (Jonas 2018), 6 min (SDOML), 1 h (Nishizuka), 2 h (Francisco 2024). |
| Metric | CV of the detrended PIL-mean series minus the mean CV of 20 matched in-image controls | Closest: Kniezewski 2024 (SD ratios of integrated emission). Harra 2026 (temporal SD maps; 2 flares). See risk 4a. |
| Saturation | Pixels > 12,000 raw DN removed, not interpolated | BADPIT uses the same 12,000 DN threshold (following Schwartz et al. 2015) but interpolates. |
| Baseline includes flare history | Model A = gate + n_C, n_M, n_X | Jonas 2018 (quote above). Camporeale & Berger 2025, Space Weather (10.1029/2025SW004546): persistence TSS 0.46; SWPC does not outperform the baselines *(2026-09-23 read of the arXiv version)*. |
| Metrics reported | log-loss, AUC, TSS, FAR, precision | Leka 2023: "no single metric provides a thorough evaluation of performance." Camporeale & Berger warn about high TSS reported alongside very high FAR *(2026-09-23 read)*. |

### 4. Known risks and limitations (stated before step 6)
- **a. Metric type.**
  - Leka 2023: "enhanced variability in EUV and UV intensity on short timescales and small spatial scales is one of the strongest discriminators", "spatial resolution matters", and "surprisingly poor is the mean intensity and its longer-term trending."
  - ΔCV is the variability of a PIL-averaged mean at 12 min, so it may miss that signal. A null result is a possible and reportable outcome.
- **b. Timing.**
  - The window ends at alarm time t, but the flare can occur up to 24 h later.
  - Kniezewski 2024: variability "increases from 4 hr before flare onset, peaking in the 1–2 hr before onset."
  - Test-years lead time from episode onset (entry 2026-09-23 "Read-only checks"): median 12.4 h for true episodes. Precursors close to the flare can therefore fall after the window.
  - Rationale for the design: an operational forecaster must decide at alarm time.
- **c. Cadence (inference, Claude chat).** 12-min sampling has a Nyquist frequency of 0.69 mHz, below Zhong's 0.9–10 mHz band. Faster variability can alias.
- **d. Residual flare emission.**
  - The SWPC end time is not the end of 94 Å emission, and Leka 2023 says flare influence lasts up to 2–3 hr.
  - So the SENSITIVITY version (begin–end removal) can still contain post-flare emission (inference).
- **e. Coverage.** 26 episodes (14 HARPs) have HMI patch pixels outside the cutout; the maximum fraction is 5.8%.
- **f. Sample.** Dev n = 98 true / 449 false (unweighted episodes); EUV is dev-only until a held-out EUV test is run.

### 5. Open proposals — NOT decided (user decision needed before step 6)
Proposed by Claude chat on 2026-09-24. Status: **not sent to Claude Code, not recorded as decisions.**
- **A.** Fill threshold 80%. Already fixed by the pre-registered rule (ff3c11c); no decision needed.
- **B.** Saturation wording check. Answered in 1b; no action needed.
- **C.** Added sensitivity: repeat the primary test without the 26 overhang episodes.
- **D.** Pre-register (do not run yet) a held-out EUV test on 2021/2023/2024: single-region T2 cohort, 313 episodes; E94 = model A + ΔCV_94 (primary version); same pipeline and rules; weighted Δlog-loss (E94 − A); HARP bootstrap 10,000; AUC.
- **E.** Run step 6 exactly as in the amendment.
- **F. (new)** Added sensitivity: also exclude frames up to 2 h after each P2 event's end time. Report n valid per group at 80%.
- **G. (new)** Report the item-1c counts alongside step 6.

### 6. Questions and answers (plain language; numbers from the entries cited)
**Q: What is the project about?**
A standard magnetic model (the gate) raises alarms for regions that look dangerous. Most alarms are false. The question: among alarmed regions, does EUV brightness variability above the polarity inversion line (PIL) separate real alarms (M1+ within 24 h) from false ones, beyond what the magnetic score and recent flare history already tell us?

**Q: What is an alarm episode, and how many are there?**
- An episode is a run of consecutive alarm hours for a HARP (rules T1–T4; alarm time = first evaluable hour).
- Dev 2010–2019: 547 episodes in 180 HARPs, of which 98 true and 449 false.
- Test 2021/2023/2024: 313 episodes (45 true, 26 delayed, 242 other false); delayed episodes count as false.

**Q: How often is an alarm real?**
- At episode onset (test): 45/313 = 14.4% (14.8% region-weighted).
- Hour level (test): 1,188/3,988 = 29.8% (FAR 0.70).
- Region level: 48/105 = 45.7% (time-linked: 39/105).

**Q: Why not use accuracy?**
Positives are rare. Hourly base rate in test rows = 3.70%, so "always no" is ~96% accurate by hour and ~85% at episode onset. AUC 0.81 (model A) is a ranking measure, not accuracy.

**Q: Is the gate a strawman?**
On test hours the gate beats persistence (TSS 0.547 vs 0.358). Its FAR (0.70 by hour) is in the range of published baselines, e.g. Bloomfield et al. 2012: best TSS 0.52 with precision ≈ 13% *(2026-09-23 read)*. Region-level persistence looks better only by construction (definition note, entry 2026-09-23).

**Q: Did 24-h magnetic trends help?**
No. Δlog-loss(A − B) = −0.0051 [−0.0201, 0.0094]. AUC: A (no trends) 0.811, B (with trends) 0.797.

**Q: What were the "phantom" false alarms (Path A)?**
Alarms counted false with HEK labels but true with SWPC originals, because HEK loses region numbers (AR = 0). The defect is already published (Hu et al. 2026); Path A quantifies its effect on FAR (entry 2026-09-22). The ×0.7 scaling is not the cause: all 34 phantoms are GOES-16/18 flares.

**Q: Why these years?**
- 2020: excluded by the ≥ 90% region-join rule.
- 2022: sensitivity only.
- 2025–2026 confirmation set: paused.
- The chronological test (train on the past, test on later years) follows Francisco 2024 and avoids the optimism of random splits (ablation: random split ~+0.11 TSS vs region-grouped).

**Q: Why keep flare frames in the primary version?**
- Removing them dropped true alarms more than false ones (90% rule: 64% vs 85% kept).
- Keeping them, with short-exposure frames removed, is the AARP method.
- The sensitivity version removes them to check that the result is not just "a flare was already happening".

**Q: Why 94 Å, the PIL mask, 24 h and 12 min?**
See section 3.

**Q: How are the frame checks done?**
See section 1a: QUALITY keyword; exposure ≥ 50% of the window median; SWPC begin–end intervals; pixel saturation > 12,000 DN.

**Q: What do the step 4 numbers mean?**
- Each episode needs enough valid 12-min slots (120 in total).
- Rule chosen in advance: the strictest level where true and false alarms lose a similar share (≤ 10 pp) in both versions.
- 90% failed (sensitivity gap 20.8 pp); 80% passed (1.15 and 6.96 pp).

**Q: Can the method change after submitting?**
ISEF: no project changes after the affiliated fair. Extra data only with the same method and only if it is in the approved research plan. So all planned phases (including the held-out EUV test) must be written into the research plan.

### 7. Administrative facts recorded (checked 2026-09-23 on the official sites; re-check before relying on them)
**IRIS 2026–27** (iris.exstemplar.com):
- Registration/submission window: 1 Aug – 3 Oct 2026, "no extensions".
- One project guide required.
- Submit: synopsis (word limits per section), full research paper and a 90-s video.
- "Maintain a research data book."
- No school name, city or state in any material.
- Eligibility with OCI: to be confirmed with IRIS.

**ISEF 2027:**
- Forms 1, 1A (with research plan), 1B, 2A, and the abstract.
- Research plan, abstract, poster and citations to be written by the student; AI use cited.
- Experiments run before a signed plan must be discussed with the sponsor/SRC.

**Sources for this entry:** the PDFs in `output/` (literature, not in git) and arXiv/journal pages: 2212.11255, 2411.12704, 2506.14004, 2503.12338, 2602.18133, 2604.26036, 1708.01323, 2410.16116, 2111.10704, 2512.13417, 10.1029/2025SW004546, 10.1029/2026SW005010, 10.1007/s11207-026-02691-5.

## 2026-09-24 — STEP 6 GO-AHEAD: PRE-REGISTRATION (decided by: user; recorded BEFORE any ΔCV is split by label)
**Scope:** dev years 2010–2019 only (`data/stage3/cohort_dev.csv`, 547 episodes); internal cross-validation, not a held-out test. No downloads. Frozen files and the FINAL Stage 5 result unchanged. This go-ahead replaces the step 6 outline in the amendment above (2026-09-23) where the two differ (twins: gate score only with the frozen Stage 4 caliper, instead of gate score + log USFLUX with caliper 0.2 pooled SD and one episode per HARP; twins bootstrap 10,000 with seed 20260921 instead of 2,000 with seed 0).

**User's items, verbatim:**
- a. "Fill threshold 80% (already fixed by the rule, ff3c11c). Each version uses its own valid episodes; A and E94 are always fitted on the SAME episodes."
- b. "PRIMARY (dev, cross-validated): model A = gate score + n_C, n_M, n_X; model E94 = A + ΔCV_94 (primary version). Identical to Stage 4: same fold assignment (data/stage4/oof_cohort_dev.csv), weights 1/n per HARP, same estimator and preprocessing as frozen_spec.json (quote them; the ΔCV column gets the same preprocessing as the other features). Metric: weighted log-loss, Δ = logloss(A) − logloss(E94) (positive = EUV helps), HARP bootstrap 10,000 resamples, seed 20260921; weighted AUC for A and E94. Delayed episodes count as false."
- c. "SENSITIVITIES (same procedure): S1 = flare-excluded version; S2 = primary excluding the 26 episodes with HMI patch pixels outside the cutout; S3 = NEW: flare-excluded plus frames up to 2 h after each P2 event end time (recompute from data/euv_full/series/*.csv with the stored per-frame means and the same 20 draws, no downloads, no image reprocessing; re-apply the 80% fill rule; report n valid true/false)."
- d. "SUPPORTING — magnetic twins: each true episode matched 1:1 to a false episode on gate score, greedy nearest neighbour, frozen caliper 0.0747 (as Stage 4). Report n pairs, mean and median paired ΔCV difference (true − false), HARP-bootstrap 95% CI, and a Wilcoxon signed-rank p. Primary version; repeat for S1."
- e. "DESCRIPTIVE: ΔCV (primary and S1) by group true / delayed / other false: n, median, IQR. No test."
- f. "Also report the frame counts from the 2026-09-24 entry, item 1c."
- g. "Pre-stated reading: \"EUV adds information\" only if the PRIMARY Δ > 0 with a 95% CI excluding 0 AND S1 Δ > 0. Otherwise report \"no detectable improvement\", in the same wording as the magnetic-trend result."
  - Note (me): decisions.md records no conclusion wording for the magnetic-trend (Stage 5) result (VERIFIED_FACTS.md row 79). The phrase "no detectable improvement" is therefore used exactly as the user wrote it above.

**Quoted from `frozen/frozen_spec.json` (`models`):**
- estimator: "LogisticRegression(penalty='l2', C=1.0, solver='lbfgs', max_iter=10000), no tuning"
- standardisation: "StandardScaler fitted on training folds"
- sample_weight: "episode weight"; cohort unit: "T2: all eligible episodes; weight 1/(eligible episodes in HARP)"
- cv: "5-fold grouped by HARP, 2 strata (>= 1 true episode / none), seed 20260921"
- matched_pairs: caliper 0.07470488674776919 ("0.2 x SD of gate score over the dev cohort episodes"); "1:1 greedy nearest on gate score, without replacement, false alarm from a different HARP, seeded order"

**Implementation details (decided by: me, before computing):**
- **Code:** `euv_step6.py` (new). Inputs: `data/stage4/oof_cohort_dev.csv` (cohort, `fold`, `true_alarm`, `delayed`), `data/euv_full/results/*.json` (`primary_dCV`, `sens_dCV`, fills, `max_frac_outside_valid`), `data/euv_full/series/*.csv` (S3 only). Outputs to `data/euv_full/step6/` only.
- **Folds:** the `fold` column of `data/stage4/oof_cohort_dev.csv` is used as-is for every analysis set; folds are NOT recomputed on subsets. Check before any EUV fit: model A on all 547 episodes with this column reproduces the stored `p_A` (|diff| < 1e-9).
- **Analysis sets:** a version's valid episodes are those with fill ≥ 0.80 for that version; HARP 8 (no AIA data) is not valid. Primary 541, S1 528 (step 4). S2 = the primary set minus episodes with `max_frac_outside_valid > 0`. S3 = episodes with S3 fill ≥ 0.80.
- **Weights:** T2 rule applied to each analysis set: weight = 1 / (number of that set's episodes in the HARP), so each HARP sums to 1 as in Stage 4. A and E94 use the same set and weights.
- **Features:** A = [score, n_C, n_M, n_X]; E94 = A + [dCV of that version]. All columns get the per-training-fold StandardScaler. Out-of-fold probabilities are pooled.
- **Metric:** weighted log-loss as in `stage4_models.wlogloss` (clip 1e-15); Δ = LL(A) − LL(E94). **Bootstrap:** resample the set's HARPs with replacement (all episodes of a drawn HARP, with their weights), 10,000 resamples, `np.random.RandomState(20260921)`, 2.5/97.5 percentiles. Weighted AUC = `roc_auc_score(..., sample_weight=weight)` on the pooled OOF probabilities.
- **S3 recomputation:**
  - P2 events: `swpc.load(t − 2 d, t)` → `euv_pilot.flare_excluded` with each event's end moved +2 h. S3 excludes frames with T_OBS in [start, end + 2 h] of a P2 event (a: C1+ same NOAA region; b: M1+ any region), on top of the S1 exclusions.
  - ΔCV uses `euv_dctrl.summarise` on the stored per-frame means (`pil_k`, `ctrl_k`, k = 0–19).
  - Fill uses the same 120 slots and ± 6 min rule.
  - Check before use: the same code with the stored `valid_primary` / `valid_sens` must reproduce the stored `primary_dCV` / `sens_dCV` and fills for all 546 episodes (|diff| < 1e-9).
- **Twins (d):**
  - The Stage 4 code path is run on each version's valid set, with delayed episodes as false: one `RandomState(20260921)` gives the order of the true episodes (a permutation), and each true episode takes the nearest unused false episode from a different HARP within the caliper.
  - The same RandomState then draws 10,000 bootstrap resamples of the true HARPs (clustered by true HARP, as in Stage 4). The 95% CIs are for the mean and the median of the paired difference.
  - Wilcoxon: `scipy.stats.wilcoxon`, two-sided, default zero handling.
- **Descriptive (e):** unweighted episodes; groups true / delayed (`true_alarm == 0 & delayed == 1`) / other false; n, median, Q1–Q3.
- **Frame counts (f):** recomputed from `series/*.csv` (`exp_ok`, `q_ok`, `flare`) and reported next to the item-1c values.

**h. HELD-OUT EUV TEST — PRE-REGISTERED, NOT RUN (user, verbatim):** "frozen primary test cohort (data/stage5/cohort_test_primary.csv, 313 episodes, 2021/2023/2024, single-region). Same image pipeline (94 Å, 12 min, (t−24h, t], same masks, D-CTRL, QUALITY, exposure, P2, P4/U4 rules, 80% fill, both versions). E94 and A fitted on the dev cohort with the 5 folds; test prediction = mean of the 5 fold models (as Stage 5). Metric: weighted Δlog-loss(A − E94), HARP bootstrap 10,000, seed 20260921; AUC. Run once; report whatever happens." **When it runs (user's rule, recorded now):** "it will be run regardless of the step 6 result. Deadline for starting the download: 2026-09-30."
- **Implementation (me):**
  - Pipeline: `euv_full.py` unchanged (per-HARP HMI + AIA exports, one pending export at a time, the user's account only), outputs in a new folder `data/euv_test/`.
  - Models: A and E94 are the 5 fold models of the step 6 PRIMARY analysis (dev primary valid set, the same set for both). S1 on test uses the dev S1 fold models.
  - Test prediction: the mean of the 5 fold models' predicted probabilities.
  - Test weights: 1 / (valid test episodes in the HARP), per version.
  - Delayed test episodes count as false.
  - The frozen Stage 4/5 model-A files are not used for this comparison, because A must be fitted on the same episodes as E94 (item a).

### Step 6 — addition before any label split: episode with undefined ΔCV (decided by: me; label not looked at)
- First run of `euv_step6.py`: all pre-registered checks passed (stored primary/sens ΔCV and fill reproduced from the series for 546 episodes, |diff| < 1e-9; Stage 4 `p_A` reproduced with the fold column, max |diff| 1.1e-16; the twins code reproduces the 83 Stage 4 pairs). The run then stopped at the `ΔCV not NaN` assertion, before any model with ΔCV was fitted.
- **Cause:** episode `4839_20141123T2259` has `n_pix = 0`. The HMI magnetogram at t has no PIL pixels under the ±150 G / 16-px rule, so there are no PIL or control samples and ΔCV is undefined in every version. Its fill passes 80% in both versions.
- **Rule (me):** an analysis set = fill ≥ 80% for that version AND a defined ΔCV for that version. This removes this one episode from every set, for both A and E94 (item a: same episodes).
  - Expected sizes: PRIMARY 540 (step 4: 541), S1 527 (step 4: 528).
  - The step 4 threshold choice is not re-run; it stays at 80% (ff3c11c).
- The episode's label was not looked at for this decision. The n true/false per set is reported with the results.

## 2026-09-24 — STEP 6 RESULT (dev 2010–2019, internal 5-fold CV — NOT a held-out test; numbers only)
Code `euv_step6.py`, console `euv_step6.log`, outputs `data/euv_full/step6/` (per-set OOF probabilities, twins pairs, the PRIMARY/S1 fold models for the held-out test). Checks passed: stored ΔCV/fill reproduced from the series (546 episodes, |diff| < 1e-9); Stage 4 `p_A` reproduced (1.1e-16); Stage 4 pairs reproduced (83). Excluded for undefined ΔCV: `4839_20141123T2259` (entry above).

**(b, c) E94 vs A.** Δ = LL(A) − LL(E94), positive = EUV helps. HARP bootstrap 10,000, seed 20260921. Weighted AUC.

| set | episodes | true | false | HARPs | LL(A) | LL(E94) | Δ | 95% CI | AUC A | AUC E94 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| PRIMARY | 540 | 96 | 444 | 178 | 0.3220 | 0.3262 | −0.0043 | [−0.0092, 0.0003] | 0.7430 | 0.7196 |
| S1 flare-excluded | 527 | 89 | 438 | 178 | 0.3375 | 0.3421 | −0.0046 | [−0.0102, 0.0004] | 0.7490 | 0.7203 |
| S2 primary, no overhang | 514 | 90 | 424 | 169 | 0.3220 | 0.3269 | −0.0049 | [−0.0108, 0.0002] | 0.7262 | 0.6925 |
| S3 flare + 2 h after end | 332 | 31 | 301 | 135 | 0.3705 | 0.3747 | −0.0042 | [−0.0199, 0.0094] | 0.4173 | 0.4873 |

- S3 at 80%: 332 of 547 valid (true 31/98, false 301/449). The +2 h extension removes 9,792 frames beyond S1.

**(d) Magnetic twins.** Gate score, caliper 0.0747, Stage 4 procedure. Paired ΔCV difference = true − false. CIs: HARP bootstrap clustered by true HARP, 10,000 resamples.

| | PRIMARY | S1 |
|---|---:|---:|
| true episodes / pairs / unmatched | 96 / 81 / 15 | 89 / 79 / 10 |
| true HARPs in pairs | 34 | 34 |
| delayed episodes among matched false | 9 | 8 |
| max \|score diff\| | 0.0623 | 0.0733 |
| mean [95% CI] | 0.0776 [−0.0463, 0.2159] | 0.0767 [−0.0331, 0.2081] |
| median [95% CI] | 0.0321 [−0.0346, 0.0999] | 0.0564 [0.0098, 0.0995] |
| fraction of pairs with true > false | 0.6049 | 0.6709 |
| Wilcoxon p (two-sided) | 0.0979 | 0.0228 |

**(e) Descriptive ΔCV** (unweighted episodes; no test). Values are median [Q1, Q3].

| set | true | delayed | other false |
|---|---|---|---|
| PRIMARY | n 96: 0.1007 [0.0415, 0.2142] | n 46: 0.1308 [0.0437, 0.1688] | n 398: 0.0678 [0.0203, 0.1768] |
| S1 | n 89: 0.0857 [0.0404, 0.1737] | n 44: 0.1043 [0.0437, 0.1721] | n 394: 0.0561 [0.0144, 0.1396] |

**(f) Frame counts** (recomputed from the series; identical to the 2026-09-24 entry, item 1c):
- exposure-rule frames: 661
  - QUALITY ≠ 0: 544; QUALITY == 0: 117
  - inside a P2 flare interval: 86 (any QUALITY), 68 (QUALITY == 0)
- frames total: 65,253
- frames in P2 flare intervals: 2,180

**(g) Pre-stated rule, applied mechanically:** PRIMARY Δ = −0.0043, CI [−0.0092, 0.0003]. Δ is not > 0 and the CI includes 0, so the rule's condition is not met. Reading: "no detectable improvement".

## 2026-09-24 — Held-out EUV test: ESTIMATE only (no export, no download) (requested by: user)
`euv_test_estimate.py` → `euv_test_estimate.log`. Inputs: cohort `data/stage5/cohort_test_primary.csv` (313 episodes, 98 HARPs) and the same per-HARP export plan as the dev run. Prep per export = 72 s + 0.2 s/file (user; on the dev exports this model gives 10.43 h vs 10.44 h logged). Bytes/file and download s/file are dev averages (AIA 270 kB, 0.36 s; HMI 260 kB, 1.81 s).

| plan | exports | AIA files | HMI files | GB | Σ prep (h) | serial download (h) | wall (h) × dev ratio 1.26 |
|---|---:|---:|---:|---:|---:|---:|---:|
| per-HARP HMI exports | 196 | 31,290 | 626 | 8.62 | 5.69 | 3.44 | 7.20 |
| one combined HMI export | 99 | 31,290 | 626 | 8.62 | 3.75 | 3.44 | 4.75 |

- Downloads overlap with the next export's prep (one pending export at a time), so the wall time is set by Σ prep. The dev ratio (13.2 h wall / 10.44 h prep) covers the compute tail and retries.
- A single HMI export across HARPs has not been tested. The record-set form `hmi.sharp_720s[h1,h2,…][t1,…]` is a HARP × time cross-product and would return extra records, so the exact form must be tested (and verified as in the per-HARP HMI test) before use.

## 2026-09-24 — EXPLORATORY DIAGNOSTIC on step 6 ΔCV — NOT PRE-REGISTERED (requested by: user; recorded BEFORE running)
**Status:** EXPLORATORY DIAGNOSTIC. Not pre-registered, no new claims, no refits of the pre-registered models. Step 6 result and its reading unchanged.
**Data:** dev 2010–2019, primary version, the 540 episodes of the step 6 PRIMARY set.

**User's items, verbatim:**
1. "Overlap with flare history: Spearman ρ of ΔCV with n_C, n_M, n_X, (n_C+n_M+n_X) and gate score."
2. "Timing: for true episodes, ΔCV vs hours from t to the flare start (Spearman ρ); median ΔCV for flare within 0–6 h vs 6–24 h after t."
3. "Eventually-flaring: weighted AUC of ΔCV ALONE for (true + delayed) vs other false, and for true vs other false; HARP-bootstrap 95% CI (2,000, seed 0)."
4. "Skew: ΔCV min, 1st, 5th, 50th, 95th, 99th percentile, max; number of |ΔCV| > 3 SD."

**Implementation (decided by: me, before running):**
- Code `euv_explore.py`; console `euv_explore.log`; outputs `data/euv_full/step6/explore_*.csv`.
- **Item 1:** `scipy.stats.spearmanr` on all 540 episodes, unweighted; ρ, p and n reported.
- **Item 2:**
  - Flare start = the first M1+ (K2, `swpc.load`, flux ≥ 1e-5) whose NOAA region is in the episode's `noaa_ars` and whose start is in (t, t + 24 h]. This is the same join as `diag_testchecks.py` item 1.
  - The number of true episodes with such a flare is reported (expected 96).
  - Windows: 0–6 h = (0, 6]; 6–24 h = (6, 24].
- **Item 3:**
  - Score = raw ΔCV, higher = positive class; no model.
  - Weights = the step 6 PRIMARY weights (1/n per HARP over the 540 episodes). The same weights are used in both comparisons; for "true vs other false" the delayed episodes are dropped.
  - Bootstrap: resample HARPs with replacement, 2,000 times, `np.random.RandomState(0)`. Resamples with only one class are skipped and counted. 2.5/97.5 percentiles.
- **Item 4:**
  - Percentiles use `np.percentile` (linear).
  - SD = sample SD (ddof = 1) over the 540 values.
  - Two counts are reported, because the wording allows both: |ΔCV| > 3 SD, and |ΔCV − mean| > 3 SD.

### EXPLORATORY DIAGNOSTIC — RESULT (not pre-registered; numbers only)
`euv_explore.py` → `euv_explore.log`. Dev 2010–2019, primary version, 540 episodes. First run stopped on a column-name clash (`weight` in both inputs); the step 6 weights are used, as recorded.

**1. Spearman ρ of ΔCV (unweighted, n = 540):**

| variable | ρ | p |
|---|---:|---:|
| n_C | 0.2294 | 7.04e-08 |
| n_M | 0.0614 | 0.154 |
| n_X | 0.0345 | 0.424 |
| n_C+n_M+n_X | 0.2231 | 1.61e-07 |
| gate score | 0.0501 | 0.245 |

**2. Timing (true episodes):**
- 96 of 96 have a region M1+ start in (t, t + 24 h].
- ρ(ΔCV, hours to flare start) = −0.0294 (p 0.777, n 96).
- Median ΔCV: 0.1189 for lead (0, 6] h (n 31); 0.1001 for lead (6, 24] h (n 65).

**3. Weighted AUC of ΔCV alone** (weights 1/n per HARP over the 540; HARP bootstrap 2,000, seed 0; 0 resamples skipped):

| comparison | episodes | pos | neg | HARPs | AUC | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| (true + delayed) vs other false | 540 | 142 | 398 | 178 | 0.5386 | [0.4692, 0.6128] |
| true vs other false | 494 | 96 | 398 | 173 | 0.5271 | [0.4395, 0.6079] |

**4. ΔCV distribution (n = 540):**
- Mean 0.1196, SD 0.1981.
- Percentiles: min −0.5021; 1st −0.3700; 5th −0.0808; 50th 0.0748; 95th 0.4201; 99th 0.8296; max 1.6496.
- |ΔCV| > 3 SD: 10 episodes; |ΔCV − mean| > 3 SD: 7 episodes.

## 2026-09-25 — PHASE X: SPATIAL 94 Å MEASURES — PRE-REGISTRATION (decided by: user; recorded BEFORE computing anything new)
**Label: EXPLORATORY on dev.** The step 6 result ("no detectable improvement", 04a2abf) stands and is reported regardless. Dev 2010–2019 only; no downloads; frozen files and FINAL results unchanged.

**User's text, verbatim:**
- "Fixed candidate list (no additions after results; definitions follow the cited papers):"
  - "R1 PIL running-difference kurtosis (Leka et al. 2023, arXiv:2212.11255, κ(ΔI)): for consecutive valid frames ≤ 24 min apart, excess kurtosis of (I_k − I_{k−1}) over PIL-mask pixels (DN/s, exposure-normalised, saturated pixels excluded); summary = median over the window; minus the same statistic on the 20 control draws (D-CTRL form)."
  - "R2 PIL running-difference skew (Leka et al. 2023, ς(ΔI)): as R1 with skewness instead of kurtosis; minus controls."
  - "R3 PIL transient-brightening fraction (adapted from BADPIT, André-Hoffmann et al. 2026, §3.2): per pixel, threshold = mean + 3 SD of that pixel over all valid frames in (t−24h, t]; a brightening = a connected patch of ≥ 4 pixels above threshold (8-connectivity); per frame, fraction of PIL pixels inside brightenings; summary = mean over frames; minus the same on the 20 control draws. Stated deviation: BADPIT's ≥ 5-consecutive-frame rule cannot be applied at 12-min cadence."
  - "R4 Whole-box counterparts of R1–R3 (no control subtraction), as in Leka's whole-field parametrisation."
- "Rules: primary-version frame rules (QUALITY, exposure rule, saturated pixels excluded; flare frames kept), same masks, 80% fill, the same label-blind exclusion if a value is undefined (report n excluded). Consecutive frames are differenced after the existing registration; report the median frame-to-frame pointing shift in pixels as a check."
- "Stated deviations from the papers: 12-min vs 72-s (Leka) / 12-s (BADPIT) sampling; PIL-local with matched controls is this project's addition."
- "Dev evaluation: each candidate added to model A exactly as in step 6 (same fold assignment, weights 1/n per HARP, estimator and preprocessing as frozen_spec.json, HARP bootstrap 10,000, seed 20260921). Report Δ = logloss(A) − logloss(A + Rk) with 95% CI, and weighted AUC, for ALL candidates."
- "Selection rule: the PIL candidate (R1–R3) with the largest dev Δ; it qualifies only if Δ > 0. Dev selection is not confirmation."
- "Held-out plan (NOT run now): if one qualifies, it will be computed ONCE on the 2021/2023/2024 test episodes with the same design as 3283478 item 1h, after the held-out download. Disclose that test-year labels and magnetic results were seen earlier; test-year EUV values were not."
- **Disclosure (as required):**
  - Test-year labels and magnetic (gate, model A/B) results were seen earlier: Stage 5 and the read-only checks of 2026-09-23.
  - No test-year EUV value has been computed or seen.
  - On dev, the step 6 ΔCV results and the exploratory diagnostic (064725c) were seen before this list was fixed.

**Implementation (decided by: me, before computing):**
- **Code:** `euv_spatial.py` (new). Outputs:
  - `data/euv_full/spatial/<eid>_pairs.csv` (per frame pair: κ and ς for the 20 PIL draws, the 20 control draws and the box; Δt; pointing shift);
  - `data/euv_full/spatial/<eid>_frames.csv` (per frame: brightening fraction for the same sets);
  - `data/euv_full/spatial/<eid>.json` (summaries R1–R4 and checks).
  - The timing runs (B) write to `data/euv_full/spatial_timing/{single,pool}/`.
- **Frames:** the rows with `valid_primary` in `data/euv_full/series/<eid>.csv`, matched to the AIA files by T_REC.
  - Each frame is processed exactly as in `euv_full.compute_episode`: raw > 12,000 DN → NaN; divide by EXPTIME; `update_pointing` with the JSOC pointing table for (t − 26 h, t + 2 h); `register_cutout`; `hmi_to_frame`.
  - The pointing table is a JSOC keyword query, as in the original run; it is not a data export or download.
  - **Check:** `frame_means` of every processed frame must reproduce the stored series values (all sample sets, |diff| < 1e-9). Otherwise the run stops.
- **Pixel values:** per HMI patch pixel, the registered AIA value (DN/s) at its mapped pixel (`hmi_to_frame`, differential rotation to each frame's time). This is the same mapping as ΔCV; it is NaN outside the cutout or if saturated. The same HMI pixel is followed from frame to frame, so the running difference I_k − I_{k−1} is taken per HMI pixel after the existing registration.
- **Sets:** from `euv_dctrl.samples` (same masks and draws as ΔCV):
  - `pil_k` and `ctrl_k`, k = 0–19; `pil_k` is the full PIL mask unless the control candidates are too few.
  - `box` = all HMI patch pixels, used for R4.
- **R1/R2 (κ, ς):**
  - Pairs = consecutive valid frames with 0 < Δt(T_OBS) ≤ 24 min.
  - Per pair and set: `scipy.stats.kurtosis(x, fisher=True, bias=True)` / `scipy.stats.skew(x, bias=True)` over the pixels finite in both frames; ≥ 4 pixels are required, otherwise NaN.
  - Per set: the median over pairs (NaN ignored).
  - R1 = mean over k of [median κ(pil_k) − median κ(ctrl_k)]; R2 likewise with ς.
  - R4a = median κ(box); R4b = median ς(box).
- **R3:**
  - Per HMI patch pixel, over all valid frames of the window: threshold = mean + 3 SD (ddof = 1). A threshold needs ≥ 3 finite values; otherwise the pixel is never "above".
  - Per frame, above = value > threshold. Connected components use 8-connectivity on the HMI patch grid (`scipy.ndimage.label`, 3×3 structure).
  - **Pixel count:** a component is a brightening if it covers ≥ 4 distinct AIA pixels (distinct mapped AIA indices). The rule is thus in AIA pixels as in BADPIT, while connectivity is assessed on the surface-tracked HMI grid.
  - Per frame and set: the fraction of the set's pixels with a finite value that lie in a brightening.
  - R3 = mean over k of [mean over frames of frac(pil_k) − mean over frames of frac(ctrl_k)]; R4c = mean over frames of frac(box).
- **Pointing-shift check:**
  - Per frame, the pixel position of the HMI patch centre, mapped with differential rotation into the registered frame.
  - Shift = Euclidean distance in AIA pixels between consecutive pair frames.
  - Reported: the median over all pairs of all episodes, plus the 95th percentile and the maximum.
- **Valid sets:** the primary 80% set (`primary_fill ≥ 0.80`, 541 episodes) AND a defined value of that candidate. The number excluded is reported per candidate. `4839_20141123T2259` (no PIL pixels) is expected to be undefined for R1–R3; for R4 it can be defined and is then kept.
- **Candidates evaluated:** R1, R2, R3, R4a (κ box), R4b (ς box), R4c (brightening fraction box).
- **Dev evaluation:**
  - The step 6 `compare` procedure: the `fold` column from `data/stage4/oof_cohort_dev.csv`; weights 1/n per HARP over the candidate's valid set; features [score, n_C, n_M, n_X] (+ Rk); a StandardScaler per training fold; the frozen LogisticRegression; weighted log-loss; HARP bootstrap 10,000 with `RandomState(20260921)`; weighted AUC. A and A + Rk are fitted on the same episodes.
  - **Check:** the same code applied to step 6 PRIMARY ΔCV must reproduce the step 6 Δ and CI (|diff| < 1e-12).
- **Timing (B):**
  - 10 dev episodes drawn label-blind: `RandomState(0)`, from the 546 with results.
  - Single process, then an 8-worker pool; the two outputs must be identical.
  - Projection = N × (mean per-episode time inside the pool) / 8, for N = 546 dev and N = 313 test.
  - If the dev projection is > 8 h: STOP and report.
- **Selection (only R1–R3):** the largest Δ; qualifies only if Δ > 0. R4a–c are reported but cannot be selected.

### PHASE X — RESULT (EXPLORATORY on dev 2010–2019, internal 5-fold CV; numbers only)
`euv_spatial.py` (timing | run | eval) → `euv_spatial_eval.log`. Per-episode outputs in `data/euv_full/spatial/`; timing in `data/euv_full/logs/spatial_timing.log`.

**B. Timing** (10 dev episodes drawn with `RandomState(0)`):
- Frame means reproduced (max |diff| 0.0); single-process output = pool output.
- Single process: 23.3 s/episode. Pool of 8: 36.9 s/episode inside the workers, 68 s wall for the 10.
- Projected: dev 546 episodes 0.70 h; test 313 episodes 0.40 h (8 workers). Dev ≤ 8 h, so step C was run.

**Run:**
- The first run stopped at 373/546 when the previous Claude session ended (the process was not detached). All 373 saved JSONs were complete.
- The run was resumed (finished episodes skipped) and completed 546/546 at 01:28.

**Checks:**
- Frame means reproduced in all 546 episodes (max |diff| 0.0).
- The step 6 PRIMARY Δ and CI are reproduced by the evaluation code.
- Frame-to-frame pointing shift of the patch centre, 62,781 pairs: median 0.307 AIA px, 95th percentile 0.949, maximum 9.539.

**1. n valid per candidate** (primary 80% set = 541):
- R1–R3: 540 episodes (96 true / 444 false, 178 HARPs). 1 excluded as undefined: `4839_20141123T2259`.
- R4a–c: 541 episodes (96 / 445, 179 HARPs). 0 excluded.

**2. Δ = LL(A) − LL(A + Rk)** (positive = candidate helps). HARP bootstrap 10,000, seed 20260921. Weighted AUC.

| candidate | LL(A) | LL(A + Rk) | Δ | 95% CI | AUC A | AUC A + Rk |
|---|---:|---:|---:|---|---:|---:|
| R1 PIL κ(ΔI) − ctrl | 0.3220 | 0.3243 | −0.0023 | [−0.0088, 0.0023] | 0.7430 | 0.7406 |
| R2 PIL ς(ΔI) − ctrl | 0.3220 | 0.3251 | −0.0031 | [−0.0080, 0.0013] | 0.7430 | 0.7440 |
| R3 PIL brightening fraction − ctrl | 0.3220 | 0.3254 | −0.0034 | [−0.0132, 0.0041] | 0.7430 | 0.7454 |
| R4a box κ(ΔI) | 0.3206 | 0.3082 | 0.0124 | [−0.0048, 0.0294] | 0.7422 | 0.8003 |
| R4b box ς(ΔI) | 0.3206 | 0.3257 | −0.0051 | [−0.0177, 0.0027] | 0.7422 | 0.7203 |
| R4c box brightening fraction | 0.3206 | 0.3169 | 0.0037 | [−0.0058, 0.0132] | 0.7422 | 0.8020 |

**3. Selection rule** (R1–R3 only): the largest Δ is R1 (−0.0023). It does not qualify (Δ ≤ 0), so no PIL candidate goes to the held-out plan. R4a–c are reported only; by the pre-registered rule they cannot be selected.

## 2026-09-25 — R4a FLARE CHECK (requested by: user; EXPLORATORY; recorded BEFORE computing)
**Label:** EXPLORATORY follow-up to Phase X (315ca5b). "R4a was not eligible under the Phase X selection rule; this check does not change that and makes no claim." Dev 2010–2019 only; no downloads.

**User's text, verbatim:**
- "Question: does R4a (whole-box running-difference kurtosis) still add to model A when frames taken during flares are removed?"
- "Definition: R4a exactly as in 315ca5b, but computed on the FLARE-EXCLUDED frame set (P2 amended, same rule as step 6 S1: frames inside the begin–end of a C1+ SWPC event from the HARP's NOAA region(s), or any M1+ event, removed). Running differences only between consecutive VALID frames ≤ 24 min apart. Call it R4a_nf."
- "Fill: 80% on the flare-excluded frame set (as S1). Label-blind exclusion if undefined."
- "Pre-stated reading: \"R4a survives flare removal\" if Δ(A − A+R4a_nf) > 0 on the same episodes AND AUC(A+R4a_nf) > AUC(A). \"R4a mostly reflected flares\" if Δ ≤ 0. Either way reported; nothing is claimed from dev alone."
  - Note (me): if Δ > 0 but AUC(A+R4a_nf) ≤ AUC(A), neither pre-stated reading applies; that case is reported as "neither condition met".

**Implementation (decided by: me, before computing):**
- **Code:** `euv_spatial.spatial_episode` gets an argument `valid` (default `"valid_primary"`, so Phase X behaviour is unchanged).
  - R4a_nf uses `valid="valid_sens"`: the stored step 6 S1 flags (`valid_primary & ~flare`) in `data/euv_full/series/<eid>.csv`.
  - Pairs are consecutive valid_sens frames with 0 < Δt ≤ 24 min. Everything else is the same code path, including the frame-means check against the stored series.
  - The other Phase X quantities are also written to the JSON by that code path. They are not read or reported.
  - Outputs go to `data/euv_full/spatial_nf/`; the pool check writes to `data/euv_full/spatial_nf_check/{single,pool}/`.
- **Workers:** `os.cpu_count() − 1` = 9 (10 cores).
  - **Check first:** 5 episodes drawn with `RandomState(0)` from the 546, run single-process and then in the 9-worker pool. JSON values and pair/frame CSVs must be identical (|diff| = 0). Otherwise the run falls back to 8 workers and this is reported.
- **Valid set:** `sens_fill ≥ 0.80` (the stored S1 fill) AND R4a_nf defined. This set is a subset of the Phase X R4a set, because valid_sens frames are a subset of the valid_primary frames.
- **Evaluation:** the Phase X/step 6 `compare` procedure, on the R4a_nf valid set only.
  - Two comparisons on the same episodes and weights: A vs A + R4a (original, from `data/euv_full/spatial/`), and A vs A + R4a_nf.
  - The code is moved to module level unchanged. **Check:** it must reproduce the Phase X R4a row of `data/euv_full/spatial/eval_compare.csv` (Δ, CI, AUCs; |diff| < 1e-12).
- **Items 3–5** use the same common set (the R4a_nf valid set):
  - Item 3: Spearman ρ (n, ρ, p) of R4a and of R4a_nf with n_C, n_M, n_X and the gate score.
  - Item 4: 99th percentile over that set (`np.percentile`, linear). "Above" = strictly greater. "Contains ≥ 1 flare frame" = ≥ 1 frame with `valid_primary & flare` in the episode's series, i.e. a flare frame that entered the original R4a. The same definition is used for both measures.
  - Item 5: Spearman ρ between R4a and R4a_nf.

## 2026-09-25 — HELD-OUT EUV TEST: DATA DOWNLOAD ONLY — started (requested by: user; recorded before the first export)
**User's text, verbatim:**
- "HELD-OUT DATA DOWNLOAD ONLY (user). No ΔCV, no R4a, no labels, no model outputs on test years — download and verify files only."
- "Cohort: data/stage5/cohort_test_primary.csv (313 episodes, 98 HARPs, 2021/2023/2024, single-region), exactly as pre-registered in 3283478 item 1h."
- "Per-HARP HMI exports (the verified dev method; NOT the untested combined export) … Per-HARP AIA im_patch url-tar exports, 94 Å, 12 min, same record-set rule and im_patch settings as dev. Pipelined, ONE pending JSOC export at a time, the user's account only, resumable, progress logged every 30 min. Output to data/euv_test/ (never overwrite data/euv_full/)."
- "When complete: verify files (counts per HARP vs expected, headers readable, HARP/T_REC match), report counts, missing/short HARPs, GB and wall time. Record in decisions.md, commit. STOP. Compute nothing on test years."

**Implementation (me):**
- `euv_test_download.py run | verify`.
  - The episode list reads only `harpnum`, `t`, `noaa_ars` from the cohort file. T_REC (TAI) comes from the labelled file with `usecols` = harpnum, t_rec_utc, t_rec_tai. No label or model column is read.
- Driver: `euv_full.run_pipeline` with a new argument `compute=False` (default True; dev behaviour unchanged). No worker pool is created and no episode is computed.
  - HMI: `hmi.sharp_720s[H][t1,…]{magnetogram,bitmap}`, one export per HARP.
  - AIA: `aia_spec`, the same record-set and im_patch rule as dev. The HMI magnetograms are read only to size the im_patch, exactly as in dev.
  - url-tar; the next export is submitted after the previous one completes; one pending export; the user's account (`euv_download.EMAIL`); resumable; 3 tries per export.
  - Progress is logged every 30 min to `data/euv_test/logs/progress.log`. Logs, `exports.csv` and `failed.csv` go under `data/euv_test/`.
- **Verify:** per HARP:
  - HMI: magnetogram + bitmap present for each episode T_REC, with header HARPNUM and T_REC matching.
  - AIA: files with a readable header; WAVELNTH = 94; T_REC inside the HARP's record range; count vs `expected_frames`.
  - Also reported: GB, failures, and export prep/download times.
- Runs in parallel with the R4a flare check (dev, 9 CPU workers). The download is network-bound.

### R4a FLARE CHECK — RESULT (EXPLORATORY; dev 2010–2019, internal 5-fold CV; numbers only)
`euv_spatial.py nf_check | nf_run | nf_eval` → `euv_r4a_nf_eval.log`. Outputs in `data/euv_full/spatial_nf/`.

**B. Compute:**
- Workers = os.cpu_count() − 1 = 9.
- 5-episode check: the pool output equals the single-process output exactly (single 102 s wall, pool 39 s); frame means reproduced (0.0).
- Full run: 546/546 in 1.40 h (12:31–13:55; the held-out download ran in parallel from 13:29). Frame means reproduced in all 546.
- Check: the module-level `compare` reproduces the Phase X R4a row exactly.

**C1. n valid:**
- R4a_nf (S1 fill ≥ 80%, defined): 528 (89 true / 439 false), 0 excluded as undefined.
- Phase X R4a: 541 (96 / 445).

**C2. Same 528 episodes, 179 HARPs.** HARP bootstrap 10,000, seed 20260921. Weighted AUC.

| comparison | LL(A) | LL(A + x) | Δ | 95% CI | AUC A | AUC A + x |
|---|---:|---:|---:|---|---:|---:|
| A vs A + R4a (flare frames kept) | 0.3359 | 0.3210 | 0.0149 | [−0.0069, 0.0373] | 0.7480 | 0.8016 |
| A vs A + R4a_nf (flare frames removed) | 0.3359 | 0.3226 | 0.0133 | [−0.0112, 0.0374] | 0.7480 | 0.7990 |

**C3. Spearman ρ** (n = 528):

| | n_C | n_M | n_X | gate score |
|---|---|---|---|---|
| R4a | 0.6901 (p 7.1e-76) | 0.4321 (2.0e-25) | 0.1862 (1.7e-05) | 0.5304 (1.2e-39) |
| R4a_nf | 0.6793 (1.0e-72) | 0.4268 (8.8e-25) | 0.1842 (2.1e-05) | 0.5277 (3.4e-39) |

**C4. Above the 99th percentile** (528 episodes):
- R4a: p99 = 741.25; 6 episodes above, all 6 with ≥ 1 flare frame (9, 8, 12, 15, 5, 2).
- R4a_nf: p99 = 708.31; 6 above, all 6 with ≥ 1 flare frame (same counts).
- They are the same 6 episodes.

**C5.** Spearman ρ(R4a, R4a_nf) = 0.9990 (n = 528).

**Pre-stated reading, applied mechanically:** Δ(A − A + R4a_nf) = 0.0133 > 0 and AUC(A + R4a_nf) 0.7990 > AUC(A) 0.7480 → "R4a survives flare removal". EXPLORATORY; nothing is claimed from dev alone. R4a's Phase X status (not eligible) is unchanged.

## 2026-09-25 — EXPLORATORY: Deshmukh-style operating point on dev OOF predictions, A vs A + R4a and A vs A + R4a_nf (requested by: user; recorded BEFORE running)
**Label:** EXPLORATORY, dev only, no claims. The held-out download continues untouched.
**User's text, verbatim:** "Deshmukh-style operating point on dev out-of-fold predictions for A vs A+R4a and A vs A+R4a_nf, same 528 episodes. For each model: threshold = the highest value keeping ≥ 88% of true episodes (weighted as step 6). Report: true kept, false removed (count and %), precision, FAR, each with HARP-bootstrap 95% CI (2,000, seed 0); and the difference in false removed (A+R4a − A) with its CI."

**Implementation (decided by: me, before running):**
- **Code:** `euv_r4a_oppoint.py`.
- **Episodes:** the 528 of the R4a flare check, weights 1/n per HARP over the 528 (as step 6).
- **OOF probabilities:** from `euv_spatial.cv_fit` (the step 6 procedure) for A, A + R4a and A + R4a_nf.
  - **Check:** the weighted log-losses must equal `data/euv_full/spatial_nf/eval_nf_compare.csv` (|diff| < 1e-12).
- **Threshold τ:** the rule of `diag_operating_point.tau_keep`. True episodes are sorted by probability (descending); τ = the probability at which the cumulative weighted fraction first reaches ≥ 0.88. Kept = probability ≥ τ.
  - τ is chosen on the same dev OOF probabilities it is evaluated on (in-sample operating point).
- **Metrics** (per model; weighted % plus unweighted counts):
  - true kept;
  - false removed;
  - precision = weighted true among kept / weighted kept;
  - FAR = 1 − precision.
- **CIs:** HARP bootstrap, 2,000 resamples, `np.random.RandomState(0)`. HARPs are resampled with their episodes and weights; τ is held fixed at the full-sample value; 2.5/97.5 percentiles.
- **Differences:** Δ false removed (weighted %) = (A + R4a − A) and (A + R4a_nf − A), computed in the same resamples (paired). The count differences are also given.

### Dev operating point — RESULT (EXPLORATORY; τ in-sample; numbers only)
`euv_r4a_oppoint.py` → `euv_r4a_oppoint.log`, `data/euv_full/spatial_nf/oppoint_dev.csv`.
- 528 episodes (89 true / 439 false), weights 1/n per HARP.
- Check: the OOF log-losses equal the R4a flare-check evaluation.
- CIs: HARP bootstrap, 2,000 resamples, seed 0, τ fixed.

| model | τ | kept | true kept (n; weighted [CI]) | false removed (n; weighted [CI]) | precision [CI] | FAR [CI] |
|---|---:|---:|---|---|---|---|
| A | 0.0713 | 431 | 80/89; 0.8833 [0.7587, 0.9861] | 88/439; 0.2313 [0.1718, 0.2934] | 0.1464 [0.1008, 0.1953] | 0.8536 [0.8047, 0.8992] |
| A + R4a | 0.0619 | 306 | 78/89; 0.9216 [0.8564, 0.9753] | 211/439; 0.4904 [0.4207, 0.5631] | 0.2125 [0.1514, 0.2797] | 0.7875 [0.7203, 0.8486] |
| A + R4a_nf | 0.0616 | 308 | 77/89; 0.9154 [0.8466, 0.9713] | 208/439; 0.4819 [0.4132, 0.5530] | 0.2086 [0.1491, 0.2750] | 0.7914 [0.7250, 0.8509] |

**Difference in false removed vs A** (paired, same resamples):
- A + R4a − A: weighted +0.2591 [+0.1887, +0.3305]; count +123.
- A + R4a_nf − A: weighted +0.2506 [+0.1802, +0.3227]; count +120.

## 2026-09-25 — PHASE F: FINDINGS FROM EXISTING DEV DATA — EXPLORATORY / DESCRIPTIVE (requested by: user; recorded BEFORE computing)
**Label:** the whole phase is EXPLORATORY / DESCRIPTIVE on dev 2010–2019. Nothing here is confirmation; every candidate is reported regardless of outcome.
- No downloads.
- Nothing after 2019 is read, scored or computed: no 2020+ rows, no test files, nothing in `data/euv_test/`. The running held-out download is not touched.
- Frozen files and FINAL results unchanged.

**Candidate count:**
- Before this phase: 9 candidates evaluated on dev — trends (model B), ΔCV_94, R1, R2, R3, R4a, R4b, R4c, R4a_nf.
- This phase adds 7: n_B, S1 (size), S2 (size), B1, B2, B1_nf, B2_nf. Total 16.
- F3 also fits one combination model (A + n_B + R4a); it is listed in F7 as a combination row.

**User's rules, verbatim:**
- "Common evaluation (\"step 6 procedure\"): candidate added to model A; same fold assignment (data/stage4/oof_cohort_dev.csv), weights 1/n per HARP, estimator and preprocessing as frozen_spec.json; weighted Δ = logloss(A) − logloss(A+x) with HARP bootstrap 10,000 (seed 20260921); weighted AUC; Deshmukh-style operating point (≥ 88% true kept, as 04b6f4f). Twins = the 81 gate-score-matched pairs (caliper 0.0747). Ratio CIs = HARP bootstrap 2,000, seed 0. Primary frame rules (flare frames kept), 80% fill, label-blind exclusion; where stated, also the flare-excluded version."
- "Selection rule for any later held-out use (not run in this phase): a candidate may be proposed for a held-out test only if dev Δ > 0; that would be pre-registered separately; dev selection is not confirmation."
- Parallelism: "workers = os.cpu_count() − 1 … Parallelise: HARP-bootstrap resamples … per-episode series/frame computations (F5, F6), and independent candidates within an item … Report wall time per item and the core count used."
- The item texts F2–F7 are those of the user's request of 2026-09-25 (Phase F).

**Implementation (decided by: me, before computing):**
- **Code and outputs:** `phase_f.py F2 | F3 | F4 | F5 | F6 | F7`; logs `phase_f_F*.log`; tables in `data/phase_f/`. Workers = os.cpu_count() − 1 = 9.
- **Parallel bootstrap (exactly reproducible):**
  - For each bootstrap, the parent process draws all resamples from ONE `np.random.RandomState(seed)`, in the same order as the sequential step 6 loop (`rng.choice(n_HARPs, n_HARPs, replace=True)` per resample, which is the same stream as `rng.choice(harps, …)`).
  - The evaluation of the resamples is split into chunks across the 9 workers, and all candidates of an item are submitted to the same pool concurrently.
  - Results are therefore identical to a single-process run. This replaces per-worker seeds, so that restated numbers equal the committed ones.
  - **Check (F3):** for A + R4a, the parallel bootstrap distribution must equal a single-process sequential loop exactly (|diff| = 0).
- **Evaluation sets:**
  - Each candidate uses the primary 80% set (`primary_fill ≥ 0.80`, 541 episodes) with the candidate defined; flare-excluded candidates use `sens_fill ≥ 0.80`. Weights 1/n per HARP over the set.
  - Trends (model B) use the Stage 4 cohort of 547.
  - n_B and A + n_B + R4a use the R4a set (541).
- **Restated rows must reproduce** their committed Δ/CI/AUC (|diff| < 1e-12): trends (Stage 4 pooled Δ), ΔCV (step 6), R1–R4c (Phase X), R4a_nf (flare check), and the 04b6f4f operating point for A + R4a_nf on 528.
- **Operating point:** as 04b6f4f — τ in-sample on the OOF probabilities, ≥ 88% weighted true kept. Reported per model: true kept, false removed (weighted %, counts), precision, FAR. Bootstrap 2,000 with seed 0, τ fixed; paired difference in false removed (A + x − A).
- **Ratios** (F2, F5, F6):
  - true ÷ false of unweighted episode medians. CI: HARP bootstrap, 2,000 resamples, seed 0.
  - Twins: the 81 pairs of `data/euv_full/step6/twins_PRIMARY.csv`, restricted to pairs with both values defined. Ratio = median of the true members ÷ median of the false members. CI: pairs resampled clustered by true HARP, 2,000, seed 0.
  - Log-scale measures (S1, B1): the ratio is on the linear scale, 10^(median_true − median_false). B2 (a slope that can be negative): the difference of medians (true − false) is reported instead of a ratio.
  - A ratio with a zero median in the denominator is reported as undefined.
- **F2 per-episode values:**
  - box brightening = median over frames of `frac_box`;
  - PIL brightening = median over frames of the per-frame mean over the 20 `frac_pil_k` (both from `data/euv_full/spatial/*_frames.csv`);
  - CV_box, CV_PIL, CV_ctrl = `primary_CV_box`, `primary_CV_PIL`, `primary_CV_ctrl` from `data/euv_full/results`.
- **F3:**
  - Events: `swpc.load` / `swpc.fetch` on the 2010–2019 daily files only.
  - B class = K2 true-scale flux in [1e-7, 1e-6) (`swpc.class_of` == "B").
  - Coverage: deduplicated B events per year, and how many carry a region number.
  - n_B uses the join of `build_dataset.label`: joinable events whose region is in the episode's `noaa_ars`, start in [t − 48 h, t), union over regions, duplicates dropped.
  - **Check:** the same code reproduces the cohort's n_C, n_M and n_X for all 547 episodes.
- **F4:**
  - Region = the episode's `noaa_ars`; M1+ = joinable K2 events with flux ≥ 1e-5.
  - HARP labelled span end = the HARP's last row in `data/stage2/oof_scores_dev.csv`. This is the dev hourly file (all dev rows with a gate score, ≤ 2019-12-31); it is used so that no post-2019 row is read. Rows without a gate score are not in it.
  - JUST-FLARED = n_M + n_X ≥ 1; QUIET-NOW = n_C + n_M + n_X = 0.
  - TOO-EARLY = the first region M1+ after t starts > 24 h after t and ≤ the span end. NEVER = no region M1+ in (t, span end].
  - True-rate per history group: weighted (1/n per HARP, Stage 4 weights) with HARP-bootstrap CI (2,000, seed 0), plus counts.
  - ΔCV = step 6 primary; R4a = Phase X.
- **F5:**
  - S1 = log10(median over valid-primary frames of [series `box` × HMI patch pixel count `npix_box`]).
  - S2 = median over frames of `n_bright_px` / `npix_box` (spatial frames).
  - AREA_ACR and USFLUX come from the SHARP magnetogram FITS header at t (`data/euv_full/hmi`, dev).
- **F6:**
  - Per frame, r = mean_k(`pil_k`) / mean_k(`ctrl_k`) from `data/euv_full/series`.
  - B1 = log10(median over valid frames of r); B2 = least-squares slope of log10(r) against hours.
  - Primary uses `valid_primary`; nf uses `valid_sens`. At least 3 valid frames are needed, otherwise undefined.
- Spearman: `scipy.stats.spearmanr`, unweighted, on each candidate's set.

### PHASE F — F2 RESULT (literature ratios under magnetic matching; EXPLORATORY; numbers only)
`phase_f.py F2` → `phase_f_F2.log`, `data/phase_f/F2_ratios.csv`. 9 workers; wall 0.8 s.
- Episodes: 541 primary-valid (96 true / 445 false); the PIL-based measures have 540.
- Ratio = true ÷ false of medians. CI: HARP bootstrap, 2,000 resamples, seed 0.
- Twins: the 81 step 6 pairs; CI by pairs resampled per true HARP.

| measure | median true | median false | ratio (all) [CI] | twins median true / false | ratio (twins) [CI] |
|---|---:|---:|---|---|---|
| box brightening fraction | 0.001133 | 0.000632 | 1.793 [1.137, 2.395] | 0.000997 / 0.000828 | 1.203 [0.838, 1.707] |
| PIL brightening fraction | 0.002428 | 0.001262 | 1.924 [1.228, 2.601] | 0.002305 / 0.001679 | 1.373 [0.887, 2.027] |
| CV_box | 0.2751 | 0.1098 | 2.506 [1.727, 3.772] | 0.2594 / 0.1319 | 1.966 [1.474, 3.173] |
| CV_PIL | 0.4601 | 0.2538 | 1.813 [1.217, 2.540] | 0.4696 / 0.2899 | 1.620 [0.968, 2.585] |
| CV_ctrl | 0.3304 | 0.1294 | 2.554 [1.677, 3.394] | 0.3348 / 0.1439 | 2.326 [1.471, 2.957] |

Context (user): BADPIT reports ~5× brightenings (2 ARs, 12 s cadence). Kniezewski et al. 2024 report ratios > 1 (3 min cadence). The cadence here is 12 min.

### PHASE F — F3 RESULT (what R4a measures: B-class activity; EXPLORATORY; numbers only)
`phase_f.py F3` → `phase_f_F3.log`, `data/phase_f/F3_*.csv`. 9 workers; wall 3.4 s (including the single-process check).

**Checks:**
- The history join reproduces the cohort's n_C, n_M and n_X for all 547 episodes.
- The parallel bootstrap equals the single-process loop for A + R4a (max |diff| 0.0).
- The restated A + R4a equals Phase X.

**1. B-class events** (K2 true scale, deduplicated) per year, and how many carry a region number:

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B events | 674 | 582 | 390 | 327 | 108 | 268 | 748 | 709 | 274 | 184 |
| with region | 493 | 427 | 248 | 260 | 87 | 230 | 589 | 559 | 241 | 161 |
| fraction | 0.732 | 0.734 | 0.636 | 0.795 | 0.806 | 0.858 | 0.787 | 0.788 | 0.880 | 0.875 |

**2. n_B on the R4a set (541):** median 0, IQR [0, 0], max 18; 412 episodes have n_B = 0.

**3. Spearman ρ** (n = 541):
- R4a vs n_B: −0.0167 (p 0.70)
- R4a vs n_B + n_C: 0.6473 (p 1.5e-65)
- R4a vs n_C: 0.7026 (p 1.1e-81). The earlier 0.6901 was on the 528-episode set.

**4. Step 6 procedure** (541 episodes, 96 true / 445 false):

| model | Δ [95% CI] | AUC A | AUC A + x | false removed at ≥ 88% true kept (A + x; A = 70/445, 0.180) | Δ false removed [CI] |
|---|---|---:|---:|---|---|
| A + n_B | −0.0049 [−0.0132, 0.0019] | 0.7422 | 0.7459 | 60/445, 0.149 [0.098, 0.205] | −0.032 [−0.086, +0.022] |
| A + n_B + R4a | 0.0092 [−0.0103, 0.0281] | 0.7422 | 0.7946 | 233/445, 0.530 [0.463, 0.601] | +0.350 [+0.277, +0.430] |
| A + R4a (restated) | 0.0124 [−0.0048, 0.0294] | 0.7422 | 0.8003 | 209/445, 0.487 [0.422, 0.557] | +0.307 [+0.240, +0.383] |

### PHASE F — F4 RESULT (anatomy of false alarms; DESCRIPTIVE; numbers only)
`phase_f.py F4` → `phase_f_F4.log`, `data/phase_f/F4_*.csv`. 9 workers; wall 1.1 s. Episodes: 547 (98 true / 449 false).

**Checks:**
- False episodes with a region M1+ in (t, t + 24 h] before the span end: 0.
- True episodes with one: 89/98. For the other 9, the span end (the HARP's last dev scored row) lies 3–20 h after t, so their flares fall after it.

**Classes (false episodes, 449):**
- JUST-FLARED: 58 (0.129)
- QUIET-NOW: 172 (0.383)
- TOO-EARLY: 59 (0.131)
- NEVER: 390 (0.869)

**Overlaps** (history × future):

| history [t−48h, t) | NEVER | TOO-EARLY | all |
|---|---:|---:|---:|
| C-only history | 185 | 34 | 219 |
| JUST-FLARED | 45 | 13 | 58 |
| QUIET-NOW | 160 | 12 | 172 |
| all | 390 | 59 | 449 |

**TOO-EARLY lead:** median 43.1 h, IQR [31.2, 61.6]; 36 of the 59 are delayed episodes.

**True episodes (98):** zero prior flares 9; JUST-FLARED 42.

**Median [IQR] per class** (primary-valid episodes with a value):

| group | ΔCV n | ΔCV median [IQR] | R4a n | R4a median [IQR] |
|---|---:|---|---:|---|
| JUST-FLARED | 57 | 0.1231 [0.0119, 0.2567] | 57 | 205.8 [88.0, 359.6] |
| QUIET-NOW | 171 | 0.0457 [0.0117, 0.0917] | 172 | 6.37 [1.82, 32.5] |
| TOO-EARLY | 58 | 0.0888 [0.0368, 0.1556] | 58 | 104.9 [65.5, 223.8] |
| NEVER | 386 | 0.0687 [0.0201, 0.1780] | 387 | 31.9 [5.17, 93.4] |
| all false | 444 | 0.0713 [0.0221, 0.1755] | 445 | 41.0 [7.26, 108.8] |
| true | 96 | 0.1007 [0.0415, 0.2142] | 96 | 201.9 [94.3, 397.2] |

**True-rate per history group** (weighted 1/n per HARP; HARP bootstrap 2,000, seed 0):
- zero history: 181 episodes, 9 true; 0.0459 [0.0092, 0.0935]
- any history: 366 episodes, 89 true; 0.1846 [0.1292, 0.2403]

### PHASE F — F5 RESULT (size; EXPLORATORY; numbers only)
`phase_f.py F5` → `phase_f_F5.log`, `data/phase_f/F5_*.csv`. 9 workers; wall 4.5 s. 541 primary-valid episodes (96 true / 445 false); S1 and S2 are defined for all 541.
- AREA_ACR and USFLUX are from the dev SHARP headers at t.
- **Note:** S2 (median over frames of n_bright_px / npix_box) equals the F2 box brightening fraction (median of frac_box) in 524 of 541 episodes (max |diff| 8.0e-06). In F2 the denominator is the box pixels with a finite value, in S2 all box pixels.

**Ratios** (CI: HARP bootstrap, 2,000 resamples, seed 0):

| measure | median true / false | ratio (all) [CI] | twins median true / false | ratio (twins) [CI] |
|---|---|---|---|---|
| S1 log10 total 94 Å | 6.135 / 5.999 | 1.368 [1.056, 1.958] (linear scale) | 6.104 / 6.112 | 0.981 [0.776, 1.407] |
| S2 bright-pixel fraction | 0.001133 / 0.000632 | 1.793 [1.137, 2.395] | 0.000997 / 0.000828 | 1.203 [0.838, 1.707] |

**Spearman ρ** (n = 541):

| | AREA_ACR | USFLUX | gate score | R4a |
|---|---|---|---|---|
| S1 | 0.836 (1.1e-142) | 0.701 (4.0e-81) | 0.535 (2.5e-41) | 0.366 (1.4e-18) |
| S2 | 0.371 (3.9e-19) | 0.502 (7.1e-36) | 0.469 (5.9e-31) | 0.695 (3.9e-79) |

**Step 6 procedure** (541 episodes). At ≥ 88% true kept, A alone removes 70/445 false (0.180):

| model | Δ [95% CI] | AUC A | AUC A + x | false removed (A + x) [CI] | Δ false removed [CI] |
|---|---|---:|---:|---|---|
| A + S1 | −0.0042 [−0.0129, 0.0016] | 0.7422 | 0.7439 | 70/445, 0.147 [0.096, 0.200] | −0.033 [−0.076, +0.009] |
| A + S2 | −0.0057 [−0.0123, 0.0001] | 0.7422 | 0.7398 | 96/445, 0.220 [0.158, 0.281] | +0.040 [−0.009, +0.091] |

### PHASE F — F6 RESULT (PIL brightness level; EXPLORATORY; numbers only)
`phase_f.py F6` → `phase_f_F6.log`, `data/phase_f/F6_*.csv`. 9 workers; wall 1.8 s.
- Sets: primary 540 (96 true / 444 false); flare-excluded 527 (89 / 438).
- Twins: 81 pairs (primary) and 77 pairs (flare-excluded, both members defined).

**Ratios and differences.** B1 is a ratio on the linear scale; B2 is a difference of medians (true − false), per hour. CI: HARP bootstrap, 2,000 resamples, seed 0.

| measure | median true / false | all [CI] | twins median true / false | twins [CI] |
|---|---|---|---|---|
| B1 | 0.1598 / 0.1029 | ratio 1.140 [1.031, 1.292] | 0.1606 / 0.0851 | 1.190 [1.066, 1.333] |
| B2 | 0.001472 / 0.000774 | diff 0.00070 [−0.0008, 0.0026] | 0.001677 / 0.001796 | −0.00012 [−0.0018, 0.0025] |
| B1_nf | 0.1539 / 0.1004 | ratio 1.131 [1.020, 1.266] | 0.1539 / 0.0855 | 1.171 [1.028, 1.306] |
| B2_nf | 0.001536 / 0.000739 | diff 0.00080 [−0.0008, 0.0026] | 0.001843 / 0.001849 | −0.000006 [−0.0022, 0.0022] |

**Spearman ρ:**

| | n_C | gate score | R4a |
|---|---|---|---|
| B1 (n 540) | 0.281 (3.1e-11) | 0.106 (0.014) | 0.519 (1.6e-38) |
| B2 (n 540) | 0.003 (0.94) | −0.001 (0.98) | 0.153 (3.6e-04) |
| B1_nf (n 527) | 0.258 (1.9e-09) | 0.084 (0.055) | 0.503 (3.8e-35) |
| B2_nf (n 527) | 0.011 (0.80) | 0.020 (0.65) | 0.163 (1.7e-04) |

**Step 6 procedure** and operating point (≥ 88% true kept). At that point A alone removes 83/444 false (0.219) on the primary set and 83/438 (0.219) on the flare-excluded set.

| model | n | Δ [95% CI] | AUC A | AUC A + x | false removed (A + x) [CI] | Δ false removed [CI] |
|---|---:|---|---:|---:|---|---|
| A + B1 | 540 | 0.0050 [−0.0050, 0.0149] | 0.7430 | 0.7720 | 107/444, 0.249 [0.191, 0.313] | +0.030 [−0.035, +0.099] |
| A + B2 | 540 | −0.0018 [−0.0089, 0.0056] | 0.7430 | 0.7510 | 105/444, 0.283 [0.221, 0.345] | +0.064 [+0.005, +0.128] |
| A + B1_nf | 527 | 0.0047 [−0.0057, 0.0150] | 0.7490 | 0.7694 | 147/438, 0.355 [0.292, 0.424] | +0.136 [+0.065, +0.199] |
| A + B2_nf | 527 | −0.0023 [−0.0087, 0.0048] | 0.7490 | 0.7442 | 98/438, 0.265 [0.203, 0.325] | +0.045 [−0.012, +0.101] |

Context (user): Leka et al. 2023 found mean intensity "surprisingly poor" at the whole-region level; the PIL-relative level was not tested there.

### PHASE F — F7 SUMMARY (every candidate evaluated on dev; EXPLORATORY; no selection, no interpretation)
`phase_f.py F7` → `phase_f_F7.log`, `data/phase_f/F7_summary.csv`. 9 workers; wall 2.8 s.
- Check: the restated rows equal Stage 4 (pooled Δ, AUC), step 6, Phase X, the R4a flare check, 04b6f4f and F3/F5/F6.
- Δ = LL(A) − LL(A + x); CI: HARP bootstrap, 10,000 resamples, seed 20260921.
- False removed at ≥ 88% weighted true kept (τ in-sample): weighted, with HARP-bootstrap CI (2,000, seed 0), and counts.

| candidate | n (true/false) | Δ | 95% CI | AUC A | AUC A + x | false removed, A | false removed, A + x [CI] |
|---|---|---:|---|---:|---:|---|---|
| trends (B) | 547 (98/449) | 0.0043 | [−0.0123, 0.0249] | 0.7432 | 0.7695 | 0.211 (67/449) | 0.460 [0.393, 0.526] (227/449) |
| ΔCV_94 | 540 (96/444) | −0.0043 | [−0.0092, 0.0003] | 0.7430 | 0.7196 | 0.219 (83/444) | 0.139 [0.090, 0.193] (54/444) |
| R1 | 540 (96/444) | −0.0023 | [−0.0088, 0.0023] | 0.7430 | 0.7406 | 0.219 (83/444) | 0.185 [0.125, 0.243] (76/444) |
| R2 | 540 (96/444) | −0.0031 | [−0.0080, 0.0013] | 0.7430 | 0.7440 | 0.219 (83/444) | 0.090 [0.050, 0.133] (30/444) |
| R3 | 540 (96/444) | −0.0034 | [−0.0132, 0.0041] | 0.7430 | 0.7454 | 0.219 (83/444) | 0.228 [0.167, 0.289] (102/444) |
| R4a | 541 (96/445) | 0.0124 | [−0.0048, 0.0294] | 0.7422 | 0.8003 | 0.180 (70/445) | 0.487 [0.422, 0.557] (209/445) |
| R4b | 541 (96/445) | −0.0051 | [−0.0177, 0.0027] | 0.7422 | 0.7203 | 0.180 (70/445) | 0.145 [0.095, 0.195] (47/445) |
| R4c | 541 (96/445) | 0.0037 | [−0.0058, 0.0132] | 0.7422 | 0.8020 | 0.180 (70/445) | 0.528 [0.455, 0.600] (243/445) |
| R4a_nf | 528 (89/439) | 0.0133 | [−0.0112, 0.0374] | 0.7480 | 0.7990 | 0.231 (88/439) | 0.482 [0.413, 0.553] (208/439) |
| n_B | 541 (96/445) | −0.0049 | [−0.0132, 0.0019] | 0.7422 | 0.7459 | 0.180 (70/445) | 0.149 [0.098, 0.205] (60/445) |
| n_B + R4a (combination) | 541 (96/445) | 0.0092 | [−0.0103, 0.0281] | 0.7422 | 0.7946 | 0.180 (70/445) | 0.530 [0.463, 0.601] (233/445) |
| S1 (size) | 541 (96/445) | −0.0042 | [−0.0129, 0.0016] | 0.7422 | 0.7439 | 0.180 (70/445) | 0.147 [0.096, 0.200] (70/445) |
| S2 (size) | 541 (96/445) | −0.0057 | [−0.0123, 0.0001] | 0.7422 | 0.7398 | 0.180 (70/445) | 0.220 [0.158, 0.281] (96/445) |
| B1 | 540 (96/444) | 0.0050 | [−0.0050, 0.0149] | 0.7430 | 0.7720 | 0.219 (83/444) | 0.249 [0.191, 0.313] (107/444) |
| B2 | 540 (96/444) | −0.0018 | [−0.0089, 0.0056] | 0.7430 | 0.7510 | 0.219 (83/444) | 0.283 [0.221, 0.345] (105/444) |
| B1_nf | 527 (89/438) | 0.0047 | [−0.0057, 0.0150] | 0.7490 | 0.7694 | 0.219 (83/438) | 0.355 [0.292, 0.424] (147/438) |
| B2_nf | 527 (89/438) | −0.0023 | [−0.0087, 0.0048] | 0.7490 | 0.7442 | 0.219 (83/438) | 0.265 [0.203, 0.325] (98/438) |

- The trends row uses 10,000 resamples. The committed Stage 4 CI used 1,000: [−0.0114, 0.0253].
- **Phase F wall times** (9 workers): F2 0.8 s, F3 3.4 s, F4 1.1 s, F5 4.5 s, F6 1.8 s, F7 2.8 s.

### HELD-OUT EUV TEST: DATA DOWNLOAD — RESULT (files only; nothing computed on test years)
`euv_test_download.py run` 13:29–20:43 (wall 7.24 h) → `data/euv_test/`. `euv_test_download.py verify` → `euv_test_verify.log`, `data/euv_test/verify_per_harp.csv`.
- **Exports:** 196 (98 HMI, 98 AIA). JSOC prep 6.31 h in total; downloads 3.80 h, overlapping.
- **Failures:** 0.
- **Retries:** 2, both recovered — a tar read timeout at 13:57 and a status-wait timeout at 18:50.
- **HMI:** magnetogram + bitmap for all 313/313 episode T_RECs (626 files). Header HARPNUM and T_REC match in every case.
- **AIA:** 31,105 files of 31,290 expected (99.41%). All 31,105 have a readable header, WAVELNTH = 94 and a T_REC inside the HARP's record range. No HARP has zero files.
- **Size:** 12.19 GB.
- **Short HARPs:** 42 of 98, 185 frames missing in total; 33 of them are short by ≤ 3 frames. Three are below 97% of expected:
  - 8932: 171/195 (0.877)
  - 12055: 240/270 (0.889)
  - 10235: 115/120 (0.958)
- **For comparison (dev run, `data/euv_full/exports.csv`):** 67 of 179 AIA exports were short (313 frames); 4 were below 97%. Re-exporting those 4 returned identical counts (archive gaps). The 3 test HARPs below 97% have NOT been re-exported; that would be a new download.
- **Label:** no label, model output, ΔCV or R4a has been read or computed for test years.

## 2026-09-25 — HELD-OUT TESTS (decided by: user)
### Step 0 — re-export check: RESULT
AIA re-exported once for HARPs 8932, 12055 and 10235 (`euv_test_download.py reexport`, one pending export, the user's account) into `data/euv_test/reexport/<H>/`.
- Counts are identical: 8932 171/171; 12055 240/240; 10235 115/115. 0 new frames, 0 missing.
- **Recorded as: archive gaps.** Nothing was copied or overwritten.

### Step 1 — PRE-REGISTRATION: HELD-OUT R4a TEST and HELD-OUT OPERATING-POINT TEST (recorded BEFORE any test-year computation)
Check: `grep` found no earlier "HELD-OUT R4a TEST" or "HELD-OUT OPERATING-POINT TEST" in decisions.md, so both are recorded now.

**Disclosure (user, verbatim):** "R4a was not eligible under the Phase X selection rule (85c8285); it was chosen AFTER seeing dev results (Phase X Δ +0.0124 [−0.0048, 0.0294]; flare check 382df4e; ρ(R4a, n_C) = 0.70; operating point 04b6f4f; Phase F). It follows Leka et al. 2023's whole-field κ(ΔI). Test-year labels and magnetic results were seen earlier; test-year EUV values were not. It is one of ~17 candidates evaluated on dev (F7)."

**User's design, verbatim:**
- "R4a test: PRIMARY A vs A+R4a (315ca5b definition); SENSITIVITY A vs A+R4a_nf (382df4e). Models fitted on dev (5 folds, step 6 settings); test prediction = mean of the 5 fold models; weighted Δ = logloss(A) − logloss(A+x); HARP bootstrap 10,000, seed 20260921; weighted AUC; 80% fill; label-blind exclusion; report n valid true/false. Reading: \"adds information on held-out years\" only if PRIMARY Δ > 0 AND CI excludes 0; \"direction consistent, not confirmed\" if Δ > 0 with CI including 0; else \"not confirmed\"."
- "Operating-point test: thresholds frozen from dev, no re-tuning; true kept, false removed (count, weighted %), precision, FAR, with HARP-bootstrap 95% CI (2,000, seed 0); differences (A+R4a − A) in false removed and true kept with CIs. Reading: \"removes more false alarms on held-out years\" only if the false-removed difference > 0 with CI excluding 0 AND true-kept difference ≥ −10 points."
- "Secondary, cannot upgrade the conclusion: A vs A+R4c (315ca5b), same design; frozen dev threshold for A+R4c computed and recorded now."
- "Descriptive: Spearman ρ of R4a with n_C on test."
- Run order (user): "a. ΔCV held-out test exactly as 3283478 item 1h (primary, S1, S2). b. R4a held-out test (primary, sensitivity) + operating-point test. c. R4c secondary. d. Descriptive ρ." Run once; no further analyses on test years.

**Frozen dev thresholds** (τ = in-sample dev OOF, ≥ 88% weighted true kept):

| model | dev set on which it was fitted and τ derived | τ |
|---|---|---|
| A | 528 (R4a flare-check set; 04b6f4f) | 0.071283 (0.0713) |
| A + R4a | 528 (04b6f4f) | 0.061914 (0.0619) |
| A + R4a_nf | 528 (04b6f4f) | 0.061598 (0.0616) |
| A (for the R4c comparison) | 541 (Phase X R4a/R4c set; F7) | 0.067970 |
| A + R4c | 541 (F7, `data/phase_f/F7_summary.csv`) | **0.070734** — computed on dev and recorded now |

**Implementation (decided by: me, before any test-year computation):**
- **Test cohort:** `data/stage5/cohort_test_primary.csv` (313 episodes, 98 HARPs, 2021/2023/2024, single-region; delayed episodes count as false). Features: `score` (mean of the 5 frozen gate fold models, as Stage 5), `n_C`, `n_M`, `n_X`.
- **Test EUV values (step 2):** the same code as dev, run on `data/euv_test/`:
  - `euv_full.compute_episode` gives ΔCV (primary and flare-excluded), fills and the coverage flag.
  - `euv_spatial.spatial_episode` gives R4a and R4c with `valid_primary`, and R4a_nf with `valid_sens`. A `root` argument is added, default `data/euv_full`, so dev behaviour is unchanged.
  - Workers = os.cpu_count() − 1 = 9. Outputs: `data/euv_test/{series,results,spatial,spatial_nf}/`.
- **Test sets:**
  - primary: primary fill ≥ 80% AND the value is defined;
  - flare-excluded: sens fill ≥ 80% AND the value is defined;
  - S2: the primary ΔCV set minus episodes with HMI patch pixels outside the cutout.
  - Test weights: 1/n per HARP over the test analysis set.
- **Models (5 fold models, step 6 settings; test prediction = mean of the 5 fold models' probabilities):**
  - **ΔCV (a):**
    - PRIMARY and S1 use the saved step 6 fold models (`data/euv_full/step6/models/{PRIMARY,S1_flare_excluded}_{A,E94}_fold*.joblib`, dev 540 / 527).
    - S2 is refitted on the dev S2 set (514) with the same procedure. Check: the refitted OOF log-losses must equal step 6 S2.
  - **R4a primary (b):** A and A + R4a fitted on the dev R4a set (541; Phase X).
  - **R4a_nf sensitivity (b):** A and A + R4a_nf fitted on the dev 528 set.
  - **Operating-point test (b):**
    - Uses the 528-set models A, A + R4a and A + R4a_nf with their frozen τ (0.0713 / 0.0619 / 0.0616).
    - A vs A + R4a is evaluated on the test R4a primary set; A vs A + R4a_nf on the test R4a_nf set.
    - For each set, A is scored on the same episodes. Reported: kept = test probability ≥ τ; true kept, false removed (counts, weighted %), precision, FAR; paired differences (A + x − A) in false removed and true kept.
    - CIs: HARP bootstrap, 2,000 resamples, `RandomState(0)`, τ fixed.
  - **R4c (c):**
    - Δ: A and A + R4c fitted on the dev 541 set.
    - Operating point: A (541, τ 0.067970) vs A + R4c (541, τ 0.070734) on the test R4c primary set.
  - **Check:** the refitted dev fold models must reproduce the committed dev OOF log-losses exactly (Phase X / flare check / step 6).
- **Δ bootstrap:** HARP bootstrap over the test HARPs of each set, 10,000 resamples, `RandomState(20260921)`, drawn in the parent; parallel evaluation identical to single process (Phase F method). AUC is weighted.
- **Readings** are applied mechanically as written above. The operating-point differences are in weighted percentage points.
- **(d):** Spearman ρ of R4a with n_C on the test R4a primary set (unweighted).

### Step 2 — test-year EUV values: RESULT (counts only)
`euv_heldout.py compute` → `data/euv_test/{series,results,spatial,spatial_nf}/`; counts in `euv_test_step2_counts.log`.
- **Run:** same code as dev (`euv_full.compute_episode`; `euv_spatial.spatial_episode` with root = data/euv_test). 9 workers (os.cpu_count() − 1). Wall 2.10 h (21:38–23:44). 313/313 episodes, 0 errors.
- **Frames:** 37,370 in total.
  - QUALITY ≠ 0: 1,127
  - exposure rule: 351
  - in P2 flare intervals (removed in the sensitivity version only): 1,848
  - saturation-flagged: 81
- Frame means are reproduced between the spatial pass and the series (max |diff| 0.0).
- **Fill ≥ 80%:**
  - primary: 306/313 (true 44/45, false 262/268);
  - flare-excluded: 294/313 (true 39/45, false 255/268).
- **Label-blind exclusions** (fill passes, value undefined): 0 for ΔCV (both versions), R4a, R4c and R4a_nf.
- **Coverage flag** (HMI pixels outside the cutout on a valid frame; used for S2): 42 episodes in the primary 80% set.

### Step 3 — HELD-OUT TESTS: RESULTS (run once; 2021/2023/2024 single-region T2 cohort; numbers only)
`euv_heldout.py test` → `euv_heldout_test.log`, `data/euv_test/heldout/`.
- **First invocation:** stopped at the pre-test τ check, before any test-year prediction or metric was computed. The default pandas CSV parser returned the stored thresholds with the last digit changed (|diff| ≤ 8e-17). Fix: the two dev files are read with `float_precision="round_trip"`; no design change. The single full run below followed.

**Checks:**
- The dev fold models reproduce step 6: the saved PRIMARY/S1 models have identical coefficients, and the S2 log-losses match.
- They also reproduce Phase X R4a/R4c and the R4a flare check.
- Frozen τ reproduced exactly: A (528) 0.071283, A + R4a 0.061914, A + R4a_nf 0.061598, A (541) 0.067970, A + R4c 0.070734.
- Test frame means: max |diff| 0.0.

**a. ΔCV** (item 1h). Test prediction = mean of the 5 dev fold models. Δ = LL(A) − LL(E94); HARP bootstrap 10,000, seed 20260921.

| set | n (true/false) | HARPs | LL(A) | LL(E94) | Δ | 95% CI | AUC A | AUC E94 |
|---|---|---:|---:|---:|---:|---|---:|---:|
| PRIMARY | 306 (44/262) | 98 | 0.3708 | 0.3683 | 0.0025 | [−0.0074, 0.0139] | 0.8002 | 0.7848 |
| S1 flare-excluded | 294 (39/255) | 98 | 0.3618 | 0.3596 | 0.0022 | [−0.0061, 0.0122] | 0.7868 | 0.7775 |
| S2 no overhang | 264 (42/222) | 90 | 0.3999 | 0.3944 | 0.0055 | [−0.0047, 0.0181] | 0.7967 | 0.8005 |

Label-blind exclusions: 0. S2 removes 42 overhang episodes.

**b. R4a**

| test | n (true/false) | LL(A) | LL(A + x) | Δ | 95% CI | AUC A | AUC A + x |
|---|---|---:|---:|---:|---|---:|---:|
| PRIMARY A vs A + R4a (dev 541 models) | 306 (44/262) | 0.3707 | 0.3623 | 0.0084 | [−0.0227, 0.0418] | 0.8002 | 0.7737 |
| SENSITIVITY A vs A + R4a_nf (dev 528 models) | 294 (39/255) | 0.3617 | 0.3537 | 0.0080 | [−0.0233, 0.0423] | 0.7861 | 0.7824 |

**Pre-stated reading (mechanical):** PRIMARY Δ 0.0084 > 0, CI includes 0 → **"direction consistent, not confirmed"**.

**Operating-point test** (frozen dev τ, 528-set models, no re-tuning). Weighted %; HARP bootstrap 2,000, seed 0.

| set | model | τ | kept | true kept | false removed | precision | FAR |
|---|---|---:|---:|---|---|---|---|
| R4a primary (306) | A | 0.0713 | 248 | 44/44; 1.0000 [1.0000, 1.0000] | 58/262; 0.2758 [0.2001, 0.3598] | 0.1866 [0.1202, 0.2584] | 0.8134 [0.7416, 0.8798] |
| R4a primary (306) | A + R4a | 0.0619 | 198 | 40/44; 0.8704 [0.7127, 0.9886] | 104/262; 0.4385 [0.3485, 0.5284] | 0.2048 [0.1309, 0.2851] | 0.7952 [0.7149, 0.8691] |
| R4a_nf (294) | A | 0.0713 | 237 | 39/39; 1.0000 [1.0000, 1.0000] | 57/255; 0.2738 [0.1985, 0.3570] | 0.1784 [0.1139, 0.2488] | 0.8216 [0.7512, 0.8861] |
| R4a_nf (294) | A + R4a_nf | 0.0616 | 192 | 36/39; 0.8894 [0.7278, 1.0000] | 99/255; 0.4454 [0.3562, 0.5373] | 0.2018 [0.1275, 0.2817] | 0.7982 [0.7183, 0.8725] |

**Differences (A + x − A), paired:**
- A + R4a: false removed +0.1627 [+0.0727, +0.2528] (+46 episodes); true kept −0.1296 [−0.2873, −0.0114] (−4).
- A + R4a_nf: false removed +0.1716 [+0.0824, +0.2595] (+42); true kept −0.1106 [−0.2722, 0.0000] (−3).

**Pre-stated reading (mechanical, A + R4a vs A):** the false-removed difference is > 0 with a CI excluding 0, but the true-kept difference is −12.96 points, below the required ≥ −10 → **condition not met**.

**c. R4c secondary** (cannot upgrade the conclusion; dev 541 models):
- A vs A + R4c: n 306 (44/262). LL(A) 0.3707, LL(A + R4c) 0.3751. Δ −0.0044 [−0.0218, 0.0140]. AUC 0.8002 → 0.7645.
- Operating point:
  - A (τ 0.0680): 306 kept, true kept 44/44, false removed 0/262.
  - A + R4c (τ 0.0707): 190 kept, true kept 39/44 = 0.8943 [0.7863, 0.9762], false removed 111/262 = 0.4684 [0.3778, 0.5559], precision 0.2185 [0.1437, 0.3027], FAR 0.7815 [0.6973, 0.8563].
  - Differences: false removed +0.4684 [+0.3778, +0.5559]; true kept −0.1057 [−0.2137, −0.0238].

**d. Descriptive:** Spearman ρ(R4a, n_C) on the test R4a primary set = 0.6220 (p 3.8e-34, n 306).

STOP. No further analyses on test years.

## 2026-09-26 — HELD-OUT REPLICATION OF F2 (decided by: user; recorded BEFORE computing anything)
**Recorded fact:** this replication was added AFTER the held-out R4a result (7438177) had been seen. Test years 2021/2023/2024 only.

**Hypothesis (wording drafted by Claude AI, reviewed and adopted by Lokesh):** In the held-out years 2021, 2023 and 2024, among true alarms matched to false alarms with a similar gate score (magnetic twins), whole-region AIA 94 Å variability (CV_box) over the 24 hours before the alarm is higher in the true alarm than in its false-alarm twin.

**User's design, verbatim:**
- "Primary measure: CV_box (primary_CV_box, same definition as Phase F F2)."
- "Cohort: data/stage5/cohort_test_primary.csv, primary 80% fill set (306 episodes)."
- "Twins: each true episode matched 1:1 to a false episode on gate score, greedy nearest neighbour, frozen caliper 0.0747, same code as step 6 twins. Report n pairs."
- "Statistic: twins ratio = median(true) / median(false); CI = pairs resampled clustered by true HARP, 2,000, seed 0 (as F2). Also the all-episodes ratio with HARP bootstrap 2,000, seed 0."
- "Pre-stated reading: \"REPLICATED\" if twins ratio > 1 AND CI lower bound > 1; \"direction consistent, not confirmed\" if ratio > 1 with CI including 1; \"NOT REPLICATED\" otherwise."
- "Secondary (cannot change the primary reading): twins matched within the same flare-history group (F4 definitions: JUST-FLARED / C-only / QUIET-NOW), then nearest gate score within caliper 0.0747. Same statistic. Also report CV_ctrl and CV_PIL ratios, descriptive only. Compute the same secondary on dev (2010–2019) as a reference, labelled EXPLORATORY."
- "STEP 1 — If CV_box/CV_ctrl/CV_PIL for test episodes are not already stored, compute them from data/euv_test series with the identical code (no image reprocessing, no downloads). Check: the same code reproduces the dev F2 values (|diff| < 1e-9)."
- "STEP 2 — Run once. Report tables (n, medians, ratios, CIs, reading). Commit. STOP. No further analyses on test years."

**Implementation (decided by: me, before computing):**
- **Code:** `euv_f2_replication.py`; log `euv_f2_replication.log`; tables in `data/euv_test/f2_replication/`.
- **Step 1:** CV_box, CV_PIL and CV_ctrl are already stored for all 313 test episodes (`primary_CV_box`, `primary_CV_PIL`, `primary_CV_ctrl` in `data/euv_test/results/*.json`), written by `euv_full.compute_episode`, the code that produced the dev values. No new computation.
  - **Check:** the ratio code of this script, applied to the dev values and the step 6 twins, must reproduce the committed F2 rows (`data/phase_f/F2_ratios.csv`) for CV_box, CV_PIL and CV_ctrl (|diff| < 1e-9).
- **Test set:** `primary_fill ≥ 0.80` and CV_box defined (306 expected). Delayed episodes count as false.
- **Twins:** the matching code of `euv_step6.twins`.
  - The order of the true episodes is `np.random.RandomState(20260921).permutation(n_true)`.
  - Each true episode takes the nearest unused false episode on gate score from a different HARP, if |Δscore| ≤ 0.07470488674776919.
  - **Check:** on the dev step 6 PRIMARY set, this code must reproduce the 81 committed pairs exactly.
- **Secondary twins:** identical, but the candidate false episodes must share the true episode's flare-history group:
  - JUST-FLARED: n_M + n_X ≥ 1;
  - QUIET-NOW: n_C + n_M + n_X = 0;
  - C-only: otherwise.
- **Statistic:** `phase_f.ratio_jobs` (the F2 code).
  - Ratio = median(true members) ÷ median(false members).
  - Twins CI: pairs resampled clustered by true HARP; all-episodes CI: HARP bootstrap. Both 2,000 resamples, seed 0.
- **Readings** are applied mechanically to the primary twins CV_box row only. CV_PIL and CV_ctrl, and all secondary rows, are descriptive.
- **Dev reference (EXPLORATORY):** the secondary history-group twins on the dev primary 80% set (541), same code.

### HELD-OUT REPLICATION OF F2 — RESULT (run once; numbers only)
`euv_f2_replication.py` → `euv_f2_replication.log`, `data/euv_test/f2_replication/`. 9 workers; wall 1.0 s.

**Checks:**
- The twins code reproduces the 81 step 6 dev pairs exactly.
- The ratio code reproduces the committed F2 rows (CV_box, CV_PIL, CV_ctrl: medians, ratios, CIs).
- Step 1 needed no computation: the test CV values were already stored.

**Test set:** 306 episodes (44 true / 262 false, 98 HARPs); CV_PIL and CV_ctrl are defined for all.

**Twins:**
- Primary (test): 40 pairs of 44 true episodes; max |Δscore| 0.0469. By group: C-only 21, JUST-FLARED 15, QUIET-NOW 4.
- History-group (test): 37 pairs; max |Δscore| 0.0375. C-only 20, JUST-FLARED 14, QUIET-NOW 3.
- History-group (dev, EXPLORATORY): 78 pairs of 96; max |Δscore| 0.0742. C-only 40, JUST-FLARED 29, QUIET-NOW 9.

**Ratios.** Ratio = median(true) ÷ median(false). All-episodes CI: HARP bootstrap; twins CI: pairs resampled by true HARP. Both 2,000 resamples, seed 0.

| twins | measure | n (true/false) | median true / false | ratio (all) [CI] | pairs | twins median true / false | ratio (twins) [CI] |
|---|---|---|---|---|---:|---|---|
| **TEST primary** | **CV_box** | 306 (44/262) | 0.1741 / 0.1112 | 1.566 [1.119, 2.428] | 40 | 0.1594 / 0.1221 | **1.306 [0.937, 2.218]** |
| TEST primary | CV_PIL (descriptive) | 306 | 0.3731 / 0.2599 | 1.435 [1.074, 2.340] | 40 | 0.3519 / 0.2606 | 1.350 [0.885, 2.353] |
| TEST primary | CV_ctrl (descriptive) | 306 | 0.2387 / 0.1309 | 1.824 [1.233, 2.782] | 40 | 0.2220 / 0.1326 | 1.675 [1.034, 2.574] |
| TEST history-group (secondary) | CV_box | 306 | as above | as above | 37 | 0.1589 / 0.1442 | 1.102 [0.653, 1.710] |
| TEST history-group (secondary) | CV_PIL | 306 | | | 37 | 0.3675 / 0.3832 | 0.959 [0.696, 1.577] |
| TEST history-group (secondary) | CV_ctrl | 306 | | | 37 | 0.2176 / 0.1671 | 1.303 [0.827, 2.188] |
| DEV history-group (EXPLORATORY) | CV_box | 541 (96/445) | 0.2751 / 0.1098 | 2.506 [1.727, 3.772] | 78 | 0.2509 / 0.1450 | 1.730 [1.359, 2.603] |
| DEV history-group (EXPLORATORY) | CV_PIL | 540 | 0.4601 / 0.2538 | 1.813 [1.217, 2.540] | 78 | 0.4408 / 0.3531 | 1.249 [0.775, 1.721] |
| DEV history-group (EXPLORATORY) | CV_ctrl | 540 | 0.3304 / 0.1294 | 2.554 [1.677, 3.394] | 78 | 0.3222 / 0.1650 | 1.953 [1.192, 2.559] |

**Pre-stated reading (mechanical; primary = TEST primary twins, CV_box):** ratio 1.3057 > 1, CI [0.9367, 2.2182] includes 1 → **"direction consistent, not confirmed"**.

STOP. No further analyses on test years.

## 2026-09-26 — EXPLORATORY: THREE LOCALISED 94 Å AREAS (decided by: user; design drafted by Claude AI, adopted by the student; recorded BEFORE computing)
**Status:**
- Added AFTER all held-out results (7438177, ec00afb) had been seen.
- DEV-ONLY EXPLORATORY: dev 2010–2019 only; nothing for 2021–2024 or 2025–26 is read or computed. Frozen files unchanged.
- Dev candidates evaluated so far: 16. This entry adds 3 (M1 SG-PIL, M2 CORE, M3 SPOT), for 19 in total.

**User's definitions, verbatim:**
- "all masks built once on the alarm-time LoS magnetogram / window, label-blind, as flat HMI-pixel index sets, mapped to every frame with euv_dctrl.hmi_to_frame exactly as S"
- "M1 SG-PIL (strong-gradient PIL, after Falconer, Moore & Gary 2003):"
  - "B = magnetogram (nan -> 0). mm_px = CDELT1 * RSUN_REF / RSUN_OBS / 1e6 (header)."
  - "Block-average B in 4x4 HMI pixels (drop the incomplete edge rows/cols) -> r (~1.45 Mm, ~ the MDI resolution at which 50 G/Mm was defined)."
  - "g = |grad r| with np.gradient(r, 4*mm_px) [G/Mm]."
  - "NL = blocks where r changes sign against any 4-neighbour."
  - "Keep NL blocks lying entirely inside euv_pilot.pil_mask(B) (all 16 pixels) AND g > 50."
  - "SG-PIL = the HMI pixels of those blocks. No further dilation."
  - "Documented deviations: Falconer's potential-transverse-field > 150 G criterion is replaced by the PIL-mask requirement; no 30° disk-centre restriction; no foreshortening correction."
- "M2 CORE: V = per-HMI-pixel values over valid_primary frames (as in spatial_episode). Per-pixel nanmedian over those frames; CORE = top 1% of pixels with a finite median (count = ceil(0.01 * n_finite); stable argsort). The same mask is used for both versions."
- "M3 SPOT: |B| >= 1000 G on the alarm-time magnetogram (design choice, not from a paper; LoS field, no projection correction — documented limitation)."
- "Per-frame value = mean over the mask (euv_dctrl.frame_means). CV_M = euv_dctrl.cv over the valid frames. Feature = log10(CV_M) (reason recorded: dev CV_box skew 2.19 raw, -0.07 log10, checked label-blind). Undefined if the mask is empty or has < 3 valid frames with finite means -> label-blind exclusion, n reported."
  - Note (me, label-blind, before recording): on the dev primary 80% set (541 CV_box values, no labels read), `scipy.stats.skew` (bias = True) gives 2.176 raw and −0.073 for log10.
- "STEP 1 — Code (new file euv_masks.py; reuse spatial_episode's frame processing exactly: same files, update_pointing, register_cutout, SAT_DN, valid_primary rows). Selftests: (a) synthetic bipole with a sharp sign change -> SG-PIL non-empty; the same bipole with a smooth wide transition (g < 50 G/Mm) -> empty; (b) SPOT threshold at exactly 1000 G included; (c) CORE count = ceil(1%) and deterministic. Checks per episode: every frame's box mean equals the stored series (|diff| < 1e-9); recomputed CV_box equals stored primary_CV_box (|diff| < 1e-9). Assert; stop on failure."
- "STEP 2 — Timing on 3 episodes, then the full dev run with ProcessPoolExecutor (os.cpu_count() - 1 workers). Outputs: data/euv_full/masks/<eid>.json and _frames.csv. Before any label is used, report (label-blind): mask pixel counts (median/min/max) per mask, n undefined per mask, median overlap fractions (SG∩SPOT, SG∩CORE, CORE∩SPOT, each / smaller mask), wall time. Commit."
- "STEP 3 — Evaluation, run once (dev):"
  - "PRIMARY per mask: euv_spatial.compare procedure (A vs A + log10 CV_M; same folds, weights 1/n per HARP, estimator; HARP bootstrap 10,000, seed 20260921) on the primary 80% set with the value defined. From the SAME resamples report the 95% CI and the Bonferroni 98.33% CI (0.833 / 99.167 percentiles). Check first: the modified function reproduces the committed Phase X R4a 95% CI exactly."
  - "Pre-stated reading per mask: \"ELIGIBLE for independent confirmation\" only if Δ > 0 AND the 98.33% CI lower bound > 0 AND AUC(A + M) > AUC(A); otherwise \"NOT ELIGIBLE\". Apply mechanically."
  - "SECONDARY (descriptive; cannot change any reading):"
    - "s1 A + log10 CV_box vs A + log10 CV_box + log10 CV_M (does the area add beyond the whole region?) — Δ, 95% CI, AUC."
    - "s2 CV_M twins ratios with the F2 ratio code: the 81 gate-score twins (data/euv_full/step6/twins_PRIMARY.csv) and the same-flare-history twins (euv_f2_replication.py dev code)."
    - "s3 flare-excluded version (valid_sens frames, sens_fill >= 0.80): the PRIMARY comparison."
    - "s4 Spearman rho of each log10 CV_M with n_C, n_M, n_X, gate score and log10 CV_box."
  - "Report the tables, commit, STOP. Nothing on 2021–2024 or 2025–26."

**Implementation (decided by: me, before computing):**
- **Episodes:** the 546 dev episodes with stored series. Frames = the stored `valid_primary` rows, processed exactly as in `euv_spatial.spatial_episode`. HMI/AIA files come from `data/euv_full`; the pointing table is the same JSOC keyword query.
- **NL (sign change):** r[i, j] · r[neighbour] < 0 for any of the 4 neighbours.
- **g:** `np.hypot(*np.gradient(r, 4 * mm_px))`.
- **CORE ordering:** descending per-pixel median, `np.argsort(-median, kind="stable")` over the finite-median pixels, first ceil(0.01 · n_finite).
- **SPOT:** `np.abs(B) >= 1000` on the magnetogram with NaN pixels excluded.
- **Per-frame mask mean:** `euv_dctrl.frame_means` on each registered frame, for box, SG-PIL and SPOT. For CORE, the identical formula (nanmean of the mapped values, NaN if none finite) is applied to the stored per-frame mapped values after the loop, because the mask needs every frame first.
- **CV versions:** CV_M (primary) over `valid_primary` frames; CV_M_nf over `valid_sens` frames.
- **Undefined:** the mask is empty, fewer than 3 valid frames have finite means, or CV ≤ 0.
- **Evaluation:**
  - The step 6 / `euv_spatial.compare` procedure, via `euv_spatial.cv_fit`; the bootstrap is drawn in the parent and evaluated in parallel (Phase F method, identical to single process).
  - Percentiles for the Bonferroni CI: 0.833 / 99.167, as stated.
  - s1 uses log10(`primary_CV_box`) from the stored results, on the set where both values are defined.
  - s2 uses raw CV_M, with `phase_f.ratio_jobs` (mode ratio, 2,000 resamples, seed 0).
  - s4 is unweighted Spearman on the PRIMARY set of each mask.

## 2026-09-26 — EXPLORATORY: TEMPORAL CONTRAST K3 (decided by: user; design drafted by AI, adopted by the student; recorded BEFORE computing)
**Status:**
- Added AFTER all held-out results (7438177, ec00afb) had been seen.
- DEV-ONLY EXPLORATORY: nothing for 2021–2024 or 2025–26; no image reprocessing, no downloads. Frozen files unchanged.
- Dev candidates so far: 16. This entry adds 1 (K3).

**Relation to the three-mask plan (bebbfe6):**
- The user's K3 entry says it "Replaces the three-mask plan (not run)", and the user asked for K3 to run "at the same time".
- When K3 arrived, the three-mask label-blind computation (bebbfe6 step 2) had already started (00:28). It continues; it is label-blind.
- No mask has been evaluated against labels. The three-mask step 3 evaluation is ON HOLD and will not be run unless the user decides otherwise. On the user's count the masks are therefore not counted as evaluated candidates (16 + 1 = 17).

**User's text, verbatim:**
- "Motivation (verified): Kniezewski et al. 2024 (ApJL 977:L29) report variability rising 2–4 h before onset (off-limb loops, other channels, flare-centred windows; does not validate this feature). Known limit: dev true alarms lead 0–6 h n=31, 6–24 h n=65 (step 6 diagnostic)."
- "DEFINITION (per episode, from data/euv_full/spatial/<eid>_pairs.csv, kappa_box as in Phase X):"
  - "t = cohort alarm time. LATE = pairs with t_obs > t − 3 h; EARLY = pairs with t_obs <= t − 3 h. (Pair time = later frame's t_obs; frames were selected by T_REC <= t, so t_obs may exceed t by <= ~8 s; accepted, recorded.)"
  - "K3 = log10( median(kappa_box LATE) / median(kappa_box EARLY) )."
  - "Undefined if LATE has < 5 pairs or either median <= 0 -> label-blind exclusion, n reported."
  - "3 h is fixed in advance; no other windows are computed."
  - "Flare-excluded version K3_nf: same from data/euv_full/spatial_nf/<eid>_pairs.csv."
- "STEP 1 — Compute K3 and K3_nf for all dev episodes. Label-blind report: n defined, n excluded, LATE-pair counts, K3 percentiles. Commit."
- "STEP 2 — Evaluate once. Same procedure as euv_spatial.compare (folds, weights 1/n per HARP, estimator, HARP bootstrap 10,000, seed 20260921), on the primary 80% set with K3 defined."
  - "PRIMARY: base = A_COLS + [\"R4a\"] (Phase X values as committed) vs base + [\"K3\"]. Check first: A vs A + R4a on the Phase X 541 set reproduces the committed Phase X values."
  - "Pre-stated reading: \"ELIGIBLE for independent confirmation\" only if Δ > 0 AND 95% CI lower bound > 0 AND AUC(base + K3) > AUC(base); else \"NOT ELIGIBLE\". Apply mechanically."
  - "SECONDARY (descriptive; cannot change the reading): s1 A vs A + K3 (without R4a). s2 flare-excluded: A_COLS + [\"R4a_nf\"] vs + [\"K3_nf\"] on the sens 80% set. s3 true episodes only: median K3 for lead (0, 6] h vs (6, 24] h (lead as in the step 6 diagnostic), with n. s4 Spearman rho of K3 with n_C, n_M, n_X, gate score and R4a."
  - "Report the tables, commit, STOP."

**Implementation (decided by: me, before computing):**
- **Code:** `euv_k3.py compute | eval`. Outputs in `data/euv_full/k3/`.
- **Alarm time:** t = `t` of `data/stage4/oof_cohort_dev.csv` (UTC); pair time = the pairs-file `t_obs`.
- **Pair counting:** only pairs with a finite `kappa_box` are counted and used (LATE count and medians). EARLY must contain ≥ 1 such pair, otherwise its median is undefined → excluded.
- **Evaluation:** `euv_spatial.cv_fit` with the given feature lists; weights 1/n per HARP over each set; bootstrap drawn in the parent (Phase F method, identical to single process).
  - PRIMARY set: `primary_fill ≥ 0.80` AND K3 defined AND R4a defined.
  - s1: the same set.
  - s2: `sens_fill ≥ 0.80` AND K3_nf and R4a_nf defined.
- **s3 lead:** `data/euv_full/step6/explore_2_timing.csv` (`lead_h`, the step 6 diagnostic), true episodes with K3 defined.
- **s4:** unweighted Spearman on the PRIMARY set.

### K3 — Step 1 RESULT (label-blind; no labels read)
`euv_k3.py compute` → `euv_k3_compute.log`, `data/euv_full/k3/k3_values.csv`. 547 dev episodes; pairs files for 546 (HARP 8 has no AIA).

| version | set | defined | excluded (LATE < 5 pairs) | LATE pairs median / min / max | K3 percentiles 0 / 5 / 25 / 50 / 75 / 95 / 100 |
|---|---|---:|---:|---|---|
| K3 | primary 80% (541) | 540 | 1 | 16 / 4 / 16 | −1.6132 / −0.6717 / −0.2131 / 0.0201 / 0.3443 / 1.1349 / 2.9062 |
| K3_nf | flare-excluded 80% (528) | 526 | 2 | 16 / 4 / 16 | −1.6745 / −0.6648 / −0.2098 / 0.0217 / 0.3621 / 1.1475 / 2.9062 |

### K3 — Step 2 RESULT (evaluated once; EXPLORATORY; dev 2010–2019, internal 5-fold CV; numbers only)
`euv_k3.py eval` → `euv_k3_eval.log`, `data/euv_full/k3/`. 9 workers; wall 3.5 s.
- Check: A vs A + R4a on the Phase X 541 set reproduces Phase X exactly (Δ 0.0124 [−0.0048, 0.0294], AUC 0.7422 → 0.8003).
- Sets: PRIMARY 540 of the 541 primary-80% episodes (1 excluded label-blind); s2 526 of 528 (2 excluded).

| test | n (true/false) | HARPs | LL(base) | LL(base + x) | Δ | 95% CI | AUC base | AUC base + x |
|---|---|---:|---:|---:|---:|---|---:|---:|
| PRIMARY A + R4a vs A + R4a + K3 | 540 (96/444) | 179 | 0.3082 | 0.3068 | 0.0013 | [−0.0069, 0.0095] | 0.8008 | 0.8039 |
| s1 A vs A + K3 | 540 (96/444) | 179 | 0.3206 | 0.3207 | −0.0001 | [−0.0062, 0.0060] | 0.7423 | 0.7515 |
| s2 A + R4a_nf vs A + R4a_nf + K3_nf | 526 (88/438) | 179 | 0.3229 | 0.3229 | −0.0000 | [−0.0071, 0.0069] | 0.7975 | 0.7942 |

**Pre-stated reading (mechanical, PRIMARY):** Δ +0.0013 > 0, but the 95% CI lower bound (−0.0069) is not > 0 → **"NOT ELIGIBLE"**.

**s3** (true episodes; lead from the step 6 diagnostic): median K3 0.1272 for lead (0, 6] h (n 31) and 0.0364 for lead (6, 24] h (n 65).

**s4 Spearman ρ of K3** (n 540):

| n_C | n_M | n_X | gate score | R4a |
|---|---|---|---|---|
| −0.170 (p 7.2e-05) | −0.131 (0.0023) | 0.042 (0.33) | −0.102 (0.017) | −0.135 (0.0017) |

## 2026-09-26 — EXPLORATORY ROBUSTNESS CHECK: log R4a (decided by: user; design drafted by AI, adopted by the student; recorded BEFORE computing)
**Status:**
- Added AFTER R4a's held-out result (7438177), as a check of whether that result depends on feeding raw R4a.
- Motivation (user): Leka et al. 2023 §3.2.2, "NCI automatically works with the natural logarithm of the variable".
- Not a confirmation; cannot be tested on 2021–2024. DEV 2010–2019 ONLY; no image reprocessing; nothing on 2021–2024 or 2025–26.
- Dev candidates total (user): 21 = 16 + 3 masks (bebbfe6; their evaluation is still on hold) + K3 + lnR4a.

**User's design, verbatim:**
- "DEFINITION: lnR4a = ln(R4a + 3) (R4a = excess kurtosis, bias=True, so R4a + 3 >= 1). Undefined R4a stays undefined."
- "EVALUATION (once): Phase X set (541), euv_spatial.compare procedure unchanged (folds, weights, estimator, HARP bootstrap 10,000, seed 20260921)."
  - "Check first: A vs A + R4a reproduces committed Phase X values."
  - "PRIMARY: A vs A + lnR4a. Report Δ, 95% CI, AUC, next to the committed A vs A + R4a row."
  - "Also: A + R4a vs A + lnR4a directly (paired, same resamples): difference in log-loss, 95% CI."
  - "Flare-excluded: A vs A + ln(R4a_nf + 3) on the 528 set."
- "Pre-stated reading: \"log matters\" only if the paired difference (A + lnR4a better than A + R4a) has a 95% CI above 0; otherwise \"raw vs log makes no clear difference\"."

**Implementation (me):**
- Code `euv_lnr4a.py`.
- Paired difference = LL(A + R4a) − LL(A + lnR4a) (positive = the log version is better). Its bootstrap uses the same HARP resamples as the other rows on the 541 set: the same seed and set give the same resample stream.
- Check: every R4a value is ≥ −3, so the log is defined wherever R4a is.
- Sets: the Phase X 541 (`primary_fill ≥ 0.80`, R4a defined) and the flare-check 528 (`sens_fill ≥ 0.80`, R4a_nf defined). Weights 1/n per HARP over each set.

### log R4a check — RESULT (evaluated once; EXPLORATORY; dev 2010–2019, internal 5-fold CV; numbers only)
`euv_lnr4a.py` → `euv_lnr4a.log`, `data/euv_full/spatial/eval_lnr4a.csv`. 9 workers; wall 7.1 s. The check reproduced committed Phase X exactly.

| test | n (true/false) | LL(base) | LL(base + x) | Δ | 95% CI | AUC base | AUC base + x |
|---|---|---:|---:|---:|---|---:|---:|
| A vs A + R4a (committed Phase X row) | 541 (96/445) | 0.3206 | 0.3082 | 0.0124 | [−0.0048, 0.0294] | 0.7422 | 0.8003 |
| PRIMARY A vs A + lnR4a | 541 (96/445) | 0.3206 | 0.3025 | 0.0181 | [0.0005, 0.0349] | 0.7422 | 0.7976 |
| paired A + R4a vs A + lnR4a (+ = log better) | 541 | 0.3082 | 0.3025 | 0.0057 | [−0.0087, 0.0204] | 0.8003 | 0.7976 |
| flare-excluded A vs A + ln(R4a_nf + 3) | 528 (89/439) | 0.3359 | 0.3202 | 0.0157 | [−0.0101, 0.0372] | 0.7480 | 0.7870 |

**Pre-stated reading (mechanical):** paired difference +0.0057, CI [−0.0087, +0.0204] not above 0 → **"raw vs log makes no clear difference"**.

### Three localised areas — Step 1–2 RESULT (label-blind; no labels read; the evaluation, step 3, is still ON HOLD)
`euv_masks.py selftest | timing | run | report` → `euv_masks_report.log`; outputs in `data/euv_full/masks/`.
- **Selftest passed:**
  - Sharp bipole: SG-PIL 512 px. Smooth bipole: SG-PIL 0 px (NL blocks inside the PIL mask have a maximum g of 38.7 G/Mm).
  - SPOT includes |B| = 1000 G.
  - CORE takes ceil(1%) with stable ties and is deterministic.
  - Test-fixture change before the pass: the smooth ramp was 12 G/px, but its PIL band (columns 29–34) held no complete 4×4 block, so it did not isolate the g criterion. It was changed to 14 G/px (38.7 G/Mm).
- **Code fix before the run:** `data/euv_full/results/` also holds `step4_choice.json` (no `eid`), which is now skipped when the stored CV_box values are read.
- **Timing:** 3 episodes (RandomState(0)), single process, 57 s in total. Box means and CV_box reproduced (≤ 5.6e-17).
- **Full run:** 546/546 dev episodes, 9 workers (os.cpu_count() − 1), wall 1.15 h (00:28–01:37). Checks in every episode: max frame box-mean |diff| 0.0; max CV_box |diff| 2.2e-16.

**Mask pixel counts and undefined values:**

| mask | pixels median / min / max | empty | undefined log10 CV: all / primary 80% (541) / flare-excluded 80% (528) |
|---|---|---:|---|
| SG-PIL | 3,056 / 0 / 19,648 | 3 | 3 / 3 / 3 |
| CORE | 3,346 / 548 / 10,563 | 0 | 0 / 0 / 0 |
| SPOT | 1,098 / 0 / 9,003 | 5 | 6 / 6 / 6 |

**Median overlap** (intersection ÷ smaller mask, episodes with both masks non-empty):
- SG ∩ SPOT: 0.0000 (n 541)
- SG ∩ CORE: 0.1236 (n 543)
- CORE ∩ SPOT: 0.0206 (n 541)

### Three localised areas — go-ahead for step 3 (decided by: user; recorded BEFORE the evaluation)
- User: "run the three-mask evaluation once, exactly as pre-registered in bebbfe6. Each mask evaluated SEPARATELY (one feature added to A at a time; no model combines M1, M2, M3). Name M2 \"brightest core\" in all outputs (94 Å brightness is not temperature). Record: this is the final dev candidate; total dev candidates = 21 (16 + K3 + log R4a + 3 masks). Report, commit, STOP. No further candidates after this."
- **Recorded:** the three masks are the FINAL dev candidates. Total dev candidates = 21 (16 + K3 + log R4a + 3 masks). No further candidates after this.
- **Implementation (me):** the bebbfe6 evaluation code is unchanged except for the output labels (SG → "SG-PIL", CORE → "brightest core", SPOT → "SPOT"). Each mask is added to A alone.

### Three localised areas — Step 3 RESULT (evaluated once; EXPLORATORY; dev 2010–2019, internal 5-fold CV; numbers only)
`euv_masks.py eval` → `euv_masks_eval.log`, `data/euv_full/masks/eval_*.csv`. 9 workers; wall 1.9 s.
- Check: the modified compare reproduces Phase X R4a exactly (Δ 0.0124, 95% CI [−0.0048, 0.0294]).
- Each mask is evaluated separately; no model combines M1–M3.

**PRIMARY: A vs A + log10 CV_M.** HARP bootstrap 10,000, seed 20260921; the 95% and Bonferroni 98.33% CIs come from the same resamples.

| mask | n (true/false) | excluded label-blind | Δ | 95% CI | 98.33% CI | AUC A | AUC A + M | reading |
|---|---|---:|---:|---|---|---:|---:|---|
| SG-PIL | 538 (96/442) | 3 | +0.0013 | [−0.0066, 0.0095] | [−0.0082, 0.0112] | 0.7409 | 0.7637 | NOT ELIGIBLE |
| brightest core | 541 (96/445) | 0 | +0.0026 | [−0.0049, 0.0099] | [−0.0067, 0.0115] | 0.7422 | 0.7756 | NOT ELIGIBLE |
| SPOT | 535 (96/439) | 6 | −0.0041 | [−0.0103, 0.0018] | [−0.0118, 0.0030] | 0.7402 | 0.7286 | NOT ELIGIBLE |

**Pre-stated readings (mechanical):** none of the three masks has a 98.33% CI lower bound > 0 → all three **"NOT ELIGIBLE"**.

**s1 (descriptive): A + log10 CV_box vs A + log10 CV_box + log10 CV_M**

| mask | n | Δ | 95% CI | AUC base → full |
|---|---:|---:|---|---|
| SG-PIL | 538 | −0.0042 | [−0.0079, −0.0010] | 0.7947 → 0.7798 |
| brightest core | 541 | −0.0017 | [−0.0032, −0.0003] | 0.7972 → 0.7929 |
| SPOT | 535 | −0.0060 | [−0.0112, −0.0017] | 0.7915 → 0.7716 |

**s2 (descriptive): CV_M ratios, true ÷ false of medians** (2,000 resamples, seed 0):

| mask | all-episodes ratio [CI] | 81 gate-score twins [CI] | 78 same-flare-history twins [CI] |
|---|---|---|---|
| SG-PIL | 1.746 [1.294, 2.208] | 1.595 [1.017, 2.392] | 1.267 [0.875, 1.617] |
| brightest core | 1.721 [1.344, 2.315] | 1.578 [1.141, 2.180] | 1.210 [0.928, 1.641] |
| SPOT | 2.092 [1.418, 3.195] | 1.877 [1.116, 2.809] | 1.139 [0.747, 1.812] |

**s3 (descriptive): flare-excluded, A vs A + log10 CV_M_nf**

| mask | n (true/false) | Δ | 95% CI | 98.33% CI | AUC A → A + M |
|---|---|---:|---|---|---|
| SG-PIL | 525 (89/436) | +0.0022 | [−0.0080, 0.0125] | [−0.0100, 0.0150] | 0.7479 → 0.7688 |
| brightest core | 528 (89/439) | +0.0015 | [−0.0096, 0.0110] | [−0.0124, 0.0128] | 0.7480 → 0.7746 |
| SPOT | 522 (89/433) | −0.0027 | [−0.0087, 0.0031] | [−0.0102, 0.0043] | 0.7467 → 0.7348 |

**s4 (descriptive): Spearman ρ of log10 CV_M**

| mask | n_C | n_M | n_X | gate score | log10 CV_box |
|---|---|---|---|---|---|
| SG-PIL (n 538) | 0.527 | 0.378 | 0.212 | 0.299 | 0.809 |
| brightest core (n 541) | 0.569 | 0.325 | 0.208 | 0.308 | 0.853 |
| SPOT (n 535) | 0.466 | 0.333 | 0.202 | 0.231 | 0.715 |

All p < 1e-5.

**Final dev candidate list closed:** 21 candidates in total. STOP.

## 2026-09-26 — 2025–26 CONFIRMATION SET: DOWNLOAD + LABEL-BLIND COMPUTATION ONLY (decided by: user; recorded BEFORE doing anything)
**User's text, verbatim:**
- "No evaluation, no true/false split printed or inspected. Frozen files unchanged."
- "STEP 0 — Read decisions.md for the recorded 2025–26 confirmation-set rules (frozen end T_REC 2026-08-16, subset rule, the 6 overlapping HARPs excluded, label build) and follow them exactly. … Check and report: GOES-16+ era labels are on the true flux scale (no ÷0.7 applied to post-GOES-15 data) as recorded."
- "STEP 1 — Gate scoring (label-blind): score the frozen gate (5 fold models, threshold -0.9925) on the 2025–26 SHARP rows; build episodes with the frozen cohort rules (T1–T4). Report ONLY: number of episodes and HARPs, for single-region and for the recorded subset separately. Do not print or look at true/false counts."
- "STEP 2 — Download plan (dry run first): same as the test-year download (euv_test_download.py pattern): AIA 94 Å, 12-min, (t−24h, t], tracked im_patch cutouts; HMI sharp_720s LoS magnetogram + bitmap at t. Output root data/euv_confirm/. Report expected episodes, exports, estimated GB (test years were 12.19 GB for 313 episodes) and estimated hours. Then run it. JSOC rules: my account only, ONE pending export at a time, never a second account."
- "STEP 3 — Compute values with the identical code as the test years (euv_full.compute_episode, euv_spatial.spatial_episode with root = data/euv_confirm; masks and K3 not needed). Report: n episodes, fill counts at 80%, n undefined, errors, wall time. Commit."
- "STOP. Nothing is evaluated against labels until I send a pre-registration."

**Recorded rules followed** (quoted from this log):
- "CONFIRMATION SET FROZEN … T_REC 2025-01-01 00:00 TAI → 2026-08-16 23:00 TAI"
- Label build (Step 1 results): `data/labelled_20250101_20260817.csv`, SHA-256 `1f6673956db3599616fe4d04fbd14b285a383737156a49d393f6c5d617c49263`, identical rules — K2, missing-day (2025-12-30 and 2025-12-31 are 404 days), empty-day, history_incomplete, region_group.
- "Confirmation set PAUSED; decisions on overlap and subset": "The 6 HARPs that also appear in 2021–2024 are excluded" and "The <= 2-region fallback applies to the confirmation set".
- The 2026-09-21 feasibility check: "flare scale 2025+ … XRA from GOES-18/19 = true scale; `swpc.py` already treats G16–G19 as true scale (K2: used as reported)".
- `NOAA_ARS` is used only for flare–region linking, never as a model input.

**Implementation (decided by: me, before doing anything):**
- **Code:** `euv_confirm.py check | cohort | plan | download | verify | compute`. Everything under `data/euv_confirm/`.
- **check:**
  - Verify the labelled-file hash.
  - GOES scale: `swpc.FLARE_SCALE == "K2"`. For every XRA event 2024-12-29 → 2026-08-18, count events per satellite; expect none from G13/14/15. For G16–G19 events, check flux == flux_reported (no ÷0.7).
  - Identify the 6 overlapping HARPs: confirmation-file HARPs that are in `frozen/split.csv` (read-only), count asserted = 6.
- **cohort:** as Stage 5 (`stage5_test.py`):
  - Rows with a missing gate feature are unscorable and dropped. Score = mean of the 5 frozen gate fold decision values; threshold −0.9924957750431066.
  - `cohort.build` (T1–T4) on each subset's scored rows. The trend windows use every labelled confirmation row of the HARP; `swpc.label_missing_days()` is used.
  - Subsets: single (`noaa_ar_count == 1`) and the recorded fallback ≤ 2 (`noaa_ar_count <= 2`).
  - Cohort files are written to `data/euv_confirm/`. Only the numbers of episodes and HARPs are printed; no label column is printed or inspected.
- **Download set:** the union of the two cohorts' episodes (same eid = same HARP and t), so both subsets are covered.
  - Per HARP: one HMI export (magnetogram + bitmap at all union T_RECs) and one AIA 94 Å im_patch export (`euv_full.aia_spec`: the HARP's earliest t − 24 h + 12 min → latest t, 12 min).
  - Driver: `euv_full.run_pipeline(compute=False)`: url-tar, one pending export at a time, the user's account only, resumable, progress every 30 min.
  - Plan (dry run): prep = 72 s + 0.2 s/file per export × 1.27 (the ratio of test wall time to modelled prep time). GB from the test-year bytes per file.
- **compute:** `euv_heldout.test_episode` logic with root `data/euv_confirm`: `euv_full.compute_episode` + `euv_spatial.spatial_episode` (valid_primary and valid_sens); 9 workers. Only counts are reported.

### Confirmation set — Step 0 check, Step 1 cohort and download plan: RESULTS (label-blind; no true/false count printed or inspected)
`euv_confirm.py check | cohort | plan` → `data/euv_confirm/logs/{check,cohort,plan}.log`.

**Step 0 checks:**
- Labelled-file hash verified (`1f667395…`).
- **GOES scale:**
  - `swpc.FLARE_SCALE = K2`.
  - XRA events 2024-12-29 → 2026-08-18: 5,292 — G18 3,860, G16 801, G19 631.
  - Events from GOES-13/14/15: 0. GOES-16+ events with flux ≠ reported (i.e. ÷0.7 applied): 0. Other observatories: 0.
  - → the labels of the GOES-16+ era are on the true flux scale, with no ÷0.7 applied, as recorded.
- **Overlapping HARPs** (in `frozen/split.csv`, i.e. 2010–2024): 6 — 12471, 12481, 12492, 12506, 12511, 12519 — excluded.

**Step 1 (gate scoring + frozen cohort rules T1–T4):**
- Rows after the exclusion: 49,604 (396 HARPs); scorable 49,597.

| subset | eligible episodes | HARPs |
|---|---:|---:|
| single-region | 165 | 62 |
| ≤ 2 regions (recorded subset) | 387 | 101 |

The cohort files are in `data/euv_confirm/cohort_{single,le2}.csv`; they were not inspected.

**Step 2 dry run** (nothing submitted):
- Union of the two cohorts: 387 episodes, 101 HARPs. All single-region episodes are also in the ≤ 2 cohort.
- 202 exports (101 HMI + 101 AIA); expected files: AIA 33,370, HMI 774.
- Estimated 13.16 GB (test-year 0.385 MB/file; test years were 12.19 GB for 313 episodes) and 7.56 h (prep model × 1.27).
- Free disk: 628 GiB.

### Confirmation set — Step 2 download RESULT (files only; label-blind)
`euv_confirm.py download` 01:48–09:25 (wall 7.63 h) → `data/euv_confirm/`; `verify` → `euv_confirm_verify.log`, `data/euv_confirm/verify_per_harp.csv`.
- **Exports:** 202 (101 HMI + 101 AIA), one pending at a time, the user's account only. Failures: 0.
- **Recovered retries:**
  - JSOC status 4 ("Cant save new export-request hash") on the AIA export of HARPs 13574, 14117 and 14610. Each resubmission was then refused with status 7 while the account's own single request was still pending, and completed.
  - A few submit/tar timeouts.
- **HMI:** magnetogram + bitmap for all 387/387 episode T_RECs; header HARPNUM and T_REC match.
- **AIA:** 33,179 files of 33,370 expected (99.43%). All have a readable header, are 94 Å and fall inside the HARP's record range. No HARP has zero files.
- **Size:** 15.03 GB.
- **Short HARPs:** 40 (191 frames missing). Below 97%:
  - 12997: 290/315
  - 13004: 589/625
  - 13599: 151/160
  - 14610: 656/680
- These have NOT been re-exported. In dev and test, re-exports of short HARPs returned identical counts (archive gaps).

### Confirmation set — Step 3 RESULT (label-blind; counts only; nothing evaluated)
`euv_confirm.py compute` → `data/euv_confirm/{series,results,spatial,spatial_nf}/`; counts in `euv_confirm_step3_counts.log`. No label column was read.
- **Run:** the same code as the test years (`euv_full.compute_episode`; `euv_spatial.spatial_episode`, root data/euv_confirm, valid_primary and valid_sens). 9 workers. Wall 2.89 h (09:30–12:23). 387/387 episodes, 0 errors.
- **Frames:** 46,221 in total.
  - QUALITY ≠ 0: 1,236
  - exposure rule: 412
  - in P2 flare intervals (sensitivity version only): 1,574
  - saturation-flagged: 127
- Frame means are reproduced between the spatial pass and the series (max |diff| 0.0).

| subset | episodes (HARPs) | primary fill ≥ 80% | flare-excluded fill ≥ 80% | undefined (fill passes): ΔCV p / ΔCV nf / R4a / R4c / R4a_nf | coverage flag (primary 80% set) |
|---|---|---:|---:|---|---:|
| single-region | 165 (62) | 163 | 159 | 0 / 0 / 0 / 0 / 0 | 6 |
| ≤ 2 regions (recorded fallback) | 387 (101) | 378 | 373 | 0 / 0 / 0 / 0 / 0 | 38 |

STOP. Nothing is evaluated against labels until the user sends a pre-registration.

### Confirmation set — re-export check: RESULT (label-blind; same procedure as the test-year check f3d6489)
AIA re-exported once for HARPs 12997, 13004, 13599 and 14610 (`euv_confirm.py reexport`, one pending export, the user's account) into `data/euv_confirm/reexport/<H>/`.
- Counts are identical: 12997 290/290; 13004 589/589; 13599 151/151; 14610 656/656. 0 new frames, 0 missing.
- **Recorded as: archive gaps.** Nothing was copied, overwritten or recomputed.

## 2026-09-26 — PRE-REGISTRATION — 2025–26 CONFIRMATION (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh; recorded BEFORE any 2025–26 label is used in evaluation)
**Verbatim (user):**

Context: added after 2021–24 results (7438177, ec00afb) and 21 dev candidates. Primary subset = noaa_ar_count <= 2 per the recorded fallback (lines 199–200, 223, 1853–1860); the 23-positive-HARP count predates the 6-HARP exclusion; not recounted. Dev and 2021–24 used single-region; this is a broader population.

TEST 1 — Hypothesis: In 2025–26, among true alarms matched to false alarms with a similar gate score (magnetic twins), whole-region AIA 94 Å variability (CV_box) over the 24 hours before the alarm is higher in the true alarm than in its false-alarm twin.
PRIMARY: CV_box twins ratio = median(true)/median(false); step 6 twins code (seeded order 20260921, greedy nearest, caliper 0.0747, partner from a different HARP, no reuse); <= 2 set, primary 80% fill; delayed episodes count as false. CI: pairs resampled by true HARP, 2,000, seed 0. Reading: "REPLICATED" if ratio > 1 AND CI lower > 1; "direction consistent, not confirmed" if ratio > 1 with CI including 1; "NOT REPLICATED" otherwise.
SECONDARY (cannot change the reading): s1 same-flare-history twins (F4 groups); s2 all-episodes ratio (HARP bootstrap 2,000, seed 0); s3 R4a: A vs A + R4a with dev-fitted fold models as 2021–24, "adds information" only if Δ > 0 AND CI excludes 0; s4 single-region subset, primary statistic, descriptive; s5 pooled CV_box twins ratio over 2021–24 (existing 40 pairs) + 2025–26 primary pairs, same code, labelled "includes 2021–24 data already analysed (ec00afb); not a confirmation". No 2020 or 2022.

TEST 2 — STEP B (pre-registered 2026-09-21, lines ~1665–1680), finalised now: evaluation set = 2025–26, <= 2 primary, all eligible episodes (no EUV fill requirement); single-region descriptive. τ_A = max weighted TSS on A's dev out-of-fold probabilities; τ_C = threshold on C's dev OOF probabilities with the same weighted TPR. A and C fitted on dev with frozen A settings; test prediction = mean of 5 fold models. Metric: weighted Δ = logloss(A) − logloss(C), HARP bootstrap 10,000, seed 20260921; AUC; false alarms at τ_A vs τ_C. Reading: "C beats A" only if Δ > 0 AND 95% CI excludes 0; else "not confirmed". Also report dev OOF Δ (exploratory); the confirmation run happens regardless.

Run TEST 1 and TEST 2 once each. Report all tables, commit, STOP. Nothing else on 2025–26.

**Implementation (decided by: me, before any 2025–26 label is used):**
- **Code:** `euv_confirm_tests.py` (run once) → `euv_confirm_tests.log`, `data/euv_confirm/test1_ratios.csv`, `test2_stepB.csv`, `twins_le2.csv`.
- **Cohorts:** `data/euv_confirm/cohort_le2.csv` (387) and `cohort_single.csv` (165), written label-blind in step 1. Values from `data/euv_confirm/results` (`primary_fill`, `primary_CV_box`) and `spatial` (R4a).
- **TEST 1:**
  - Primary set = ≤ 2 cohort with `primary_fill ≥ 0.80` and CV_box defined (378 expected).
  - Twins = `euv_f2_replication.twins` (the step 6 matching code; it reproduced the 81 dev pairs in ec00afb). s1 = the same with `by_group=True` (F4 groups JUST-FLARED / C-only / QUIET-NOW).
  - Ratio and CIs = `phase_f.ratio_jobs` (mode ratio; the twins CI resamples pairs clustered by true HARP; the all-episodes CI is a HARP bootstrap; 2,000 each, seed 0). s2 = the all-episodes ratio of the primary row.
  - s4 = the same on the single-region cohort (primary 80% fill).
  - s5: the 40 pairs of `data/euv_test/f2_replication/twins_test_primary.csv` (2021/2023/2024 values from `data/euv_test/results`) plus the 2025–26 primary pairs. Ratio = median(true members) ÷ median(false members) over the pooled pairs; pairs resampled by true HARP (the HARP numbers do not overlap between the two sets).
  - s3: A and A + R4a fitted on the dev R4a set (541) with the step 6 settings (`euv_heldout.fit_folds`; check: they reproduce the Phase X dev log-losses). Test prediction = mean of the 5 fold models. Set = the TEST 1 primary set with R4a defined; weights 1/n per HARP. HARP bootstrap 10,000, seed 20260921.
- **TEST 2 (Step B):**
  - **R:** as recorded 2026-09-21 — hours since the most recent C1+ (K2 flux ≥ 1e-6, joinable SWPC events) start in (t − 48 h, t) from the episode's `noaa_ars`, capped at 48; feature log(1 + R).
    - Events: `swpc.fetch` 2010-04-28 → 2019-12-31 for dev and 2024-12-29 → 2026-08-18 for 2025–26.
    - **Check:** (R < 48) ⇔ (n_C + n_M + n_X ≥ 1) for every episode (the same window and events as the history counts).
  - **A:** the frozen Stage 4 A fold models (hash-verified against `frozen_spec.json`). Check: a refit with `fit_folds` on the dev cohort (547, fold column, Stage 4 weights) reproduces them and the stored `p_A`.
  - **C:** fitted the same way with A_COLS + [log(1 + R)].
  - **τ_A:** over the distinct dev OOF probabilities of A in descending order, kept = p ≥ τ; weighted TPR/FPR with the Stage 4 weights; τ_A = the first maximum of weighted TSS.
  - **τ_C:** the highest distinct dev OOF probability of C whose weighted TPR is ≥ A's weighted TPR at τ_A.
  - **Evaluation:**
    - 2025–26 sets: the ≤ 2 cohort (all 387 eligible episodes, primary) and single-region (165, descriptive). Weights 1/n per HARP over the set.
    - Δ with a HARP bootstrap of 10,000, seed 20260921; weighted AUC.
    - False alarms = false episodes with p ≥ τ (count and weighted fraction of false episodes). True kept is also reported.
  - **Dev OOF Δ** (exploratory): the same bootstrap on the dev 547.
- **Readings** are applied mechanically as written. TEST 1's reading uses the PRIMARY row only; TEST 2's uses the ≤ 2 row only.

### 2025–26 CONFIRMATION — RESULTS (run once; numbers only)
`euv_confirm_tests.py` → `euv_confirm_tests.log`, `data/euv_confirm/test1_ratios.csv`, `test2_stepB.csv`, `twins_le2.csv`. 9 workers; wall 3.6 s.

**Checks:**
- Frozen A fold models hash-verified; the refit reproduces them and Stage 4 `p_A`.
- The dev R4a models reproduce the Phase X dev log-losses.
- The R window is consistent with the history counts on dev and on 2025–26.

**TEST 1 — CV_box magnetic twins.** ≤ 2 set, primary 80% fill: 378 episodes (56 true / 322 false, 101 HARPs). 50 twin pairs of 56 true episodes; max |Δscore| 0.0598. By history group: C-only 24, JUST-FLARED 23, QUIET-NOW 3.
- Ratio = median(true) ÷ median(false).
- Twins CI: pairs resampled by true HARP; all-episodes CI: HARP bootstrap. Both 2,000 resamples, seed 0.

| row | n (true/false) | median true / false | all-episodes ratio [CI] | pairs | twins median true / false | twins ratio [CI] |
|---|---|---|---|---:|---|---|
| **PRIMARY (≤ 2)** | 378 (56/322) | 0.2378 / 0.0720 | s2: 3.301 [1.370, 6.457] | 50 | 0.2218 / 0.0680 | **3.262 [1.296, 9.489]** |
| s1 same-flare-history twins (≤ 2) | 378 | | | 47 | 0.2245 / 0.0797 | 2.817 [1.017, 6.823] |
| s4 single-region subset (descriptive) | 163 (19/144) | 0.2192 / 0.0963 | 2.276 [0.863, 5.431] | 16 | 0.2352 / 0.0683 | 3.443 [1.363, 7.305] |
| s5 POOLED 2021–24 (40 pairs) + 2025–26 (50 pairs) — "includes 2021–24 data already analysed (ec00afb); not a confirmation" | 691 (101/590) | 0.1959 / 0.0903 | 2.170 [1.466, 3.711] | 90 | 0.1817 / 0.0965 | 1.883 [1.226, 3.369] |

**TEST 1 pre-stated reading (mechanical, PRIMARY):** twins ratio 3.2624 > 1 and CI lower bound 1.2956 > 1 → **"REPLICATED"**.

**s3 R4a** (dev 541 fold models; mean of 5): n 378 (56/322, 101 HARPs).
- LL(A) 0.3933, LL(A + R4a) 0.3679; Δ 0.0254 [−0.0067, 0.0629]; AUC 0.7631 → 0.7606.
- The CI includes 0 → "adds information" condition not met.

**TEST 2 — STEP B (A vs C = A + log(1 + R))**
- **Dev** (EXPLORATORY, OOF, 547 episodes): LL(A) 0.3336, LL(C) 0.3356; Δ −0.0020 [−0.0129, 0.0084]; AUC 0.7432 → 0.7645.
- **Frozen dev thresholds:**
  - τ_A = 0.094958 (max weighted TSS 0.4516; weighted TPR 0.6482, FPR 0.1966).
  - τ_C = 0.100840 (the highest threshold with weighted TPR ≥ 0.6482: TPR 0.6688, FPR 0.2905).

| set | n (true/false) | HARPs | LL(A) | LL(C) | Δ [95% CI] | AUC A → C | false alarms at τ_A / τ_C (count; weighted) | true kept A / C (count; weighted TPR) |
|---|---|---:|---:|---:|---|---|---|---|
| **PRIMARY ≤ 2, all eligible** | 387 (56/331) | 101 | 0.3930 | 0.3757 | **0.0173 [0.0016, 0.0350]** | 0.7489 → 0.7527 | 90 / 107; 0.2163 / 0.3165 | 37 / 40; 0.5799 / 0.6809 |
| single-region (descriptive) | 165 (19/146) | 62 | 0.3659 | 0.3558 | 0.0101 [−0.0091, 0.0332] | 0.7555 → 0.7245 | 27 / 41; 0.1707 / 0.3023 | 10 / 13; 0.4651 / 0.6256 |

**TEST 2 pre-stated reading (mechanical, PRIMARY):** Δ 0.0173 > 0 and CI [0.0016, 0.0350] excludes 0 → **"C beats A"**.

STOP. Nothing else on 2025–26.

## 2026-09-26 — DESCRIPTIVE ONLY after the confirmation (requested by: user; recorded before computing)
User: "Descriptive only (cannot change any reading; no new tests): (a) sign and size of the log(1+R) coefficient in the dev-fitted model C (does recent flaring raise or lower the predicted probability?); (b) label-blind distribution of CV_box by year for all episodes 2010–2026 (median, IQR) to check for instrument drift between periods."

**Implementation (me):** `euv_descriptive_after.py` → `euv_descriptive_after.log`.
- **(a)** The 5 dev fold models of C (refit exactly as in `euv_confirm_tests.py`). Reported per fold and as the fold mean:
  - the standardized coefficient (per 1 SD of log(1 + R)) with its odds ratio;
  - the per-unit coefficient (coef ÷ training-fold SD);
  - the other coefficients of C for context.
- Direction, stated mechanically: R = hours since the most recent C1+ flare (48 = none in 48 h). A negative coefficient means a shorter time since a flare gives a higher predicted probability.
- **(b)** `primary_CV_box` from every stored episode result: dev `data/euv_full/results` (single-region, 2010–2019); test `data/euv_test/results` (single-region, 2021/2023/2024); confirmation `data/euv_confirm/results` (≤ 2 union, 2025–2026).
  - Grouped by the calendar year of t: n, median, Q1, Q3.
  - All episodes with a defined value, plus the same restricted to primary fill ≥ 80%.
  - No label column is read.

### Descriptive follow-up — RESULT (cannot change any reading; numbers only)
`euv_descriptive_after.py` → `euv_descriptive_after.log`, `data/euv_confirm/cv_box_by_year.csv`.

**(a) Model C = A + log(1 + R)** (dev fold models). Coefficients are standardized, per 1 SD, after the training-fold StandardScaler.

| fold | score | n_C | n_M | n_X | log(1+R) | log(1+R) per unit | SD of log(1+R) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.738 | 0.043 | 0.071 | 0.058 | −0.179 | −0.149 | 1.200 |
| 1 | 0.533 | −0.071 | 0.358 | 0.030 | −0.362 | −0.299 | 1.213 |
| 2 | 0.874 | 0.069 | 0.202 | −0.168 | −0.266 | −0.226 | 1.181 |
| 3 | 0.782 | −0.327 | 0.257 | −0.077 | −0.332 | −0.279 | 1.187 |
| 4 | 0.594 | −0.011 | 0.230 | 0.051 | −0.358 | −0.285 | 1.254 |

- **log(1 + R) across folds:** mean standardized coefficient −0.299 (odds ratio 0.741 per 1 SD); per unit −0.248 (odds ratio 0.781). The sign is negative in 5 of 5 folds.
- **Dev log(1 + R):** median 3.027; 33.1% of episodes are at the cap (no C1+ in 48 h).
- **Direction (mechanical):** negative → a shorter time since the last C1+ flare gives a HIGHER predicted probability.

**(b) CV_box by calendar year** (all episodes with a value; label-blind): n, median [Q1, Q3].
- Dev (single-region):
  - 2010: 40, 0.051 [0.032, 0.081]
  - 2011: 88, 0.233 [0.128, 0.396]
  - 2012: 61, 0.159 [0.062, 0.231]
  - 2013: 95, 0.116 [0.061, 0.220]
  - 2014: 110, 0.117 [0.057, 0.221]
  - 2015: 111, 0.164 [0.058, 0.356]
  - 2016: 10, 0.181 [0.117, 0.479]
  - 2017: 24, 0.142 [0.079, 0.269]
  - 2018: 3, 0.097 [0.080, 0.198]
  - 2019: 4, 0.392 [0.086, 0.784]
- Test (single-region):
  - 2021: 22, 0.131 [0.071, 0.175]
  - 2023: 181, 0.114 [0.058, 0.186]
  - 2024: 110, 0.136 [0.084, 0.267]
- Confirmation (≤ 2 union):
  - 2025: 266, 0.084 [0.043, 0.184]
  - 2026: 121, 0.078 [0.040, 0.207]
- Confirmation, single-region only:
  - 2025: 102, 0.107 [0.038, 0.237]
  - 2026: 63, 0.110 [0.044, 0.250]
- The fill ≥ 80% versions are within 0.004 of these medians (see log).

## 2026-09-26 — EUV-UNSEEN FOLLOW-UP VALIDATION — CV_box AS A FALSE-ALARM FILTER (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh; recorded verbatim BEFORE anything else)
**Verbatim (user):**

Frozen files unchanged; never overwrite existing models or results. Do not run stage5_test.py (it prints outcomes). JSOC: my account only, ONE pending export at a time across ALL running jobs.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else; commit.
Disclosure (record verbatim): added after the 2021–24 and 2025–26 results (ec00afb, ae1b174) and after 21 dev candidates. The hypothesis was chosen after earlier EUV results. Flare labels and magnetic results for 2021–2024 were seen in Stage 5; EUV values for this set have never been computed or seen. This is an "EUV-unseen follow-up validation", not an untouched test. The model is trained on single-region dev episodes and evaluated on <= 2-region episodes (population change; reported).

HYPOTHESIS: Adding whole-region AIA 94 Å variability (log10 CV_box) to Model A removes more false alarms at fixed, dev-frozen thresholds while keeping true alarm episodes.

SETS (label-blind construction; outcomes never printed or inspected):
- PRIMARY: eligible <= 2-region episodes (frozen cohort rules T1–T4) from 2021, 2023, 2024 that are NOT in data/stage5/cohort_test_primary.csv.
- SENSITIVITY: the same rule for 2022 only (2022 is excluded from primary by Decision L2, line 921: attribution completeness 89.7% < 90%). Reported separately, never pooled into the primary reading.
- Exclusions for both: every HARP AND every NOAA region that appears anywhere in data/euv_full, data/euv_test, data/euv_confirm, data/euv_pilot or data/euv_cad (raw data directories, manifests and results).
- SIZE RULE (label-blind, decided now): if PRIMARY has < 100 episodes or < 30 HARPs, STOP after Step 1 and report "too small; not run".

MODELS AND THRESHOLDS (dev 2010–2019 only; frozen BEFORE any new-set download):
- Dev rows: the dev primary 80% set with CV_box finite and > 0 (same rows for both models). log10 because CV is skewed (recorded: 2.176 raw, −0.073 log10).
- Models, as NEW artifacts (do not overwrite Stage 4 A): A = A_COLS; A_CV = A_COLS + log10 CV_box; C = A_COLS + log(1+R) (Step B definition); C_CV = C + log10 CV_box. Step 6 settings (same folds, weights 1/n per HARP, training-fold scaling, estimator). New-set prediction = mean of the 5 fold models.
- Thresholds: τ for each model = highest dev OOF threshold keeping >= 88% of weighted true episodes (p >= τ), exactly as 04b6f4f. Each model has its own frozen τ.
- Save and hash: model files, thresholds, the exact dev row list.

EVALUATION (later, only on command). New set at primary 80% fill with CV_box finite and > 0; weights 1/n per HARP; delayed episodes count as false. Failed downloads or undefined values = label-blind exclusion, counted.
PRIMARY comparison: A vs A_CV at their frozen thresholds. From the SAME paired HARP resamples (2,000, seed 0) compute:
 D_false = weighted % false alarms removed (A_CV minus A), with 95% CI;
 D_true  = weighted % true alarm episodes kept (A_CV minus A), with 95% CI.
READING (mechanical, decided now):
 "CONFIRMED SAFE FILTER" if D_false CI lower > 0 AND D_true CI lower >= −10 points.
 "MEETS OPERATING CRITERION" if D_false CI lower > 0 AND D_true point estimate >= −10 points (but its CI lower < −10).
 "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)" if D_false CI lower > 0 AND D_true point estimate < −10 points.
 "INCONCLUSIVE" if the CIs cannot be computed (e.g. no true episodes in resamples).
 "NOT CONFIRMED" otherwise.
Wording in all outputs: "true alarm episodes kept", not "real flares".
SECONDARY (cannot change the reading): counts kept/removed per model; Δ log-loss (A minus A_CV; HARP bootstrap 10,000, seed 20260921); AUC; the same comparison for C vs C_CV; CV_box twins ratio (step 6 twins code, same CI procedure as TEST 1); PRIMARY set composition (single- vs two-region, by year). SENSITIVITY: all of the above on 2022, labelled separately.

STEP 1 — Build PRIMARY and SENSITIVITY sets label-blind. Save and hash the inclusion/exclusion manifest (every episode, reason). Report ONLY: episodes and HARPs by year and set, single- vs two-region composition, numbers excluded per rule. Apply the SIZE RULE. Commit. If too small: STOP here.
STEP 2 — On dev only: fit A, A_CV, C, C_CV; compute and freeze all four thresholds; save and hash; record τ values in decisions.md. Commit.
STEP 3 — Download AIA 94 Å (12-min, (t−24h, t], tracked im_patch) + HMI magnetogram/bitmap at t, same pattern as the test/confirmation downloads, to data/euv_extra/ (PRIMARY first, then 2022). Dry run first: report episodes, exports, GB, hours. Then run it.
STEP 4 — Compute values with the identical code (euv_full.compute_episode); report fill counts, undefined values, errors, wall time. Commit.
STOP. Do not evaluate until I say "run the pre-registered filter test once".

**Implementation of Step 1 (decided by: me, before building the sets):**
- **Code:** `euv_extra.py sets` → `data/euv_extra/manifest.csv` (every candidate episode with its set, year, region count at t and the reason it was included or excluded), `data/euv_extra/excluded_ids.json`; hashes recorded here.
- **Candidates:** as Stage 5 (`stage5_test.py`), label-blind.
  - `frozen/split.csv` test HARPs; rows of `data/labelled_20100501_20250101.csv` (hash-verified) in the set's years.
  - Rows with a missing gate feature are dropped. Score = mean of the 5 frozen gate fold models.
  - `noaa_ar_count <= 2`; `cohort.build` (T1–T4) with the trend windows over every labelled row of the HARP and `swpc.label_missing_days()`.
  - PRIMARY = years 2021, 2023, 2024 in one build (as Stage 5's primary period); SENSITIVITY = 2022 alone.
  - `stage5_test.py` is not run.
- **Exclusion order (the first matching reason is recorded):**
  1. (harpnum, t) in `data/stage5/cohort_test_primary.csv`;
  2. HARP in the excluded HARP set;
  3. any NOAA region of the candidate HARP (the union of `noaa_ars` over all its labelled rows) in the excluded region set.
- **Excluded HARP set:** every HARP number found anywhere under data/euv_full, data/euv_test, data/euv_confirm, data/euv_pilot, data/euv_cad (recursive):
  - digit-only directory names;
  - `<HARP>_<yyyymmdd>T<hhmm>` prefixes of file and directory names;
  - HMI FITS file names (`hmi.sharp_720s.<HARP>.…`) and FITS header `HARPNUM`;
  - any CSV column named harpnum/HARPNUM.
- **Excluded NOAA region set:**
  - (a) header `NOAA_ARS` of every HMI FITS file in those directories;
  - (b) any CSV column noaa_ars/NOAA_ARS in those directories;
  - (c) a conservative addition (me): every `noaa_ars` value on any labelled row, 2010–2024 and 2025–26 files, of every excluded HARP, so that a region seen under another HARP number is also excluded. `noaa_ars` is a region link, not a label.
- **Report:** only counts — episodes and HARPs by year and set, single- vs two-region composition at t, and exclusions per rule. No label or outcome column is printed.

### EUV-unseen follow-up — Step 1 RESULT (label-blind; counts only)
`euv_extra.py sets` → `euv_extra_sets.log`, `data/euv_extra/manifest.csv` (SHA-256 `1766206f1b7d016980404e563a53320002bb5a7bb05757862bd259affcc67d41`), `data/euv_extra/excluded_ids.json` (`7632a6f8c36695c6cd511c186df77728b6769f97a58ab2f36fa34079bf47c015`). A rerun reproduced both hashes.

**Excluded IDs:**
- 396 HARPs from the five EUV directories. This includes all 180 dev, all 98 test and all 101 confirmation-cohort HARPs.
- 434 NOAA regions: 418 from the directories, plus 16 from the labelled rows of the excluded HARPs.
- No included HARP is in the excluded set or in the test cohort.

| set | candidate eligible episodes | not eligible (cohort: no evaluable hour) | in cohort_test_primary | HARP in EUV dirs | NOAA region in EUV dirs | **INCLUDED** | HARPs | single / two-region at t |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| PRIMARY 2021/2023/2024 | 476 | 87 | 313 | 0 | 5 | **158** | **40** | 0 / 158 |
| SENSITIVITY 2022 | 152 | 30 | 0 | 0 | 0 | **152** | **44** | 101 / 51 |

- PRIMARY by year: 2021 8 episodes (2 HARPs); 2023 94 (23); 2024 56 (15).
- **SIZE RULE:** PRIMARY 158 ≥ 100 episodes and 40 ≥ 30 HARPs → **PASS**; continue to Step 2.

### EUV-unseen follow-up — Step 2 RESULT: dev models and FROZEN thresholds (dev 2010–2019 only; before any new-set download)
`euv_extra.py models` → `euv_extra_models.log`; artifacts in `data/euv_extra/`, all new; nothing overwritten.
- **Dev rows:** 541 episodes, 179 HARPs (primary 80% set, CV_box finite and > 0), listed in `dev_rows.csv` with fold and weight.
- **Fitting:** step 6 settings (fold column, weights 1/n per HARP over the 541, training-fold StandardScaler, frozen LogisticRegression).
- **log(1+R)** follows the Step B definition.
- **Check:** A reproduces the Phase X dev log-loss exactly.

**FROZEN thresholds** (τ = highest dev OOF threshold keeping ≥ 88% of weighted true alarm episodes, as 04b6f4f):

| model | features | τ (frozen) | dev OOF weighted true alarm episodes kept |
|---|---|---:|---:|
| A | score, n_C, n_M, n_X | **0.067970** | 0.8815 |
| A_CV | A + log10 CV_box | **0.074657** | 0.8817 |
| C | A + log(1+R) | **0.062570** | 0.8807 |
| C_CV | C + log10 CV_box | **0.068936** | 0.8803 |

**SHA-256:**
- `thresholds.json` `7a34507c20d37756906e4ad6dfaf9069c48ad74bff5b42521a4dd4f1c573c6ad`
- `dev_rows.csv` `a32b3afe915743f4022a35b83f9084b3adb002a7a6ac8231254ea238f37590b3`
- The 20 fold-model files (`models/{A,A_CV,C,C_CV}_fold{0-4}.joblib`) are listed in `euv_extra_models.log` and `model_hashes.json`, e.g. A_fold0 `547b5d2c…`, A_CV_fold0 `a28363dc…`, C_fold0 `bb0ef14b…`, C_CV_fold0 `e5bd214c…`.

### EUV-unseen follow-up — Step 3 dry run (nothing submitted)
`euv_extra.py plan`. Outputs go to separate roots `data/euv_extra/primary/` and `data/euv_extra/s2022/`, so a HARP in both sets can never mix files. Same pipeline as test/confirmation (`euv_full.run_pipeline`, compute = False), PRIMARY first, then 2022; one pending export at a time, the user's account only; no other JSOC job running.

| set | episodes | HARPs | exports | AIA files | HMI files | ~GB | ~hours |
|---|---:|---:|---:|---:|---:|---:|---:|
| PRIMARY | 158 | 40 | 80 | 17,645 | 316 | 6.92 | 3.31 |
| 2022 | 152 | 44 | 88 | 14,770 | 304 | 5.81 | 3.31 |
| total | 310 | 84 | 168 | 32,415 | 620 | 12.73 | 6.62 |

## 2026-09-27 — EXPLORATORY — RECHARGE vs CLUSTERING TEST (decided by: user; design drafted by Claude AI, adopted by the student; recorded verbatim BEFORE computing)
**Verbatim (user):**

DEV 2010–2019 ONLY (dev candidate #22). Do NOT read or compute anything for 2021–2026. No images, no downloads, no JSOC calls (the euv_extra download is running — do not touch it). Frozen files unchanged; do not overwrite existing models.

Physics (record): the recharge/"saturation" picture (Hudson 2020, MNRAS 491:4435: waiting time AFTER a flare correlates with its size; Sun et al. 2012, ApJ 748:77: free energy drops ~0.3e32 erg within 1 h of an X2.2 flare) predicts a NEGATIVE effect of the last flare's size on the chance of an M1+ in (t, t+24h]. The clustering/active-phase picture (Step B: log(1+R) coefficient negative in 5/5 folds, i.e. recent flaring raises probability) predicts a POSITIVE effect. Question: among gate alarms, after accounting for recency, does the size of the region's last flare help separate true from false alarms, and which way?

FEATURE:
- S_last = log10(K2-scale peak flux of the region's most recent C1+ SWPC flare whose start is in (t − 48 h, t)), using exactly the same event source, K2 scaling and noaa_ars region join as Step B's R (euv_confirm_tests.log_r logic).
- If no such flare: S_last = log10(1e-6) (floor). log(1+R) = log(49) already flags "none".
- Check (assert): for every episode, (R < 48) ⇔ (S_last came from a real flare); and the same event join reproduces the cohort's n_C, n_M, n_X.

MODELS (dev 547 episodes, data/stage4/oof_cohort_dev.csv, Stage 4 fold column and weights):
- C = A_COLS + log(1+R) (must reproduce the committed Step B dev result: LL(C) 0.3356)
- C_S = C + S_last
- Step 6 / Step B settings (same folds, weights 1/n per HARP, training-fold scaling, estimator).

REPORT:
- Δ = logloss(C) − logloss(C_S) (positive = S_last helps), HARP bootstrap 10,000, seed 20260921; 95% CI; weighted AUC for both.
- S_last coefficient in each of the 5 folds (per 1 SD) and its sign.
- Descriptive: Spearman ρ of S_last with n_M, n_X, log(1+R); number of episodes at the floor.

PRE-STATED READING (applied mechanically):
- "RECHARGE SUPPORTED" if Δ > 0 AND CI lower > 0 AND coefficient negative in >= 4 of 5 folds.
- "CLUSTERING SUPPORTED" if Δ > 0 AND CI lower > 0 AND coefficient positive in >= 4 of 5 folds.
- Otherwise "NO DETECTABLE EFFECT".
Label everything EXPLORATORY (dev only; nothing claimed as confirmed).

Report the tables, commit, STOP. No other analyses.

**Implementation (decided by: me, before computing):**
- **Code:** `euv_recharge.py` → `euv_recharge.log`.
- **Events:** `swpc.fetch(2010-04-28, 2019-12-31 23:59)` (local daily files only; no network), C1+ = flux ≥ 1e-6.
- **Tie rule:** if several joinable events share the most recent start time, S_last uses the largest flux among them.
- **n_C/M/X check:** the `build_dataset.label` join (all joinable events, window [t − 48 h, t), union over regions, duplicates on (start, class) dropped) must equal the cohort columns.
- **LL(C) check:** C is refit with `euv_heldout.fit_folds`, the same path as `euv_confirm_tests.py`. Its weighted OOF log-loss must round to 0.3356.
- **Bootstrap:** drawn in the parent and evaluated on 9 workers (Phase F method, identical to single process).
- **Coefficients:** standardized (training-fold StandardScaler), per fold.

### RECHARGE vs CLUSTERING — RESULT (EXPLORATORY; dev 2010–2019 only; nothing claimed as confirmed; numbers only)
`euv_recharge.py` → `euv_recharge.log`. 9 workers; wall 3.2 s. No images, JSOC calls or 2021–2026 data; the running download was not touched.

**Checks:**
- (R < 48) ⇔ a real last flare, for all 547 episodes.
- The event join reproduces n_C, n_M and n_X.
- LL(C) = 0.3356, matching Step B dev.

**Δ = LL(C) − LL(C_S)** (positive = S_last helps): **+0.0017 [−0.0144, 0.0184]** (HARP bootstrap 10,000, seed 20260921). LL(C) 0.3356, LL(C_S) 0.3338. Weighted AUC: C 0.7645, C_S 0.7503.

**C_S coefficients** (per 1 SD):

| fold | score | n_C | n_M | n_X | log(1+R) | S_last |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.689 | 0.090 | −0.061 | 0.060 | −0.084 | +0.372 |
| 1 | 0.492 | −0.025 | 0.211 | 0.029 | −0.278 | +0.369 |
| 2 | 0.810 | 0.153 | −0.038 | −0.169 | −0.151 | +0.555 |
| 3 | 0.740 | −0.309 | 0.002 | −0.038 | −0.220 | +0.494 |
| 4 | 0.528 | 0.020 | 0.040 | 0.055 | −0.228 | +0.548 |

The S_last sign is positive in 5 of 5 folds (negative 0/5).

**Descriptive:**
- 181 of 547 episodes are at the floor (no C1+ in (t − 48 h, t)).
- Spearman ρ of S_last: with n_M 0.493 (p 7.4e-35), with n_X 0.206 (p 1.2e-06), with log(1+R) −0.701 (p 6.3e-82).

**Pre-stated reading (mechanical):** Δ +0.0017, but the CI lower bound (−0.0144) is not > 0 → **"NO DETECTABLE EFFECT"**.

## 2026-09-27 — EXPLORATORY — PARASITIC-POLARITY "DOTS" NEAR THE PIL (decided by: user; design drafted by Claude AI, adopted by the student; recorded verbatim BEFORE computing)
(The user's first version of this request was interrupted; the second version, below, is the one followed.)

**Verbatim (user):**

DEV 2010–2019 (dev candidate #23), plus a conditional pre-registered follow-up. Frozen files unchanged; do not overwrite existing models or results. No downloads, no JSOC calls.

RUNS ALONGSIDE THE euv_extra DOWNLOAD: do not read, write or lock anything in data/euv_extra now; write all outputs to data/dots/; if a git commit hits index.lock, wait and retry (never delete the lock); append to decisions.md only (never rewrite other entries). Use at most 4 CPU workers.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE computing anything; commit.
Physics (record): Kusano et al. 2012 (ApJ 760:31): small magnetic structures near the PIL with flux "reversed to the potential component or the nonpotential component" of the main field trigger eruptions. Limit (record): Bamba & Kusano 2018 (ApJ 856:43) found only ~30% of 32 flares > M5 consistent with that model using vector + chromospheric data; this project uses one line-of-sight magnetogram at alarm time only, so this is a crude proxy.
Question: among gate alarms, does the number of small opposite-polarity patches ("dots") inside the PIL zone help separate true from false alarms beyond Model A?

FEATURE (label-blind; alarm-time LoS magnetogram per dev episode in data/euv_full/hmi, read with the same hmi_files() lookup as compute_episode):
- B = magnetogram data (nan -> 0). mm_px = CDELT1 * RSUN_REF / RSUN_OBS / 1e6 (from header).
- Background sign map: sign of B smoothed with a Gaussian of sigma = 5 Mm (sigma_px = 5 / mm_px).
- Candidate dots: 8-connected components of |B| >= 100 G in which >= 90% of pixels have sign OPPOSITE to the background sign map, with area between 1 and 20 Mm^2 (area = n_pixels * mm_px^2).
- Keep dots whose centroid pixel lies inside euv_pilot.pil_mask(B).
- N_dots = number of kept dots; feature = log(1 + N_dots).
- Descriptive only: Phi_dots = sum of |B| * pixel area over kept dots (Mx).
- Selftests (assert): (a) synthetic bipole with one 5 Mm^2 opposite-polarity patch inside the PIL zone -> N_dots = 1; (b) the same patch placed far from the PIL -> 0; (c) a 30 Mm^2 opposite patch -> 0 (too big); (d) deterministic on repeat.

STEP 1 — Compute N_dots for all 547 dev episodes. Label-blind report first: N_dots median, IQR, max, % of episodes with 0; any episode with a missing magnetogram (count, excluded label-blind). Save data/dots/dev_dots.csv; commit.

STEP 2 — EVALUATION, run once (dev 547, data/stage4/oof_cohort_dev.csv, Stage 4 fold column and weights; step 6 settings: same folds, weights 1/n per HARP, training-fold scaling, estimator):
- A vs A + log(1+N_dots): Δ = logloss(A) − logloss(A + dots) (+ = helps), HARP bootstrap 10,000, seed 20260921, 95% CI; weighted AUC both; coefficient per fold (per 1 SD, sign).
- Check first: A reproduces the committed Stage 4 dev p_A (max |diff| < 1e-12).
- Descriptive: Spearman rho of log(1+N_dots) with gate score, n_C, n_M and (where defined) log10 CV_box; N_dots twins ratio on the 81 gate-score twins (data/euv_full/step6/twins_PRIMARY.csv), same ratio/CI code as F2.
PRE-STATED READING (mechanical):
- "ELIGIBLE FOR FOLLOW-UP" only if Δ > 0 AND 95% CI lower > 0 AND AUC(A + dots) > AUC(A).
- Otherwise "NOT ELIGIBLE".
Label everything EXPLORATORY (dev only). Commit.

STEP 3 — CONDITIONAL FOLLOW-UP (pre-registered now; do NOTHING here unless Step 2 says "ELIGIBLE"):
- Wait until the euv_extra download and compute have finished; do not interrupt them.
- Compute the same feature label-blind on the EUV-unseen PRIMARY set magnetograms (data/euv_extra) with identical code; report the N_dots distribution; commit.
- A and A + log(1+N_dots) fitted on dev (Step 2 models, mean of 5 fold models); evaluate ONCE, only when I say "run the pre-registered filter test once" (same run as the filter test). Δ log-loss with 95% CI (HARP bootstrap 10,000, seed 20260921), AUC.
- Reading: "CONFIRMED ON FOLLOW-UP SET" if Δ > 0 AND CI lower > 0; otherwise "NOT CONFIRMED".
- Disclosure (record): this set's labels were seen in Stage 5; its magnetogram features were never computed; it is an EUV-unseen follow-up validation, not an untouched test.

Report the tables after Step 2, commit, STOP.

**Implementation clarifications (decided by: me, before computing; flagged for the user):**
1. **Components per sign.**
   - The components are 8-connected components of {B ≥ +100 G} and of {B ≤ −100 G}, labelled SEPARATELY. The ≥ 90%-opposite and area rules are then applied to each same-sign component.
   - Reason: labelling {|B| ≥ 100} as one mask merges touching opposite polarities. A dot embedded in strong field of the other sign would then join its surroundings, and selftest (a) could not pass.
2. **Background sign.**
   - `np.sign(scipy.ndimage.gaussian_filter(B, 5 / mm_px))` (default reflect boundary). A pixel counts as opposite if sign(B) = −background and the background is ≠ 0.
   - "Centroid pixel" = the component's unweighted centre of mass, rounded to the nearest pixel.
3. **Synthetic tests.**
   - The bipole is two finite ±800 G blocks meeting at a sharp PIL, inside a weak +50 G surround (below 100 G, so the surround forms no component).
   - Placing test (b)'s patch in the weak surround means `pil_mask` finds no strong field of the other polarity near it. Inside strong field, any dot creates its own local PIL overlap and would count by construction.
   - mm_px = 0.362; the patches are 5 Mm² (≈ 38 px) and 30 Mm² (≈ 229 px).
4. **Episodes:** HMI files from `data/euv_full/hmi/<HARP>`, found with `euv_full.hmi_files`. T_REC comes from `data/stage2/oof_scores_dev.csv` (dev only), so the 2010–2024 labelled file is not read.
5. **Workers:** 4 (`ProcessPoolExecutor(4)`) for the episodes and the bootstrap. The bootstrap is drawn in the parent (Phase F method, identical to single process).
6. **Outputs:** only `data/dots/` and repo-root code/log files. Nothing in `data/euv_extra` is read or written.

### DOTS — Step 1 RESULT (label-blind; no labels read)
`euv_dots.py selftest | compute` → `euv_dots_compute.log`, `data/dots/dev_dots.csv`.
- **Selftests passed:**
  - (a) a 4.7 Mm² opposite patch (6×6 px) in the PIL zone → N_dots = 1;
  - (b) the same patch far from the PIL → 0;
  - (c) a 29.5 Mm² patch → 0;
  - (d) deterministic.
- **Run:** 547 dev episodes, 4 workers, 43.5 s. Missing magnetogram: 0.
- **N_dots:** median 15, IQR [9, 22], max 67. Zero in 3 of 547 episodes (0.5%).
- **Phi_dots:** median 9.98e19 Mx.

### DOTS — Step 2 RESULT (evaluated once; EXPLORATORY; dev 2010–2019 only; numbers only)
`euv_dots.py eval` → `euv_dots_eval.log`. 4 workers. Check: A reproduces Stage 4 `p_A` (max |diff| < 1e-12).

**A vs A + log(1+N_dots)** (dev 547: 98 true / 449 false, 180 HARPs):
- LL(A) 0.3336, LL(A + dots) 0.3392.
- **Δ −0.0056 [−0.0218, +0.0083]** (HARP bootstrap 10,000, seed 20260921).
- AUC 0.7432 → 0.7469.
- log(1+N_dots) coefficient per fold (per 1 SD): +0.587, +0.417, +0.197, +0.533, +0.243 (positive 5/5).

**Descriptive:**
- Spearman ρ of log(1+N_dots) with:
  - gate score: +0.563 (p 3.8e-47)
  - n_C: +0.513 (4.4e-38)
  - n_M: +0.383 (1.5e-20)
  - log10 CV_box: +0.371 (2.8e-19, n 546)
- **N_dots ratio** (F2 code; 2,000 resamples, seed 0):
  - all episodes: 1.464 [1.143, 2.077] (medians 20.5 / 14.0);
  - 81 gate-score twins: 1.053 [0.805, 1.372] (medians 20.0 / 19.0).

**Pre-stated reading (mechanical):** Δ −0.0056 is not > 0 → **"NOT ELIGIBLE"**. Step 3 (the conditional follow-up) is therefore NOT run; nothing is computed on data/euv_extra.

## 2026-09-27 — EXPLORATORY — "NEW vs REPEAT" BRIGHTENING LOCATIONS (decided by: user; idea by the student; prompt drafted by Claude AI; recorded verbatim BEFORE computing)
**Verbatim (user):**

DEV 2010–2019 (dev candidate #24), plus a conditional pre-registered follow-up. Frozen files unchanged; no downloads, no JSOC calls.

RUNS ALONGSIDE THE euv_extra DOWNLOAD: do not read, write or lock anything in data/euv_extra now; write outputs to data/novelty/; if git hits index.lock, wait and retry (never delete it); append to decisions.md only; use at most 4 CPU workers. Start only after the dots test (data/dots/) has finished.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE computing; commit.
Physics (record): Dissauer, Barnes, Leka & Wagner 2025 (arXiv:2503.12338): before flares, transient brightenings "tend to occur in one large cluster close to the future flare ribbon location"; in quiet epochs they "appear in smaller clusters not following a clear spatial pattern" (3 cases, qualitative). Prediction: true alarms have a LOWER new-location fraction (brightening repeats in the same place). Test is two-sided.

FEATURE (label-blind; reuse euv_spatial.spatial_episode frame processing and its R3 brightening definition EXACTLY: per-pixel threshold = mean + 3 SD over the episode's valid frames; bright = 8-connected patches covering >= 4 distinct AIA pixels; values on the HMI pixel grid mapped with hmi_to_frame, so "same pixel" follows the Sun's rotation):
- For each box pixel, record the frames in which it is bright.
- NEW = bright pixel-frames where that pixel was never bright in any EARLIER valid frame of the window; REPEAT = all other bright pixel-frames.
- F_new = (number of NEW pixel-frames) / (total bright pixel-frames). Undefined if total bright pixel-frames = 0 (label-blind exclusion, count reported).
- Primary uses valid_primary frames; also compute F_new_nf on valid_sens frames (flare frames removed).
- Checks (assert): box frame means reproduce the stored series (|diff| < 1e-9); per-frame bright-pixel counts reproduce the stored spatial n_bright_px exactly.
- Selftests: synthetic stack where one spot flashes 5 times -> F_new = 1/5 for that spot; 5 different spots once each -> F_new = 1.

STEP 1 — Compute for all dev episodes (primary 80% set). Label-blind report: F_new median, IQR, n undefined; Spearman rho of F_new with R4c and log10 CV_box (label-blind). Save data/novelty/dev_novelty.csv; commit.

STEP 2 — EVALUATION, run once (dev primary 80% set with F_new defined; step 6 settings: same folds, weights 1/n per HARP, training-fold scaling, estimator):
- A vs A + F_new: Δ = logloss(A) − logloss(A + F_new), HARP bootstrap 10,000, seed 20260921, 95% CI; weighted AUC; coefficient sign per fold (per 1 SD).
- Secondary (cannot change the reading): A vs A + F_new_nf on the sens 80% set; F_new twins ratio on the 81 gate-score twins (F2 ratio/CI code); A + log10 CV_box vs A + log10 CV_box + F_new (does location add beyond restlessness?).
PRE-STATED READING (mechanical):
- "ELIGIBLE FOR FOLLOW-UP" only if Δ > 0 AND 95% CI lower > 0 AND AUC(A + F_new) > AUC(A).
- Otherwise "NOT ELIGIBLE". Also report whether the coefficient sign matches the predicted direction (negative) in >= 4 of 5 folds.
Label everything EXPLORATORY. Commit.

STEP 3 — CONDITIONAL FOLLOW-UP (pre-registered now; do NOTHING unless Step 2 says "ELIGIBLE"): after the euv_extra download and compute finish (do not interrupt them), compute F_new label-blind on the EUV-unseen PRIMARY set with identical code; A and A + F_new fitted on dev (mean of 5 fold models); evaluate ONCE, only when I say "run the pre-registered filter test once". Reading: "CONFIRMED ON FOLLOW-UP SET" if Δ > 0 AND CI lower > 0; otherwise "NOT CONFIRMED". Disclosure: this set's labels were seen in Stage 5; its EUV was never computed; EUV-unseen follow-up validation, not an untouched test.

Report tables after Step 2, commit, STOP.

**Implementation (decided by: me, before computing):**
- **Code:** `euv_novelty.py selftest | compute | eval`. The dots test finished and was committed (d89a1a0) before this entry.
- **Episodes:** the dev primary 80% set (541).
- **Images:** from `data/euv_full` (no download). The frame loop is copied from `euv_spatial.spatial_episode`: the same files, `update_pointing` with the same JSOC pointing table, `register_cutout`, SAT_DN and `hmi_to_frame`.
  - The JSOC pointing-table query is the same keyword query every earlier image run made. It is not a download or an export. It is **flagged here** because this entry says "no JSOC calls"; without it the registration cannot be reproduced, and the checks below would fail.
- **Brightenings:** the R3 block is copied verbatim (per-pixel mean + 3 SD with ddof = 1 over the set's valid frames, needing ≥ 3 finite values; 8-connected on the HMI grid; ≥ 4 distinct AIA pixels).
  - For F_new_nf the threshold is taken over the valid_sens frames, exactly as the stored `spatial_nf` run did. Its per-frame counts are checked against `data/euv_full/spatial_nf/<eid>_frames.csv`.
- **NEW:** frames are in time order. A bright pixel-frame is NEW if that HMI pixel was not bright in any earlier frame of the same frame set (primary or nf).
- **Workers:** 4 processes.
- **Decision (user, 2026-09-27, answering my question):** "Wait for download". Step 1, which needs the JSOC pointing-table keyword queries, runs only after the euv_extra download and its computation have finished. No JSOC call is made while the download runs. Selftests passed (one spot flashing 5 times → F_new 0.2 (9/45); five different spots once each → 1.0).

### EUV-unseen follow-up — Step 3 download + Step 4 computation: RESULT (label-blind; counts only; nothing evaluated)
**Download** (`euv_extra.py download`; one pending export at a time, the user's account only):
- PRIMARY 23:11–02:32 (3.35 h); 2022 02:32–05:43 (3.18 h). Failures: 0. Tar timeouts at 01:10 recovered on retry.
- **File checks** (`euv_extra_verify.log`):
  - PRIMARY: HMI 158/158; AIA 17,498 of 17,645 (99.2%); 11.05 GB. 22 short HARPs (147 frames); below 97%: HARP 8923 (753/790).
  - 2022: HMI 152/152; AIA 14,742 of 14,770 (99.8%); 6.35 GB. 13 short HARPs (28 frames); none below 97%.
  - No HARP without AIA.

**Computation** (`euv_extra.py compute`, `euv_full.compute_episode`, 9 workers): 310/310 episodes, 0 errors, wall 0.70 h.

**Counts** (`euv_extra_counts.log`; no label read):

| set | episodes | with results | frames | QUALITY ≠ 0 | exposure | flare (sens only) | primary fill ≥ 80% | CV_box undefined/≤ 0 (fill ok) | evaluable (HARPs) | flare-excl. fill ≥ 80% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| PRIMARY | 158 | 158 | 18,865 | 446 | 209 | 1,176 | 155 | 0 | 155 (40) | 146 |
| 2022 | 152 | 152 | 18,203 | 364 | 165 | 771 | 152 | 0 | 152 (44) | 149 |

STOP (filter test not run). It is evaluated only when the user says "run the pre-registered filter test once".

### NEW vs REPEAT — Step 1 RESULT (label-blind; no labels read)
`euv_novelty.py compute` (started automatically after the euv_extra download and computation finished) → `euv_novelty_compute.log`, `data/novelty/dev_novelty.csv`. 4 workers; wall 1.22 h (06:30–07:43).
- **Coverage:** 541/541 episodes of the dev primary 80% set.
- **Checks passed:** box frame means reproduced (max |diff| 0.0); per-frame n_bright_px reproduced exactly for both the stored spatial and spatial_nf runs, in every episode.
- **F_new:** median 0.5431, IQR [0.4835, 0.6268]. Undefined (no bright pixel-frames): 0 for F_new, 0 for F_new_nf.
- **Spearman ρ:** F_new with R4c −0.861 (p 1.1e-160); with log10 CV_box −0.821 (p 4.6e-133).

### NEW vs REPEAT — Step 2 RESULT (evaluated once; EXPLORATORY; dev 2010–2019 only; numbers only)
`euv_novelty.py eval` → `euv_novelty_eval.log`, `data/novelty/eval.csv`. 4 workers. Δ = LL(base) − LL(base + x); HARP bootstrap 10,000, seed 20260921.

| test | n (true/false) | HARPs | LL base | LL base + x | Δ [95% CI] | AUC base → base + x |
|---|---|---:|---:|---:|---|---|
| **PRIMARY A vs A + F_new** | 541 (96/445) | 179 | 0.3206 | 0.3131 | **+0.0075 [−0.0062, +0.0208]** | 0.7422 → 0.7924 |
| secondary: A vs A + F_new_nf (sens 80%) | 528 (89/439) | 179 | 0.3359 | 0.3278 | +0.0081 [−0.0123, +0.0266] | 0.7480 → 0.7858 |
| secondary: A + log10 CV_box vs + F_new | 541 (96/445) | 179 | 0.3132 | 0.3151 | −0.0018 [−0.0082, +0.0040] | 0.7972 → 0.7888 |

- **F_new coefficient** (per 1 SD): −0.622, −0.517, −0.812, −0.715, −0.625. Negative, the predicted direction, in 5/5 folds → it matches the predicted direction in ≥ 4 of 5.
- **F_new ratio** (true ÷ false medians, F2 code, 2,000 resamples, seed 0): all episodes 0.886 [0.802, 0.942]; 81 gate-score twins 0.934 [0.844, 0.989] (medians 0.4995 / 0.5346).

**Pre-stated reading (mechanical):** Δ +0.0075 > 0 and the AUC rises, but the 95% CI lower bound (−0.0062) is not > 0 → **"NOT ELIGIBLE"**. Step 3 (the conditional follow-up) is therefore NOT run.

### EUV-unseen follow-up — re-export check on HARP 8923: RESULT (label-blind)
AIA re-exported once for the PRIMARY set's range of HARP 8923 (`euv_extra.py reexport primary 8923`; one pending export, the user's account) into `data/euv_extra/primary/reexport/8923/`.
- 753/753 frames, 0 new, 0 missing → **archive gap.** Nothing was copied, overwritten or recomputed.
- Note (label-blind fact): HARP 8923 has INCLUDED episodes in both sets — 5 in PRIMARY (2023-01) and 1 in 2022 (2022-12-31). The sets are evaluated separately and never pooled, as pre-registered; its 2022 copy is complete (120/120).

### Status of the dots test (#23) at the user's request
- Step 2 was run once (d89a1a0). Pre-stated reading: **"NOT ELIGIBLE"** (Δ −0.0056 [−0.0218, +0.0083]).
- Its Step 3 follow-up feature was therefore NOT computed on the PRIMARY set, and no dots follow-up is run with the filter test.

### EUV-unseen follow-up — filter test: implementation (decided by: me, BEFORE the test is run; the pre-registered design 338c0aa is unchanged)
- **Code:** `euv_extra.py filter` (run once) → `euv_extra_filter_test.log`, `data/euv_extra/filter_test/`.
- **Integrity:** every file in `model_hashes.json` (20 fold models, `thresholds.json`, `dev_rows.csv`) must match its recorded SHA-256 before any label is read.
- **New-set features:**
  - `score`, `n_C`, `n_M`, `n_X` at t from `cohort_{set}_all_eligible.csv`. The score is the mean of the 5 frozen gate folds, as Stage 5.
  - log10 CV_box = log10(`primary_CV_box`) from `<set>/results`.
  - log(1+R) with the Step B code (`euv_confirm_tests.log_r`, `swpc.fetch` 2020-12-29 → 2025-01-01). Check: (R < 48) ⇔ (n_C + n_M + n_X ≥ 1).
- **Evaluable set:** INCLUDED ∩ `primary_fill` ≥ 0.80 ∩ CV_box finite and > 0 (PRIMARY 155, 2022 152). Weights 1/n per HARP over that set; delayed episodes are false. Prediction = mean of the 5 fold models; kept = p ≥ frozen τ.
- **D_false and D_true:**
  - D_false = FR(A_CV) − FR(A), with FR = Σ w(1 − y)[p < τ] / Σ w(1 − y) (weighted fraction of false alarms removed).
  - D_true = TK(A_CV) − TK(A), with TK = Σ w·y·[p ≥ τ] / Σ w·y (weighted fraction of true alarm episodes kept).
  - Both are reported in percentage points.
- **CIs:** paired HARP bootstrap, 2,000 resamples, `np.random.RandomState(0)`; the same resamples serve both statistics and both model pairs. The 2.5/97.5 percentiles are taken over resamples in which both statistics are defined; the number dropped is reported.
- **INCONCLUSIVE** if the set has no true or no false episode, or no resample is valid.
- **Reading** (mechanical, as pre-registered; −10 points = −0.10):
  - "CONFIRMED SAFE FILTER": D_false CI lower > 0 and D_true CI lower ≥ −10.
  - "MEETS OPERATING CRITERION": D_false CI lower > 0 and D_true point ≥ −10 (CI lower < −10).
  - "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)": D_false CI lower > 0 and D_true point < −10.
  - "INCONCLUSIVE" as above; otherwise "NOT CONFIRMED".
  - The reading uses the PRIMARY set's A vs A_CV only.
- **Secondary** (cannot change the reading), for both sets:
  - counts per model (true alarm episodes kept, false alarms kept, false alarms removed);
  - Δ log-loss A − A_CV and C − C_CV (HARP bootstrap 10,000, seed 20260921);
  - AUC of all four models;
  - C vs C_CV D_false / D_true (same resamples);
  - CV_box twins ratio (`euv_f2_replication.twins` = the step 6 code; `phase_f.ratio_jobs`; pairs resampled by true HARP, 2,000, seed 0);
  - composition by year × single/two-region.
- **Wording:** "true alarm episodes kept".

### EUV-unseen follow-up — PRE-REGISTERED FILTER TEST: RESULTS (run once; numbers only)
`euv_extra.py filter` → `euv_extra_filter_test.log`, `data/euv_extra/filter_test/`. Integrity: all 22 model/threshold/dev-row files matched their recorded SHA-256. A label-free smoke test of the data path ran before the single run. The dots follow-up was NOT run (dots: "NOT ELIGIBLE").

**PRIMARY 2021/2023/2024:**
- INCLUDED 158; evaluable 155 (32 true / 123 false, 40 HARPs); 3 label-blind exclusions (fill).
- Composition: all two-region — 2021: 8, 2023: 94, 2024: 53.

| model | τ (frozen) | true alarm episodes kept (n; weighted) | false alarms kept | false alarms removed (n; weighted) | AUC | log-loss |
|---|---:|---|---:|---|---:|---:|
| A | 0.0680 | 32/32; 1.0000 | 123 | 0/123; 0.0000 | 0.8006 | 0.3954 |
| A_CV | 0.0747 | 26/32; 0.8383 | 53 | 70/123; 0.6020 | 0.8075 | 0.3905 |
| C | 0.0626 | 28/32; 0.8978 | 101 | 22/123; 0.1701 | 0.7752 | 0.3922 |
| C_CV | 0.0689 | 27/32; 0.8717 | 62 | 61/123; 0.5232 | 0.8075 | 0.3912 |

| comparison | D_false (pts) [95% CI] | D_true (pts) [95% CI] | Δ log-loss (base − CV) [95% CI] | AUC base → CV |
|---|---|---|---|---|
| **A vs A_CV** | **+60.20 [+46.92, +72.77]** | **−16.17 [−37.58, −1.98]** | +0.0050 [−0.0181, +0.0256] | 0.8006 → 0.8075 |
| C vs C_CV | +35.32 [+17.11, +51.85] | −2.60 [−13.33, +3.49] | +0.0011 [−0.0240, +0.0224] | 0.7752 → 0.8075 |

- 2,000/2,000 resamples were used.
- CV_box twins ratio: 23 pairs of 32 true episodes; 1.630 [0.791, 3.839] (medians 0.1563 / 0.0959). All-episodes ratio 1.706 [0.878, 2.837].

**PRE-STATED READING (mechanical; PRIMARY, A vs A_CV):** D_false CI lower +46.92 > 0, but D_true point −16.17 < −10 → **"REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)"**.

**SENSITIVITY 2022** (reported separately; never pooled; cannot change the reading):
- 152 evaluable (28 true / 124 false, 44 HARPs); 101 single-region, 51 two-region.

| model | true alarm episodes kept | false alarms removed | AUC | log-loss |
|---|---|---|---:|---:|
| A | 28/28; 1.0000 | 0/124; 0.0000 | 0.7397 | 0.4177 |
| A_CV | 22/28; 0.8567 | 68/124; 0.6068 | 0.8222 | 0.3749 |
| C | 26/28; 0.9435 | 18/124; 0.2444 | 0.7484 | 0.4028 |
| C_CV | 22/28; 0.8567 | 66/124; 0.5536 | 0.8217 | 0.3758 |

- A vs A_CV: D_false +60.68 [+49.02, +72.57]; D_true −14.33 [−32.52, −3.42]; Δ log-loss +0.0427 [+0.0010, +0.0945].
- C vs C_CV: D_false +30.92 [+15.36, +46.18]; D_true −8.68 [−27.03, +1.89]; Δ log-loss +0.0270 [−0.0040, +0.0591].
- CV_box twins ratio: 25 pairs; 3.235 [1.255, 4.545]. All-episodes ratio 2.766 [1.019, 6.291].

STOP.

## 2026-09-27 — 2025–26 RE-TEST: CV_box AS A FILTER ON TOP OF MODEL C (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user):**

Frozen files unchanged; never overwrite existing models, thresholds or results. Do not run stage5_test.py. No JSOC downloads are needed; if any step seems to need one, STOP and ask.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else, headed "2026-09-27 — 2025–26 RE-TEST: CV_box AS A FILTER ON TOP OF MODEL C (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)". Commit.
Disclosure (record verbatim): This comparison (C vs C_CV) was chosen AFTER seeing it as a secondary result in the EUV-unseen follow-up (5abc40a: +35.3 [+17.1, +51.9] false removed, −2.6 [−13.3, +3.5] true kept), where the pre-registered primary (A vs A_CV) was not confirmed because A's frozen threshold kept every episode. 2025–26 flare labels and CV_box values were already seen together in TEST 1 (twins) and TEST 2 (Step B) (ae1b174). This is a "pre-registered re-test on an already-analysed set", NOT an untouched test. Models were trained on single-region dev episodes and are applied to <= 2-region episodes (population change; reported).

HYPOTHESIS: Adding log10 CV_box to Model C removes more false alarms at the dev-frozen thresholds while keeping true alarm episodes, on the 2025–26 confirmation cohort.

SET: data/euv_confirm/cohort_le2.csv, the same evaluable rows as TEST 1 (fill >= 80%, CV_box finite and > 0), with R (hours since last C1+ flare, capped 48; Step B definition) exactly as used in TEST 2. Weights 1/n per HARP. Delayed episodes count as false.

MODELS AND THRESHOLDS: use ONLY the frozen artifacts in data/euv_extra/models/ and data/euv_extra/thresholds.json (C τ 0.062570, C_CV τ 0.068936, A τ 0.067970, A_CV τ 0.074657). Verify every SHA-256 against data/euv_extra/model_hashes.json before use. No refitting. Prediction = mean of the 5 fold models.

PRIMARY comparison: C vs C_CV at their frozen thresholds. From the SAME paired HARP resamples (2,000, seed 0):
 D_false = weighted % false alarms removed (C_CV minus C), with 95% CI;
 D_true  = weighted % true alarm episodes kept (C_CV minus C), with 95% CI.
READING (mechanical, decided now):
 "CONFIRMED SAFE FILTER" if D_false CI lower > 0 AND D_true CI lower >= −10 points.
 "MEETS OPERATING CRITERION" if D_false CI lower > 0 AND D_true point estimate >= −10 points (but its CI lower < −10).
 "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)" if D_false CI lower > 0 AND D_true point estimate < −10 points.
 "INCONCLUSIVE" if the CIs cannot be computed.
 "NOT CONFIRMED" otherwise.
SECONDARY (cannot change the reading): counts kept/removed per model; AUC; Δ log-loss (C minus C_CV; HARP bootstrap 10,000, seed 20260921); A vs A_CV with the same outputs; composition (single- vs two-region, by year). Never pool with any other set.
Wording in all outputs: "true alarm episodes kept", not "real flares".

STEP 1 — LABEL-BLIND checks only (do not read true_alarm or delayed; do not print outcomes):
 a) Row count and HARP count of the evaluable set; confirm they match TEST 1's evaluable set; list any mismatch with reasons.
 b) Confirm every model input column exists with no missing values; confirm R matches the TEST 2 definition (report how you checked).
 c) All hash checks pass.
 d) BASELINE GUARD (decided now): report the weighted % of ALL episodes with p >= τ for C and for C_CV. If C keeps > 95% of all episodes, write "BASELINE THRESHOLD DOES NOT FILTER — TEST NOT RUN" in decisions.md, commit, and STOP permanently.
 Commit the check results. STOP.

Do not evaluate until I say "run the 2025–26 filter re-test once". Then: run it exactly once, write the results table and the mechanical reading to euv_confirm_filter_retest.log and decisions.md, commit, and report the numbers verbatim with no interpretation beyond the pre-stated reading.

### 2025–26 RE-TEST — Step 1 LABEL-BLIND CHECKS: RESULT (true_alarm and delayed not read; no outcome printed)
`euv_confirm_retest.py checks` → `euv_confirm_retest_checks.log`. Only label-free cohort columns were read: harpnum, t, score, n_C, n_M, n_X, noaa_ars.
- **a)** Evaluable set: 378 episodes, 101 HARPs. TEST 1's evaluable set (rebuilt with its rule: fill ≥ 80%, CV_box not NaN) is also 378 / 101. Mismatch: 0 episodes.
- **b) Model inputs** (score, n_C, n_M, n_X, logR, log10_CV_box): 0 missing values in every column.
  - R was computed with `euv_confirm_tests.log_r`, the function TEST 2 used, on all 387 ≤ 2 episodes with TEST 2's event window (2024-12-29 → 2026-08-18 23:59; C1+ = K2 flux ≥ 1e-6; start in (t − 48 h, t); cap 48).
  - A repeated computation is identical; (R < 48) ⇔ (n_C + n_M + n_X ≥ 1) holds for all 387.
- **c)** All 22 files in `model_hashes.json` match; `thresholds.json` matches `7a34507c…`. Frozen τ: A 0.067970, A_CV 0.074657, C 0.062570, C_CV 0.068936.
- **d) BASELINE GUARD** — weighted % of ALL evaluable episodes with p ≥ τ:
  - A 100.00% (378/378)
  - A_CV 43.18% (148/378)
  - **C 72.55% (289/378)**
  - C_CV 50.02% (168/378)
  - C keeps 72.55% ≤ 95% → **guard passed** (the test may be run on the user's command).

STOP. The re-test is not evaluated until the user says "run the 2025–26 filter re-test once".

### 2025–26 RE-TEST — implementation details (recorded BEFORE the run; the pre-registered reading, 25fcd66, is unchanged)
- **Trigger:** the user said "run the 2025–26 filter re-test once" (2026-09-27). The run is `euv_confirm_retest.py run` on the 378 evaluable episodes checked in e4eb16e. All hashes are re-verified first (`load_models`).
- **Statistics:** the SAME functions as the EUV-unseen filter test (5abc40a, `euv_extra.py filter`) are reused:
  - `phase_f.boot_many` with statistic `"op"` (`phase_f._op` → `phase_f.op_stats`: weighted true alarm episodes kept, weighted false alarms removed, precision). It is run once with kept = [A, A_CV, C, C_CV] at the frozen τ: 2,000 paired HARP resamples, `RandomState(0)`, drawn in the parent (the same resamples for every model and both comparisons).
  - `phase_f.boot_many` with `"dll"` (`phase_f._dll` → `phase_f.wlogloss`): Δ log-loss, 10,000 resamples, seed 20260921.
  - `phase_f.pct` for the Δ log-loss CI; `sklearn.metrics.roc_auc_score(sample_weight=w)` for AUC; `phase_f.wlogloss` for log-loss.
  - Prediction = mean of the 5 frozen fold models' probabilities; kept = p ≥ τ; weights 1/n per HARP over the 378.
- **No new statistics code.** The few lines that turn the `op` resamples into D_false / D_true and their percentiles were inline in `euv_extra.py filter` (not a function). They are copied verbatim into `euv_confirm_retest.py`: D = (CV model − base) per resample; ok = both D_false and D_true finite; 2.5/97.5 percentiles over the ok resamples; ×100 → points.
- **Resamples with no true or no false episodes:** as in 5abc40a, `op_stats` returns NaN for the undefined fraction. Those resamples are dropped from both CIs, and `resamples_used` is reported. The reading is "INCONCLUSIVE" if the set has no true or no false episode, or 0 resamples are usable.
- **Output order:** everything is computed first and printed only at the end. A crash therefore happens before any outcome is printed.

### 2025–26 RE-TEST — RESULTS (run once; numbers only; "pre-registered re-test on an already-analysed set", NOT an untouched test)
`euv_confirm_retest.py run` → `euv_confirm_filter_retest.log`, `data/euv_confirm/retest_models.csv`, `retest_comparisons.csv`. The run completed without error.
- **Integrity:** 22 files and `thresholds.json` re-verified; frozen models only; no refitting.
- **Set:** 378 evaluable ≤ 2-region episodes (56 true / 322 false, 101 HARPs); weights 1/n per HARP; delayed = false.
- **Composition** (year / regions at t): 2025/1: 101, 2025/2: 161, 2026/1: 62, 2026/2: 54.

| model | τ (frozen) | true alarm episodes kept (n/N; weighted) | false kept | false removed (n/N; weighted) | AUC | log-loss |
|---|---:|---|---:|---|---:|---:|
| A | 0.0680 | 56/56; 1.0000 | 322 | 0/322; 0.0000 | 0.7631 | 0.3933 |
| A_CV | 0.0747 | 41/56; 0.7863 | 107 | 215/322; 0.6312 | 0.7993 | 0.3662 |
| C | 0.0626 | 54/56; 0.9262 | 235 | 87/322; 0.3102 | 0.7693 | 0.3774 |
| C_CV | 0.0689 | 41/56; 0.7863 | 127 | 195/322; 0.5507 | 0.7977 | 0.3672 |

D_false and D_true are in percentage points: paired HARP bootstrap, 2,000 resamples, seed 0. Δ log-loss = base − CV model: HARP bootstrap, 10,000 resamples, seed 20260921.

| comparison | D_false [95% CI] | D_true [95% CI] | resamples_used | Δ log-loss [95% CI] | AUC base → CV |
|---|---|---|---:|---|---|
| **PRIMARY C vs C_CV** | **+24.05 [+14.63, +33.45]** | **−13.98 [−28.47, −4.42]** | 2000 | +0.0102 [−0.0170, +0.0371] | 0.7693 → 0.7977 |
| SECONDARY A vs A_CV | +63.12 [+54.38, +71.83] | −21.37 [−40.33, −7.32] | 2000 | +0.0272 [−0.0010, +0.0568] | 0.7631 → 0.7993 |

**PRE-STATED READING (mechanical; PRIMARY C vs C_CV):** D_false CI lower +14.63 > 0, but D_true point −13.98 < −10 → **"REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)"**.

STOP.

## 2026-09-27 — DESCRIPTIVE AIA 94 Å FOLLOW-UPS: alert tiers, noise/exposure/saturation check, calm-flarer profile (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user):**

EXPLORATORY / DESCRIPTIVE ONLY. Nothing here is a test or a confirmation, and no result can be reported as "confirmed". Frozen files unchanged; never overwrite existing models, thresholds, series or results. Do not run stage5_test.py. No downloads of any kind; if a step seems to need one, STOP and ask.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else, headed "2026-09-27 — DESCRIPTIVE AIA 94 Å FOLLOW-UPS: alert tiers, noise/exposure/saturation check, calm-flarer profile (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)". Commit.
Disclosure (record verbatim): Defined AFTER the 2025–26 filter re-test (4b65f23) and after seeing that the true alarm episodes dropped by C_CV had low CV_box. All definitions below are fixed now, before computing, and every result is reported whatever it shows. Post-hoc, descriptive, not pre-registered.

SETS (each reported separately, never pooled):
 S1 = 2025–26 confirmation <= 2-region evaluable set (378 episodes; e4eb16e/4b65f23).
 S2 = EUV-unseen PRIMARY 2021/23/24 evaluable set (155; 5abc40a).
 S3 = 2022 sensitivity evaluable set (152; 5abc40a).
Weights 1/n per HARP within each set. Delayed episodes count as false (as in the tests), but "delayed" is also reported where stated.

MODELS: frozen data/euv_extra models and thresholds only (hash-verify all 22 files + thresholds.json). Prediction = mean of 5 fold models. No refitting.

PART 1 — ALERT TIERS (fixed definitions):
 NO ALERT = p_C < τ_C.
 WATCH    = p_C >= τ_C AND p_C_CV < τ_C_CV.
 WARNING  = p_C >= τ_C AND p_C_CV >= τ_C_CV.
 Also count "CV-only" = p_C < τ_C AND p_C_CV >= τ_C_CV (reported, not a tier).
 Per set and tier: episodes, true, false, weighted flare rate (true share) with HARP bootstrap 95% CI (2,000, seed 0); share of all true alarm episodes in each tier; rate ratio WARNING/WATCH with CI from the same resamples. Among false episodes: fraction delayed in WARNING vs WATCH (counts + weighted).

PART 2 — IS CV_box AN ARTIFACT? (noise, exposure, saturation)
 First reproduce the stored CV_box for every episode in S1–S3 from its series file with the EXACT existing code path (same valid_primary frames, same detrending, same function). Required: |diff| < 1e-9 for all. If not, STOP and report.
 Then, per episode, recompute CV_box with ONLY the frame set changed:
  2a Exposure: keep only valid frames whose exptime is within ±5% of the episode's median exptime. Report per set the fraction of valid frames removed, medians for true vs false.
  2b Saturation: keep only valid frames with sat_px == 0. Report the fraction of frames removed, true vs false.
 2c Photon + read noise: expected noise CV per episode = relative SD of the box-mean series from Poisson photon noise + read noise, using box mean DN/s × exptime, the number of box pixels (take it from the existing masks/code; state how), and the AIA 94 Å DN-per-photon and read noise. Get these constants from aiapy (quote the function and the values) or from Boerner et al. 2012 (quote table and page). If neither can be done without a download, STOP and report. Corrected CV_corr = sqrt(max(CV_box² − CV_noise², 0)). Report median CV_noise / CV_box, true vs false.
 For each of 2a, 2b, 2c: the twins ratio (median true / median false) using the SAME stored twin pairs and the SAME CI procedure as the original twins result of that set (S1: TEST 1 pairs, ae1b174; S2/S3: 5abc40a). Print it next to the original ratio. Episodes that become undefined: count them and drop the pair (reported).

PART 3 — CALM-FLARER PROFILE (true alarm episodes only, per set):
 Compare true episodes in WATCH vs WARNING (and NO ALERT, if any). For each: peak class of the largest M1+ flare in (t, t+24h]; hours from t to the first M1+ flare start; flare-history group (JUST-FLARED / C-only / QUIET-NOW, F4 definitions); regions at t (1 or 2); gate score; CV_box; fill; |longitude| at t if already in local files (else "not available"); number of saturated frames.
 Flare details must come from the SAME label code/event list that produced true_alarm; first check that it reproduces the stored true_alarm for every episode (report mismatches and STOP if any). Report group medians and counts; for S1 also list every true episode individually. No p-values.

OUTPUTS: descriptive_aia94.py, descriptive_aia94.log, a results entry in decisions.md (verbatim numbers), figures/alert_tiers.png (flare rate per tier per set with CIs; clearly titled "descriptive, post-hoc"). Commit. Report the numbers verbatim with the commit hash. No interpretation, and never use the words "confirmed", "validated" or "significant". STOP.

### DESCRIPTIVE AIA 94 Å FOLLOW-UPS — RESULTS (EXPLORATORY / DESCRIPTIVE; post-hoc; not pre-registered; sets never pooled; numbers only)
`descriptive_aia94.py` → `descriptive_aia94.log`, `figures/alert_tiers.png`, `data/descriptive_aia94_{S1,S2,S3}.csv`. Frozen euv_extra models (22 files + thresholds.json hash-verified; τ_C 0.062570, τ_C_CV 0.068936); no refitting; no download.

**Log note:** the first invocation piped stdout through `grep -v -i warn`, which also removed every line containing "WARNING" (the tier name). The deterministic script was re-run once with a filter that removes only Python warning lines. The results are identical; `descriptive_aia94.log` is the complete output.

**Checks:**
- Stored CV_box reproduced from the series with `euv_dctrl.cv` (the `summarise` code path, valid_primary frames): S1 378/378 (max |diff| 2.2e-16), S2 155/155 (9.7e-17), S3 152/152 (1.1e-16).
- The label code's event list (`swpc.fetch` joinable M1+, region in noaa_ars, start in (t, t + 24 h]) reproduces the stored true_alarm for every episode (0 mismatches).
- The original twins ratios are reproduced exactly: S1 with the TEST 1 stored pairs; S2/S3 with pairs regenerated by the 5abc40a code.

**Noise constants** (no download): `aiapy.calibrate.utils.get_error_table` on aiapy's packaged `aia_V3_error_table.txt`. Its SHA-256 `66ff0349…` equals aiapy's recorded hash of the SSW V3 table. 94 Å: DNPERPHT = 1.975 DN/photon. Read noise 1.14 DN/pixel for camera 4, from `aiapy.calibrate.estimate_error`, which cites Boerner et al. 2012 Table 6.
- **Box pixel count:** n_HMI = NAXIS1 × NAXIS2 of the alarm-time magnetogram (the `euv_dctrl.samples` box = all HMI patch pixels). n_AIA = n_HMI × (CDELT1_HMI / 0.6″)² × (1 − frac_outside) per frame.
- **Noise per frame:** σ = √(g·box·exptime + read²) / √n_AIA / exptime. CV_noise = √mean(σ²) / mean(box).

**PART 1 — alert tiers.** Weighted flare rate = weighted share of true alarm episodes; HARP bootstrap 2,000, seed 0.

| set | tier | episodes | true | false | weighted rate [95% CI] | share of true (n; weighted) | delayed among false (n; weighted) |
|---|---|---:|---:|---:|---|---|---|
| S1 | NO ALERT | 89 | 2 | 87 | 0.0406 [0.0000, 0.1243] | 0.0357; 0.0738 | 2/87; 0.0119 |
| S1 | WATCH | 135 | 13 | 122 | 0.0769 [0.0225, 0.1569] | 0.2321; 0.1398 | 11/122; 0.1186 |
| S1 | WARNING | 154 | 41 | 113 | 0.2631 [0.1486, 0.3773] | 0.7321; 0.7863 | 14/113; 0.1232 |
| S2 | NO ALERT | 26 | 4 | 22 | 0.1215 [0.0000, 0.3086] | 0.1250; 0.1022 | 2/22; 0.0588 |
| S2 | WATCH | 47 | 2 | 45 | 0.0210 [0.0000, 0.0726] | 0.0625; 0.0382 | 4/45; 0.0389 |
| S2 | WARNING | 82 | 26 | 56 | 0.3206 [0.1791, 0.4616] | 0.8125; 0.8596 | 18/56; 0.3097 |
| S3 | NO ALERT | 20 | 2 | 18 | 0.0378 [0.0000, 0.1204] | 0.0714; 0.0565 | 2/18; 0.0198 |
| S3 | WATCH | 56 | 5 | 51 | 0.0455 [0.0059, 0.1091] | 0.1786; 0.1042 | 4/51; 0.0871 |
| S3 | WARNING | 76 | 21 | 55 | 0.2707 [0.1223, 0.4352] | 0.7500; 0.8393 | 9/55; 0.1245 |

**Rate ratio WARNING / WATCH:**
- S1: 3.4208 [1.4332, 11.4293] (1,998 of 2,000 resamples defined)
- S2: 15.3000 [3.0444, 23.1692] (1,284 of 2,000 defined)
- S3: 5.9465 [1.6984, 33.0968] (1,968 of 2,000 defined)

**CV-only** (not a tier; contained in NO ALERT):
- S1: 14 episodes (0 true / 14 false)
- S2: 7 (1 / 6)
- S3: 4 (1 / 3)

**PART 2 — CV_box artifact check** (only the frame set changed):
- **2a exposure ±5% of the median:** valid frames removed S1 0.02% of 44,240; S2 0.02% of 18,089; S3 0.02% of 17,826. Per-episode median removed: 0.00% for true and false in all sets.
- **2b sat_px == 0:** removed S1 0.26%; S2 0.43%; S3 0.22%. Per-episode median 0.00% for true and false in all sets.
- **2c median CV_noise / CV_box** (all; true; false; max): S1 0.0112; 0.0041; 0.0132; max 0.1751. S2 0.0072; 0.0044; 0.0080; max 0.0856. S3 0.0091; 0.0041; 0.0098; max 0.0848. CV_corr = 0 in 0 episodes.

**Twins ratios** (median true ÷ median false; pairs resampled by true HARP, 2,000, seed 0; no pairs dropped; 0 undefined episodes):

| set (pairs) | original CV_box | 2a CV_exp | 2b CV_sat | 2c CV_corr |
|---|---|---|---|---|
| S1 (50) | 3.2624 [1.2956, 9.4887] | 3.2624 [1.2956, 9.4887] | 2.6904 [1.1650, 7.6317] | 3.2640 [1.2956, 9.4911] |
| S2 (23) | 1.6295 [0.7907, 3.8386] | 1.6295 [0.7907, 3.8386] | 1.6295 [0.7908, 3.2193] | 1.6295 [0.7907, 3.8387] |
| S3 (25) | 3.2350 [1.2554, 4.5452] | 3.2350 [1.2553, 4.5452] | 3.2350 [1.2554, 4.2509] | 3.2354 [1.2554, 4.5454] |

**PART 3 — calm-flarer profile** (true alarm episodes; flare details from the label code's event list; K2 true scale). Values are medians; "two-region" is a count.

| set | tier | n | h to first M1+ | gate score | CV_box | fill | \|lon\| | sat. frames | two-region | peak class | history group |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| S1 | NO ALERT | 2 | 7.08 | −0.9771 | 0.0859 | 0.9917 | 31.90 | 0 | 0 | M 2 | QUIET-NOW 2 |
| S1 | WATCH | 13 | 10.94 | −0.9484 | 0.0694 | 0.9917 | 23.56 | 0 | 10 | M 13 | C-only 11, JUST-FLARED 2 |
| S1 | WARNING | 41 | 6.94 | −0.9301 | 0.3820 | 0.9917 | 15.16 | 1 | 27 | M 39, X 2 | JUST-FLARED 27, C-only 13, QUIET-NOW 1 |
| S2 | NO ALERT | 4 | 16.17 | −0.9771 | 0.0693 | 0.9917 | 9.57 | 0 | 4 | M 4 | QUIET-NOW 3, C-only 1 |
| S2 | WATCH | 2 | 16.59 | −0.9635 | 0.0838 | 0.9917 | 31.95 | 0 | 2 | M 2 | C-only 2 |
| S2 | WARNING | 26 | 9.44 | −0.0900 | 0.2140 | 0.9583 | 19.71 | 0 | 26 | M 26 | JUST-FLARED 19, C-only 6, QUIET-NOW 1 |
| S3 | NO ALERT | 2 | 21.47 | −0.9573 | 0.1822 | 0.9917 | 29.53 | 0 | 0 | M 2 | C-only 1, QUIET-NOW 1 |
| S3 | WATCH | 5 | 15.49 | −0.8949 | 0.0508 | 0.9917 | 25.48 | 0 | 2 | M 4, X 1 | C-only 4, QUIET-NOW 1 |
| S3 | WARNING | 21 | 6.66 | −0.8591 | 0.2983 | 0.9917 | 19.98 | 1 | 9 | M 20, X 1 | JUST-FLARED 13, C-only 7, QUIET-NOW 1 |

The S1 per-episode list of all 56 true alarm episodes is in `descriptive_aia94.log`.

## 2026-09-27 — SENSITIVITY: CV_box twins with magnetic + flare-history matching AND flare frames removed; image-only spike removal (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user):**

SENSITIVITY CHECK ONLY (post-hoc, on already-analysed data). Nothing here is a test or a confirmation, and no result can be called "confirmed". Frozen files unchanged; never overwrite existing series, results, models or pairs. Do not run stage5_test.py. No downloads; if a step seems to need one, STOP and ask.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else, headed "2026-09-27 — SENSITIVITY: CV_box twins with magnetic + flare-history matching AND flare frames removed; image-only spike removal (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)". Commit.
Disclosure (record verbatim): Defined after all 2025–26 results (ae1b174, 4b65f23, 5af931b) and after an ad-hoc check by Claude AI (not committed) that found, on 2025–26, a twins ratio of 2.92 [1.18, 8.45] with flare frames removed (49 pairs). Purpose: check whether real alarms are more restless than magnetic twins after holding magnetic score AND flare history constant AND removing flare-time frames, including a version built from 94 Å images only. All definitions below are fixed now, before computing, and every cell is reported whatever it shows.

SETS: PRIMARY = S1, the 2025–26 <= 2-region evaluable set (378 episodes; TEST 1, ae1b174). SECONDARY (reported separately, never pooled): S2 = EUV-unseen PRIMARY 2021/23/24 (155) and S3 = 2022 (152), as in 5abc40a.

CV_box VERSIONS (same CV_box function and detrending as the stored values; only the frame set changes):
 V0 = stored primary CV_box (flare frames kept). Reference.
 V1 = stored flare-excluded CV_box (sens_CV_box; frames inside a C1+ SWPC event of the HARP's NOAA region(s), or any M1+ event, removed; sens_fill >= 0.80).
 V2 = IMAGE-ONLY spike removal. No flare list, no magnetic data. Using the stored per-frame box values of valid_primary frames in time order:
   a) running median m_i over the 5 valid frames centred on frame i (shrink at the ends);
   b) residual r_i = box_i − m_i; robust scale s = 1.4826 × median(|r_i|) over the episode;
   c) flag frame i if r_i > 3 s (upward jumps only);
   d) remove the flagged frames and repeat a)–c) on the remaining frames until nothing new is flagged (max 5 rounds);
   e) fill = remaining frames / expected slots; require >= 0.80; then CV_box on the remaining frames.
 V2 robustness (reported, not primary): the same with 2.5 s and 4 s.

CHECKS FIRST (STOP if any fails):
 - Reproduce stored V0 and V1 from the series files with the frame-subset code path: |diff| < 1e-9 for every episode.
 - Report V2 frames removed per episode (median, mean) for true vs false, and agreement with the flare list: of V2-flagged frames, the fraction inside V1 flare windows; of V1 flare frames, the fraction flagged by V2.

TWINS (the magnetic/flare-history control):
 T_a = magnetic twins: the stored TEST 1 pairs (S1) / the 5abc40a pairs (S2, S3).
 T_b = magnetic + flare-history twins: the SAME code as the TEST 1 secondary "s1" (by_group=True; F4 groups JUST-FLARED / C-only / QUIET-NOW; caliper 0.0747; same seed and order), built on the V0 evaluable set.
 For each version, keep a pair only if both members are defined under that version; report pairs dropped.

STATISTICS (same as TEST 1): twins ratio = median(true) / median(false); 95% CI with pairs resampled clustered by true HARP, 2,000, seed 0; the count of pairs where the true member is higher; a two-sided sign-test p. Report all 2 × 3 cells (T_a/T_b × V0/V1/V2) plus the V2 robustness rows, for S1, then S2 and S3.

DESCRIPTIVE READING (per cell, fixed now): "direction holds, CI above 1" if ratio > 1 and CI lower > 1; "direction holds, CI includes 1" if ratio > 1 and CI lower <= 1; "direction reversed" if ratio <= 1. Never the words "confirmed", "validated" or "significant".

OUTPUTS: sensitivity_combined.py, sensitivity_combined.log, a results entry in decisions.md (verbatim numbers), and figures/sensitivity_combined.png (twins ratio with CI for each cell, S1 on top, S2/S3 below; titled "post-hoc sensitivity"). Commit. Report the numbers verbatim with the commit hash. STOP.

### 2026-09-27 — SENSITIVITY (92027fa): implementation note, recorded before the complete run (decided by: me)
- **Scripts reused:** `sensitivity_combined.py` reuses `descriptive_aia94.load_set` (the same sets as 5af931b), `euv_dctrl.cv` and `euv_f2_replication.twins` (T_a = `twins(c)`; T_b = `twins(c, by_group=True)`, the TEST 1 s1 code). It also uses `phase_f.ratio_jobs` / `boot_many` (twins CI, pairs resampled by true HARP, 2,000, seed 0) and `scipy.stats.binomtest` for the two-sided sign test (ties excluded).
- **V1 definedness:** V1 is defined when the stored sens_fill is ≥ 0.80.
- **V2 fill:** V2 fill = remaining frames / 120 expected 12-min slots in (t−24h, t].
- **Extra reproduction checks (a failure also STOPs):**
  - The regenerated S1 T_a pairs must equal the stored `twins_le2.csv`.
  - T_a × V0 must reproduce the committed ratios for S1–S3.
  - S1 T_b × V0 must reproduce TEST 1 s1 (47 pairs, 2.817 [1.017, 6.823]).
- **First run crashed before any output:**
  - What happened: the V0/V1 reproduction checks passed, then `boot_many` failed on a cell with 0 pairs (`np.concatenate` of an empty list).
  - Cause: at 3 s, V2 as defined removes about 60 of about 119 valid frames per episode (40-episode S1 look). Between 32% and 50% of round-1 residuals are exactly 0 (the median of 5 equals the centre frame), so s = 1.4826 × median|r| is 0 or tiny and V2 fill falls below 0.80.
  - What changed: the V2 definition is unchanged. A cell with 0 pairs gets no bootstrap; its ratio and CI are reported as undefined and its reading as "undefined (0 pairs)". The fixed readings need a ratio, so no reading is applied to such cells.
  - Added descriptive counts only: episodes with s = 0 in some round; episodes still flagging in round 5 (the cap); and the per-episode fraction of round-1 residuals that are exactly 0. The figure labels 0-pair cells as such.
  - The script is then run once to completion.

### 2026-09-27 — SENSITIVITY (92027fa): RESULTS (post-hoc; not a test; sets never pooled)
Recorded from `sensitivity_combined.log`. The script was run twice: the second time only to fix the figure's y-limits, which were clipping the bottom row. The logs are identical apart from the wall time.

**CHECKS (all passed):**
- **V0/V1 reproduction:** stored V0 and V1 were reproduced from the series files with the frame-subset code path (|diff| < 1e-9):
  - S1: 378/378 (max 2.2e-16 V0 / 9.7e-17 V1)
  - S2: 155/155 (9.7e-17 / 9.7e-17)
  - S3: 152/152 (1.1e-16 / 1.1e-16)
  - Stored V1 undefined (< 3 frames): 0.
- **S1 T_a:** the regenerated pairs are identical to the stored TEST 1 pairs.
- **T_a × V0:** reproduces the committed ratios for S1–S3.
- **S1 T_b × V0:** reproduces TEST 1 s1 (47 pairs, 2.817 [1.017, 6.823]).

**Defined episodes and V2 diagnostics** (V2 fill = remaining frames / 120 slots):

| set | episodes | V0 | V1 | V2 3 s | V2 2.5 s | V2 4 s | round-1 residuals exactly 0, per-episode median [IQR] |
|---|---:|---:|---:|---:|---:|---:|---|
| S1 | 378 | 378 | 373 | 19 | 6 | 79 | 0.3697 [0.3277, 0.4200] |
| S2 | 155 | 155 | 146 | 7 | 1 | 33 | 0.3613 [0.3273, 0.4009] |
| S3 | 152 | 152 | 149 | 4 | 1 | 22 | 0.3697 [0.3305, 0.4118] |

| set | V2 | removed per episode: true median / mean | false median / mean | flagged frames | flagged inside V1 flare windows | V1 flare frames flagged | median fill | s = 0 in some round | still flagging in round 5 |
|---|---|---|---|---:|---|---|---:|---:|---:|
| S1 | 3 s | 61.0 / 58.14 | 54.5 / 53.67 | 20,537 | 1,047 (0.0510) | 1,047/1,441 (0.7266) | 0.5167 | 138 | 335 |
| S1 | 2.5 s | 65.5 / 63.61 | 64.0 / 60.29 | 22,974 | 1,087 (0.0473) | 1,087/1,441 (0.7543) | 0.4375 | 155 | 362 |
| S1 | 4 s | 45.5 / 49.21 | 39.0 / 43.36 | 16,719 | 984 (0.0589) | 984/1,441 (0.6829) | 0.6250 | 99 | 288 |
| S2 | 3 s | 52.0 / 52.09 | 52.0 / 50.35 | 7,860 | 629 (0.0800) | 629/1,050 (0.5990) | 0.5333 | 30 | 133 |
| S2 | 2.5 s | 63.0 / 59.28 | 62.0 / 58.45 | 9,086 | 669 (0.0736) | 669/1,050 (0.6371) | 0.4583 | 44 | 152 |
| S2 | 4 s | 38.0 / 43.38 | 34.0 / 39.27 | 6,218 | 538 (0.0865) | 538/1,050 (0.5124) | 0.6750 | 27 | 111 |
| S3 | 3 s | 63.5 / 61.50 | 59.5 / 55.90 | 8,653 | 520 (0.0601) | 520/750 (0.6933) | 0.4750 | 57 | 136 |
| S3 | 2.5 s | 70.0 / 67.64 | 67.0 / 62.01 | 9,583 | 548 (0.0572) | 548/750 (0.7307) | 0.4167 | 67 | 144 |
| S3 | 4 s | 48.5 / 52.46 | 40.0 / 46.81 | 7,273 | 489 (0.0672) | 489/750 (0.6520) | 0.6125 | 47 | 121 |

**TWINS RATIOS** (median true ÷ median false; 95% CI with pairs resampled by true HARP, 2,000, seed 0; sign test two-sided, 0 ties in every cell; 0 undefined resamples):

| set | twins | version | pairs (dropped) | medians true / false | ratio [95% CI] | true higher | sign p | reading |
|---|---|---|---|---|---|---|---|---|
| S1 | T_a | V0 | 50 (0) | 0.2218 / 0.0680 | 3.2624 [1.2956, 9.4887] | 39/50 | 0.0001 | direction holds, CI above 1 |
| S1 | T_a | V1 | 49 (1) | 0.1765 / 0.0604 | 2.9247 [1.1771, 8.2515] | 37/49 | 0.0005 | direction holds, CI above 1 |
| S1 | T_a | V2 3 s | 0 (50) | — | undefined | — | — | undefined (0 pairs) |
| S1 | T_a | V2 2.5 s | 0 (50) | — | undefined | — | — | undefined (0 pairs) |
| S1 | T_a | V2 4 s | 4 (46) | 0.0453 / 0.0228 | 1.9851 [0.8061, 6.8436] | 2/4 | 1.0000 | direction holds, CI includes 1 |
| S1 | T_b | V0 | 47 (0) | 0.2245 / 0.0797 | 2.8174 [1.0169, 6.8227] | 35/47 | 0.0011 | direction holds, CI above 1 |
| S1 | T_b | V1 | 47 (0) | 0.1801 / 0.0659 | 2.7309 [1.1042, 6.1989] | 34/47 | 0.0031 | direction holds, CI above 1 |
| S1 | T_b | V2 3 s | 0 (47) | — | undefined | — | — | undefined (0 pairs) |
| S1 | T_b | V2 2.5 s | 0 (47) | — | undefined | — | — | undefined (0 pairs) |
| S1 | T_b | V2 4 s | 2 (45) | 0.1097 / 0.0401 | 2.7323 [0.6978, 6.8436] | 1/2 | 1.0000 | direction holds, CI includes 1 |
| S2 | T_a | V0 | 23 (0) | 0.1563 / 0.0959 | 1.6295 [0.7907, 3.8386] | 13/23 | 0.6776 | direction holds, CI includes 1 |
| S2 | T_a | V1 | 21 (2) | 0.1594 / 0.0786 | 2.0280 [0.8206, 4.2110] | 13/21 | 0.3833 | direction holds, CI includes 1 |
| S2 | T_a | V2 3 s / 2.5 s / 4 s | 0 (23) each | — | undefined | — | — | undefined (0 pairs) |
| S2 | T_b | V0 | 22 (0) | 0.1399 / 0.1047 | 1.3356 [0.6674, 2.1473] | 15/22 | 0.1338 | direction holds, CI includes 1 |
| S2 | T_b | V1 | 19 (3) | 0.1594 / 0.1188 | 1.3423 [0.6685, 2.5072] | 13/19 | 0.1671 | direction holds, CI includes 1 |
| S2 | T_b | V2 3 s / 2.5 s / 4 s | 0 (22) each | — | undefined | — | — | undefined (0 pairs) |
| S3 | T_a | V0 | 25 (0) | 0.2641 / 0.0816 | 3.2350 [1.2554, 4.5452] | 18/25 | 0.0433 | direction holds, CI above 1 |
| S3 | T_a | V1 | 23 (2) | 0.2149 / 0.0816 | 2.6323 [0.9065, 3.8331] | 15/23 | 0.2100 | direction holds, CI includes 1 |
| S3 | T_a | V2 3 s / 2.5 s / 4 s | 0 (25) each | — | undefined | — | — | undefined (0 pairs) |
| S3 | T_b | V0 | 24 (0) | 0.2695 / 0.1033 | 2.6106 [1.0820, 3.8852] | 15/24 | 0.3075 | direction holds, CI above 1 |
| S3 | T_b | V1 | 22 (2) | 0.2132 / 0.0766 | 2.7844 [0.8929, 5.4379] | 15/22 | 0.1338 | direction holds, CI includes 1 |
| S3 | T_b | V2 3 s / 2.5 s / 4 s | 0 (24) each | — | undefined | — | — | undefined (0 pairs) |

**Outputs:**
- `sensitivity_combined.py`
- `sensitivity_combined.log`
- `figures/sensitivity_combined.png`
- `data/sensitivity_combined_{S1,S2,S3}.csv` and `data/sensitivity_combined_cells.csv` (data/ is not tracked)

## 2026-09-27 — POST-HOC RE-ANALYSIS: B-class flare count + R4a (dev candidate 'n_B + R4a', Phase F F3) on already-analysed test sets (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user):**

POST-HOC RE-ANALYSIS (not an untouched test). Frozen files unchanged; never overwrite existing models, thresholds or results. Do not run stage5_test.py. No downloads; if a step seems to need one, STOP and ask.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else, headed "2026-09-27 — POST-HOC RE-ANALYSIS: B-class flare count + R4a (dev candidate 'n_B + R4a', Phase F F3) on already-analysed test sets (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)". Commit.
Disclosure (record verbatim): Chosen after all results. On dev (F3/F7), n_B alone did not help (delta −0.0049; 60/445 false removed vs A 70/445) and the combination (delta +0.0092) was below R4a alone (+0.0124). R4a already failed its held-out tests on 2021/23/24 (euv_heldout_test.log: condition not met) and 2025–26 (euv_confirm_tests.log s3: not confirmed). Both sets below were used for those tests, so this is a re-analysis, not a confirmation. Candidate count: about the 25th idea tried.

DEFINITIONS: n_B, R4a and every transform EXACTLY as in Phase F F3 (quote the code and the definitions in the log; no changes). Models: A (A_COLS), A+R4a, A+n_B+R4a ("COMBO"), each fitted on the dev 541 set with the Step 6 settings (same folds, 1/n per HARP weights, training-fold scaling, estimator); new-set prediction = mean of the 5 fold models. Thresholds: τ per model = highest dev OOF threshold keeping >= 88% of weighted true episodes (as 04b6f4f). Fit, freeze, hash and record the τ values BEFORE touching any test set.

SETS (reported separately, never pooled):
 PRIMARY = the 2021/2023/2024 single-region R4a primary set (306 episodes; euv_heldout_test.log).
 SECONDARY = the 2025–26 <= 2-region evaluable set (378; the s3 R4a set in euv_confirm_tests.log).
 Weights 1/n per HARP; delayed episodes count as false.

STEP 1 — LABEL-BLIND CHECKS ONLY (do not read true_alarm or delayed; print no outcome):
 a) Reproduce the dev F3 COMBO and A+R4a results exactly (delta, AUC, false removed counts).
 b) Episode counts per set; n_B and R4a defined for every episode (list any undefined).
 c) B-flare attribution quality: per year (dev years and 2021–2026), the fraction of B-class events that carry a NOAA region number. If any test year's fraction differs from the dev average by more than 20 percentage points, write "n_B NOT COMPARABLE ACROSS YEARS — TEST NOT RUN" in decisions.md, commit and STOP permanently.
 d) BASELINE GUARD per set: weighted % of ALL episodes with p_A >= τ_A. If A keeps > 95% in a set, the PRIMARY comparison for that set is declared "not interpretable (baseline does not filter)" now, before labels are read, and only the matched-retention comparison (below) is reported for it.
 Commit. STOP. Do not evaluate until I say "run the n_B + R4a re-analysis once".

EVALUATION (once, on command):
 PRIMARY comparison: A vs COMBO at frozen τ. From the SAME paired HARP resamples (2,000, seed 0): D_false = weighted % false alarms removed (COMBO minus A), D_true = weighted % true alarm episodes kept (COMBO minus A), each with 95% CI.
 READING (mechanical, fixed now):
  "SAFE FILTER ON THIS SET" if D_false CI lower > 0 AND D_true CI lower >= −10 points.
  "MEETS OPERATING CRITERION" if D_false CI lower > 0 AND D_true point >= −10 (but CI lower < −10).
  "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)" if D_false CI lower > 0 AND D_true point < −10.
  "INCONCLUSIVE" if CIs cannot be computed. "NOT CONFIRMED" otherwise.
 SECONDARY (cannot change the reading):
  - COMBO vs A+R4a: same D_false/D_true (does n_B add anything beyond R4a?).
  - Matched retention (the fair comparison): for A, A+R4a and COMBO, weighted % false alarms removed at the threshold keeping >= 80%, 88% and 95% weighted true episodes in that set; paired differences vs A with HARP bootstrap CIs (2,000, seed 0). Label: "threshold chosen on the test set — descriptive".
  - Δ log-loss (A − COMBO; HARP bootstrap 10,000, seed 20260921); AUC for all three models.

OUTPUTS: nb_r4a_reanalysis.py, nb_r4a_reanalysis.log, a results entry in decisions.md (verbatim numbers), commit. Report the numbers verbatim with the commit hash. Never use "confirmed", "validated" or "significant". STOP.

### 2026-09-27 — n_B + R4a RE-ANALYSIS (68e57b1): FROZEN before any test set was read, plus implementation note (decided by: me)
- **Freeze (dev only):** `nb_r4a_reanalysis.py freeze` read no test set; its log section is in `nb_r4a_reanalysis.log`.
  - **Definitions:** n_B and R4a are quoted verbatim from `phase_f.item_F3` and `euv_spatial` in the log. There is no transform. B = K2 true flux in [1e-7, 1e-6); only joinable events count, with start in [t−48h, t) for the regions in noaa_ars.
  - **Checks:** the n_B join reproduces the cohort's n_C, n_M and n_X for all 547 dev episodes, and n_B equals `data/phase_f/F3_n_B.csv` for all 547.
- **Dev set:** 541 episodes (true 96, false 445, 179 HARPs). Fitting uses `euv_heldout.fit_folds` (= `cv_fit`, Step 6 settings).
- **1a — dev F3 reproduced exactly** (|diff| < 1e-12; counts and τ identical):
  - A+R4a: delta 0.012353, AUC 0.800327, false removed 209/445 (0.487080 w), true kept 84/96.
  - COMBO: delta 0.009197, AUC 0.794578, false removed 233/445 (0.529998 w), true kept 81/96.
- **Frozen τ (dev OOF, ≥ 88% weighted true kept):**
  - τ_A = 0.0679701247 (87/96; false removed 70/445)
  - τ_A+R4a = 0.0612215400 (84/96; 209/445)
  - τ_COMBO = 0.0646075144 (81/96; 233/445)
- **SHA-256 of the frozen files** (`data/nb_r4a/`):
  - A_fold0–4: 547b5d2c…, bdc8f859…, 4044fa9b…, 11109aa5…, 4ab93e1e…
  - A_R4a_fold0–4: 0a004dd3…, 78abaa09…, fdac7294…, 597e68cf…, 05091044…
  - COMBO_fold0–4: 93da5cf3…, 18c60f77…, 65ea9adb…, ff66fcba…, e5b3b52d…
  - dev_rows.csv: 9abca2e6…
  - thresholds.json: 7f658c2d…
  - Full hashes are in the log and in `data/nb_r4a/model_hashes.json`, which is verified before every later use.
- **Test sets, read label-blind** (usecols exclude true_alarm and delayed):
  - PRIMARY = `cohort_test_primary.csv` (313) with primary_fill ≥ 0.80 and R4a defined (= the euv_heldout R4a primary set).
  - SECONDARY = `cohort_le2.csv` (387) with primary_fill ≥ 0.80, CV_box defined and R4a defined (= the TEST 1 s3 set).
  - Weights are 1/n per HARP within each set. n_B is computed with the same join (events fetched 2020-12-29 to 2025-01-01 23:59 and 2024-12-29 to 2026-08-18 23:59), which must reproduce n_C, n_M and n_X for every episode.
- **1c rule, fixed before computing:**
  - "Dev average" is evaluated two ways: (i) the mean of the 10 per-year dev fractions for 2010–2019, and (ii) the pooled dev fraction.
  - STOP if any test year (2021–2026) differs from EITHER by more than 20 percentage points. Applying both is the stricter reading.
  - 2026 covers only the cached days, up to 2026-08-18; days cached are printed for each year.
- **1d:** p_A = the mean of the 5 frozen A fold models, and the result is weighted % of all episodes with p_A ≥ τ_A.

### 2026-09-27 — n_B + R4a RE-ANALYSIS (68e57b1): STEP 1 LABEL-BLIND CHECKS — RESULT: n_B NOT COMPARABLE ACROSS YEARS — TEST NOT RUN
**n_B NOT COMPARABLE ACROSS YEARS — TEST NOT RUN**

Per the 1c rule this is a permanent stop. No evaluation will be run, true_alarm and delayed were never read, and no outcome was computed. The checks section of `nb_r4a_reanalysis.log` holds the output. The checks were run twice because the first run printed small pp differences with 4 decimals (e.g. "0.1899" for +0.19 pp). The second run changed only the display; its numbers are identical and it is the one appended to the log.

- **Integrity:** 17 frozen files hash-verified. τ_A 0.0679701247, τ_A+R4a 0.0612215400, τ_COMBO 0.0646075144.
- **1b — episode counts:**
  - PRIMARY 2021/23/24 single-region: 306 episodes, 98 HARPs. R4a undefined 0; n_B undefined 0. n_B median 0.0, IQR [0.0, 0.0], max 16, zero in 283.
  - SECONDARY 2025–26 ≤2-region: 378 episodes, 101 HARPs. R4a undefined 0; n_B undefined 0. n_B median 0.0, IQR [0.0, 0.0], max 12, zero in 326.
  - In both sets the n_B join reproduces the cohort's n_C, n_M and n_X for every episode.
- **1c — share of B-class events with a NOAA region number:**
  - Dev: 2010 0.7315; 2011 0.7337; 2012 0.6359; 2013 0.7951; 2014 0.8056; 2015 0.8582; 2016 0.7874; 2017 0.7884; 2018 0.8796; 2019 0.8750. These reproduce `F3_B_coverage.csv`.
  - Dev average: mean of the per-year fractions 0.7890; pooled 0.7727.
  - Test years (fraction; difference vs mean / vs pooled, pp):

    | year | fraction | vs mean | vs pooled |
    |---|---|---|---|
    | 2021 | 0.7551 | −3.39 | −1.76 |
    | 2022 | 0.6352 | −15.39 | −13.76 |
    | **2023** | **0.5714** | **−21.76** | **−20.13** |
    | 2024 | 0.7143 | −7.47 | −5.85 |
    | 2025 | 0.7746 | −1.44 | +0.19 |
    | 2026 (230 cached days, to 2026-08-18) | 0.7887 | −0.03 | +1.59 |

  - B events per year: 2021 1,609; 2022 825; 2023 49; 2024 35; 2025 142; 2026 336.
  - 2023 exceeds 20 pp under both definitions → **n_B NOT COMPARABLE ACROSS YEARS — TEST NOT RUN.**
- **1d — baseline guard (label-blind; computed before the stop was applied):**
  - PRIMARY: A keeps 1.0000 weighted (306/306 episodes).
  - SECONDARY: A keeps 1.0000 weighted (378/378).
  - Both are > 95%, so the PRIMARY comparison would have been "not interpretable (baseline does not filter)" in both sets.

## 2026-09-27 — PROSPECTIVE PRE-REGISTRATION: bursty fraction (BF) and late-window restlessness (CV6) (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user):**

PRE-REGISTRATION + DEV-ONLY EXPLORATION. No held-out or confirmation set is touched. Frozen files unchanged; never overwrite existing series, results, models or pairs. Do not run stage5_test.py. JSOC: my account only, ONE pending export at a time; NO downloads in Steps 0–2.

STEP 0 — Record this whole entry verbatim in decisions.md BEFORE anything else, headed "2026-09-27 — PROSPECTIVE PRE-REGISTRATION: bursty fraction (BF) and late-window restlessness (CV6) (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)". Commit.

Disclosure (record verbatim): Proposed after all existing results (latest commits 1465063 and b7e7749). Motivated by Tiwari et al. 2023 (ApJ; per-pixel minimum/average brightness maps separate steady from bursty 4–8 MK heating), Kniezewski et al. 2024 (ApJL 977:L29; EUV variability peaks 1–2 h before flare onset), Krista 2024 (ApJ 978:121; precursors elevated in the last 2 h), and the descriptive finding that calm true alarms flare later (5af931b). Dev 2010–2019 is used for exploration only. The ONLY confirmatory test is the prospective set defined below, whose data do not exist in the repo today. The 2021–2024, 2022 and 2025–26 sets are never used for these measures.

MEASURES (definitions fixed now; never changed after seeing any value):
 CV6 = CV_box computed with the EXISTING CV_box function (same detrending, same valid_primary frames), restricted to frames in (t − 6 h, t]. Requires >= 80% of the 30 expected 12-min slots valid; otherwise undefined (label-blind exclusion, counted).
 BF (bursty fraction) = share of the HARP-box 94 Å luminosity that is not steady, from frames in (t − 24 h, t]:
  a) use the SAME frame rules as the primary version (QUALITY == 0, exposure rule, saturated pixels set to NaN, flare frames kept, exposure-normalised DN/s);
  b) co-register valid frames to the last valid frame using the EXISTING registration code, and use the HARP box mask exactly as the existing CV_box code does;
  c) keep box pixels that are finite in >= 80% of valid frames;
  d) per kept pixel i: floor_i = 5th percentile over frames; mean_i = mean over frames (the 5th percentile, not the strict minimum, for robustness to noise);
  e) BF = 1 − (Σ floor_i) / (Σ mean_i) over kept pixels;
  f) BF is undefined if frame fill < 80% or < 80% of box pixels are kept (label-blind exclusion, counted).
 If a), b) or the box mask cannot be implemented from existing code without a new decision, STOP and list the options with their consequences. Do not choose one yourself.

STEP 1 — DEV ONLY, LABEL-BLIND COMPUTE (do not read true_alarm or delayed):
 Compute CV6 and BF for the 547 dev episodes (data/stage3/cohort_dev.csv) from AIA/HMI files already on disk (data/euv_full/). No downloads.
 Checks first: the CV_box function reproduces the stored dev CV_box for every episode (|diff| < 1e-9) when given the full 24-h frame set; BF code self-test on a synthetic cube (constant cube → BF = 0; cube with added bursts → BF > 0).
 Report ONLY: counts defined/undefined per rule; median and IQR of CV6 and BF; Spearman rho of CV6 and BF with CV_box, n_C and gate score (label-free); wall time.
 Save data/prospective/dev_values.csv and record its SHA-256. Commit. STOP.

STEP 2 — DEV EXPLORATION (run only when I say "run dev exploration"; EXPLORATORY; nothing here changes the prospective plan):
 For BF, CV6 and CV_box, each separately:
  - twins ratio on the step 6 gate-score pairs (data/euv_full/step6/twins_PRIMARY.csv; both values defined): median true / median false; CI with pairs resampled by true HARP, 2,000, seed 0;
  - Δ log-loss for A vs A + log10(x) and for C vs C + log10(x) (Step 6 settings: Stage 4 folds, 1/n per HARP weights, training-fold scaling, same estimator; C = A + log(1+R) as in Step B; HARP bootstrap 10,000, seed 20260921); AUC for each model.
 Commit. STOP.

PROSPECTIVE TEST (recorded now; executed ONLY when I say "run the prospective test once", and not before 2026-11-10):
 COVERAGE CHECK (first, recorded before any download): E = min(2026-10-31 23:00 TAI, the latest T_REC with complete SHARP + SWPC + GOES coverage, allowing 24 h of label follow-up after each t).
 SET: alarm episodes with t in [2026-08-17 00:00 TAI, E], built with EXACTLY the same gate, cohort rules and fallbacks as the 2025–26 confirmation set (749208e: T1–T4, <= 2 regions); labels from SWPC originals on the true-flux scale; delayed episodes count as false. Exclude every HARP and every NOAA region present in any earlier EUV data directory (data/euv_full, euv_test, euv_confirm, euv_extra, euv_pilot, euv_cad).
 DOWNLOAD: exactly as the 2025–26 confirmation download (AIA 94 Å, 12-min, (t − 24 h, t], tracked im_patch cutouts; HMI magnetogram + bitmap at t). Dry run first (report episodes, exports, GB, hours). One pending export at a time, my account only.
 SIZE RULE (label-blind, before reading labels): if fewer than 60 episodes have BF defined, report "TOO SMALL — DESCRIPTIVE ONLY", give the numbers, and give no reading.
 PRIMARY: BF, magnetic twins (gate score, frozen caliper 0.0747, the same twins code as TEST 1 in ae1b174). Statistic: median true / median false; 95% CI with pairs resampled by true HARP, 2,000, seed 0.
 READING (mechanical):
  "REPLICATED" if ratio > 1 AND CI lower > 1;
  "DIRECTION CONSISTENT, NOT CONFIRMED" if ratio > 1 AND CI lower <= 1;
  "NOT REPLICATED" otherwise.
 SECONDARY (cannot change the reading): the same statistic for CV6 and CV_box; magnetic + flare-history twins (the TEST 1 s1 code, by_group=True) for all three; counts of pairs with true > false; sign-test p. Never pooled with any earlier set.

OUTPUTS: prospective_measures.py, prospective_step1.log, prospective_step2.log, and decisions.md entries with the numbers verbatim. Never use "confirmed", "validated" or "significant" for dev results. STOP after each step and report the commit hash.

### 2026-09-27 — PROSPECTIVE PRE-REGISTRATION (2f62f88): STEP 1 STOPPED BEFORE COMPUTING — BF item b) needs a decision (recorded by: me)
Nothing has been computed or read beyond code and file counts. Per the entry, I am not choosing an option.

**Can be built from existing code without a new decision:**
- **a) frame rules** (`euv_full.compute_episode` / the stored `valid_primary`): QUALITY == 0; exposure rule EXPTIME ≥ 0.5 × median; raw > 12,000 DN → NaN; divide by EXPTIME; flare frames kept.
- **Box mask:** every HMI pixel of the HARP patch (`samples()["box"]`), mapped into each AIA frame by `euv_dctrl.hmi_to_frame` (nearest AIA pixel, differentially rotated to the frame time). The CV_box series is the mean over these HMI pixels.
- **CV6:** `euv_dctrl.cv` on the `valid_primary` frames in (t−6h, t], with no new decision.

**b) — why it needs a decision:** the existing registration (`update_pointing` → `register_cutout` → `hmi_to_frame`) never aligns frames to an AIA reference frame. Every frame is sampled onto the alarm-time HMI grid instead.

**Options (the user's decision):**
1. **Existing code as it is:** the `euv_spatial.spatial_episode` per-pixel cube on the HMI grid at t.
2. **The last valid AIA frame as reference, nearest-pixel:** a new variant of `hmi_to_frame`, with the box being the unique AIA pixels of the HARP footprint on that frame.
3. **The last valid AIA frame as reference, interpolated:** `reproject_interp`, as the existing `euv_run.to_frame` does for masks, onto that frame's WCS.

Consequences are listed in the report to the user.

**Also flagged (with precedent; not treated as blocking):** reproducing the frame pipeline needs aiapy's pointing table, which is a JSOC keyword query (`aia.master_pointing3h`). Earlier entries recorded it as "not a data export or download" (Phase X; `euv_masks`; novelty #24).

### 2026-09-27 — PROSPECTIVE PRE-REGISTRATION (2f62f88): CLARIFICATION of BF part b) and implementation defaults, made BEFORE any BF value is computed (decided by: user)
**Verbatim (user):**

Use Option 1 for BF part b): the existing per-pixel stack on the alarm-time HMI grid (existing mapping with differential rotation), the same pixels and weighting as CV_box. Record this in decisions.md as a clarification of part b), made before any BF value is computed: "co-registration reference = the alarm-time HMI grid used by the existing CV_box code, instead of the last valid AIA frame; chosen so BF uses exactly the same pixels and weighting as CV_box and is checkable against the stored series."

Accept your defaults and record them the same way:
- 5th percentile = numpy default (linear) over each pixel's finite values;
- BF frame fill = stored primary_fill;
- CV6 slots = t − 5 h 48 min … t, a slot counts if a valid frame lies within ±6 min (existing fill rule).

The aiapy pointing-table keyword query is NOT a download or export (as in earlier entries); allowed.

These choices also apply unchanged to the prospective test. Add a per-episode check that the per-frame box means from the per-pixel stack reproduce the stored CV_box series (|diff| < 1e-9); STOP if any episode fails. The episode without stored series counts as undefined.

Commit the clarification, then run Step 1 (label-blind). Report as specified and STOP.

### 2026-09-27 — PROSPECTIVE PRE-REGISTRATION (2f62f88, bb8a137): STEP 1 RESULTS — dev 2010–2019, label-blind (recorded by: me)
Recorded from `prospective_step1.log`. true_alarm and delayed were never read: `data/stage3/cohort_dev.csv` was read with usecols harpnum, t, noaa_ars, score and n_C. No downloads; only the aiapy pointing-table keyword query was made (allowed, bb8a137).

- **Implementation:** `prospective_measures.py`. The frame loop is copied from `euv_spatial.spatial_episode` / `euv_masks.mask_episode`. BF uses the per-pixel stack on the alarm-time HMI grid. CV6 uses valid_primary frames with T_REC in (t−6h, t] and 30 slots from t−5h48m to t (±6 min).
- **Checks (all passed):**
  - BF self-test: constant cube → BF 0; the cube with added bursts → BF 0.2216; both undefined rules trigger.
  - All 546 episodes with stored series: the per-frame box means of the per-pixel stack reproduce the stored series (max |diff| 0.0e+00).
  - `euv_dctrl.cv` on the full 24-h valid_primary frames reproduces the stored CV_box (max |diff| 2.2e-16).
- **Episodes:** 547. One has no stored series (8_20100504T2059) and counts as undefined.
  - **BF:** defined 541; undefined 6 (fill < 80%: 5; no series: 1; kept pixels < 80%: 0). Median 0.5902, IQR [0.5413, 0.6724]. Kept-pixel fraction among episodes with fill ≥ 80%: median 1.0000, minimum 0.9547.
  - **CV6:** defined 522; undefined 25 (6-h fill < 80%: 24; no series: 1). Median 0.0647, IQR [0.0252, 0.1518].
- **Spearman rho (label-free; pairwise complete):**

  | pair | rho | p | n |
  |---|---|---|---|
  | BF vs CV_box | +0.3769 | 1.05e-19 | 541 |
  | BF vs n_C | +0.0616 | 1.53e-01 | 541 |
  | BF vs gate score | −0.0660 | 1.25e-01 | 541 |
  | CV6 vs CV_box | +0.7617 | 4.46e-100 | 522 |
  | CV6 vs n_C | +0.5021 | 1.08e-34 | 522 |
  | CV6 vs gate score | +0.2956 | 5.49e-12 | 522 |
  | BF vs CV6 | +0.2815 | 6.87e-11 | 518 |

- **Saved:** `data/prospective/dev_values.csv`, SHA-256 `15113e5ca707b6d2398e75052ca4ac4fbf2de859f9cbeb7a1aaa5b07c44532a6`.
- **Wall time:** 1.54 h with 9 workers for 545 episodes. One further episode (71_20100630T0359) was computed first, in-process, as a timing and check run (11.3 s); its output was checked and not re-run.

## 2026-09-27 — BF LABEL-BLIND NOISE DIAGNOSTIC, before Step 2 (decided by: user; recorded verbatim before anything else)
**Verbatim (user):**

Before Step 2: LABEL-BLIND NOISE DIAGNOSTIC for BF (do not read true_alarm or delayed). Record this entry verbatim in decisions.md first, then commit.

Reason (record verbatim): median BF 0.5902 is close to the value expected from photon noise alone for a faint pixel (~15 DN per 12-min exposure → σ/mean ≈ 0.36 → 5th percentile ≈ mean − 1.645σ → BF ≈ 0.59), and BF barely correlates with CV_box (ρ 0.38), n_C or gate score. BF may be dominated by per-pixel photon noise. This check uses no labels, so a definition change decided from it is allowed before Step 2.

For each of the 541 dev episodes with BF defined:
1. BF_noise = the BF that the SAME pixels would have with NO real variability: for every kept pixel, simulate its frame series as its own mean (DN/s) plus photon + read noise at each frame's exposure time (AIA 94 Å gain 1.975 DN/photon and read noise 1.14 DN from the aiapy V3 table already used in 5af931b; Poisson photons, Gaussian read noise), with the same frames/NaN pattern; seed 0. Compute BF exactly as defined.
2. Report: median and IQR of BF_noise; median of BF_noise / BF; Spearman ρ(BF, BF_noise); Spearman ρ(BF, box-mean brightness).
3. MECHANICAL RULE (fixed now): if median BF_noise / BF > 0.5, write "BF IS NOISE-DOMINATED" in decisions.md, commit and STOP. Then list options for a noise-robust BF, e.g. (a) BF on spatially binned macropixels (e.g. 4×4 AIA pixels), (b) floor corrected by the expected noise: floor_i + 1.645·σ_noise,i, (c) restrict to pixels above a brightness cut. For each option, give its expected BF_noise on these same episodes (label-blind). Do NOT choose.
   Otherwise write "BF NOISE CONTRIBUTION ACCEPTABLE", commit and STOP.
Do not run Step 2.

### 2026-09-27 — BF NOISE DIAGNOSTIC (21e9e89): implementation, recorded before computing (decided by: me)
**Set:** the 541 dev episodes with BF defined. The per-pixel stack is rebuilt with the Step 1 frame loop, and checks are required: the per-frame box means reproduce the stored series (< 1e-9), and the recomputed BF equals the stored BF in `dev_values.csv` (|diff| < 1e-12).

**Noise model:**
- g = 1.975 DN/photon; read noise 1.14 DN (aiapy V3 table, as in 5af931b).
- e_f is the EXPTIME of each valid frame, taken from the series.
- μ_p is the nanmean over frames of pixel p (DN/s).
- A simulated value is (g·Poisson(max(μ_p, 0)·e_f/g) + 1.14·N(0,1)) / e_f.
- The NaN pattern is the same as in the data, and each simulation uses `np.random.RandomState(0)`, fresh per episode.

**1. BF_noise:** the noise is drawn independently per stack pixel (per HMI-grid pixel, as specified). BF is then computed exactly as defined with the same fill, so the same pixels are kept.

**2. Box-mean brightness:** the mean of the stored box series over the valid_primary frames (DN/s).

**Options, computed in the same label-blind pass** (reported only if the rule triggers; not a choice):
- **(a) Macropixels.** Blocks of k×k HMI-grid pixels, with k = round(2.4″ / CDELT1_HMI), i.e. about 4×4 AIA pixels at 0.6″ (k = 5 for 0.504″).
  - Partial blocks at the edges are kept.
  - Each block's value per frame is the nanmean of its pixels (the CV_box weighting). BF rules c)–f) are then applied to the blocks.
  - The noise simulation here draws one value per AIA pixel per frame. Every stack pixel that maps to that AIA pixel shares it (through the stored `hmi_to_frame` index), with λ from the mean μ_p of those stack pixels. The block mean therefore averages the correct number of independent AIA pixels.
- **(b) Noise-corrected floor.** BF_b = 1 − Σ(floor_i + 1.645·σ_i) / Σ mean_i over the kept pixels.
  - σ_i = sqrt(mean over the pixel's finite frames of (g·max(mean_i, 0)·e_f + 1.14²) / e_f²).
  - There is no cap. Its noise-only value comes from the BF_noise simulation.
- **(c) Brightness cut.** Keep only pixels with mean_i × median(e_f) ≥ C DN per exposure, for C = 100 and C = 300. The cut is selected on the real means, and the same pixels are used for the noise-only value.
  - BF is computed over those pixels; the 80%-of-box rule is not applied.
  - Reported: the fraction of kept pixels that pass, and the number of episodes with ≥ 1 passing pixel.

**Code change:** the Step 1 frame loop is moved into a function without changing its behaviour; the BF-reproduction check verifies this.

### 2026-09-27 — BF NOISE DIAGNOSTIC (21e9e89; implementation 721ffa9): RESULT — BF IS NOISE-DOMINATED
**BF IS NOISE-DOMINATED**

Recorded from `prospective_noise.log`. Dev 2010–2019, 541 episodes with BF defined. No labels were read, Step 2 was not run, and no option has been chosen (the user's decision).

- **Checks (all passed):** the per-frame box means of the rebuilt stack reproduce the stored series (max |diff| 0.0e+00), and the recomputed BF equals `dev_values.csv` (max |diff| 0.0e+00) for all 541.
- **Results:**
  - BF (data): median 0.5902, IQR [0.5413, 0.6724].
  - BF_noise: median 0.6583, IQR [0.5570, 0.7636].
  - BF_noise / BF: median 1.1464, IQR [0.9375, 1.3242].
  - Spearman BF vs BF_noise: ρ +0.1676 (p 8.97e-05, n 541).
  - Spearman BF vs box-mean brightness: ρ −0.2646 (p 4.08e-10, n 541).
- **Mechanical rule:** median BF_noise / BF = 1.1464 > 0.5 → **"BF IS NOISE-DOMINATED"**.
- **Options for a noise-robust BF** (label-blind; NOT chosen). Each gives the value on the data, the noise-only value, the median per-episode ratio noise / data, and Spearman with CV_box on the data:

  | option | defined | data median [IQR] | noise-only median [IQR] | ratio median | ρ vs CV_box |
  |---|---|---|---|---|---|
  | (a) macropixels, 5×5 HMI pixels (≈ 4×4 AIA px) | 541 (0 undefined) | 0.3891 [0.3281, 0.4774] | 0.1765 [0.1482, 0.2034] | 0.4505 | +0.8359 (p 1.55e-142, n 541) |
  | (b) floor_i + 1.645·σ_noise,i (no cap) | 541 | −0.1537 [−0.2769, −0.0259] | −0.0759 [−0.0942, −0.0586] | 0.3440 | +0.8762 (p 5.42e-173, n 541) |
  | (c) C = 100 DN per exposure | 262 episodes with ≥ 1 pixel | 0.7456 [0.6532, 0.8235] | 0.1972 [0.1855, 0.2095] | 0.2655 | +0.3587 (p 2.25e-09, n 262) |
  | (c) C = 300 DN per exposure | 55 episodes with ≥ 1 pixel | 0.8586 [0.7976, 0.8893] | 0.1218 [0.1157, 0.1243] | 0.1406 | +0.4536 (p 5.05e-04, n 55) |

  - For (b), the data value is < 0 in 422 of 541 episodes.
  - For (c), the fraction of kept pixels passing is median 0.0000, IQR [0.0000, 0.0048] at C = 100 and median 0.0000, IQR [0.0000, 0.0000] at C = 300.
- **Saved:** `data/prospective/noise_values.csv`, SHA-256 `0d0b28022c5253c2561837fd6e9d1a416937d8c465f2178ff53dca23cfb5bab4`.
- **Wall time and one failure:**
  - Pool from 18:47 to 21:52 local (3.09 h) with 5 workers (7 were planned; 5 were used for memory). The sum of per-episode times was 15.37 h.
  - One episode (71_20100702T2059) failed in the pool on a transient JSOC pointing-table query timeout (OSError, Errno 60) and was recomputed in a separate process with the same code. Because the exception was raised inside the pool, the pool wrote no progress lines and no "done" line; the report's wall-time line was patched to use the start time and the last result's file time.
  - The report was run twice: the first run printed the wall-time line wrongly, and the second changed only that line.

## 2026-09-27 — BF DEFINITION (option a) AND AMENDED PROSPECTIVE TEST, label-blind, before Step 2 (decided by: user; recorded verbatim before Step 2)
**Verbatim (user):**

Decisions (label-blind; record verbatim in decisions.md BEFORE Step 2, then commit):

1. BF definition: use option (a) — BF computed on 5×5 HMI-pixel blocks (≈4×4 AIA pixels), otherwise identical to the pre-registered BF (same frames, same Option 1 grid, 5th-percentile floor, luminosity-weighted, same 80% rules). Rationale: the per-pixel BF is noise-dominated (a215701: median BF_noise/BF 1.1464). (a) passes the 0.5 noise rule (0.4505) and keeps all 541 episodes.
   Rejected: (b) gives BF < 0 in 422/541 episodes (over-correction, not physical); (c) leaves most episodes with no qualifying pixels (median share 0), so exclusion would depend on brightness and could depend on outcome.
   Note (record): BF(a) correlates ρ 0.84 with CV_box, so it is largely redundant with CV_box.

2. Amend the PROSPECTIVE TEST before any prospective data exist:
   PRIMARY = CV_box, magnetic twins (gate score, caliper 0.0747, TEST 1 code): a prospective replication of the confirmed 2025–26 twins result (ae1b174). Same statistic, CI, size rule and mechanical reading as already recorded.
   SECONDARY (cannot change the reading) = CV6 and BF(a), with the same statistic; magnetic + flare-history twins for all three.
   Rationale (record): BF is noise-dominated at 12-min single-exposure pixel scale; BF(a) is largely redundant with CV_box; the confirmed measure is the most valuable to replicate prospectively.

3. Then run Step 2 (dev exploration, EXPLORATORY) exactly as specified, for BF(a), CV6 and CV_box. Report and STOP.

### 2026-09-27 — PROSPECTIVE STEP 2 (dev exploration, EXPLORATORY): implementation, recorded before running (decided by: me)
**Values:**
- BF(a) = `BF_a` in `data/prospective/noise_values.csv` (SHA-256 0d0b2802…). Its 6 undefined episodes are undefined by the same rules as BF: fill < 80% (5) and no series (1).
- CV6 = `data/prospective/dev_values.csv` (SHA-256 15113e5c…).
- CV_box = the stored primary_CV_box.

**Analysis set for each measure:** the Stage 4 dev cohort (`phase_f.load_base`, with the fold column) restricted to episodes where x is defined by its own rules, with log10(x) finite. Weights are 1/n per HARP, recomputed within that set (`phase_f.prep`).
- CV_box: primary_fill ≥ 0.80 and CV_box > 0, i.e. the set of all earlier CV_box analyses.
- BF(a): its own rules.
- CV6: its 6-h fill rule only.

**Twins ratio:** `phase_f.ratio_jobs` on `data/euv_full/step6/twins_PRIMARY.csv` (81 pairs), keeping pairs with both values defined. The statistic is median true / median false on the raw x, with CI from pairs resampled by true HARP (2,000, seed 0).

**Δ log-loss:**
- A = A_COLS and C = A_COLS + logR, where logR = `euv_confirm_tests.log_r` over 2010-04-28 to 2019-12-31 23:59 (Step B).
- A vs A + log10(x) and C vs C + log10(x), each fitted with `euv_heldout.fit_folds` (Step 6 settings).
- Δ = LL(base) − LL(base + x), with a HARP bootstrap (10,000, seed 20260921) via `phase_f.boot_many`. Weighted AUC is reported for every model.

**Checks (STOP on failure):**
- On the full dev 547, LL(C) = 0.3356 (Step B).
- The CV_box twins ratio and CI reproduce `data/phase_f/F2_ratios.csv`.
- On the CV_box set, the out-of-fold LL of A, A + log10 CV_box, C and C + log10 CV_box equals the frozen `data/euv_extra/thresholds.json` dev values exactly.

### 2026-09-27 — PROSPECTIVE STEP 2 RESULTS: dev exploration (EXPLORATORY; dev 2010–2019, internal 5-fold CV)
Recorded from `prospective_step2.log`. BF = option (a) (eb3e7d5); implementation d2ed360. Nothing here changes the prospective plan.

- **Checks (all passed):**
  - LL(C) on dev 547 = 0.3356 (Step B).
  - The CV_box twins ratio and CI reproduce `data/phase_f/F2_ratios.csv`.
  - On the CV_box set, A, A + log10 CV_box, C and C + log10 CV_box reproduce the `data/euv_extra/thresholds.json` dev log-loss exactly.

**Twins ratio** on the step 6 gate-score pairs (81; both values defined). The statistic is median true / median false, with 95% CI from pairs resampled by true HARP (2,000, seed 0).

| measure | pairs | medians true / false | ratio [95% CI] |
|---|---|---|---|
| BF(a) | 81 | 0.4729 / 0.3900 | 1.2125 [1.1048, 1.3194] |
| CV6 | 69 | 0.1254 / 0.0590 | 2.1261 [1.2479, 3.3090] |
| CV_box | 81 | 0.2594 / 0.1319 | 1.9661 [1.4737, 3.1731] |

**Δ log-loss** = LL(base) − LL(base + log10 x), where + means x helps. HARP bootstrap 10,000, seed 20260921; weighted AUC.

| measure | comparison | n (true / false; HARPs) | LL base → + x | Δ [95% CI] | AUC base → + x |
|---|---|---|---|---|---|
| BF(a) | A vs A + log10 BF(a) | 541 (96 / 445; 179) | 0.3206 → 0.3166 | +0.0040 [−0.0072, +0.0158] | 0.7422 → 0.7925 |
| BF(a) | C vs C + log10 BF(a) | 541 (96 / 445; 179) | 0.3223 → 0.3195 | +0.0027 [−0.0082, +0.0141] | 0.7720 → 0.7863 |
| CV6 | A vs A + log10 CV6 | 522 (84 / 438; 178) | 0.3184 → 0.3146 | +0.0038 [−0.0071, +0.0151] | 0.7184 → 0.7682 |
| CV6 | C vs C + log10 CV6 | 522 (84 / 438; 178) | 0.3204 → 0.3132 | +0.0072 [−0.0054, +0.0219] | 0.7333 → 0.7591 |
| CV_box | A vs A + log10 CV_box | 541 (96 / 445; 179) | 0.3206 → 0.3132 | +0.0074 [−0.0060, +0.0212] | 0.7422 → 0.7972 |
| CV_box | C vs C + log10 CV_box | 541 (96 / 445; 179) | 0.3223 → 0.3160 | +0.0062 [−0.0058, +0.0184] | 0.7720 → 0.7888 |

Wall time 1.8 s with 9 workers.

### 2026-09-27 — CV6 LABEL-DEPENDENT EXCLUSION (decided by: user; recorded verbatim; no computation)
**Verbatim (user):** CV6 dev exclusion is label-dependent — undefined for 12/96 true (12.5%) vs 7/445 false (1.6%) episodes (208202b). CV6 results are therefore on a selected subset and are not comparable with CV_box/BF(a). For the prospective test, CV6 stays secondary and unchanged; the report must include CV6 undefined counts by true/false.

**Note (me), no computation:** these counts are the differences between the Step 2 CV_box/BF(a) set (541: 96 true / 445 false) and the CV6 set (522: 84 / 438).

The CV6 set only needs the 6-h fill rule, not the 24-h primary_fill ≥ 80%, so it is not required to be a subset of the 541. The exact CV6-undefined counts by label among all 547 dev episodes were therefore not computed here and may differ slightly.

## 2026-09-27 — PRE-REGISTRATION AMENDMENT: secondary model COMBO-T (decided by: user; recorded verbatim before implementation; no 2021–2026 evaluation)
**Verbatim (user):**

PRE-REGISTRATION AMENDMENT (before any prospective data exist; record verbatim, then implement; no 2021–2026 evaluation):
Add secondary model "COMBO-T" (tuned on dev only by Claude AI, exploratory): Model C columns (score, n_C, n_M, n_X, log(1+R)) + log10 CV_box + prot12, where prot12 = 1 if the region had >= 1 flare of class C2.0 or larger (SWPC originals, true-flux scale, same NOAA-region join as labels) starting in (t − 12 h, t). No interaction term. LogisticRegression L2, C = 0.3, lbfgs; Step 6 settings otherwise (Stage 4 folds, 1/n per HARP weights, training-fold StandardScaler). Selected from a 90-configuration grid on dev OOF by: max weighted false removed at >= 88% weighted true kept (tie: lower log-loss).
Fit on dev 2010–2019 only; save and hash the 5 fold models; τ at 88% dev OOF (≈ 0.079) recorded but secondary.
PROSPECTIVE outputs for COMBO-T: (1) Δ log-loss = LL(Model C) − LL(COMBO-T), HARP bootstrap 10,000, seed 20260921, 95% CI (descriptive reading: "BETTER PROBABILITIES" if CI lower > 0, else "NOT SHOWN"); (2) reliability table for tiers <5%, 5–15%, 15–30%, >30% (n, true, mean predicted, observed rate); (3) at τ: D_true and D_false vs Model C (paired HARP bootstrap 2,000, seed 0).
Disclosure (verbatim): a Claude AI exploratory check on 2021–2026 (not committed) gave LL 0.3657 vs Model C 0.3768, AUC 0.768 vs 0.750, and at τ 128/160 true kept, 477/831 false removed; the dev-88% cutoff kept only 80% of true alarms on 2021–2026 (cutoff drift).
Commit. STOP.

### 2026-09-27 — COMBO-T (9a88d70): implemented and FROZEN on dev 2010–2019 only; no 2021–2026 data read (recorded by: me)
Recorded from `combo_t_freeze.log` (`combo_t.py freeze`).

**Implementation:**
- **prot12:** 1 if a region in noaa_ars had ≥ 1 flare with true flux ≥ 2.0e-6 (C2.0+) starting strictly inside (t − 12 h, t). The events are the joinable SWPC originals from `swpc.fetch` (K2 true scale), and the join is the same code as `euv_confirm_tests.log_r`.
- **logR:** `log_r` over 2010-04-28 to 2019-12-31 23:59 (Step B).
- **log10 CV_box:** the stored primary_CV_box.
- **Fitting:** as `euv_heldout.fit_folds`, but with `LogisticRegression(penalty="l2", C=0.3, solver="lbfgs", max_iter=10000)`.
- **Dev set:** the frozen `euv_extra` dev rows (541: primary fill ≥ 80%, CV_box > 0). The grid search that chose this configuration was not re-run here.

**Checks (all passed):**
- The dev set equals `data/euv_extra/dev_rows.csv` (541, same order).
- prot12 = 1 only where a C1+ started in (t − 12 h, t).
- Model C (C = 1.0) reproduces the frozen `euv_extra` dev OOF log-loss and τ exactly.

**Dev set:** 541 episodes (96 true / 445 false; 179 HARPs). prot12 = 1 in 166 of them (59 true / 107 false).

**COMBO-T, dev out-of-fold (exploratory):**
- LL 0.3139; weighted AUC 0.7930.
- **τ (≥ 88% weighted true kept) = 0.0792151183.**
- True kept 84/96 (0.8840 w); false removed 255/445 (0.5735 w).

**Reference, frozen Model C, dev out-of-fold:**
- LL 0.3223; weighted AUC 0.7720.
- τ 0.0625698316; true kept 88/96 (0.8807 w); false removed 154/445 (0.3579 w).

**Coefficients per fold** (per 1 SD):
- score: +0.4637 to +0.7408
- log10 CV_box: +0.3124 to +0.5279
- prot12: −0.0716, +0.0663, +0.0837, +0.1563, +0.1515
- logR: −0.1210 to +0.0775
- The full table is in the log.

**SHA-256** (`data/combo_t/`; full hashes in the log and in `model_hashes.json`):
- COMBO_T_fold0–4: 1ea33fa1…, a2b5d7f0…, 932a64ef…, faacdc41…, 76ac7ba6…
- thresholds.json: 3b598cc7…
- dev_rows.csv: 2717b304…

## 2026-09-28 — PRE-REGISTRATION: C+ protection rule = the ONLY confirmatory false-alarm system (decided by: user; wording drafted by Claude AI, reviewed and adopted by Lokesh)
**Verbatim (user), PART 0:**

Definition (fixed now): keep an alarm episode if EITHER (a) p_C_CV >= 0.068936 using the FROZEN euv_extra C_CV fold models (mean of 5; hash-verify), OR (b) the region had >= 1 flare of class C1.0 or larger (C, M or X; SWPC originals; true-flux scale; flux >= 1e-6 W/m²) whose START is in (t − 24 h, t), joined by the same NOAA-region join as the labels. Otherwise removed. Baseline = Model C (frozen euv_extra C, τ 0.062570).
Rationale (verbatim): 24 h matches the forecast window; C1.0 is the standard class boundary and the definition Model C already uses for "time since last flare"; no parameter was tuned on 2021–2026. COMBO-T (e17a8a3) remains a secondary exploratory model only; its 12-h window and C2.0 threshold came from a 90-configuration dev grid and are not used in the confirmatory system.
Disclosure (verbatim): Designed after post-hoc inspection by Claude AI (in chat, not committed) of all 2010–2026 alarms: of 44 true alarms rejected by C_CV, 24 had >= 1 C-class flare in the prior 24 h; including M/X changed 1 of 1,532 alarms. Claude's post-hoc simple counts: 2010–19 91/96 true kept, 179/445 false removed; 2021–2026 combined 146/160, 282/831 (Model C 150/160, 199/831); 2025–26 52/56, 125/322 (Model C 54/56, 87/322). The same pattern is visible in 2010–19 alone (7 of 12 C_CV-rejected true alarms had a prior C flare). All data up to 2026-08-16 are invalid for confirming this rule.
LOOK 1 (descriptive only, no reading): the already-registered prospective set (t in [2026-08-17, E], E = min(2026-10-31, coverage end)); runs with "run the prospective test once", not before 2026-11-10.
LOOK 2 (CONFIRMATORY): t in [2026-08-17 00:00 TAI, E2], E2 = min(2027-02-28 23:00 TAI, latest complete SHARP+SWPC+GOES coverage with 24 h follow-up). Same gate, cohort rules and fallbacks as 749208e (T1–T4, <= 2 regions), same labels (SWPC originals, true-flux scale, delayed = false), same EUV download and frame rules (94 Å, 12-min, (t−24 h, t]; one pending JSOC export at a time, my account only; dry run first). Exclude every HARP and NOAA region present in any EUV data directory created before 2026-09-28. Run only on "run the C+ confirmation once", not before 2027-03-15; E2 and coverage check recorded before any download. SIZE RULE (label-blind): < 150 evaluable episodes → "TOO SMALL — DESCRIPTIVE ONLY".
PRIMARY (Look 2): from the same paired HARP resamples (2,000, seed 0): D_false = weighted % false removed (C+ minus Model C), D_true = weighted % true kept (C+ minus Model C), 95% CIs.
READING (mechanical): "CONFIRMED BETTER TRADE-OFF" if D_false CI lower > 0 AND D_true CI lower >= −10 pts; "MEETS OPERATING CRITERION" if D_false CI lower > 0 AND D_true point >= −10 (CI lower < −10); "REMOVES MORE FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS" if D_false CI lower > 0 AND D_true point < −10; "NOT CONFIRMED" otherwise; "INCONCLUSIVE" if CIs cannot be computed.
Commit. STOP.

**Note (me), from a file read only, no computation:** the frozen `data/euv_extra/thresholds.json` values are τ_C_CV = 0.06893616544608924 and τ_C = 0.06256983158392139. The entry's 0.068936 and 0.062570 are these rounded to 6 decimals. An episode whose p falls between the rounded and the exact value would be classified differently, so the user should confirm which applies before Look 1 / Look 2.

## 2026-09-28 — DOCUMENTATION UPDATE, Parts 1–5: instructions recorded verbatim (decided by: user)
**Verbatim (user):**

DOCUMENTATION UPDATE — APPEND-ONLY. Never edit, reorder or delete any existing decisions.md entry, frozen file, model, threshold, result or figure. No JSOC downloads. No prospective data. Do not run stage5_test.py. Do NOT draft the research plan, abstract, synopsis, paper or poster text (ISEF rule: student-written). Commit after each part and STOP at the end of each part.

PART 1 — REPRODUCE AND LOG CLAUDE-CHAT POST-HOC ANALYSES (already-seen data; every number labelled "POST-HOC, exploratory, originally computed by Claude AI in chat on 2026-09-27/28; reproduced here"). Use only frozen models (euv_extra A, A_CV, C, C_CV; data/combo_t COMBO-T) with dev predictions out-of-fold (dev_rows.csv folds) and new-set predictions = mean of 5 fold models. Sets, reported separately: dev 2010–19; 2021/23/24 test (euv_test, 306); 2021/23/24 extra (155); 2022 (152); 2025–26 (378). Report simple counts AND weighted (1/n per HARP) values; add HARP-bootstrap 95% CIs (2,000, seed 0) where a difference is reported. For each item, write a one-line statement of whether the reproduction matches the chat numbers (list any mismatch; do not adjust to match).
 1a. Matched-retention comparison C vs C_CV at 80/88/95% true kept (per set).
 1b. Sign of the log(1+R) coefficient in all 5 frozen C fold models and in C_CV.
 1c. For true alarms rejected by C_CV (and separately by COMBO-T): count and list of flares (class, start time) from the same region in (t−24 h, t); median hours to the M1+ flare, split by any-C+ vs none. Also the same summary for false alarms removed/kept and true alarms kept.
 1d. Spearman ρ between number of C-class flares in (t−24 h, t) and CV_box, per set and pooled; median CV_box by C-count bin (0,1,2,3–4,5+) split true/false.
 1e. Rule comparisons per set (true kept, false removed, precision): gate only; Model A; Model C; A+CV; C+CV; C-flare rule alone; C-protected (C-class only); C+ rule (C1.0+ incl. M/X); C-level sweep C1.0–C7.0 with the dev-only choice rule "max false removed with true kept >= Model C on dev" (record the chosen level); per-C-count restlessness cutoff "table rule" (cutoffs at 88% on dev).
 1f. COMBO (default: C + log10 CV_box + anyC24 + interaction, C=1) fitted on dev; the 90-configuration dev grid that selected COMBO-T (record the full grid table); COMBO-T and COMBO default on each later set: true kept, false removed, AUC, log-loss; reliability tiers (<5%, 5–15%, 15–30%, >30%); COMBO-T + C+ override.
 1g. Walk-forward recalibration: τ re-set on the three 2021–24 sets combined (targets 88/90/95%), applied once to 2025–26, for Model C, COMBO default and COMBO-T.
 1h. Literature-style metrics on 2025–26: unclustered twins CI and Wilcoxon p; max-TSS thresholds tuned on the set itself (labelled "threshold tuned on test set — optimistic").
 1i. Excess-area check (area of brightness above the 24-h mean) for the 6 GIF twin pairs and ρ with CV_box over all 2025–26 episodes.
Write all tables to docs/posthoc_2026-09-28.md and a results entry in decisions.md. Commit. STOP.

PART 2 — FIGURE AND FILE INVENTORY:
List every file created in figures/ and data/ since 2026-09-26 (name, size, what it shows, generating script if known, whether it is a figure for use or a scratch/check file such as figures/_chk_*.png, figures/_gif_frame_check.png). Do not delete anything; mark scratch files "scratch — can be deleted by the user". Write docs/file_inventory.md. Commit. STOP.

PART 3 — RESULTS HIERARCHY (factual summary; not presentation text):
Create/overwrite docs/RESULTS_SUMMARY.md (a new file; do not edit old summaries) with sections, each item giving the number, CI, data set, and commit hash:
 A. CONFIRMED (pre-registered, run once): TEST 1 twins 3.26 [1.30, 9.49] 39/50; TEST 2 Step B Δ +0.0173 [0.0016, 0.0350]; gate region TSS 0.728 [0.630, 0.820]; the pre-registered filter tests and their readings (5abc40a, 4b65f23); the Stage 5 magnetic-trend null; R4a held-out results.
 B. POST-HOC ROBUSTNESS (defined before computing, after the main result): 1465063 cells incl. T_b×V1 2.73 [1.10, 6.20]; noise/exposure/saturation checks; alert tiers.
 C. POST-HOC EXPLORATORY (not results): everything from Part 1, C+ rule, COMBO-T.
 D. FAILED / STOPPED: every dev candidate and its reading (list all ~30 with commit hashes), V2 image-only failure, BF noise-dominated, n_B + R4a stop (B-flare attribution), CV6 label-dependent exclusion.
 E. PENDING (pre-registered, not yet run): prospective test (CV_box primary; CV6, BF(a), COMBO-T secondary), Look 1, Look 2 (C+ rule confirmatory).
 F. DATA-QUALITY FINDINGS: HEK AR=0 phantom false alarms (FAR 0.724 vs 0.543), Bobra & Couvidat partial reproduction, B-flare disappearance near solar maximum, cutoff drift across the cycle.
Commit. STOP.

PART 4 — AI-USE AND PROVENANCE RECORD (for the student's disclosure; factual):
Create docs/AI_USE_LOG.md containing:
 - From git: commit count by author trailer (Co-Authored-By: Claude …), date range, and the list of scripts/files written by AI.
 - From decisions.md: every entry marked "wording drafted by Claude AI" (date, heading, commit).
 - Idea provenance table. Record as "stated by the user" these user-originated ideas: research topic/question; PIL flicker hypothesis; extending data to 2026 (the 2025–26 set); strong-gradient PIL / brightest core / sunspot masks; magnetic dots count; overlay/new-pixel brightenings; background brightness; area under the brightness curve; removing flare frames; an AIA measure independent of flare counts and magnetics (the combined control); "are we testing too harshly"; checking prior small flares in missed true alarms; the C-flare protection rule and its C1.0+ (incl. M/X) version; turning signals into a flare-probability ("chance") model; removing the 12-h/C2 settings. For every other measure or test, record the proposer as shown in decisions.md; if decisions.md does not say, write "not recorded" (do not guess).
Commit. STOP.

PART 5 — FINAL CHECK: re-verify all hashes of frozen models/thresholds (euv_extra, combo_t, nb_r4a, stage 4/5); confirm no existing decisions.md line changed (diff against the commit before Part 0, additions only); report the commit hashes of Parts 0–4. STOP.

## 2026-09-28 — CLARIFICATION: C+ rule thresholds = exact frozen values; PART 1 definitions and chat reference numbers (decided by: user; recorded verbatim before any Look 1 / Look 2 data exist and before Part 1 is computed)
**Verbatim (user):**

THRESHOLDS (record as a clarification in decisions.md BEFORE any Look 1/Look 2 data exist): the C+ rule uses the EXACT frozen values read from the frozen threshold files (τ_C_CV = 0.06893616544608924 from data/euv_extra/thresholds.json; τ_C = 0.06256983158392139). The 6-decimal numbers in 8aa1797 were shorthand. Same for COMBO-T (τ from data/combo_t/thresholds.json).

GENERAL NOTES ON MY CHAT NUMBERS: computed with my own SWPC parser (edited-events XRA lines; GOES-13/14/15 flux ÷0.7; 4-digit region +10000; flare START time; duplicates dropped). Use the repo's label code instead and report any difference. "Simple counts" = unweighted n/N. Where I said weighted, weights = 1/n per HARP within each set. Dev predictions = out-of-fold with dev_rows.csv folds (reproduced 0.8803 / 0.8807 weighted true kept for C_CV / C). My scripts were in /tmp on the VM, not the repo.

1a (matched retention; weighted false removed at the highest threshold keeping >= target weighted true; paired HARP bootstrap 2,000, seed 0, my own implementation):
 2025–26: target 0.80 C 0.553 / C_CV 0.485, diff −0.068 [−0.291, +0.398]; 0.85 0.452/0.393; 0.88 0.452/0.355, diff −0.097 [−0.293, +0.323]; 0.90 0.440/0.355; 0.95 0.200/0.330, diff +0.131 [−0.229, +0.223].
 2021/23/24 extra: 0.80 0.55/0.66 (+11 pts [−9, +45]); 0.88 0.27/0.35 (+7 [−11, +49]); 0.95 0.11/0.18 (+8 [−12, +43]).
 2022: 0.80 0.48/0.81 (+33 [−12, +57]); 0.88 0.31/0.53 (+22 [−20, +56]); 0.95 0.24/0.23 (−2 [−24, +43]).
 (2021/23/24 single-region test set: not computed in chat.)

1b: log(1+R) standardized coefficient, C folds 0–4: −0.198, −0.326, −0.185, −0.261, −0.321. C_CV folds 0–4: +0.146, −0.144, +0.178, −0.006, +0.027.

1c: C_CV-rejected true alarms (simple counts) and how many had >= 1 C-CLASS flare (1e-6 <= flux < 1e-5) in (t−24 h, t): dev 12 (7), 2021/23/24 test 6 (3), extra 5 (2), 2022 6 (2), 2025–26 15 (10); total 44 (24) from 32 HARPs. Median hours to first M1+: rejected with C 10.7 (n=24), rejected without C 15.5 (n=20), true kept 9.3. Groups with >= 1 C-class flare: false removed 201/662, false kept 449/614, true kept 183/212. Any M/X in prior 24 h: true rejected 5%, true kept 47%, false kept 21%, false removed 0%.
 COMBO-T-rejected true alarms at frozen τ: 44 (dev 12, test 4, extra 6, 2022 6, 2025–26 16) from 30 HARPs; 22 had >= 1 flare >= C1.0 (incl. M/X) in prior 24 h; median predicted chance 6.0%; median hours to M1+ 13.1.

1d: Spearman ρ(C-class count in (t−24 h, t), CV_box): dev +0.658 (n 541), test +0.587 (306), extra +0.439 (155), 2022 +0.535 (152), 2025–26 +0.530 (378), pooled +0.567 (1,532); within true +0.309 (256), within false +0.560 (1,276). Median CV_box by C-count bin 0 / 1 / 2 / 3–4 / 5+: false 0.056 / 0.110 / 0.152 / 0.189 / 0.286; true 0.111 / 0.237 / 0.251 / 0.243 / 0.337.

1e DEFINITIONS:
 - "C-flare rule alone": keep iff >= 1 C-CLASS flare (1e-6 <= flux < 1e-5; M/X NOT counted) from the region with start in (t−24 h, t). No model.
 - "C-protected (C-class only)": keep iff C_CV keeps OR >= 1 C-CLASS flare (M/X not counted) in (t−24 h, t).
 - "C+ rule": as in 8aa1797 (C1.0+ incl. M/X).
 - "C-level sweep": keep iff C_CV keeps OR the largest C-CLASS flare (C-class only) in (t−24 h, t) >= level; levels C1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0. Dev-only choice rule: max false removed subject to true kept >= Model C's dev true kept (88/96) → chose C2.0.
 - "Table rule": bins by C-class count in (t−24 h, t): 0, 1, 2, 3–4, 5+. Per-bin cutoff = sorted dev TRUE CV_box values r (unweighted), cutoff = r[floor(0.12·n)]. Keep iff CV_box >= that bin's cutoff (no Model C). Dev cutoffs: 0.065, 0.081, 0.196, 0.085, 0.194.
 1e CHAT NUMBERS (true kept / false removed, simple counts):
 - 2021–26 combined: Model C 150/160, 199/831; C_CV 128/160, 444/831; A_CV 125/160, 492/831; C-flare rule alone 130/160, 386/831; C-protected 145/160, 282/831; C+ 146/160, 282/831; table rule 109/160, 404/831.
 - Dev: C-flare rule 77/96, 240/445; C-protected 91/96, 179/445; C+ 91/96, 179/445; table rule 87/96, 188/445; Model A 87/96, 70/445.
 - C-level sweep, all sets pooled (256 true / 1,276 false): C1.0 236, 461; C1.5 231, 513; C2.0 227, 549; C2.5 226, 592; C3.0 221, 617; C4.0 220, 635; C5.0 217, 646; C7.0 215, 658; none 212, 662.

1f GRID (dev only): features = Model C columns (score, n_C, n_M, n_X, log(1+R)) + log10 CV_box + prot [+ prot × log10 CV_box if interaction]. prot = 1 if the region's max flare flux (any class) with start in (t − W, t) >= L.
 - Grid: W ∈ {12, 24, 48} h; L ∈ {C1.0, C2.0, C5.0}; interaction ∈ {yes, no}; LogisticRegression L2 C ∈ {0.03, 0.1, 0.3, 1, 3}, lbfgs, max_iter 10000. 90 configs.
 - Setup: StandardScaler fit per training fold; sample_weight 1/n per HARP; τ = highest dev OOF threshold keeping >= 88% weighted true.
 - Objective: max weighted false removed at τ; tie → lower weighted OOF log-loss.
 - Top: W12 / C2 / no interaction / C=0.3 (τ 0.0792, fr_w 0.5735, tk_w 0.8840, LL 0.3139). Next: W12 C2 inter C0.3 (0.5718); W24 C5 inter C0.3 (0.5533).
 - Default COMBO = W24, L=C1.0, interaction, C=1 (dev τ 0.0642).
 2021–26 pooled (my log-loss weighted 1/n per (set, HARP); AUC unweighted):
 - COMBO-T: 128/160, 477/831, AUC 0.768, LL 0.3657.
 - Default: 142/160, 324/831, AUC 0.755, LL 0.3756.
 - Model C: 150/160, 199/831, AUC 0.750, LL 0.3768.
 COMBO-T by set: test 40/44, 138/262; extra 26/32, 63/123; 2022 22/28, 66/124; 2025–26 40/56, 210/322.
 COMBO-T tiers (2021–26): <5% 183 alarms / 5 true; 5–15% 639/83; 15–30% 99/38; >30% 70/34. Default COMBO tiers: <5% 274/12; 5–15% 538/74; 15–30% 104/37; >30% 75/37.
 COMBO-T + C+ override: dev 90/96, 198/445; 2021–26 144/160, 318/831; 2025–26 51/56, 141/322.

1g WALK-FORWARD (τ re-set on the three 2021–24 sets pooled, weighted, targets 88/90/95%; applied to 2025–26, simple counts true kept/56, false removed/322):
 - Model C: τ 0.074 → 48, 153; τ 0.067 → 52, 122; τ 0.060 → 54, 63.
 - Default COMBO: 0.072 → 48, 152; 0.057 → 52, 130; 0.046 → 53, 115.
 - COMBO-T: 0.073 → 43, 190; 0.061 → 48, 142; 0.056 → 50, 130.

1h (2025–26):
 - Twins: unclustered pair-bootstrap CI [1.63, 8.04]; Wilcoxon p 1.5e-6; sign test two-sided p 9.0e-5 (39/50).
 - Max-TSS with threshold tuned on the set itself (unweighted):
   - A: AUC 0.756, TSS 0.424 (68% kept, 75% removed).
   - C: AUC 0.777, TSS 0.437 (80%, 63%).
   - C_CV: AUC 0.781, TSS 0.491 (64%, 85%).
   - CV_box alone: AUC 0.753, TSS 0.396.
 - Frozen C_CV precision 0.244 vs gate 0.148.

1i PAIRS (true vs false):
 - twin_pair_24h / magnetic_vs_aia94_twin_pair: 13299_20250529T1459 vs 13891_20251018T2059.
 - twin_gif_1_p10: 14117_20251206T1159 vs 13726_20250905T0959.
 - _2_p30: 13574_20250806T2159 vs 14825_20260627T0659.
 - _3_p50: 13708_20250830T1359 vs 12889_20250313T0659.
 - _4_p70: 13574_20250803T0959 vs 14284_20260123T0959.
 - _5_p90: 14117_20251208T2259 vs 14765_20260616T0259.
 Later GIFs (inventory only):
 - pair_good_1: 12713_20250213T0459 vs 14003_20251107T1359.
 - pair_good_2: 12597_20250116T2059 vs 12752_20250214T0159.
 - pair_calm_flarer_missed: 14924_20260725T1859 vs 14191_20251227T0959.
 Definitions: excess area = trapezoid ∫ max(box/mean − 1, 0) dt (hours) over valid_primary frames in (t−24 h, t); raw area = ∫ box dt. Chat ρ over 387 episodes with CV_box > 0 (I did not apply the 80% fill rule): ρ(excess area, CV_box) 0.934; ρ(|box/mean − 1| area, CV_box) 0.936. Chat excess areas (true / false):
 - first pair 1.059 / 0.114
 - p10 0.991 / 1.396
 - p30 1.865 / 0.815
 - p50 0.612 / 0.607
 - p70 0.953 / 0.307
 - p90 4.256 / 0.398

Where your reproduction differs from these, report both and do not adjust anything.

### 2026-09-28 — PART 1 RESULTS: Claude-chat post-hoc analyses reproduced (POST-HOC, exploratory, originally computed by Claude AI in chat on 2026-09-27/28; reproduced here)
**Outputs:** `posthoc_2026_09_28.py`, `posthoc_2026-09-28.log`, and every table in `docs/posthoc_2026-09-28.md`.

**Data and method:** already-seen data only; no new data, no JSOC, no prospective data.
- Frozen models only (euv_extra A, A_CV, C, C_CV; COMBO-T), at their exact frozen τ.
- Dev predictions are out-of-fold from the frozen fold models; later sets use the mean of the 5 fold models.
- Flares come from the repo's label code (`swpc.fetch` joinable events, K2 true scale, noaa_ars join), not the chat's parser.

**Checks:**
- Hashes verified.
- The dev set equals the euv_extra dev rows (541, same folds).
- Dev OOF from the frozen fold models reproduces the frozen dev log-loss for A, A_CV, C, C_CV and COMBO-T exactly, and the COMBO-T τ.
- prot12 reproduces the COMBO-T dev rows.
- The top of the 90-configuration grid is the frozen COMBO-T (τ and log-loss identical).
- The label code reproduces stored true_alarm with 0 mismatches in all 5 sets.

**Match with the chat numbers:** all 288 compared values match at the chat's precision. Part 0 15/15; 1a 49/49; 1b 10/10; 1c 34/34; 1d 18/18; 1e 48/48; 1f 51/51; 1g 27/27; 1h 21/21; 1i 15/15. No differences arose from using the repo's label code instead of the chat's parser.

**Selected numbers** (simple counts; the weighted values are in the doc):

C+ rule vs Model C, true kept / false removed:

| set | C+ | Model C |
|---|---|---|
| dev | 91/96, 179/445 | 88/96, 154/445 |
| test | 41/44, 94/262 | 42/44, 72/262 |
| extra | 29/32, 36/123 | 28/32, 22/123 |
| 2022 | 24/28, 27/124 | 26/28, 18/124 |
| 2025–26 | 52/56, 125/322 | 54/56, 87/322 |
| 2021–26 combined | 146/160, 282/831 | 150/160, 199/831 |

C+ minus Model C (weighted points; paired HARP bootstrap 2,000, seed 0; post-hoc — these sets cannot confirm the rule):

| set | D_true | D_false |
|---|---|---|
| dev | +4.9 [−1.9, +14.6] | +4.4 [−1.4, +10.2] |
| test | −1.0 [−4.0, +0.0] | +5.0 [−3.6, +13.3] |
| extra | +1.2 [+0.0, +4.5] | +9.8 [−3.5, +22.1] |
| 2022 | −5.6 [−20.6, +3.2] | +2.9 [−7.1, +12.6] |
| 2025–26 | −1.3 [−3.7, +0.0] | +7.9 [+0.7, +15.5] |

- **C_CV-rejected true alarms:** 44 across the 5 sets, from 32 HARPs; 24 had ≥ 1 C-class flare in (t − 24 h, t).
  - Median hours to the first M1+: 10.66 with a prior C-class flare (n 24), 15.49 without (n 20); true alarms kept, 9.28 (n 212).
  - Any M/X in (t − 24 h, t): true rejected 4.5%, true kept 47.2%, false kept 21.2%, false removed 0.3%.
- **C-level sweep:** the dev choice is C2.0.
- **Table-rule dev cutoffs:** 0.065, 0.081, 0.196, 0.085, 0.194.
- **COMBO default:** dev τ 0.0642.

## 2026-09-29 — Reproduction runs R5–R7 defined (decided by: user; DIAGNOSTIC; dev period 2010-05-01 … 2014-05-31 only; gate, frozen files, split, cohorts and existing results unchanged)
**Verbatim (user):**

Diagnostic only (dev period 2010-05-01 … 2014-05-31). Do NOT modify the gate, frozen files, split, cohorts, or any existing result. decisions.md is append-only.
Goal: test the two remaining untested assumptions of our Bobra & Couvidat (2015) reproduction (D7/D8/R1–R4), using the R2 construction (10 features, exact 12-min SHARP records, NGDC location admissions) exactly as implemented in `diag_r.py`.
Step 1 — reproduction check. Rerun R2 with the existing code and confirm it reproduces the recorded R2 rows exactly (TSS 0.520 ± 0.049 and 0.708 ± 0.038; P 291, N 4,802). If it does not match, STOP and report.
Step 2 — runs (RBF, γ = 0.075, tol = 1e-8, median/SD scaling on the whole catalogue, decision value 0, stratified random 70/30 splits; both C1/C2 = 2 and 15):
* R5 (penalty placement): same as R2, but C = 4 applies to the flare class: C_pos = 4, C_neg = 4/ratio (i.e. `C=4, class_weight={1:1.0, 0:1/ratio}`). 1,000 splits.
* R6 (negative-draw variability): same as R2, but draw the negative set 20 times independently (seeds SEED+1000 … SEED+1019), N = round(16.5·P) each time, with 200 splits per draw. Report, per C1/C2 setting: the mean TSS of each draw, and the min / median / max across the 20 draws.
* R7: R5 and R6 combined.
Step 3 — report, table only: for each run and setting: P, N, TSS mean ± sd, recall, precision, FPR, whether it's in the target range, and for R6/R7 the across-draw min / median / max and how many of the 20 draws land in the target. Save outputs to `data/diag/r5_r7.csv` and the script as `diag_r5_r7.py`, and append the results table to decisions.md. Report runtime. No interpretation, no changes to anything else. Stop.

**Targets (unchanged):** Table 2 (C1/C2 = 2) TSS 0.562–0.658; Table 3 (C1/C2 = 15) TSS 0.722–0.800.

**Reading rule:** "a run 'matches' if its mean TSS lies in the target range; no conclusion beyond the table." For R6/R7, the run's mean TSS is the mean over all 20 × 200 splits; the per-draw means are reported alongside.

### R5–R7 implementation details (decided by: me, before running)
- **Reusing the existing code:** `diag_r5_r7.py` runs `diag_r.py`'s source up to (not including) the line `TARGET = …`, exactly as `diag_r.py` itself runs `diag_d7.py`'s header.
  - This defines the R2 construction unchanged: `positives(True)` = P2, the negative pool POOL, `build()` and `split()`.
  - All inputs come from local caches (`data/diag/r_sharp12.csv`, `r_swansf.csv`, `r_cgem.csv`, raw SHARP chunk files, `data/ngdc`). No JSOC query is made.
- **Step 1:** `build(P2)` plus `split()` for i = 0 … 999 at C1/C2 = 2 and 15, formatted exactly as `diag_r.py`. The R2 rows of `data/diag/r_runs.csv` (P, N, neg pool, TSS, recall, precision, FPR, all strings) must be reproduced identically; otherwise STOP.
- **R5:** R2's catalogue and split seeds (`train_test_split(…, stratify=y, random_state=SEED + i)`, i = 0 … 999), with `SVC(kernel="rbf", C=4.0, gamma=0.075, tol=1e-8, class_weight={1: 1.0, 0: 1/ratio})`.
- **R6:** for draw j = 0 … 19, the same code as `build()` except `pool.sample(n=N, replace=False, random_state=SEED + 1000 + j)`.
  - Scaling (median/SD) is recomputed on each draw's whole catalogue.
  - 200 splits per draw with i = 0 … 199 (random_state SEED + i, the same split seeds as R2's first 200). The R2 estimator is used (C = 4, class_weight {1: ratio, 0: 1}).
  - Check: the copied build code with random_state = SEED must reproduce `build(P2)` exactly.
- **R7:** R6's 20 draws and 200 splits per draw, with R5's estimator.
- **Metrics:**
  - Per split: TP, FN, FP and TN at decision value 0, from which TSS, recall, precision (undefined if nothing is predicted positive; counted) and FPR are computed.
  - Per row: mean ± sd (ddof 1) over all splits, as `diag_r.py`.
  - For R6/R7, also each draw's mean TSS; the min, median and max across the 20 draws; and how many draws have a mean TSS in the target range.
- **Parallelism:** joblib with os.cpu_count() − 1 workers (`diag_r.py` used 3). Each split is deterministic, so the worker count does not affect any value.

### R5–R7 — RESULTS (diagnostic; dev period 2010-05-01 … 2014-05-31 only; gate, frozen files, split, cohorts and existing results unchanged; table only)
Outputs: `diag_r5_r7.py` → `data/diag/r5_r7.csv`; log in `diag_r5_r7.log`. The targets were pre-registered in d34431f: Table 2 0.562–0.658; Table 3 0.722–0.800.

**Step 1:** the R2 rerun reproduces `data/diag/r_runs.csv` exactly, for both C1/C2 settings: P 291, N 4,802, neg pool 132,978, TSS 0.520 ± 0.049 and 0.708 ± 0.038, and identical recall, precision and FPR. The copied build code with the D7 seed reproduces `build(P2)`.

In every row, P = 291, N = 4,802 and neg pool = 132,978. No split had undefined precision. R5 has 1,000 splits; R6 and R7 have 20 draws × 200 splits = 4,000.

| run | C1/C2 | TSS | recall | precision | FPR | TSS in target | across 20 draws: min / median / max | draws in target |
|---|---:|---|---|---|---|---|---|---|
| R5 (C_pos = 4, C_neg = 4/ratio) | 2 | 0.511 ± 0.051 | 0.527 ± 0.052 | 0.670 ± 0.051 | 0.016 ± 0.004 | no | — | — |
| R5 (C_pos = 4, C_neg = 4/ratio) | 15 | 0.744 ± 0.033 | 0.859 ± 0.037 | 0.312 ± 0.021 | 0.115 ± 0.012 | **yes** | — | — |
| R6 (20 negative draws, R2 penalty) | 2 | 0.510 ± 0.050 | 0.524 ± 0.051 | 0.704 ± 0.057 | 0.014 ± 0.004 | no | 0.484 / 0.508 / 0.538 | 0/20 |
| R6 (20 negative draws, R2 penalty) | 15 | 0.703 ± 0.037 | 0.796 ± 0.040 | 0.342 ± 0.023 | 0.093 ± 0.010 | no | 0.692 / 0.703 / 0.713 | 0/20 |
| R7 (R5 + R6) | 2 | 0.497 ± 0.050 | 0.511 ± 0.051 | 0.700 ± 0.057 | 0.013 ± 0.004 | no | 0.475 / 0.496 / 0.529 | 0/20 |
| R7 (R5 + R6) | 15 | 0.738 ± 0.033 | 0.857 ± 0.036 | 0.304 ± 0.021 | 0.119 ± 0.013 | **yes** | 0.724 / 0.738 / 0.746 | 20/20 |

**Per-draw mean TSS** (draws j = 0 … 19, seeds SEED + 1000 + j):

| run | C1/C2 | per-draw mean TSS |
|---|---:|---|
| R6 | 2 | 0.484; 0.489; 0.503; 0.507; 0.533; 0.520; 0.538; 0.504; 0.512; 0.510; 0.498; 0.490; 0.511; 0.516; 0.514; 0.506; 0.538; 0.525; 0.498; 0.507 |
| R6 | 15 | 0.692; 0.697; 0.708; 0.702; 0.707; 0.702; 0.712; 0.697; 0.710; 0.703; 0.699; 0.694; 0.702; 0.701; 0.709; 0.703; 0.713; 0.705; 0.699; 0.712 |
| R7 | 2 | 0.475; 0.480; 0.497; 0.489; 0.520; 0.503; 0.522; 0.486; 0.502; 0.496; 0.483; 0.479; 0.495; 0.497; 0.503; 0.499; 0.529; 0.510; 0.483; 0.495 |
| R7 | 15 | 0.725; 0.739; 0.735; 0.732; 0.744; 0.741; 0.746; 0.732; 0.742; 0.742; 0.736; 0.724; 0.740; 0.735; 0.746; 0.739; 0.746; 0.736; 0.737; 0.735 |

**Runtime:** 4.8 min in total (Step 1 R2 rerun 0.5; R5 0.4; R6 + R7 3.9), with 9 workers.

## 2026-09-30 — Read-only search: source of the post-hoc 2025–26 twins intervals (requested by: user; nothing recomputed)
**Searched:**
- All .py, .log, .md, .txt, .csv and .json files in the repo, including `data/`, `figures/` and `docs/`; `.venv` was excluded.
- The untracked `Claude outputs/` folder, including the extracted text of both PDFs.
- `git log` messages, and all commit diffs via `git log -S "8.94"` / `-S "1.48"`.
- Method keywords: false-HARP resampling, two-way, "both sides", "linked groups", non-flaring side.

**Found — only "flaring side only 1.30–9.49":**
- It is the pre-registered TEST 1 CV_box twins interval, with pairs resampled by true (flaring) HARP, 2,000 resamples, seed 0.
- Code: `euv_confirm_tests.py` (`ratio_block` → `phase_f.ratio_jobs` / `boot_many`, statistic "ratio_pairs", groups = true_harp).
- Output: `euv_confirm_tests.log`, lines 5 and 10: ratio 3.2624 [1.2956, 9.4887], 50 pairs, reading "REPLICATED".
- Commit: ae1b174. It was also restated in 1465063 (sensitivity, T_a × V0) and 5af931b.

**Not found:**
- "non-flaring side only 1.48–8.94"
- "both sides 0.86–12.2"
- "4 linked groups 0.68–18.9"

No code, log, document, figure data or commit contains these intervals or a false-side, two-way or linked-group clustered twins bootstrap. The only occurrences of those digits are unrelated values (e.g. 18.9436 hours to M1+ in `descriptive_aia94.log`, 12.29% in `relabel_*.log`, and data values in history diffs). Nothing was recomputed.

## 2026-09-30 — Post-hoc twin-interval check under region reuse (decided by: user; POST-HOC diagnostic; recorded before computing)
**Verbatim (user):**

Post-hoc diagnostic on the 2025–26 CV_box magnetic twins (the 50 TEST 1 pairs from `euv_confirm_tests.py`). Do not modify any existing file or result; decisions.md is append-only.
Step 0 — record before computing. Append an entry to decisions.md, "Post-hoc twin-interval check under region reuse," containing the definitions below, and commit it before Step 1. State that it is post-hoc and that it replaces the untraceable values 1.48–8.94, 0.86–12.2 and 0.68–18.9 quoted in the team paper, which have no source in the repo.
Step 1 — reproduction check. With the existing code, reproduce TEST 1 exactly: ratio 3.2624 [1.2956, 9.4887], resampling by true HARP (2,000 resamples, seed 0). STOP if it doesn't match.
Step 2 — three intervals. Same statistic (median true CV_box ÷ median false CV_box over the resampled pairs), 2,000 resamples, seed 0, percentile 95% CI:
* (a) Non-flaring side: resample false-alarm HARPs with replacement; each pair enters as many times as its false HARP was drawn.
* (b) Both sides (two-way): independently draw true HARPs (counts aᵢ) and false HARPs (counts bⱼ) with replacement; each pair (i, j) gets weight aᵢ·bⱼ. Compute weighted medians on each side. Skip resamples with zero total weight and count them.
* (c) Linked groups: build a graph whose nodes are HARPs and whose edges are pairs (a HARP on both sides is one node); take connected components; resample components with replacement.
Step 3 — report, table only. For each: number of clusters, CI, share of resamples with ratio ≤ 1, skipped resamples. Also give the number of distinct true HARPs, false HARPs and HARPs on both sides, and the size of every component. Save as `posthoc_twin_reuse.py` and `.log`, append the table to decisions.md, commit. No interpretation. Stop.

**Status:** this check is POST-HOC. The TEST 1 result (ae1b174) is already known. Its intervals **replace the untraceable values 1.48–8.94, 0.86–12.2 and 0.68–18.9 quoted in the team paper**, which have no source in the repo (search recorded in 44ac3dc).

### Implementation details (decided by: me, before computing)
**Data:** the 50 stored TEST 1 pairs (`data/euv_confirm/twins_le2.csv`). CV_box = the stored primary_CV_box of the TEST 1 set, built exactly as `euv_confirm_tests.py` builds it (`conf_cohort("le2")`, primary_fill ≥ 0.80, CV_box defined; 378 episodes).

**Statistic:** median(true CV_box) / median(false CV_box) over the resampled pairs with multiplicity (`phase_f.med_ratio`, mode "ratio"). CI = 2.5th and 97.5th percentiles over the defined resamples.

**Step 1:** `phase_f.ratio_jobs` + `boot_many` exactly as TEST 1. Groups are the pairs grouped by true HARP, in order of first appearance in the pairs file, and the resample indices are `phase_f.choices(n_groups, 2000, 0)`. It must reproduce 3.2624 [1.2956, 9.4887]; otherwise STOP.

**(a) Non-flaring side:** the same machinery (`boot_many`, statistic "ratio_pairs", 2,000, seed 0), with the pairs grouped by false HARP in order of first appearance. Each pair enters as many times as its false HARP was drawn.

**(b) Both sides:**
- Streams: one `np.random.RandomState(0)`. In each resample, draw first nT indices with replacement from the nT distinct true HARPs, then nF from the nF distinct false HARPs (both in order of first appearance).
- Counts: aᵢ = bincount of the true draws, bⱼ = bincount of the false draws. Pair k (true HARP i, false HARP j) gets integer weight aᵢ·bⱼ.
- Weighted median on each side: the ordinary median of the values repeated by their weights (`np.median(np.repeat(x, w))`), which is the same multiset definition as (a), (c) and Step 1.
- Skipping: resamples with total weight 0 are skipped and counted; the CI uses the non-skipped resamples.

**(c) Linked groups:**
- Graph: nodes are HARPs, edges are pairs; a HARP that is the true member of one pair and the false member of another is one node. Connected components come from union-find.
- Ordering: components are ordered by their smallest HARP number.
- Resampling: components are resampled with replacement via `boot_many` (statistic "ratio_pairs", 2,000, seed 0), and each pair enters as many times as its component was drawn.

**Reported per interval:**
- Clusters: true HARPs for Step 1, false HARPs for (a), "nT true × nF false" for (b), components for (c).
- The 95% CI, the share of defined resamples with ratio ≤ 1, and the skipped or undefined resamples.

**Also reported:** the numbers of distinct true HARPs, false HARPs and HARPs on both sides, and every component's size (HARPs, pairs).

### Post-hoc twin-interval check under region reuse — RESULTS (7c9b7bb; POST-HOC; table only)
Outputs: `posthoc_twin_reuse.py` and `posthoc_twin_reuse.log`. The script was run twice: the second run changed only the printing of the "both sides" HARP list (`np.int64(…)` → plain integers); every other log line is identical.

**Step 1:** TEST 1 is reproduced exactly with the existing code: ratio 3.2624 [1.2956, 9.4887], 50 pairs, pairs resampled by true HARP (2,000 resamples, seed 0).

All intervals use the median of true CV_box divided by the median of false CV_box over the 50 pairs (ratio 3.2624), with 2,000 resamples, seed 0, and a percentile 95% CI.

| interval | clusters | 95% CI | share of resamples with ratio ≤ 1 | resamples used | skipped (zero weight) | undefined |
|---|---|---|---|---:|---:|---:|
| flaring side only (true HARP; TEST 1) | 18 true HARPs | [1.2956, 9.4887] | 0.0060 | 2,000 | 0 | 0 |
| (a) non-flaring side only (false HARP) | 41 false HARPs | [1.4764, 8.9395] | 0.0025 | 2,000 | 0 | 0 |
| (b) both sides (two-way, weights aᵢ·bⱼ) | 18 true × 41 false HARPs | [0.8632, 12.2290] | 0.0380 | 2,000 | 0 | 0 |
| (c) linked groups (connected components) | 4 components | [0.6812, 18.8683] | 0.0405 | 2,000 | 0 | 0 |

**Distinct HARPs:** 18 true, 41 false, 51 in total. Eight HARPs appear on both sides: 12713, 12793, 13708, 13726, 13883, 14187, 14915 and 14924.

**Components** (HARPs / pairs, ordered by smallest HARP):

| component | HARPs / pairs | members |
|---:|---|---|
| 1 | 45 / 47 | the other 45 HARPs (listed in the log) |
| 2 | 2 / 1 | 12853, 12896 |
| 3 | 2 / 1 | 13030, 13190 |
| 4 | 2 / 1 | 13269, 13946 |

**Comparison with the quoted values:** rounded to the precision quoted in the team paper, (a), (b) and (c) equal the untraceable values 1.48–8.94, 0.86–12.2 and 0.68–18.9. They now have a source: this entry and 7c9b7bb.

## 2026-09-30 — DEV CANDIDATE #25: AIA 1600 Å UV brightening area (UVA) — PRE-REGISTRATION (decided by: user; EXPLORATORY, dev 2010–2019 only; recorded before any 1600 Å download or computation)
**Context (user):** this is new dev candidate #25; the user states that 31 candidates have been tested before (see decisions.md), and most failed on dev. It is exploratory on dev, and nothing here confirms anything.

**Hard rules (user, verbatim):**
- decisions.md is APPEND-ONLY. Never modify frozen files (model_hashes.json list, thresholds.json, frozen/), never overwrite existing results, never delete data.
- JSOC: my account only, ONE export at a time, same download code path as euv_full/euv_download (adapted for 1600 Å). Keyword queries (pointing table) are allowed.
- DEV 2010–2019 ONLY until I say otherwise. Do NOT download, compute, or read any 1600 Å data for 2021–2026. Do NOT touch the prospective (post-2026-08-18) data or the C+ Look 1/Look 2 test.
- Every number reported must come from a committed log; quote verbatim. Label everything EXPLORATORY (dev).
- STOP at each CHECKPOINT and wait for my explicit "go".

### Step 0a — literature check (read before this entry; numbers as printed; text paraphrased)
**Nishizuka et al. 2017** (arXiv:1611.01791v1):
- **Three UV features** (Table 1, PDF pp. 19–20; rank and importance as printed):
  - CHArea, "Chromospheric (UV) brightening area" — rank 8, 0.0235.
  - CHAll, "Total chromospheric (UV) brightening" — rank 27, 0.0134.
  - CHMax, "Maximum intensity of chromospheric (UV) brightening" — rank 58, 0.006.
  - The 24-h time derivative dt24CHArea is rank 43, 0.0103.
- **Threshold** (PDF p. 9): the brightening-area threshold is 700 photons cm⁻⁵ s⁻¹ pix⁻¹ (units as printed), chosen by a parameter survey.
  - The authors used original photon numbers because the 1600 Å exposure time is almost constant (∼3 s) from 2010 to 2015.
  - The total intensity integrates the intensity above the threshold over the brightening-area pixels.
  - The paper mentions no degradation or sensitivity correction.
- **Region** (PDF p. 5): features are computed "in a whole AR". ARs are detected on the full-disk LOS magnetogram (8×8 binning, |B| > 140 G), placed in 160-pixel (∼80″) squares, and merged when overlapping. This is not a HARP.
- **Cadence** (PDF p. 4): the 1600 Å cadence is stated as 12 s and reduced to 1 h. Time derivatives are taken over 24 h, 12 h and 2 h. The data run from June 2010 to December 2015.

**Leka et al. 2023** (arXiv:2212.11255v1, NCI paper II):
- **Channels:** 1600 Å is analysed together with seven EUV filters (94, 131, 171, 193, 211, 304, 335 Å). **1700 Å is not analysed**: there are 0 occurrences of "1700" in the text.
- **Performance** (PDF p. 16): the C IV 1600 Å-based parameters never appear in any "top-10" list, and the top parameters are dominated by 94 Å and other hot-plasma filters.
- **Bottom-5 tables** (Brier Skill Score / Max(TSS) / G, as printed):
  - M1.0+/24 hr (Table 4, PDF p. 15): dµ(∆I1600)/dt 0.000 ± 0.000 / −0.031* / −0.036* (* = bottom score); µ(∆I1600) 0.000 ± 0.000 / −0.031 / −0.024.
  - M1.0+/6 hr (Table 6, PDF p. 17): µ(∆I1600) 0.001 ± 0.001 / 0.060 / 0.046; µ(I1600) −0.001 ± 0.001 / 0.141 / 0.139.

### Step 0b — aiapy and pilot checks (local code and files only; nothing downloaded)
- **Degradation correction (aiapy 0.12.1):**
  - `aiapy.calibrate.correct_degradation(smap, correction_table=None, calibration_version=10)` divides the intensity by `aiapy.calibrate.degradation(channel, obstime, …)`.
  - `degradation` normalises to the calibration epoch containing obstime (A_eff(t_e)/A_eff(t_0) times a cubic in δt), using terms from the JSOC `aia.response` series or a user table.
  - 1600 Å is supported: the code selects WAVE_STR "1600" with no thick/thin designation.
  - Validity: `_select_epoch_from_correction_table` raises "No valid calibration epoch" if obstime is outside every epoch.
  - The default table (version 10) is not local; it comes from `get_correction_table("JSOC")` (a keyword query of `aia.response`) or from SSW.
  - The only local table is aiapy's test file `aia_V8_20171210_050627_response_table.txt` (version 8). It has 10 epochs for 1600 Å covering 2010-03-24 to 2030-05-01; the last epoch starts 2016-05-01, so later dates use its extrapolation.
- **Pilot data** (`data/euv_pilot/<harp>/3/`): tracked 1600 Å im_patch cutouts (`aia.lev1_uv_24s`) at 12-min cadence over (t − 24 h, t].

  | HARP | window | files | frames with QUALITY ≠ 0 | per-frame max DN |
  |---|---|---:|---:|---|
  | 3248 | 2013-10-07 12:11 → 2013-10-08 12:00 | 120 | 1 | 59–12,507 (1 frame > 12,000) |
  | 4231 | 2014-06-11 13:11 → 2014-06-12 13:00 | 120 | 1 | 245–10,835 |
  | 6975 | 2017-03-30 07:11 → 2017-03-31 07:00 | 119 | 9 | 1,035–15,018 (1 frame > 12,000) |

  - Median EXPTIME is 2.9007–2.9013 s. No pixel exceeds 16,000 DN.
  - Synoptic 1600 Å files (`syn_1600`, 1024² 4×4-binned) also exist: 120 / 120 / 112 files.
  - Existing 1600 Å D-CTRL series: `series_dctrl_cutout_1600.csv` and `series_dctrl_synoptic_1600.csv`.
  - The 1600 Å query already exists in `euv_download.py` (the pilot): `aia.lev1_uv_24s[t−24h+12m – t @12m][1600]{image}` with im_patch.

### Step 0c — design (the user's design, verbatim)
- Episodes: the same dev episodes and fold assignment as the euv_full / euv_extra dev set (541 with CV_box defined; report the n).
- Data: AIA 1600 Å, 12-min slots over (t−24h, t], same tracked cutout (HARP box + 50″) as the 94 Å run; same frame rules (QUALITY == 0; exposure ≥ 0.5 × median; saturated pixels excluded — state the saturation DN value used); same registration and HMI mapping; fill ≥ 80%.
- Threshold (stated deviation from Nishizuka, because 1600 Å sensitivity drifts over the mission): a pixel is "bright" if its exposure-normalised intensity > 3 × the median of cutout pixels with |B_LOS| < 50 G in the same frame (HMI magnetogram at t, mapped as in the 94 Å pipeline). Report the median number of reference pixels; if < 500 in any frame, that frame is invalid.
- PRIMARY feature UVA = log10(1 + median over valid frames of the number of bright pixels within the HARP bitmap), with FLARE FRAMES EXCLUDED (euv_pilot.flare_excluded rules: C1+ from the region, M1+ anywhere).
- Secondaries (reported, cannot rescue the primary): UVA_keep (flare frames kept); UVA_max (max instead of median); UVI (log10 total excess intensity of bright pixels, median over frames); UVA_abs (aiapy-degradation-corrected absolute threshold, value chosen by matching the median bright area of 2010–2011 to the primary — report the value).
- Evaluation on dev (identical machinery to earlier candidates: same folds, weights 1/n per HARP, training-fold StandardScaler, same logistic estimator, mean of 5 fold models, HARP bootstrap 10,000, seed 20260921):
  E1 Δ log-loss = LL(C) − LL(C + UVA), 95% CI; AUC C → C+UVA (weighted).
  E2 Matched retention: at dev OOF thresholds keeping 88% and 95% of weighted true episodes, weighted % false removed by C+UVA minus C, paired HARP bootstrap 2,000, seed 0.
  E3 Twins: UVA ratio true/false in magnetic twins (euv_f2_replication.twins, T_a and T_b), 2,000 resamples, seed 0, plus sign test.
  E4 Overlap: Spearman ρ of UVA with log10 CV_box, n_C, n_M, log(1+R), gate score.
- QUALIFICATION RULE (pre-stated, mechanical): UVA qualifies for a later held-out test only if E1 Δ > 0 AND E2 at 88% > 0 (point estimates). Otherwise reading = "NOT ELIGIBLE". Dev qualification is not confirmation.
- Held-out plan (NOT run now): if it qualifies, a separate pre-registration will be written before any 2021–2026 1600 Å data are downloaded. Disclose there that 2021–2026 labels and 94 Å results were already seen.

### Step 0c — required statements and clarifications (decided by: me; flagged for the user at CHECKPOINT 1; none uses data)
1. **n:** 541 episodes (`data/euv_extra/dev_rows.csv`: 541 rows, Stage 4 folds).
2. **Saturation:** raw DN > 12,000 → NaN, before exposure normalisation. This is the existing P4/U4 rule, which already names `aia.lev1_uv_24s`. The pilot per-frame maxima above show this cut is reached in 1600 Å only occasionally.
3. **Why the reference pixels are restricted (a necessary clarification):** the HMI SHARP magnetogram covers only the HARP patch, not the 50″ cutout margin, so |B_LOS| exists only for AIA pixels within the patch footprint. The reference set is therefore the patch pixels with |B_LOS| < 50 G, mapped into each frame by `euv_dctrl.hmi_to_frame`. Using the margin would need another data product (a full-disk magnetogram), i.e. a new download.
4. **Pixel grid (unspecified detail; my choice, flagged):** all pixel sets are on the alarm-time HMI grid, like CV_box and the adopted BF Option 1 (bb8a137). Each HMI patch pixel carries the AIA value at its mapped location.
   - Reference median: taken over HMI pixels with |B| < 50 G.
   - "Within the HARP bitmap": HMI pixels with bitmap ≥ 33 (the convention in `euv_dctrl.samples`).
   - Units: the bright count and the 500 reference-pixel minimum are both in HMI-grid pixels (≈ 0.504″, ≈ 1.4 per AIA pixel).
   - Alternative: count distinct AIA pixels instead. The user may choose this at CHECKPOINT 1.
5. **Fill:** the slot rule of `euv_full` (a valid frame within ±6 min of each 12-min slot).
   - For UVA, UVA_max, UVI and UVA_abs, fill counts only valid frames that are also not flare-excluded (like the 94 Å flare-excluded version). UVA_keep uses all valid frames.
   - Frames with fewer than 500 reference pixels are invalid.
   - **Risk (flagged, as the CV6 lesson, 313c1c0):** a flare-excluded fill rule can exclude flare-active episodes more often, which is a label-dependent exclusion. The Step 3 report will therefore give UVA-undefined counts by true/false. This cannot change the reading.
6. **UVI:** per frame, Σ over bright bitmap pixels of (I − threshold) in DN/s. UVI = log10(1 + median over frames). The "+1" handles frames with no bright pixel.
7. **UVA_abs:**
   - Intensities are corrected with `aiapy.calibrate.degradation(1600 Å, T_OBS)`, using the version-10 table from `get_correction_table("JSOC")` (a keyword query). Its hash is recorded, and its 1600 Å epochs must cover 2010-01-01 to 2019-12-31; otherwise STOP and report.
   - T_abs is found by bisection, label-blind: the median over the 2010–2011 dev episodes of the per-episode median bright count at T_abs must equal the same statistic for the primary definition.
8. **Models:**
   - The analysis set is the 541 episodes with UVA defined; C = A_COLS + logR (Step B).
   - C and C + UVA are both fitted on that set with `euv_heldout.fit_folds`, and their dev predictions are out-of-fold. "Mean of 5 fold models" applies only to new sets, of which there are none here.
9. **E2:** τ per model = `tau_keep` (0.88 and 0.95) on dev OOF. The kept masks are fixed, and the paired HARP bootstrap resamples rows (`phase_f` "op" statistic).
10. **E3:**
    - Pairs are built on the 541 set: T_a = `twins(c)`, T_b = `twins(c, by_group=True)`. Only pairs with both UVA defined are kept.
    - The ratio is taken on the untransformed 1 + median count, i.e. `ratio_jobs` mode "log" (10^(median UVA true − median UVA false)).
    - The CI comes from pairs resampled by true HARP (2,000, seed 0). The sign test is two-sided `binomtest` with ties excluded.
11. **Download:** the `euv_full` per-HARP export path, with the query changed to `aia.lev1_uv_24s[…@12m][1600]{image}` (as `euv_download.py`) and the same im_patch. There is one pending export at a time, from the user's account.

## 2026-09-30 — PROJECT REPORT GENERATED (decided by: user; written by Claude Code from committed files only)
- Report: `docs/report/Project_Report.pdf` (33 pages) with its source `docs/report/report_source.txt`, build script `docs/report/build_report.py`, checker `docs/report/verify_report.py` and log `docs/report/verify_report.log`; committed in 2b5aa9f.
- Cover: "Not a competition submission. Prepared with AI assistance from the project records."
- Every number is tagged with a file:line or git source and checked against the committed repository at d85e8dc; verify_report.py: 910 sourced values, 0 mismatches, 0 untagged numbers, RESULT: PASS.
- No new data, models, tests or downloads. No frozen file changed. Numbers that could not be traced to a committed file are left out and listed in the report's Appendix C.

## 2026-09-30 — NEW DEV CANDIDATE #26: MAGNETIC RESTLESSNESS (MR) — PRE-REGISTRATION (design decided by: user; literature notes and clarifications drafted by Claude AI, flagged for the user at CHECKPOINT 1; recorded BEFORE any MR value is computed and before any label is read for MR)
Status: EXPLORATORY (dev) candidate. Nothing has been computed for MR. No SHARP value, cohort label or model output was read to write this entry (only file headers, code and earlier decisions.md entries).

**Verbatim (user):**

PROJECT: <project folder> — solar-flare false-alarm project. NEW CANDIDATE #26: MAGNETIC RESTLESSNESS (MR).
Idea: the same detrended-variability measure as CV_box, applied to hourly SHARP magnetic parameters over the 24 h before each alarm.
Literature: Kniezewski et al. 2025, ApJ (arXiv:2506.14004): current, twist, shear and free energy become more variable 2–4 h before flare onset (NLFFF, 18 flares). Efremov, Parfinenko & Solov'ev 2017 (Geomagnetism and Aeronomy 57(8)): HMI magnetic data carry a 12-hour artifact from SDO's orbital velocity. Read both (abstracts at least) and quote the relevant sentences verbatim in the entry; do not paraphrase numbers.

HARD RULES
- decisions.md APPEND-ONLY; never modify frozen files (model_hashes.json list, thresholds.json, frozen/); never overwrite results; never delete data.
- NO JSOC exports or downloads. Use only the hourly SHARP files already on disk (data/raw_sharp_*.csv and raw_sharp_extra_*). A JSOC keyword query is allowed ONLY if I approve it at a checkpoint.
- Do not touch prospective data (t >= 2026-08-17) and do not run Look 1 / Look 2.
- Every number comes from a committed log; quote verbatim. Label dev results EXPLORATORY (dev).
- Record in the entry who decided each design choice: "decided by: user" for choices I confirm; "drafted by Claude AI" for text you draft.
- STOP at every CHECKPOINT and wait for my explicit "go".

STEP 0 — Pre-registration (no labels read, no feature computed)
Write this entry to decisions.md BEFORE computing anything:
 Episodes: the same dev episodes and fold assignment as the euv_extra dev set (541); also report MR for all 547 dev episodes.
 Data: hourly SHARP records of the episode's HARP with T_REC in (t − 24 h, t], QUALITY == 0 (report how many records QUALITY removes; it is known to remove the TAI 06:00/18:00 records). An episode is evaluable if >= 18 records remain (same as the trend rule T3). Report the undefined count.
 [DEFAULT — primary parameter set] P = {TOTUSJH, TOTPOT, TOTUSJZ} (current helicity, free-energy proxy, total current: the SHARP analogues of Kniezewski's current/twist/free energy).
 [DEFAULT — detrending] For each parameter, fit by least squares: a + b·t + c·sin(2πt/12h) + d·cos(2πt/12h) (removes the linear trend and the 12-h orbital artifact). CV_p = SD(residuals, ddof=1) / mean(series). Undefined if mean <= 0.
 PRIMARY feature MR = mean over p in P of log10(CV_p).
 Secondaries (reported, cannot rescue the primary): each log10 CV_p alone; MR_lin (linear detrend only, as CV_box); log10 CV of USFLUX, R_VALUE, MEANSHR; MR computed over (t − 12 h, t] if >= 9 records.
 [DEFAULT — flare handling] Primary keeps all hours (as CV_box primary). Secondary MR_nf drops hours inside flare intervals (euv_pilot.flare_excluded rules: C1+ from the region, M1+ anywhere).
 Evaluation on dev (identical machinery to earlier candidates: same folds, weights 1/n per HARP, training-fold StandardScaler, same LogisticRegression, mean of 5 fold models; HARP bootstrap 10,000, seed 20260921; twins resamples 2,000, seed 0):
  E1 Twins: MR ratio true/false on magnetic twins (euv_f2_replication.twins, T_a and T_b), sign test. Ratio = median(10^MR true) / median(10^MR false).
  E2 Δ log-loss = LL(C) − LL(C + MR), 95% CI; AUC C → C+MR (weighted).
  E3 Matched retention: at dev OOF thresholds keeping 88% and 95% of weighted true episodes, weighted % false removed by C+MR minus C, paired HARP bootstrap 2,000, seed 0.
  E4 Overlap: Spearman ρ of MR with log10 CV_box, n_C, n_M, log(1+R), gate score; and the E1 twins ratio of CV_box within MR tertiles (does coronal restlessness survive holding magnetic restlessness roughly fixed?).
  E5 Label-dependence check: undefined MR counts by true/false.
 QUALIFICATION RULE (pre-stated, mechanical): MR qualifies for the held-out test only if E1 T_a ratio > 1 AND E2 Δ > 0 (point estimates). Otherwise reading "NOT ELIGIBLE". Dev qualification is not confirmation. Whatever the outcome, E4 is reported.
 HELD-OUT PLAN (recorded now, run later only on my "go"): if MR qualifies, compute MR once on the 2021/23/24 test set and the 2025–26 set (labels of both were seen earlier; MR values never computed — disclose this), E1 and E2 only, same code, frozen dev models for C+MR (fit on dev now, hash them).
 PROSPECTIVE AMENDMENT (record now, before any prospective data are downloaded): add MR (primary definition above) as a SECONDARY measure of the already-registered prospective test (2f62f88 / eb3e7d5) and of Look 2: magnetic-twins ratio with 95% CI (same twins code and resampling as the CV_box primary). It cannot change any registered primary reading.
CHECKPOINT 1: show me the entry and commit hash. Wait for "go".

STEP 1 — Label-blind compute (dev)
New script mag_restless.py. Compute MR and all secondaries for all dev episodes WITHOUT reading true_alarm. Report: records per episode (median, min), undefined counts and reasons, percentiles of MR, MR by year (drift check), fitted 12-h amplitude median (as % of mean) per parameter, and 3 example plots (series + fit) in figures/mag_restless/.
CHECKPOINT 2: wait for "go" before reading labels.

STEP 2 — Dev evaluation (run once)
Run E1–E5 exactly as pre-registered. Write mag_restless_eval.log; append results verbatim + mechanical reading to decisions.md; if MR qualifies, fit and hash the C+MR fold models and freeze their τ (dev OOF, 88% rule) BEFORE any held-out computation. Commit.
CHECKPOINT 3: report results, hashes, reading. STOP.

**Who decided:** the design above (episodes, data rule, parameter set P, detrending, MR definition, secondaries, flare handling, E1–E5, the qualification rule, the held-out plan and the prospective amendment) is **decided by: user**; the three [DEFAULT] items are the user's stated defaults. Steps 0a and 0b below are **drafted by Claude AI**. Every item in 0b awaits the user's confirmation at CHECKPOINT 1; the items marked OPEN need a user choice.

### Step 0a — literature check (read 2026-09-30; drafted by Claude AI; quotes verbatim, kept short; numbers as printed)
**Kniezewski, Mason, Emmons, Fitch & Garland, arXiv:2506.14004** (arXiv abstract page; v1 submitted 16 Jun 2025, the only version listed). The arXiv Comments field reads "Accepted for publication to the Astrophysical Journal"; the published ApJ version was not checked (as in the entry of 2026-09-23, which checked only the arXiv HTML page).
- Design (abstract): NLFFF extrapolation "for 6 hours before and 1 hour after 18 on-disk solar flares", plus flare-quiet windows for each active region.
- Finding (abstract): "a significant increase in variation starting 2-4 hours before flare onset" "for the current, twist, shear, and free energy".
- Caveat (abstract): "For this small pool of clean events".
- Already recorded (2026-09-23 flare-handling table): flares removed if a ≥ C5.0 flare occurred in the same AR within 6 h; 18 flares (6 C/6 M/6 X).
- Relevance (inference, drafted by Claude AI): (i) their signal starts 2-4 h before onset, while the MR window ends at the alarm time t, and the median lead time of true episodes on the test years was 12.4 h (entry 2026-09-23, risk b), so most of that rise would fall after the window; (ii) their quantities are NLFFF volume quantities, while TOTUSJH, TOTPOT and TOTUSJZ are photospheric SHARP summaries, so P is an analogue, not the same measurement.

**Efremov, Parfinenko & Solov'ev, "Analysis of a 12-Hour Artifact in LF Oscillations of the Magnetic Field of Sunspots According to SDO/HMI Data"**, Geomagnetism and Aeronomy 57, issue 8 (Crossref), pp. 1045–1055 (Springer page: volume 57, 2017; published online 03 March 2018). Only the abstract was read; the full text is paywalled.
- Cause (abstract): the 12-h artifact is "caused by the nonzero radial velocity of the station relative to the Sun".
- Mode (abstract): "only a 12-h mode is physically justified"; "the 24-h harmonic appears only as an artifact" of the Fourier decomposition of the amplitude-modulated signal.
- Dependence (abstract): HMI field values are "sensitive only to the station's radial velocity absolute values".
- Filtering (abstract): "the 12-h artifact mode can be completely filtered from the time series" at any orbital point.
- Scope note (drafted by Claude AI): the paper studies long-period oscillations of sunspot field strength, not SHARP integrated parameters. Whether the artifact is visible in P, USFLUX, R_VALUE and MEANSHR is checked label-blind in Step 1 (median fitted 12-h amplitude as % of mean). The user's wording "from SDO's orbital velocity" and the abstract's "radial velocity of the station relative to the Sun" describe the same cause.

### Step 0b — required statements and clarifications (drafted by Claude AI; none uses data; each awaits the user at CHECKPOINT 1)
1. **Episodes and n.** All dev episodes = `data/stage4/oof_cohort_dev.csv` via `phase_f.load_base()` (547). The analysis set = `data/euv_extra/dev_rows.csv` (columns eid, harpnum, t, fold, weight; 541 rows; Stage 4 folds) restricted to episodes with MR defined; its n is reported. E1–E5 use the analysis set; MR, its secondaries and the undefined counts are reported for all 547.
2. **SHARP files.** Only the monthly chunk files named by `chunks.files("raw_sharp")` and the matching `raw_sharp_extra` chunks, 2010-05 to 2019-12. TOTUSJH, TOTPOT, USFLUX, R_VALUE, MEANSHR, QUALITY and LON_FWT come from `raw_sharp_*`; TOTUSJZ exists only in `raw_sharp_extra_*`. Rows are joined on (HARPNUM, T_REC). The ad-hoc files `raw_sharp_20100501_20100801.csv` and `raw_sharp_20100501_20250101.csv` are not read (the chunks.py rule against double counting). Duplicate (HARPNUM, T_REC) rows are dropped and counted. No file after 2019 is read in Steps 1–2.
3. **Time and window.** T_REC (TAI) is converted to UTC with astropy exactly as `build_dataset.py`. The window is (t − 24 h, t] on the UTC times, as the T3/T4 trend window in `cohort.py`; t = the episode's t in the cohort. The fit's time axis is hours relative to t.
4. **OPEN — longitude cut.** The T3 trend window used the labelled file, which also applies |LON_FWT| ≤ 45° (`build_dataset.py`). The user's rule names only QUALITY == 0. **Default = the user's text (QUALITY == 0 only, no longitude cut).** Step 1 reports how many window records have |LON_FWT| > 45°. Alternative: also require |LON_FWT| ≤ 45°, matching T3 exactly.
5. **Evaluable records.** For MR, MR_lin, MR_12h and MR_nf a record counts only if QUALITY == 0 and all three P parameters are finite. For a single-parameter secondary, that parameter must be finite. Minimum 18 records for (t − 24 h, t] and 9 for (t − 12 h, t]. Step 1 reports the QUALITY-removed count and the undefined count by reason.
6. **Fit.** Ordinary least squares (`numpy.linalg.lstsq`) on the columns [1, t, sin(2πt/12), cos(2πt/12)], t in hours. mean(series) = the mean of the same records' raw values. CV_p is undefined if mean ≤ 0 or the residual SD is 0 (log10 undefined); MR is undefined if any of its three CV_p is undefined.
   - Stated limitation: the free sine/cosine phase removes any 12-h component, including real solar variability at that period.
   - Inference (drafted by Claude AI; no change planned): if the artifact follows the absolute radial velocity, it is not a pure sinusoid, and shorter-period harmonics would remain in the residuals. Step 1's example plots will show residuals.
7. **MR_lin:** the same P and records with a linear fit only (a + b·t), as `euv_pilot.detrended_sd` for CV_box.
8. **MR_12h:** (t − 12 h, t], ≥ 9 records, the same four-term fit. Note: four fitted terms on 9–12 points leave few residual degrees of freedom.
9. **USFLUX, R_VALUE, MEANSHR:** the same four-term fit. R_VALUE is already a logarithmic quantity and is 0 when no strong-gradient PIL is present; a window with mean ≤ 0 gives an undefined value, which is counted.
10. **MR_nf:** records whose UTC time lies inside a flare interval are removed with `euv_pilot.flare_excluded(record times, swpc.load(t − 2 d, t) events, the episode's noaa_ars)`, exactly as `euv_full.py`; ≥ 18 records must remain. Risk (the CV6 lesson, 313c1c0): this exclusion can depend on the label, so E5 also reports MR_nf undefined counts by true/false.
11. **E1.** Pairs are built on the 541 set: T_a = `twins(c)`, T_b = `twins(c, by_group=True)`; only pairs with both MR defined are kept. The ratio follows the user's definition, median(10^MR true) / median(10^MR false), i.e. `ratio_jobs` mode "ratio" on 10^MR. This can differ slightly from 10^(median difference) when the number of pairs is even. The CI resamples pairs by true HARP (2,000, seed 0). The sign test is two-sided `binomtest` (true MR > false MR), ties excluded.
12. **E2.** C = A_COLS + logR (Step B). C and C + MR are both fitted on the analysis set with `euv_heldout.fit_folds` (Stage 4 folds; weights 1/n per HARP recomputed on the analysis set by `phase_f.prep`); dev predictions are out-of-fold. "Mean of 5 fold models" applies only to new sets. Δ CI: HARP bootstrap 10,000, seed 20260921. AUC weighted.
13. **E3.** τ per model = `tau_keep` (0.88 and 0.95) on dev OOF; the kept masks are fixed, and the paired HARP bootstrap resamples rows (`phase_f` "op" statistic, 2,000, seed 0).
14. **E4.** Spearman ρ on the analysis set (pooled, unweighted) of MR with log10 CV_box, n_C, n_M, logR and gate score. CV_box within MR tertiles: the cut points are the 1/3 and 2/3 quantiles of MR over the analysis set (label-blind; computed in Step 1). Twins are rebuilt inside each tertile with `twins(c_k)` (T_a matching), so both members share a tertile; CV_box ratio = `ratio_jobs` mode "ratio", pairs resampled by true HARP, 2,000, seed 0; pairs per tertile reported. Descriptive, no reading. Alternative: split the E1 T_a pairs by the true member's tertile.
15. **E5** (Step 2 only): undefined counts of MR, each secondary, MR_12h and MR_nf, by true/false, on the 547 and 541 sets.
16. **Label-blindness in Step 1.** `mag_restless.py` reads only eid, harpnum, t, noaa_ars and fold from the cohort files; true_alarm, delayed and flare-label columns are not loaded. Outputs: `data/mag_restless/dev_mr.csv` (no labels), `figures/mag_restless/*.png`. The three example episodes are chosen label-blind: those at the 10th, 50th and 90th percentiles of MR.
17. **If MR qualifies (Step 2):** the C + MR fold models are fitted with `fit_folds` on the dev analysis set and saved with sha256 hashes, and τ (tau_keep 0.88, dev OOF) is frozen, before any held-out computation.
    - **OPEN — held-out sets.** Proposed: 2021/2023/2024 = `data/stage5/cohort_test_primary.csv` (the single-region T2 cohort of the gate test); 2025–26 = `conf_cohort("le2")` (the TEST 1 cohort before the EUV fill rule). MR needs no EUV data, so no fill rule applies. Held-out prediction = the mean of the 5 frozen fold models.
    - **Disclosure (to be repeated at run time):** the labels of both sets were seen earlier, and their SHARP series were already used (gate scores; model B's USFLUX and TOTUSJH trends on 2021/2023/2024, f84a613). MR values have never been computed on them.
    - **OPEN — held-out readings.** The user's plan names E1 and E2 but no reading wording. Proposed (drafted by Claude AI), to be fixed by the user before any held-out run: E1 T_a "REPLICATED" if ratio > 1 AND CI lower > 1; "DIRECTION CONSISTENT, NOT CONFIRMED" if ratio > 1 AND CI lower ≤ 1; "NOT REPLICATED" otherwise. E2 "C + MR BEATS C" if Δ > 0 AND CI lower > 0; "DIRECTION CONSISTENT, NOT CONFIRMED" if Δ > 0 AND CI lower ≤ 0; "NO IMPROVEMENT" otherwise.
18. **Prospective amendment (recorded now; decided by: user).** MR (the primary definition, with the longitude rule chosen at CHECKPOINT 1) is added as a SECONDARY measure of the prospective test (2f62f88 / eb3e7d5) and of Look 2 (8aa1797): magnetic-twins ratio median(10^MR true) / median(10^MR false) with a 95% CI, using the TEST 1 twins code on the registered prospective cohort, pairs resampled by true HARP (2,000, seed 0); undefined counts by true/false reported. It cannot change any registered primary reading. No reading wording was given; default = reported only, no reading.
    - Practical note: TOTUSJZ is not in the default SHARP keyword list (it is in the `raw_sharp_extra` files), so the prospective SHARP query must include it. That query belongs to the prospective run itself; nothing is downloaded now.
19. **Step 1 report contents** (as the user listed): records per episode (median, min); QUALITY-removed count; |LON_FWT| > 45° count (clarification 4); duplicate count; undefined counts by reason; MR percentiles; MR by year; median fitted 12-h amplitude, √(c² + d²) / mean × 100, per parameter; three example plots.

## 2026-09-30 — CANDIDATE #26 (MR): CHECKPOINT 1 DECISIONS — AMENDMENT BEFORE STEP 1 (decided by: user; recorded verbatim before any MR value is computed)
**Verbatim (user):**

Decisions (decided by: user):
1. Add the longitude cut |LON_FWT| <= 45° on window records, matching T3. Report how many records/episodes it removes.
2. E1 ratio: use exactly the same ratio/bootstrap function as the CV_box twins test (phase_f.ratio_jobs / boot_many), applied to 10^MR.
3. E4: keep the default (twins rebuilt within MR tertiles); descriptive only.
4. Held-out sets approved as proposed. Readings: twins — "REPLICATED" if ratio > 1 AND CI lower > 1; "DIRECTION CONSISTENT, NOT CONFIRMED" if ratio > 1 AND CI lower <= 1; "NOT REPLICATED" otherwise. Δ log-loss — "MR ADDS" if Δ > 0 AND CI excludes 0; "NO DETECTABLE ADDITION" otherwise. State in the entry that labels of both held-out sets were seen earlier; MR values never computed.
5. Prospective secondary approved, reported-only, no reading; the future SHARP query must include TOTUSJZ, QUALITY and LON_FWT.
I have read the 19 clarifications and accept them as written [or list changes].
Record these as an amendment before Step 1, commit, then go to Step 1 (label-blind) and STOP at CHECKPOINT 2.

**Effect on the pre-registration (46207c7; drafted by Claude AI):**
- Clarification 4 is replaced: a window record counts only if QUALITY == 0 AND |LON_FWT| ≤ 45°, for MR and every secondary. Step 1 reports the records removed by each rule and the episodes whose evaluability changes because of the longitude cut.
- Clarification 11: the E1 ratio and CI are computed with `phase_f.ratio_jobs` (mode "ratio") and `boot_many` on the column 10^MR, as in the CV_box twins test.
- Clarification 14 (E4 within-tertile twins) is kept as the default; descriptive, no reading.
- Clarification 17: the held-out sets are those proposed (2021/2023/2024 = `data/stage5/cohort_test_primary.csv`; 2025–26 = `conf_cohort("le2")`), and the held-out readings are the user's wording above (they replace the proposal in 46207c7). **Disclosure:** the labels of both held-out sets were seen earlier; MR values have never been computed on them.
- Clarification 18: prospective MR secondary approved as reported-only, no reading; the future prospective SHARP query must include TOTUSJZ, QUALITY and LON_FWT.
- All other clarifications (1–3, 5–10, 12, 13, 15, 16, 19) are accepted as written. The bracketed "[or list changes]" in the user's text is template wording; no changes were listed.

## 2026-09-30 — CANDIDATE #26 (MR): STEP 1 RESULTS, LABEL-BLIND (EXPLORATORY (dev); numbers verbatim from `mag_restless_step1.log`; no label read)
`mag_restless.py step1` → `mag_restless_step1.log`, `data/mag_restless/dev_mr.csv` (no labels), `data/mag_restless/tertiles.json`, `figures/mag_restless/mr_examples_p10_p50_p90.png`. `mag_restless.py selftest` passed (synthetic 12-h amplitude recovered; the undefined rules fire).
- **Label-blindness:** "label columns loaded: none (cohort usecols = harpnum, t, noaa_ars, fold)".
- **Input:** 116 raw and 116 extra dev chunk files; 77 duplicate (HARPNUM, T_REC) rows in each, all identical, dropped; "raw_without_extra: 0"; "after de-duplication: 53591 records for 180 HARPs".
- **Window records:** "records in windows: 12831; removed by QUALITY != 0: 1251 (of which at TAI 06:00/18:00: 1049); removed by |LON_FWT| > 45 (after QUALITY): 166".
- **Longitude cut (amendment b2ca7ac, item 1):** "episodes with >= 1 record removed by the longitude cut: 51"; "made undefined by the cut: 0"; "MR value changed by the cut (defined both ways): 51".
- **Records per episode (MR):** "547: median 22.0, min 18, max 24; 12-h window median 11.0, min 7".
- **Undefined (547):** MR 0; MR_lin 0; MR_12h 44 ("< 9 records"); MR_nf 55 ("< 18 records"); R_VALUE 3 ("mean <= 0"); every other secondary 0. On the 541 set: MR_12h 43, MR_nf 54, R_VALUE 3. MR_nf removed 359 flare-affected records in 198 episodes.
- **MR percentiles (547):** "p0 -2.0390, … p10 -1.7454, p25 -1.6152, p50 -1.4635, p75 -1.3015, p90 -1.0292, … p100 0.1645".
- **MR by year (547):** yearly medians range from -1.5726 (2010) to -1.2450 (2016, 10 episodes); the table is in the log.
- **Median fitted 12-h amplitude (% of mean):** TOTUSJH 2.7080%, TOTPOT 1.6911%, TOTUSJZ 2.6751%, USFLUX 1.6987%, R_VALUE 1.3602%, MEANSHR 0.8080%.
- **E4 tertile cut points (541 set, MR defined, n 541):** "1/3 -1.562797, 2/3 -1.372930".
- **Examples (label-blind, MR percentiles):** p10 2372_20130113T0959, p50 750_20110804T1259, p90 3843_20140318T1059.
- **Implementation detail (drafted by Claude AI):** "residual SD = 0" is tested as SD ≤ 1e-12 × mean, because an exact least-squares fit leaves floating-point residuals near 1e-15, not exactly 0. It changed no episode (no "residual SD = 0" case occurred).
STOP at CHECKPOINT 2; no label has been read for MR.

## 2026-09-30 — CANDIDATE #26 (MR): AMENDMENT A1–A2 BEFORE STEP 2 (decided by: user; recorded verbatim before any label is read for MR; decided after seeing label-blind Step 1 output only, 53146c2)
**Verbatim (user):**

Decisions (decided by: user), recorded as an amendment BEFORE any label is read:
A1 Add one secondary feature MR_quad: identical to MR but the least-squares fit is a + b·t + c·t² + d·sin(2πt/12h) + e·cos(2πt/12h). Reported like the other secondaries (E1 twins and E2 Δ log-loss); cannot change the primary reading. Reason (recorded): Step 1 example plots show slow curvature that the linear+12h fit leaves in the residuals; MR_quad tests whether MR reflects slow evolution rather than short-timescale variability. This was decided after seeing label-blind Step 1 output only.
A2 Primary MR definition and qualification rule unchanged.
Compute MR_quad label-blind (report distribution and undefined counts), commit, then run Step 2 once exactly as pre-registered and STOP at CHECKPOINT 3.

**Implementation (drafted by Claude AI):** MR_quad uses exactly MR's records (QUALITY == 0, |LON_FWT| ≤ 45°, all of P finite, ≥ 18) and time axis (hours relative to t); only the design matrix gains the column t². The same undefined rules apply (mean ≤ 0; residual SD = 0 as tested in Step 1). It is computed by a separate label-blind mode, `mag_restless.py quad`, which writes `data/mag_restless/dev_mr_quad.csv` and `mag_restless_quad.log`; the Step 1 outputs are not overwritten.

## 2026-09-30 — CANDIDATE #26 (MR): MR_quad COMPUTED, LABEL-BLIND (EXPLORATORY (dev); numbers verbatim from `mag_restless_quad.log`; no label read)
`mag_restless.py quad` → `mag_restless_quad.log`, `data/mag_restless/dev_mr_quad.csv`. Selftest extended (an exact quadratic + 12-h sinusoid is removed by the quad fit) and passed.
- "Step 1 reproduced: all 42 columns of data/mag_restless/dev_mr.csv identical for 547 episodes".
- 547: "defined 547, undefined 0"; 541: "defined 541, undefined 0".
- 547 percentiles: "p10 -1.8548, p25 -1.7327, p50 -1.6093, p75 -1.4547, p90 -1.2454" (p0 -2.1047, p100 0.1377).
- "MR_quad − MR: median -0.1138, p10 -0.3372, p90 -0.0162; Spearman rho(MR, MR_quad) 0.8632 (n 547)".
Next: Step 2, run once.

## 2026-09-30 — CANDIDATE #26 (MR): STEP 2 RESULTS, DEV EVALUATION RUN ONCE (EXPLORATORY (dev); numbers verbatim from `mag_restless_eval.log`)
`mag_restless.py step2` → `mag_restless_eval.log`, `data/mag_restless/eval_E1.csv`, `eval_E2.csv`, `eval_E4.csv`. Nothing claimed as confirmed; dev only.
- **Disclosure (drafted by Claude AI):** before this single run, the code path was crash-tested once on a scratch copy of the script with the labels randomly permuted (seed 99), with the reproduction assert, the file outputs and the freeze step disabled. That output carried no label information, was not used, and the scratch copy was deleted. The real run above is the only evaluation with the true labels.
- **Checks:** "analysis set = data/euv_extra/dev_rows.csv (541, same order, same weights); MR defined for all 541; model C OOF reproduces the frozen euv_extra C exactly (LL 0.3222578513, tau 0.0625698316)"; "analysis set: 541 episodes (true 96, false 445), 179 HARPs"; "T_a pairs 81, T_b pairs 78 (of 96 true episodes)".

**E1 twins (ratio = median(10^x true) / median(10^x false); CI pairs by true HARP, 2,000, seed 0; sign test two-sided):**

| feature | twins | pairs | ratio [95% CI] | true higher / false higher | sign p |
|---|---|---:|---|---|---:|
| **MR** | **T_a** | **81** | **1.0814 [0.9193, 1.3109]** | 42 / 39 | 0.8243 |
| MR | T_b | 78 | 0.9531 [0.7882, 1.1538] | 35 / 43 | 0.4282 |
| lcv_TOTUSJH | T_a | 81 | 0.9664 [0.8367, 1.1360] | 41 / 40 | 1.0000 |
| lcv_TOTPOT | T_a | 81 | 1.0464 [0.7785, 1.4595] | 45 / 36 | 0.3742 |
| lcv_TOTUSJZ | T_a | 81 | 0.9856 [0.7757, 1.1250] | 37 / 44 | 0.5052 |
| MR_lin | T_a | 81 | 1.0998 [0.8840, 1.3065] | 42 / 39 | 0.8243 |
| lcv_USFLUX | T_a | 81 | 1.0373 [0.6940, 1.4907] | 38 / 43 | 0.6570 |
| lcv_R_VALUE | T_a | 81 | 0.7104 [0.5359, 0.9884] | 31 / 50 | 0.0448 |
| lcv_MEANSHR | T_a | 81 | 0.8546 [0.7235, 1.1098] | 37 / 44 | 0.5052 |
| MR_12h | T_a | 63 | 0.9581 [0.7934, 1.2078] | 30 / 33 | 0.8013 |
| MR_nf | T_a | 58 | 1.1618 [0.8880, 1.3937] | 32 / 26 | 0.5118 |
| MR_quad | T_a | 81 | 0.9882 [0.8420, 1.1470] | 39 / 42 | 0.8243 |

T_b rows for the secondaries and the all-episode ratios are in the log (MR all-episode ratio 0.8409 [0.6787, 1.0331]).

**E2 Δ log-loss = LL(C) − LL(C + x) (HARP bootstrap 10,000, seed 20260921; AUC weighted):**

| feature | n | Δ [95% CI] | AUC C → C + x |
|---|---:|---|---|
| **MR** | **541** | **−0.0113 [−0.0299, 0.0026]** | 0.7720 → 0.7333 |
| lcv_TOTUSJH | 541 | −0.0108 [−0.0266, 0.0011] | 0.7720 → 0.7293 |
| lcv_TOTPOT | 541 | −0.0081 [−0.0207, 0.0014] | 0.7720 → 0.7303 |
| lcv_TOTUSJZ | 541 | −0.0085 [−0.0262, 0.0045] | 0.7720 → 0.7405 |
| MR_lin | 541 | −0.0136 [−0.0355, 0.0024] | 0.7720 → 0.7302 |
| lcv_USFLUX | 541 | −0.0100 [−0.0264, 0.0021] | 0.7720 → 0.7227 |
| lcv_R_VALUE | 538 | −0.0079 [−0.0318, 0.0099] | 0.7702 → 0.7466 |
| lcv_MEANSHR | 541 | −0.0099 [−0.0309, 0.0057] | 0.7720 → 0.7368 |
| MR_12h | 498 | −0.0077 [−0.0236, 0.0044] | 0.7441 → 0.7174 |
| MR_nf | 487 | −0.0094 [−0.0235, 0.0006] | 0.7586 → 0.7124 |
| MR_quad | 541 | −0.0093 [−0.0284, 0.0052] | 0.7720 → 0.7386 |

**E3 matched retention (primary MR; paired HARP bootstrap 2,000, seed 0):**
- target 0.88: C "true kept 88/96 (0.8807 w), false removed 154/445 (0.3579 w)"; C+MR "true kept 89/96 (0.8843 w), false removed 93/445 (0.2470 w)"; "false removed (C+MR − C): -11.09 points [-16.78, -5.33]".
- target 0.95: C "true kept 92/96 (0.9792 w), false removed 54/445 (0.1436 w)"; C+MR "true kept 95/96 (0.9563 w), false removed 13/445 (0.0370 w)"; "false removed (C+MR − C): -10.66 points [-16.85, -4.67]".

**E4 overlap (pooled, unweighted Spearman, n 541):** "rho(MR, log10_CV_box) = -0.0460 (p 2.86e-01)"; "rho(MR, n_C) = -0.2271"; "rho(MR, n_M) = -0.3180"; "rho(MR, logR) = 0.1528"; "rho(MR, score) = -0.4074".
CV_box twins within MR tertiles (DESCRIPTIVE, no reading): all 541 (reference) 81 pairs, 1.9661 [1.4737, 3.1731] (the same value as recorded for CV_box in 208202b); tertile 1: 33 pairs, 2.3773 [1.3318, 3.2504]; tertile 2: 29 pairs, 2.2559 [1.6493, 4.7354]; tertile 3: 16 pairs, 1.8594 [0.4002, 2.9664].

**E5 undefined counts by label (true / false):** 547 (true 98, false 449): MR 0/0; MR_12h 19/25; MR_nf 20/35; lcv_R_VALUE 0/3; all others 0/0. 541 (true 96, false 445): MR_12h 19/24; MR_nf 20/34; lcv_R_VALUE 0/3; all others 0/0. The MR_12h and MR_nf exclusions are label-dependent (more often undefined for true alarms), so those two secondaries are on selected subsets.

**PRE-STATED READING (mechanical):** "E1 T_a ratio 1.0814 > 1 is True; E2 Δ -0.0113 > 0 is False -> "NOT ELIGIBLE"".
- MR does not qualify for the held-out test; no C+MR models or τ were frozen, and the held-out plan (b2ca7ac) is not run. The prospective MR secondary (reported only, no reading) stays registered as decided in b2ca7ac.
STOP at CHECKPOINT 3.

## 2026-09-30 — NEW DEV CANDIDATE #27: MINIROCKET ON THE 94 Å LIGHT CURVE (MRKT) — PRE-REGISTRATION (design decided by: user; literature, environment and clarifications drafted by Claude AI, flagged for the user at CHECKPOINT 1; recorded BEFORE any curve is built or any label is read for MRKT)
Status: EXPLORATORY (dev) candidate. Nothing has been computed for MRKT. Only code, file headers, the file count of the series folders and earlier decisions.md entries were read. One Python package set was installed (0b); no model was fitted.

**Verbatim (user):**

PROJECT: <project folder> — solar-flare false-alarm project. NEW CANDIDATE #27: MINIROCKET ON THE 94 Å LIGHT CURVE (MRKT).
Question: does the full 24-h 94 Å box-brightness curve carry information beyond the single CV_box number, the gate score and flare history?

HARD RULES
- decisions.md APPEND-ONLY; never modify frozen files (model_hashes.json list, thresholds.json, frozen/); never overwrite results; never delete data.
- No JSOC calls, no image reprocessing: use the stored per-episode series files only (the ones CV_box was computed from).
- DEV 2010–2019 ONLY until I say otherwise; do not touch prospective data (t >= 2026-08-17); do not run Look 1/Look 2.
- Installing a Python package (sktime or aeon, for MiniRocket) is allowed: pin and record the exact version.
- Crash tests must use SYNTHETIC random labels (numpy random 0/1 with the same prevalence), never real labels shuffled. Real labels are read exactly once, in Step 2.
- Record who decided each choice ("decided by: user" / "drafted by Claude AI"). Label everything EXPLORATORY (dev). Quote numbers verbatim from committed logs.
- STOP at every CHECKPOINT and wait for my "go".

STEP 0 — Pre-registration (nothing computed, no labels read)
Write this entry to decisions.md and commit:
 Literature: cite Dempster, Schmidt & Webb 2021 (MiniRocket, KDD) — read the abstract and quote the defining sentence; state the library and version you will use.
 Episodes: the 541 dev episodes and 5 folds of dev_rows.csv (same weights 1/n per HARP).
 [DEFAULT] Curve: the stored primary-version box-mean 94 Å series (flare frames kept, same valid-frame rules as CV_box), placed on the 120-slot 12-min grid over (t−24h, t] (nearest valid frame within 6 min, as the fill rule); missing slots linearly interpolated (edges: nearest value); then divided by the series mean and 1 subtracted (relative brightness, like CV). Report the median number of interpolated slots.
 [DEFAULT] Features: MiniRocket, default settings (num_kernels = 10,000), random_state = 20260921, fitted on the training fold only.
 [DEFAULT] Curve model: StandardScaler + LogisticRegression (L2, lbfgs, max_iter 10000, sample_weight = episode weights); C chosen from {1e-4, 1e-3, 1e-2, 1e-1} by INNER grouped 3-fold CV (grouped by HARP) on weighted log-loss, inside each outer training fold only.
 Primary comparison (stacking, no leakage): for each outer fold k —
   (a) inside the outer training set, compute inner out-of-fold curve scores (grouped inner 5-fold, same procedure as above);
   (b) fit Model C_CV + logit(curve score) (same estimator/settings as C_CV) on the outer training set using those inner OOF scores;
   (c) fit the curve model on the full outer training set, score the outer test fold, and predict with (b).
   Baseline = C_CV with the same outer folds (must reproduce its committed dev OOF log-loss; stop if not).
 E1 PRIMARY Δ = LL(C_CV) − LL(C_CV + curve), 95% CI (HARP bootstrap 10,000, seed 20260921); weighted AUC before → after.
 E2 Matched retention at dev OOF thresholds keeping 88% and 95% of weighted true episodes: weighted % false removed (C_CV + curve minus C_CV), paired HARP bootstrap 2,000, seed 0.
 E3 Descriptive: curve-score-only OOF AUC vs CV_box-only OOF AUC; curve-score twins ratio (euv_f2_replication.twins T_a, T_b); Spearman ρ of curve score with log10 CV_box, n_C, log(1+R), gate score.
 E4 Stability: repeat E1 with MiniRocket random_state in {1,2,3,4,5}; report all five Δ (primary stays seed 20260921).
 QUALIFICATION RULE (pre-stated, mechanical): qualifies for a held-out test only if E1 Δ > 0 AND E2 (88%) > 0 (point estimates); otherwise "NOT ELIGIBLE". Dev qualification is not confirmation.
 HELD-OUT PLAN (recorded now, run later only on my "go"): if it qualifies, freeze the full-dev-trained curve model + C_CV+curve model + τ (88% rule) with hashes BEFORE computing anything held-out; then run E1/E2 once on 2021/23/24 test and 2025–26 (labels seen earlier; curve scores never computed — disclose).
 PROSPECTIVE AMENDMENT (record now, before any prospective data are downloaded): if MRKT qualifies AND passes held-out, the frozen curve score is added as a reported-only secondary of the prospective test; otherwise not.
CHECKPOINT 1: show me the entry + commit hash.

STEP 1 — Label-blind build
Build all 541 curves; report interpolated-slot counts, any undefined episodes and why, and plot 6 example curves (random, fixed seed) to figures/minirocket/. Crash-test the full pipeline on SYNTHETIC random labels (no files saved, no models frozen; record that it was done). Commit.
CHECKPOINT 2: wait for "go" before reading real labels.

STEP 2 — Dev evaluation (run once)
Run E1–E4 exactly as registered; write minirocket_eval.log; append verbatim results + mechanical reading to decisions.md; if qualified, freeze and hash models BEFORE any held-out step. Commit.
CHECKPOINT 3: report and STOP.

**Who decided:** the design above (question, episodes, the three [DEFAULT] items, the stacking comparison and baseline, E1–E4, the qualification rule, the held-out plan and the prospective amendment) is **decided by: user**. Steps 0a–0c below are **drafted by Claude AI**; every item in 0c awaits the user's confirmation at CHECKPOINT 1, and items marked OPEN need a user choice.

### Step 0a — literature (read 2026-09-30; drafted by Claude AI; quotes verbatim and kept short)
**Dempster, Schmidt & Webb, "MINIROCKET: A Very Fast (Almost) Deterministic Transform for Time Series Classification"**, KDD 2021, doi:10.1145/3447548.3467231; arXiv:2012.08791 (v1 16 Dec 2020; v2 14 Jul 2021, "Updated to accepted version"). Only the arXiv abstract was read.
- Defining sentence (abstract; quoted in part): "We reformulate ROCKET into a new method, MINIROCKET", "making it up to 75 times faster on larger datasets", "almost deterministic", "while maintaining essentially the same accuracy".
- What ROCKET does (abstract): "transforming input time series using random convolutional kernels", then using the transformed features "to train a linear classifier".
- Relevance (drafted by Claude AI): the paper evaluates classification accuracy on the UCR archive; this project uses the MiniRocket features inside a weighted logistic model and scores log-loss, so the paper's accuracy claims do not transfer directly.

### Step 0b — library and environment (drafted by Claude AI; done 2026-09-30, before anything is computed)
- **Library: sktime 1.2.0**, class `sktime.transformations.panel.rocket.MiniRocket` (univariate). Signature as installed: `num_kernels=10000, max_dilations_per_kernel=32, n_jobs=1, random_state=None`. Its numba back end: **numba 0.67.0**, **llvmlite 0.49.0**; plus **scikit-base 1.1.1**.
- Installed into `.venv` with `pip install sktime==1.2.0 numba==0.67.0 llvmlite==0.49.0 scikit-base==1.1.1`. A `pip freeze` diff before/after shows only these four additions; numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1 and pandas 3.0.6 are unchanged.
- **aeon was not used:** a pip dry run showed that aeon 1.6.0 would downgrade numpy (2.5.3 → 2.3.5) and scipy (1.18.1 → 1.17.1), which could break the exact reproduction checks of frozen models.

### Step 0c — required statements and clarifications (drafted by Claude AI; none uses data; each awaits the user at CHECKPOINT 1)
1. **Episodes, folds, weights.** `data/euv_extra/dev_rows.csv` (541 rows): its fold column (Stage 4 folds, grouped by HARP) is the outer split, and its weight column (1/n per HARP over the 541) is used unchanged everywhere, in fitting (sample_weight) and in every weighted log-loss, including inner CV subsets.
2. **Series files.** `data/euv_full/series/<eid>.csv` (546 files for the 547 dev episodes), written by `euv_full.py`. Valid frames = the stored `valid_primary` column (QUALITY == 0, exposure ≥ 0.5 × median, box defined; flare frames kept), the frames CV_box used. Value = the stored `box` column.
3. **Grid.** The 120 slots are `pd.date_range(t − 24 h + 12 min, t, freq = 12 min)`, exactly as the fill rule in `euv_full.py`. Each slot takes the box value of the nearest valid frame by `t_obs` if within ≤ 6 min, otherwise it is missing; ties go to the earlier frame.
4. **Interpolation and normalisation.** Missing slots are filled by linear interpolation in slot index; leading or trailing gaps take the nearest filled value (`numpy.interp`). **Series mean (unspecified detail; default drafted):** the mean over the filled (non-interpolated) slots, so it does not depend on the interpolation. The curve = value / mean − 1. Alternative: the mean of all 120 slots after interpolation.
5. **Undefined.** An episode is undefined if its series file is missing, it has no filled slot, or the mean is ≤ 0; reasons are counted in Step 1. All 541 passed the fill ≥ 80% rule, so at most 24 slots are interpolated.
6. **MiniRocket use.** Input array shape (n, 1, 120). Defaults otherwise; random_state = 20260921 (primary). A MiniRocket transform is fitted on the training part of every split at every level (outer, inner, inner-inner), then applied to the matching held-out part. The actual number of output features is reported in Step 1.
7. **Curve model.** MiniRocket → StandardScaler (fitted on the training part) → `LogisticRegression(penalty="l2", solver="lbfgs", max_iter=10000, C=C*)` with sample_weight = episode weights. The curve score = its predicted probability.
8. **C selection.** Within a given training set: `sklearn.model_selection.GroupKFold(n_splits=3)` by HARP (no shuffling; deterministic). For each C in {1e-4, 1e-3, 1e-2, 1e-1}, the whole curve model (MiniRocket included) is fitted on two parts and scores the third. C* = the smallest pooled weighted log-loss over the three held-out parts; ties go to the smaller C. The curve model is then refitted on the whole training set with C*.
9. **Stacking.**
   - (a) Inner OOF scores within the outer training set: `GroupKFold(n_splits=5)` by HARP; each inner fit selects its own C* as in item 8.
   - (b) The stacker is C_CV + logit(curve score): columns score, n_C, n_M, n_X, logR, log10_CV_box and logit_curve. It is fitted like C_CV (training-fold StandardScaler + `LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=10000)` = `stage4_models.LR`, sample_weight).
   - (c) The curve model is fitted on the whole outer training set (its own C*), scores the outer test fold, and (b) predicts it.
   - logit uses p clipped to [1e-6, 1 − 1e-6] (unspecified detail; default drafted).
   - The outer OOF predictions over the five folds give LL(C_CV + curve).
10. **Baseline check.** C_CV = `euv_heldout.fit_folds` on the 541 set with the frozen columns (logR from `euv_confirm_tests.log_r`, as `euv_extra.py models`). Its OOF weighted log-loss must equal the frozen value in `data/euv_extra/thresholds.json` (C_CV `dev_oof_logloss` 0.3160449750917507) exactly, and its τ must equal 0.06893616544608924; otherwise STOP.
11. **E1–E2** use the `phase_f` machinery (`dll` bootstrap 10,000, seed 20260921; `tau_keep` 0.88 / 0.95 and the paired `op` bootstrap 2,000, seed 0). AUC weighted.
12. **E3.**
    - Curve-only OOF AUC = weighted AUC of the outer OOF curve scores from 9(c).
    - CV_box-only OOF AUC = weighted AUC of `fit_folds(c, ["log10_CV_box"])` OOF predictions.
    - Twins: T_a = `twins(c)`, T_b = `twins(c, by_group=True)` on the 541 set; ratio = `phase_f.ratio_jobs` mode "ratio" on the OOF curve scores (pairs by true HARP, 2,000, seed 0), plus the sign test (two-sided, ties excluded).
    - Spearman ρ (pooled, unweighted) of the OOF curve score with log10 CV_box, n_C, logR and gate score.
13. **E4.** The whole nested pipeline (items 8–9) is rerun with MiniRocket random_state = 1, 2, 3, 4, 5. For each seed, Δ is reported with its CI (same bootstrap). The primary stays seed 20260921.
14. **OPEN — frozen model form (only if it qualifies).** The user's text says "full-dev-trained". **Default = the user's text:**
    - the curve model is fitted on all 541 (C* by item 8 on all 541);
    - the stacker is fitted on all 541 using the outer OOF curve scores from 9(c);
    - τ = `tau_keep` 0.88 on the outer OOF stacked predictions (dev OOF).
    Alternative (the project's usual convention): keep the five outer-fold pipelines and average their held-out predictions, so that τ comes from the same models' OOF predictions.
15. **OPEN — held-out sets and readings (only if it qualifies).**
    - Proposed sets: 2021/2023/2024 = the TEST primary 80%-fill set with CV_box defined (series in `data/euv_test/series/`, 313 files); 2025–26 = the TEST 1 set (fill ≥ 80%, CV_box defined; series in `data/euv_confirm/series/`, 387 files).
    - Disclosure: the labels of both sets were seen earlier, and C_CV was already evaluated on 2025–26 (4b65f23); curve scores have never been computed.
    - No reading wording was given. Proposed, as for MR: E1 "CURVE ADDS" if Δ > 0 AND CI excludes 0, else "NO DETECTABLE ADDITION"; E2 reported only.
    - "Passes held-out" (for the prospective amendment) is also undefined. Proposed: "CURVE ADDS" on both held-out sets.
16. **Synthetic crash-test labels (Step 1).** Labels are drawn as `numpy.random.RandomState(12345).binomial(1, 96/541, 541)`, using the committed prevalence (541 = 96 true / 445 false, e.g. decisions.md Phase X table "541 (96/445)"), so the label column is not read. The C_CV reproduction check is skipped in the crash test, and nothing is saved or frozen. The crash test also gives the runtime estimate for Step 2.
17. **Outputs.** Script `minirocket.py`; `data/minirocket/curves.csv` (label-free); `figures/minirocket/examples.png` (6 episodes drawn with `numpy.random.RandomState(20260921)`); logs `minirocket_step1.log` and `minirocket_eval.log`.

## 2026-09-30 — CANDIDATE #27 (MRKT): CHECKPOINT 1 DECISIONS — AMENDMENT BEFORE STEP 1 (decided by: user; recorded verbatim before any curve is built or any label is read)
**Verbatim (user):**

Decisions (decided by: user), recorded as an amendment before Step 1:
1. Series mean = mean of slots filled with real frames (interpolated slots excluded), as CV_box.
2. Clip curve score to [1e-6, 1 − 1e-6] before the logit.
3. Frozen form (only if qualified): project convention — keep the 5 outer-fold pipelines (curve model + stacker per fold), average their held-out predictions; τ from the dev outer OOF predictions by the 88% rule. Freeze and hash all before any held-out computation.
4. Held-out readings per set (E1): "CURVE ADDS" if Δ > 0 AND CI excludes 0; "DIRECTION CONSISTENT, NOT CONFIRMED" if Δ > 0 AND CI includes 0; "NO DETECTABLE ADDITION" otherwise. E2 reported only. "Passes held-out" (for the prospective amendment) = Δ > 0 on BOTH sets AND "CURVE ADDS" on at least one.
5. Synthetic crash-test labels with prevalence 96/541 from committed tables; real labels first read in Step 2.
I have read the 17 clarifications and accept them [or list changes].
Commit the amendment, run Step 1 (label-blind + synthetic crash test, report runtime), STOP at CHECKPOINT 2.

**Effect on the pre-registration (16569b6; drafted by Claude AI):**
- Clarifications 4 and 9 are confirmed as drafted (mean over real-frame slots; clip [1e-6, 1 − 1e-6]).
- Clarification 14 is replaced by item 3: the five outer-fold pipelines (curve model + stacker per fold) are kept, and held-out predictions are their average. τ = `tau_keep` 0.88 on the dev outer OOF stacked predictions. Everything is frozen and hashed before any held-out computation.
- Clarification 15: the held-out sets are those proposed; the E1 readings per set and the definition of "passes held-out" are the user's wording above; E2 is reported only.
- Clarification 16 is confirmed (synthetic labels, prevalence 96/541 from committed tables).
- All other clarifications (1–3, 5–8, 10–13, 17) are accepted as written. The bracketed "[or list changes]" is template wording; no changes were listed.

## 2026-09-30 — CANDIDATE #27 (MRKT): STEP 1 RESULTS, LABEL-BLIND + SYNTHETIC CRASH TESTS (EXPLORATORY (dev); numbers verbatim from `minirocket_step1.log`; no real label read)
`minirocket.py step1` → `minirocket_step1.log`, `data/minirocket/curves.csv` (label-free), `figures/minirocket/examples.png`.
- **Label-blindness:** "label columns loaded: none (dev_rows.csv; oof_cohort_dev.csv usecols = harpnum, t, score, n_C, n_M, n_X, noaa_ars; euv_full results json: primary_CV_box, primary_fill). Episodes: 541".
- **Curves:** "defined 541, undefined 0"; "check: filled slots / 120 reproduces the stored primary_fill for all 541 episodes".
- **Interpolated slots per episode:** "median 1.0, mean 3.12, min 1, max 22; episodes with 0: 0". Distribution in the log.
  - A label-free check run afterwards in the terminal (not in the log) showed the missing slots are not concentrated at the edges: slot 0 is interpolated in 2.77% of episodes, slot 119 (at t) in 4.62%, and at most 10.35% at any middle slot; 15 of 541 episodes miss only slot 119.
- **Relative curve values:** "median -0.0290, p1 -0.4860, p99 1.2919, min -0.7224, max 10.4688".
- **Figure examples** (RandomState(20260921)): 401_20110312T0959, 750_20110802T1659, 753_20110801T2059, 753_20110801T2359, 1993_20120830T1359, 4231_20140616T1159.
- **MiniRocket features:** "[9996]" (sktime rounds 10,000 down to a multiple of 84).
- **Crash test 1 (in the log; SYNTHETIC labels):** "numpy RandomState(12345).binomial(1, 96/541, 541) -> 94 ones; no real label read; C_CV reproduction check skipped; no file saved; no model frozen"; "full nested pipeline ran for 6 MiniRocket seeds x 5 outer folds; OOF predictions finite for all 541 in every seed"; "wall for the pipeline 55.2 s (0.9 min); per outer fold task median 15.5 s".
- **Crash test 2 (drafted by Claude AI; SYNTHETIC labels, same RandomState(12345); terminal only, not in a committed log):** after crash test 1, `evaluate` was changed to build its report lines in synthetic mode as well (printed only for real labels), so the report code is exercised. A scratch script then ran the pipeline with model return for the primary seed, a joblib round trip of one fold's models to a scratch file (identical predictions; the file was deleted), and `evaluate(..., synthetic=True)` ("26 lines built, not printed"). Wall 59.5 s. Nothing was saved or frozen. The freeze step itself (Step 2, only if MRKT qualifies) was not exercised.
- **Runtime estimate for Step 2:** about 1 minute for the pipeline plus the bootstraps.
STOP at CHECKPOINT 2; no real label has been read for MRKT.

## 2026-09-30 — CANDIDATE #27 (MRKT): STEP 2 GO + ADDITION (decided by: user; recorded verbatim before any real label is read)
**Verbatim (user):** Go for Step 2 (single run, real labels), exactly as registered.
Addition (decided by: user, before any label is read): if MRKT qualifies, after freezing and BEFORE any held-out computation, reload the frozen models from disk and confirm they reproduce the dev outer-OOF predictions exactly (report max abs difference); if not identical, STOP.
Report results, the mechanical reading, commit hashes, and STOP at CHECKPOINT 3.

**Implementation (drafted by Claude AI):** the freeze and the reload check are separate functions in `minirocket.py`. The reload check predicts each outer fold's test episodes with that fold's reloaded curve model and stacker, under the same single-thread BLAS limit as the worker processes, and compares the result with the in-run outer OOF predictions (max absolute difference; STOP unless it is exactly 0). Before the real run, both functions are crash-tested once on SYNTHETIC labels (RandomState(12345), prevalence 96/541), writing to a scratch folder outside the repository that is deleted afterwards. No real label is used, and nothing is kept.

## 2026-09-30 — CANDIDATE #27 (MRKT): STEP 2 RESULTS, DEV EVALUATION RUN ONCE (EXPLORATORY (dev); numbers verbatim from `minirocket_eval.log`)
`minirocket.py step2` (script as committed in dd6210c) → `minirocket_eval.log`. This is the first and only run with the real labels. Nothing claimed as confirmed; dev only.
- **Checks:** "C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL 0.3160449751, tau 0.0689361654); episodes 541 (true 96, false 445), HARPs 179"; "curves identical to the Step 1 file data/minirocket/curves.csv"; "pipeline wall 58.8 s".
- **E1 PRIMARY (random_state 20260921):** "LL(C_CV) 0.3160, LL(C_CV + curve) 0.3263; Δ -0.0103 [-0.0219, -0.0018]; weighted AUC 0.7888 -> 0.7528". Chosen C over the 5 outer + 25 inner curve models: "{0.0001: 21, 0.001: 9}". The stacker coefficient on logit_curve (per 1 SD) by outer fold: −0.2823, −0.1791, +0.0084, +0.5487, −0.3052.
- **E2 matched retention (paired HARP bootstrap 2,000, seed 0):**
  - target 0.88: C_CV "true kept 84/96 (0.8803 w), false removed 218/445 (0.4863 w)"; C_CV + curve "true kept 85/96 (0.9228 w), false removed 189/445 (0.4039 w)"; "false removed (C_CV + curve − C_CV): -8.24 points [-13.37, -3.71]".
  - target 0.95: C_CV "true kept 88/96 (0.9544 w), false removed 193/445 (0.4191 w)"; C_CV + curve "true kept 90/96 (0.9669 w), false removed 132/445 (0.2400 w)"; "false removed (C_CV + curve − C_CV): -17.91 points [-23.43, -12.56]".
- **E3 descriptive:**
  - "curve-score-only OOF weighted AUC 0.7054; CV_box-only OOF weighted AUC (fit_folds on log10_CV_box) 0.7068".
  - Curve-score twins: T_a 81 pairs, ratio 1.9428 [1.1077, 2.7734], true higher 54 / false higher 27, sign p 0.0036; T_b 78 pairs, 1.7602 [0.7797, 2.3131], 50 / 28, sign p 0.0169.
  - Spearman ρ (n 541): log10_CV_box 0.8155; n_C 0.6763; logR −0.6405; gate score 0.4288.
- **E4 stability (Δ [95% CI]):** random_state 20260921 −0.0103 [−0.0219, −0.0018]; 1: −0.0105 [−0.0222, −0.0020]; 2: −0.0105 [−0.0225, −0.0018]; 3: −0.0096 [−0.0203, −0.0018]; 4: −0.0093 [−0.0196, −0.0017]; 5: −0.0103 [−0.0220, −0.0018].
- **PRE-STATED READING (mechanical):** "E1 Δ -0.0103 > 0 is False; E2 (88%) -8.24 points > 0 is False -> "NOT ELIGIBLE"".
- MRKT does not qualify for a held-out test. No model or τ was frozen, so the reload check (bf2dbc4) did not apply. The held-out plan is not run, and by the prospective amendment (16569b6) the curve score is not added to the prospective test.
STOP at CHECKPOINT 3.

## 2026-09-30 — NEW DEV CANDIDATE #28: SMALL 1D-CNN ON THE 94 Å LIGHT CURVE (CNN1D) — PRE-REGISTRATION (design decided by: user; literature, environment and clarifications drafted by Claude AI, flagged for the user at CHECKPOINT 1; recorded BEFORE any network is trained or any label is read for CNN1D)
Status: EXPLORATORY (dev) candidate. Nothing has been trained. One package set was installed (0b), and one untrained network was built only to count its parameters.

**Verbatim (user):**

PROJECT: <project folder> — NEW CANDIDATE #28: SMALL 1D-CNN ON THE 94 Å LIGHT CURVE (CNN1D).
Question: can a small convolutional network learn curve information beyond CV_box + gate score + flare history, where MiniRocket (#27, NOT ELIGIBLE, 62fc126) could not?

HARD RULES
- Same as #27: decisions.md APPEND-ONLY; frozen files untouched; no JSOC, no image reprocessing; DEV 2010–2019 ONLY; no prospective data; no Look 1/2.
- Reuse #27's curves (identical file), outer folds, stacking design, C_CV baseline and reproduction checks, E1–E4 definitions, readings and held-out/prospective rules, and the freeze + reload check. Change ONLY the curve model.
- Installing PyTorch (CPU) is allowed only if a before/after pip freeze shows no change to numpy, scipy, scikit-learn, pandas, sktime or numba; otherwise STOP and report. Pin versions.
- Crash tests use SYNTHETIC labels only (as #27). Real labels read exactly once, in Step 2.
- Record "decided by: user" / "drafted by Claude AI". EXPLORATORY (dev). STOP at every CHECKPOINT.

STEP 0 — Pre-registration (nothing trained, no labels read)
 Literature: cite Wang, Yan & Oates 2017 ("Time series classification from scratch with deep neural networks: a strong baseline", IJCNN) — read the abstract, quote the defining sentence in short fragments. State MiniRocket's #27 result as the prior.
 [DEFAULT] Architecture (fixed, ~1–2k parameters; report the exact count): input 1×120 relative curve → Conv1d(1→8, kernel 7, padding same) → ReLU → MaxPool(2) → Conv1d(8→16, kernel 5, padding same) → ReLU → global average pool → Dropout(0.3) → Linear(16→1) → sigmoid.
 [DEFAULT] Training: weighted binary cross-entropy with the episode weights (1/n per HARP; no extra class weighting); Adam, lr 1e-3, weight_decay 1e-3, batch 32; max 200 epochs; early stopping on an inner validation split = 20% of the training HARPs (GroupShuffleSplit, fixed seed), patience 20, restore best weights. No data augmentation. No hyperparameter search of any kind.
 [DEFAULT] Determinism: torch.manual_seed, numpy seed, torch.use_deterministic_algorithms(True), torch.set_num_threads(1). Primary seed 20260921.
 Curve score = CNN output probability; everything downstream (clip, logit, stacking into C_CV, E1–E4, qualification rule, held-out readings, freeze form = 5 outer-fold pipelines averaged, reload check) exactly as #27 (b1fbd2e).
 E4 stability: seeds {1,2,3,4,5}, full nested pipeline each; report every Δ with CI.
 Add E5 (descriptive): mean best epoch and train vs inner-validation loss per fold (overfitting check).
CHECKPOINT 1: entry + commit hash.

STEP 1 — Label-blind
 Confirm the curve file is identical to #27's (hash). Report parameter count and runtime. Crash-test the full nested pipeline + freeze/reload on SYNTHETIC labels in a scratch folder outside the repo (deleted after). Commit the code before the real run.
CHECKPOINT 2: wait for "go".

STEP 2 — Single real run
 Run E1–E5 once; log to cnn1d_eval.log; append verbatim results + mechanical reading to decisions.md; freeze + reload check only if qualified. Commit.
CHECKPOINT 3: report and STOP.

**Who decided:** the design above (question, rules, the three [DEFAULT] items, reuse of #27, E1–E5, qualification, held-out and prospective rules) is **decided by: user**. Steps 0a–0c are **drafted by Claude AI**; every item in 0c awaits the user at CHECKPOINT 1, and items marked OPEN need a user choice.

### Step 0a — literature and prior (read 2026-09-30; drafted by Claude AI; quotes verbatim and kept short)
**Wang, Yan & Oates, "Time series classification from scratch with deep neural networks: A strong baseline"**, 2017 International Joint Conference on Neural Networks (IJCNN), pp. 1578–1585, doi:10.1109/ijcnn.2017.7966039 (Crossref); arXiv:1611.06455 (v1 20 Nov 2016 … v4 14 Dec 2016). Only the arXiv abstract was read.
- Defining sentence (abstract; quoted in fragments): "a simple but strong baseline for time series classification from scratch"; the models are "pure end-to-end without any heavy preprocessing on the raw data or feature crafting".
- Model (abstract): "The proposed Fully Convolutional Network (FCN)". Its global average pooling enables a Class Activation Map that shows "the contributing region in the raw data".
- Relevance (drafted by Claude AI): the abstract reports classification performance; this project scores log-loss of a stacked logistic model on 541 episodes, so the paper's results do not transfer directly. The network here is a small fixed architecture chosen by the user; the abstract does not give the paper's model sizes.

**Prior, #27 MRKT (62fc126; `minirocket_eval.log`):** "Δ -0.0103 [-0.0219, -0.0018]" and E2 (88%) "-8.24 points" → "NOT ELIGIBLE". Its curve score had Spearman ρ 0.8155 with log10 CV_box, and its curve-only OOF AUC 0.7054 was close to CV_box-only 0.7068.

### Step 0b — environment and model size (drafted by Claude AI; done 2026-09-30)
- **Installed:** `pip install torch==2.14.0` into `.venv` (the standard macOS arm64 wheel; only the CPU device is used).
  - A `pip freeze --all` diff before/after shows only additions: filelock 4.0.7, Jinja2 3.1.6, MarkupSafe 3.0.3, mpmath 1.3.0, networkx 3.7, setuptools 84.0.0, sympy 1.14.0 and torch 2.14.0.
  - The protected packages are unchanged: numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, pandas 3.0.6, sktime 1.2.0, numba 0.67.0.
- **Exact parameter count: 737** — Conv1d(1→8, k 7) 8×1×7 + 8 = 64; Conv1d(8→16, k 5) 16×8×5 + 16 = 656; Linear(16→1) 17. This is below the user's "~1–2k" estimate. The architecture is kept exactly as specified (flagged, not changed).

### Step 0c — clarifications (drafted by Claude AI; none uses data; each awaits the user at CHECKPOINT 1)
1. **Reuse, and implementation.** A new script `cnn1d.py` imports from `minirocket.py`, unchanged: `base_frame`, `build_curves`, `logit` (clip 1e-6), `CCV`, `SEED`, `E4_SEEDS`, the C_CV reproduction check and the same stacking steps (a)–(c). Only the curve model (fit and predict) is replaced.
   - E1–E4 are computed as in `minirocket.evaluate` (same bootstraps, thresholds, twins and Spearman); the MiniRocket-specific report lines ("chosen C", feature count) are replaced by E5.
   - `minirocket.py` is not modified.
2. **Curves.** `data/minirocket/curves.csv`. Step 1 records its sha256 and checks that a fresh `minirocket.build_curves` gives exactly the same values.
3. **Network.** `Conv1d(1, 8, 7, padding="same") → ReLU → MaxPool1d(2) → Conv1d(8, 16, 5, padding="same") → ReLU → AdaptiveAvgPool1d(1) → Flatten → Dropout(0.3) → Linear(16, 1)`, sigmoid on the output.
   - PyTorch default initialisation, seeded; float32; CPU.
   - The input is the #27 relative curve, with no further scaling.
4. **Loss.** Per-episode binary cross-entropy on the logit (`BCEWithLogitsLoss(reduction="none")`). The batch loss is Σ w·l / Σ w with the dev_rows episode weights, and there is no class weighting.
5. **Optimiser.** `torch.optim.Adam(lr=1e-3, weight_decay=1e-3)` (PyTorch's Adam adds weight_decay as an L2 term to the gradient; it is not AdamW).
6. **Batches.** Size 32, reshuffled every epoch with a `torch.Generator` seeded with the run seed; the last partial batch is kept.
7. **Early stopping.** Within each network's training set, `GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)` over HARPs gives the validation part, and the network is fitted on the other 80% only. There is no refit on 100% afterwards.
   - After each epoch, the weighted BCE (Σ w·l / Σ w) on the validation part is computed in eval mode (dropout off).
   - Best = the lowest value (a strict improvement is needed; ties keep the earlier epoch). Training stops after 20 epochs without improvement or at 200, and the best weights are restored.
   - **OPEN — split seed in E4.** Default: the run seed drives everything (initialisation, batch order, dropout and the validation split), so E4 measures total seed sensitivity. Alternative: keep the split seed at 20260921 in every E4 run.
8. **Determinism.** Before every network fit: `torch.manual_seed(seed)`, `np.random.seed(seed)`, `torch.use_deterministic_algorithms(True)`, `torch.set_num_threads(1)`. Outer folds run in parallel processes, as in #27, each single-threaded.
9. **Stacking (as #27):**
   - (a) inner `GroupKFold(5)` OOF network scores within the outer training set; each inner network has its own 20% validation split from its own training set;
   - (b) stacker = C_CV + logit(score), fitted with `stage4_models.LR`;
   - (c) a network trained on the whole outer training set (its own 20% split) scores the outer test fold.
   #27's 3-fold C selection has no counterpart, because there is no hyperparameter search.
10. **E5 (descriptive, primary seed only).** For each of the 5 outer-fold networks from (c): the best epoch, the epochs run, and the weighted BCE on its training part and on its validation part at the best epoch (eval mode). Also the mean best epoch over all 30 networks (5 outer + 25 inner).
11. **Freeze and reload (only if it qualifies; b1fbd2e, bf2dbc4).** Per outer fold, the network `state_dict` is saved with `torch.save` and the scaler and stacker with joblib, plus τ (88% rule on the dev outer OOF stacked predictions) and sha256 hashes. The reload check must reproduce the dev outer OOF predictions exactly (max abs difference 0) under the same thread settings; otherwise STOP.
12. **Crash tests (Step 1).**
    - Labels: `numpy.random.RandomState(12345).binomial(1, 96/541, 541)`.
    - What runs: the full nested pipeline for all 6 seeds, the report code, and freeze + reload.
    - Where: in a scratch folder outside the repository, deleted afterwards.
    - The C_CV reproduction check is skipped there, and nothing is kept.
13. **Outputs.** `cnn1d.py`, `cnn1d_step1.log`, `cnn1d_eval.log`. No figure is required.

## 2026-09-30 — CANDIDATE #28 (CNN1D): CHECKPOINT 1 DECISIONS — AMENDMENT BEFORE STEP 1 (decided by: user; recorded verbatim before any network is trained or any label is read)
**Verbatim (user):**

Decisions (decided by: user), recorded before Step 1:
1. Keep the architecture exactly as specified: 737 parameters (the "~1–2k" in my instruction was an arithmetic estimate, not a design requirement).
2. E4: the run seed drives everything, including the 20% early-stopping split (default).
3. No refit: the early-stopped model trained on 80% of training HARPs is used as is.
I have read the 13 clarifications and accept them [or list changes].
Commit, run Step 1 (curve-file hash check, synthetic-label crash test incl. freeze/reload in a scratch folder, commit code before the real run), STOP at CHECKPOINT 2.

**Effect (drafted by Claude AI):** clarifications 1–13 of fdf044d are accepted as written; the OPEN item 7 (E4 split seed) is resolved as the default. The bracketed "[or list changes]" is template wording; no changes were listed.

## 2026-09-30 — CANDIDATE #28 (CNN1D): STEP 1 RESULTS, LABEL-BLIND + SYNTHETIC CRASH TEST (EXPLORATORY (dev); numbers verbatim from `cnn1d_step1.log`; no real label read)
`cnn1d.py step1 <scratch>` → `cnn1d_step1.log`. The code is committed with this entry, before the real run.
- **Model:** "torch 2.14.0; parameters 737".
- **Curves:** "curve file data/minirocket/curves.csv sha256 eafb4b00c16228ce7995f6d6f0d949d52371ae4de05c139f6995fb9672b94129; identical to a fresh minirocket.build_curves rebuild for all 541 episodes; no label column read".
- **Crash test (SYNTHETIC labels):** "numpy RandomState(12345).binomial(1, 96/541, 541) -> 94 ones; no real label read; C_CV reproduction check skipped; freeze/reload in a scratch folder outside the repository, deleted afterwards".
  - "full nested pipeline ran for 6 seeds x 5 outer folds (180 networks); OOF predictions finite for all 541 in every seed".
  - "wall for the pipeline 43.1 s (0.7 min); per outer fold task median 11.8 s".
  - "E1-E5 code paths ran on the synthetic predictions, including the report (28 lines built, not printed); values not reported".
  - "freeze wrote 12 hashed files to the scratch folder; reload check max abs difference 0.0; scratch folder deleted: True".
- **Extra check (drafted by Claude AI; terminal only, SYNTHETIC labels, nothing saved):** two fits of the same network with the same seed in one process gave identical weights (training is deterministic). In that synthetic fit the best epoch was 200, the cap, so the 200-epoch limit can bind; E5 will report best epochs with the real labels. This is an observation only; nothing is changed.
- **Runtime estimate for Step 2:** under 1 minute for the pipeline plus the bootstraps.
STOP at CHECKPOINT 2; no real label has been read for CNN1D.

## 2026-09-30 — CANDIDATE #28 (CNN1D): EPOCH-CAP DECISION + STEP 2 GO (decided by: user; recorded verbatim BEFORE any real label is read)
**Verbatim (user):** Decision (decided by: user), recorded BEFORE Step 2: keep max_epochs = 200 as registered. Pre-stated interpretation: if E5 shows best epoch = 200 in more than half of the 30 networks, the result is reported with the limitation "possibly under-trained (epoch cap binding)"; no rerun and no change to the reading.
Then go for Step 2: single real run exactly as registered. Report results, E5, the mechanical reading, commit hashes, and STOP at CHECKPOINT 3.

**Implementation (drafted by Claude AI):** the E5 report of `cnn1d.py` gains one line before the run: the number of the 30 primary-seed networks whose best epoch = 200, and the pre-stated interpretation applied mechanically ("more than half" = at least 16 of 30). Nothing else changes; the code is committed before the run.

## 2026-09-30 — CANDIDATE #28 (CNN1D): STEP 2 RESULTS, DEV EVALUATION RUN ONCE (EXPLORATORY (dev); numbers verbatim from `cnn1d_eval.log`)
`cnn1d.py step2` (script as committed in d419770) → `cnn1d_eval.log`. This is the first and only run with the real labels. Nothing claimed as confirmed; dev only.
- **Checks:** "C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL 0.3160449751, tau 0.0689361654); episodes 541 (true 96, false 445), HARPs 179"; "curve file data/minirocket/curves.csv sha256 eafb4b00c16228ce7995f6d6f0d949d52371ae4de05c139f6995fb9672b94129, identical to a fresh rebuild"; "pipeline wall 62.8 s".
- **E1 PRIMARY (seed 20260921):** "LL(C_CV) 0.3160, LL(C_CV + curve) 0.3158; Δ +0.0002 [-0.0041, +0.0041]; weighted AUC 0.7888 -> 0.7864". The stacker coefficient on logit_curve (per 1 SD) by outer fold: −0.2715, −0.3896, −0.4217, −0.0759, −0.0858.
- **E2 matched retention (paired HARP bootstrap 2,000, seed 0):**
  - target 0.88: C_CV "true kept 84/96 (0.8803 w), false removed 218/445 (0.4863 w)"; C_CV + curve "true kept 84/96 (0.8876 w), false removed 214/445 (0.4625 w)"; "false removed (C_CV + curve − C_CV): -2.38 points [-5.43, -0.05]".
  - target 0.95: C_CV "true kept 88/96 (0.9544 w), false removed 193/445 (0.4191 w)"; C_CV + curve "true kept 88/96 (0.9544 w), false removed 181/445 (0.3875 w)"; "false removed (C_CV + curve − C_CV): -3.16 points [-7.53, +0.88]".
- **E3 descriptive:**
  - "curve-score-only OOF weighted AUC 0.6445; CV_box-only OOF weighted AUC (fit_folds on log10_CV_box) 0.7068".
  - Curve-score twins: T_a 81 pairs, ratio 1.0921 [1.0449, 1.1809], true higher 56 / false higher 25, sign p 0.0008; T_b 78 pairs, 1.0799 [1.0144, 1.1627], 52 / 26, sign p 0.0043.
  - Spearman ρ (n 541): log10_CV_box 0.7612; n_C 0.4724; logR −0.5402; gate score 0.2920.
- **E4 stability (Δ [95% CI]):** seed 20260921 +0.0002 [−0.0041, +0.0041]; 1: −0.0084 [−0.0180, +0.0005]; 2: −0.0047 [−0.0151, +0.0045]; 3: +0.0036 [−0.0033, +0.0105]; 4: −0.0052 [−0.0127, +0.0014]; 5: −0.0055 [−0.0228, +0.0094].
- **E5 training (seed 20260921; weighted BCE at the best epoch, train 80% / val 20%):**
  - Outer folds 0–4: best epoch 95 / 92 / 31 / 200 / 106; train 0.3865 / 0.3301 / 0.3651 / 0.3576 / 0.3679; val 0.3346 / 0.4584 / 0.4895 / 0.3514 / 0.4080.
  - "mean best epoch over all 30 networks (5 outer + 25 inner): 84.47 (min 10, max 200); networks stopped by patience: 26/30".
  - "networks with best epoch = 200: 2/30 -> epoch cap not binding in more than half of the networks (pre-stated rule)". The limitation "possibly under-trained (epoch cap binding)" therefore does not apply (rule of d419770).
- **PRE-STATED READING (mechanical):** "E1 Δ +0.0002 > 0 is True; E2 (88%) -2.38 points > 0 is False -> "NOT ELIGIBLE"".
- CNN1D does not qualify for a held-out test. No model or τ was frozen, so the reload check did not apply. The held-out plan is not run, and by the prospective rule (b1fbd2e) the curve score is not added to the prospective test.
STOP at CHECKPOINT 3.

## 2026-09-30 — NEW DEV CANDIDATE #29: FLICKER + BRIGHTNESS LEVEL (FBL) — PRE-REGISTRATION (design and stopping rule decided by: user; prior-evidence quotes and clarifications drafted by Claude AI, flagged for the user at CHECKPOINT 1; recorded BEFORE any L value is computed or any label is read for FBL)
Status: EXPLORATORY (dev) candidate. Nothing has been computed for FBL; only code and earlier decisions.md entries were read.

**Verbatim (user):**

PROJECT: <project folder> — NEW CANDIDATE #29: FLICKER + BRIGHTNESS LEVEL (FBL).
Question: does the mean 94 Å brightness level add information beyond CV_box (flicker) + gate score + flare history, alone or through a flicker × level interaction?
Prior evidence (quote from decisions.md, do not recompute): S1 total brightness Δ −0.0042, twins 0.981; S2 −0.0057; B1 +0.0050, twins 1.190; MiniRocket #27 and CNN1D #28 (relative curves, level removed) NOT ELIGIBLE.

HARD RULES
- decisions.md APPEND-ONLY; frozen files untouched; no JSOC exports/downloads (a JSOC keyword query for the aiapy degradation table only if I approve it at a checkpoint); DEV 2010–2019 ONLY; no prospective data; no Look 1/2.
- Crash tests on SYNTHETIC labels only; real labels read exactly once, in Step 2.
- Record "decided by: user" / "drafted by Claude AI". EXPLORATORY (dev). STOP at every CHECKPOINT.
- STOPPING RULE (decided by: user): if FBL is NOT ELIGIBLE, record in decisions.md: "Feature testing on the 94 Å data is closed after candidate #29; no further 94 Å features will be tested on 2010–2026 data." 

STEP 0 — Pre-registration (nothing computed, no labels read)
 Episodes/folds/weights: the 541 dev episodes of dev_rows.csv; same folds; weights 1/n per HARP; same estimator/preprocessing as C_CV; mean of 5 fold models.
 [DEFAULT] PRIMARY feature L = log10(mean box brightness in DN/s per pixel over the valid primary frames) — i.e., the exact denominator used in CV_box (report that CV_box × mean reproduces the stored detrended SD).
 PRIMARY model: C_CV + L.
 SECONDARY models (reported, cannot change the reading): (s1) C_CV + L + L × log10CV_box (interaction, both centred on the training fold); (s2) C_CV + log10 S1 (total brightness, as the earlier S1).
 [DEFAULT] No degradation correction in the primary (as S1). Step 1 must report the median of L by year (instrument-degradation drift check); if the drift across 2010–2019 exceeds 0.1 dex, flag it — do not change the definition.
 E1 Δ = LL(C_CV) − LL(C_CV + L), 95% CI (HARP bootstrap 10,000, seed 20260921); weighted AUC before → after.
 E2 Matched retention at 88% and 95%: weighted % false removed (C_CV + L minus C_CV), paired HARP bootstrap 2,000, seed 0.
 E3 Descriptive: twins ratio of 10^L (euv_f2_replication.twins T_a, T_b, same ratio function as CV_box); Spearman ρ of L with log10 CV_box, gate score, n_C, n_M, log(1+R).
 QUALIFICATION RULE (mechanical): qualifies only if E1 Δ > 0 AND E2 (88%) > 0 (point estimates); otherwise "NOT ELIGIBLE".
 HELD-OUT PLAN (run later only on my "go"): if qualified, freeze C_CV+L fold models + τ (88% rule) with hashes and a reload check (max abs diff must be 0) BEFORE any held-out computation; then E1/E2 once on 2021/23/24 test and 2025–26 (labels seen earlier; L never used in a model — disclose). Readings per set: "L ADDS" (Δ > 0, CI excludes 0) / "DIRECTION CONSISTENT, NOT CONFIRMED" (Δ > 0, CI includes 0) / "NO DETECTABLE ADDITION".
CHECKPOINT 1: entry + commit hash.

STEP 1 — Label-blind
 Compute L for all 541 (and 547) episodes from the stored series; report undefined counts, distribution, median by year (drift), and the CV_box × mean reproduction check. Crash-test the full pipeline on SYNTHETIC labels (nothing saved). Commit code before the real run.
CHECKPOINT 2: wait for "go".

STEP 2 — Single real run
 Run E1–E3 once; log to fbl_eval.log; append verbatim results + mechanical reading to decisions.md; apply the STOPPING RULE if NOT ELIGIBLE; freeze + reload check only if qualified. Commit.
CHECKPOINT 3: report and STOP.

**Who decided:** the question, rules, design, the two [DEFAULT] items, E1–E3, the qualification rule, the held-out plan and readings, and the **STOPPING RULE** are **decided by: user**. Steps 0a and 0b are **drafted by Claude AI**; every item in 0b awaits the user at CHECKPOINT 1, and items marked OPEN need a user choice.

### Step 0a — prior evidence, quoted from decisions.md (drafted by Claude AI; nothing recomputed)
- **S1, S2, B1 (Phase F / F7 summary; model A vs A + x, dev 2010–2019, EXPLORATORY):** line "| S1 (size) | 541 (96/445) | −0.0042 | [−0.0129, 0.0016] |…"; "| S2 (size) | 541 (96/445) | −0.0057 | [−0.0123, 0.0001] |…"; "| B1 | 540 (96/444) | 0.0050 | [−0.0050, 0.0149] |…".
- **Twins:** S1 "| S1 log10 total 94 Å | 6.135 / 5.999 | 1.368 [1.056, 1.958] (linear scale) | 6.104 / 6.112 | 0.981 [0.776, 1.407] |"; B1 "| B1 | 0.1598 / 0.1029 | ratio 1.140 [1.031, 1.292] | 0.1606 / 0.0851 | 1.190 [1.066, 1.333] |".
- **Note (drafted by Claude AI):** those Δ values compare A with A + x, not C_CV with C_CV + x as here. S1 = log10 of the median over valid frames of (box mean × box pixel count), `phase_f._size`; B1 is the PIL-to-control brightness level.
- **#27 MRKT** (62fc126): "NOT ELIGIBLE". **#28 CNN1D** (d6c417d): "NOT ELIGIBLE". Both used relative curves (value / mean − 1), so the level was removed.

### Step 0b — clarifications (drafted by Claude AI; none uses data; each awaits the user at CHECKPOINT 1)
1. **Episodes.**
   - The analysis set is `data/euv_extra/dev_rows.csv` (541; its folds and weights; 1/n per HARP), with the C_CV inputs built label-free as in #27 (`minirocket.base_frame`, which reads no label column).
   - L is also computed for the 547 dev episodes where a series file exists (546 files).
   - The dev predictions are out-of-fold. "Mean of 5 fold models" applies to new (held-out) sets, as in earlier candidates.
2. **L.** From `data/euv_full/series/<eid>.csv`: the valid frames are the `valid_primary` rows with a finite `box` (the frames `euv_dctrl.cv` uses for CV_box), and L = log10(mean of `box` over those frames). `box` is the mean over the box pixels of the exposure-normalised image (DN/s per pixel; `euv_full.py` maps raw / EXPTIME). L is undefined if there are no valid frames or the mean ≤ 0; reasons are counted.
3. **Reproduction check.** The detrended SD is not stored (the results json holds only `primary_CV_box`). Step 1 therefore recomputes it with the same function (`euv_pilot.detrended_sd` on the valid frames' t_obs and box) and requires |CV_box_stored × mean − SD_recomputed| ≤ 1e-12 × SD for every episode where CV_box is defined (floating-point tolerance). Mismatches are counted and listed.
4. **Models.** `euv_heldout.fit_folds` (Stage 4 folds, training-fold StandardScaler, `stage4_models.LR`, sample_weight) on the 541 set:
   - baseline C_CV (must reproduce the frozen euv_extra C_CV dev OOF log-loss 0.3160449750917507 and τ 0.06893616544608924 exactly; otherwise STOP);
   - primary C_CV + L.
5. **Secondary (s1), interaction.** Within each outer fold, L and log10 CV_box are centred on the training-fold means, and the product of the centred values is added as a column. The rest is `fit_folds` (StandardScaler + LR) with the columns C_CV + L + product. This needs a fold loop identical to `fit_folds` apart from building the product column.
6. **Secondary (s2).** The stored S1 in `data/phase_f/F5_values.csv` is already log10 of total brightness (`phase_f._size`), so it is used as is, without a second log ("log10 S1" read as the earlier S1 value). The model is C_CV + S1 on the episodes with S1 defined (n reported).
7. **E1 and E2** are computed for the primary; E1 also for s1 and s2 (reported only). They use the `phase_f` machinery: `dll` bootstrap 10,000, seed 20260921; `tau_keep` 0.88 / 0.95 on dev OOF per model; the paired `op` bootstrap 2,000, seed 0; AUC weighted.
8. **E3.** Twins T_a = `twins(c)`, T_b = `twins(c, by_group=True)` on the 541 set; `phase_f.ratio_jobs` mode "ratio" on 10^L (the mean brightness), pairs by true HARP, 2,000, seed 0; plus the sign test. Spearman ρ (pooled, unweighted) of L with log10 CV_box, gate score, n_C, n_M and logR.
9. **Drift check (Step 1).**
   - Drift = max − min of the yearly medians of L over the years with dev episodes (547 set); flagged if > 0.1 dex.
   - Years 2016–2019 have few episodes (10, 24, 3 and 4 in the MR Step 1 table, `mag_restless_step1.log`), so their medians are noisy.
   - The yearly medians mix instrument degradation with changes in which regions raised alarms, so a drift cannot be attributed to degradation alone.
   - No JSOC query is made; none is requested.
10. **Crash test (Step 1).**
    - Labels: `numpy.random.RandomState(12345).binomial(1, 96/541, 541)`.
    - What runs: every model fit, bootstrap, twins and report line, plus the freeze + reload code.
    - Where: in a scratch folder outside the repository, deleted afterwards.
    - The C_CV reproduction check is skipped there, and nothing is kept.
11. **Held-out plan details (only if qualified).**
    - Frozen: the 5 C_CV + L fold models, τ = `tau_keep` 0.88 on the dev OOF, sha256 hashes, and a reload check (the reloaded fold models reproduce the dev OOF predictions; max abs difference must be 0).
    - Held-out sets (as proposed for #27): 2021/2023/2024 = the TEST primary 80%-fill set with CV_box defined (series in `data/euv_test/series/`); 2025–26 = the TEST 1 set (series in `data/euv_confirm/series/`). L is computed the same way.
    - Baseline = the frozen euv_extra C_CV fold models (mean of 5); C_CV + L = the frozen fold models (mean of 5).
    - E2 on the held-out sets uses each model's frozen dev τ and is reported only.
    - Disclosure: the labels of both sets were seen earlier; C_CV was already evaluated on 2025–26 (4b65f23); L has never been used in a model.
    - No prospective amendment is registered for FBL.
12. **Stopping rule.** If the reading is "NOT ELIGIBLE", the Step 2 entry records the user's sentence verbatim.
13. **Outputs.** `fbl.py`; `fbl_step1.log`; `fbl_eval.log`; `data/fbl/dev_L.csv` (label-free).

## 2026-09-30 — CANDIDATE #29 (FBL): CHECKPOINT 1 ANSWERS — AMENDMENT BEFORE STEP 1 (decided by: user; recorded verbatim; nothing computed yet)
**Verbatim (user):**

Answers to Checkpoint 1 (decided by: user). Append as an amendment to the FBL entry before Step 1; nothing computed yet.
1. Reproduction check: accepted. If it fails at 1e-12 relative, report the max relative difference and STOP; do not loosen the tolerance.
2. s2: use the stored S1 as is (already log10). Accepted.
3. Drift: report the median of L and n for every year; compute the 0.1 dex flag only over years with n >= 10. Record that the flag cannot separate instrument degradation from cycle phase or episode selection. Flag only; the definition does not change.
4. Held-out details: accepted as proposed. No prospective amendment now.
5. UNITS: check the code and state whether the stored box series is DN or DN/s (exposure-normalised). The pre-registration said DN/s per pixel; your clarification said "exactly CV_box's denominator". If box is in DN, STOP and show me: the units, whether EXPTIME is available per frame, and the spread of exposure times across the 541 episodes. I will pick the definition before Step 1.
6. Add to E3 (descriptive only, cannot change the reading): Spearman rho of L with calendar year, because L may track year/cycle phase.
Commit the amendment, give the hash, then proceed to Step 1 only if item 5 shows box is already DN/s; otherwise wait.

**Effect (drafted by Claude AI):**
- Clarification 3: tolerance fixed at 1e-12 relative; on failure, report the max relative difference and STOP.
- Clarification 9: yearly median and n for every year; the 0.1 dex flag uses only years with n ≥ 10.
- E3 gains Spearman ρ(L, calendar year of t), descriptive.
- The drift flag cannot separate instrument degradation from cycle phase or episode selection.
- Clarifications 6 and 11 are accepted.
- Item 5 (units) is checked in the code before Step 1 and recorded in the next entry.

## 2026-09-30 — CANDIDATE #29 (FBL): UNITS CHECK + STEP 1 RESULTS, LABEL-BLIND (EXPLORATORY (dev); numbers verbatim from `fbl_step1.log`; no real label read)
**Units (item 5 of 83973d1; code check, drafted by Claude AI): the stored `box` is DN/s per pixel (exposure-normalised).**
- `euv_full.py` lines 246–247: `q, exp = int(m.meta.get("quality", 0)), m.exposure_time.to_value("s")` and `raw = m.data.astype(float)` (DN). Pixels > 12,000 DN are set to NaN (`SAT_DN`).
- Line 259: `r = register_cutout(sunpy.map.Map(raw / exp, m.meta))`. `euv_run.register_cutout` only rotates to north and rescales to 0.6″/px (order 3); it does not change units.
- Line 263: `frame_means(r.data, idx, S)` stores the mean over the box pixels as `box`.
- EXPTIME is also stored per frame (`exptime`). Step 1 therefore proceeded, as instructed.

`fbl.py step1 <scratch>` → `fbl_step1.log`, `data/fbl/dev_L.csv` (label-free). The code is committed with this entry, before the real run.
- "label columns loaded: none. Dev episodes 547: L defined 546, undefined 1 {'no series file': 1}".
- **Reproduction check:** "546 episodes; max relative difference 5.960e-15; failures at 1e-12: 0".
- "analysis set 541: L defined 541; S1 defined 541".
- **L percentiles (541):** "p0 0.0049, … p10 0.2598, p25 0.3826, p50 0.4871, p75 0.6143, p90 0.7002, … p100 1.3733".
- **L by year (median, n):** 2010 0.2516 (40); 2011 0.6016 (88); 2012 0.5158 (61); 2013 0.5144 (95); 2014 0.4787 (110); 2015 0.4368 (111); 2016 0.5451 (10); 2017 0.3985 (24); 2018 0.4025 (3); 2019 0.2723 (4).
- **Drift flag:** "drift over years with n >= 10 ([2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017]): max − min of yearly medians = 0.3501 dex -> FLAG: drift > 0.1 dex. The flag cannot separate instrument degradation from cycle phase or episode selection; flag only, the definition does not change."
  - Note (drafted by Claude AI): the lowest median is the earliest year (2010), so the spread is not a simple monotonic decline with time. This is an observation only.
- **Crash test (SYNTHETIC labels):** "numpy RandomState(12345).binomial(1, 96/541, 541) -> 94 ones; no real label read; C_CV reproduction check skipped; freeze/reload in a scratch folder outside the repository, deleted afterwards"; "E1-E3 code paths ran on the synthetic labels, including the report (22 lines built, not printed)"; "freeze wrote 7 hashed files to the scratch folder; reload check max abs difference 0.0; scratch folder deleted: True".
- "wall total 3.6 s".
STOP at CHECKPOINT 2; no real label has been read for FBL.

## 2026-10-01 — CANDIDATE #29 (FBL): STEP 2 GO + INTERPRETATION NOTE (decided by: user; recorded verbatim BEFORE the run; no analysis change)
**Verbatim (user):** go (decided by: user).
Before the run, append this interpretation note to the FBL entry (no analysis change): "Step 1 found yearly medians of L span 0.35 dex vs a 10th–90th range of 0.44 dex. If FBL qualifies, the result will be reported with the caveat that L may act as a proxy for year/cycle phase or episode selection rather than a physical signal; E3 rho(L, year) is the descriptive check."
Order in Step 2: (1) reproduce the frozen C_CV baseline (log-loss 0.3160449750917507, tau 0.06893616544608924) and STOP if either mismatches; (2) run E1–E3 once; (3) log, append verbatim results + mechanical reading, apply the STOPPING RULE if NOT ELIGIBLE; (4) freeze + reload only if qualified. Commit and STOP at Checkpoint 3.

Note (drafted by Claude AI): from `fbl_step1.log`, the 10th–90th range of L on the 541 set is 0.7002 − 0.2598 = 0.4404 dex, and the yearly-median span is 0.3501 dex. `fbl.py step2` (as committed in 29a4d1d) already runs in the stated order: the C_CV reproduction assert comes before any evaluation, and the freeze and reload run only if qualified.

## 2026-10-01 — CANDIDATE #29 (FBL): STEP 2 RESULTS, DEV EVALUATION RUN ONCE (EXPLORATORY (dev); numbers verbatim from `fbl_eval.log`)
`fbl.py step2` (script as committed in 29a4d1d) → `fbl_eval.log`. This is the first and only run with the real labels. Nothing claimed as confirmed; dev only.
- **(1) Baseline check (before any evaluation):** "L identical to Step 1 (data/fbl/dev_L.csv); C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL 0.3160449751, tau 0.0689361654); episodes 541 (true 96, false 445), HARPs 179".
- **(2) E1 (HARP bootstrap 10,000, seed 20260921; AUC weighted):**
  - PRIMARY C_CV + L: "LL(C_CV) 0.3160, LL(model) 0.3205; Δ -0.0044 [-0.0095, +0.0005]; AUC 0.7888 -> 0.7745".
  - s1 (interaction; reported only): "Δ -0.0015 [-0.0116, +0.0088]; AUC 0.7888 -> 0.7763".
  - s2 (C_CV + S1; reported only): "Δ -0.0044 [-0.0162, +0.0040]; AUC 0.7888 -> 0.7710".
  - Primary coefficient on L (per 1 SD) by fold: −0.2257, −0.4091, −0.1045, +0.0385, −0.2533.
- **E2 (primary; paired HARP bootstrap 2,000, seed 0):**
  - target 0.88: C_CV "true kept 84/96 (0.8803 w), false removed 218/445 (0.4863 w)"; C_CV + L "true kept 84/96 (0.8803 w), false removed 204/445 (0.4459 w)"; "false removed (C_CV + L − C_CV): -4.03 points [-7.17, -1.18]".
  - target 0.95: C_CV "true kept 88/96 (0.9544 w), false removed 193/445 (0.4191 w)"; C_CV + L "true kept 89/96 (0.9546 w), false removed 136/445 (0.2538 w)"; "false removed (C_CV + L − C_CV): -16.52 points [-22.02, -11.42]".
- **E3 descriptive:**
  - Twins of 10^L: T_a 81 pairs, ratio 1.1776 [0.9404, 1.3693], true higher 55 / false higher 26, sign p 0.0017; T_b 78 pairs, 1.0975 [0.8939, 1.3283], 50 / 28, sign p 0.0169. All-episode ratio 1.3508 [1.1546, 1.5812].
  - Spearman ρ(L, ·) (n 541): log10_CV_box 0.6084; score 0.4782; n_C 0.5801; n_M 0.4673; logR −0.5546; "year = -0.1619 (p 1.56e-04, n 541)".
- **(3) PRE-STATED READING (mechanical):** "E1 Δ -0.0044 > 0 is False; E2 (88%) -4.03 points > 0 is False -> "NOT ELIGIBLE"".
- **(4)** FBL does not qualify, so no model or τ was frozen, the reload check did not apply, and the held-out plan is not run. The interpretation note of 6fca646 (proxy caveat) applied only if FBL qualified.

**STOPPING RULE APPLIED (decided by: user, b3b0c3a):** "Feature testing on the 94 Å data is closed after candidate #29; no further 94 Å features will be tested on 2010–2026 data."
STOP at CHECKPOINT 3.

## 2026-10-05 — LATEX PAPER SCAFFOLD (TEMPLATE) FOR IRIS 2026-27 / ISEF 2027: INSTRUCTIONS RECORDED VERBATIM (decided by: user; drafted by Claude AI (chat))
**Verbatim (user):**

PROJECT: <project folder> — BUILD A LATEX PAPER SCAFFOLD (template, not the final paper) for IRIS 2026-27 / ISEF 2027.
Decided by: user. Drafted by Claude AI (chat). Record this prompt verbatim in decisions.md (append-only) before starting.

ABSOLUTE RULES
1. NO PROSE. ISEF Rule 8: AI may not write the research plan, abstract, poster or citations; the user has extended this to the paper and synopsis. You must NOT write paragraphs, abstract text, synopsis text, figure captions in sentence form, or bibliography entries. Every place where prose goes gets a \writebox{...} placeholder (defined below) listing: (a) the question that paragraph must answer, (b) the facts/numbers available, each as a macro with its source file:line, (c) wording rules. Axis labels, legends, table headers and section headings are allowed.
2. NO NEW ANALYSES. Use only results already in the repo logs/CSVs. Replotting stored per-episode values is allowed only after the replot reproduces the logged number exactly (report the check). If a number is not in the repo, list it as MISSING — do not compute it. Numbers that exist only in Claude-chat messages (e.g. 2021/23/24 flare-removed 1.267, CV-alone AUC 0.753, the two-region split) are NOT to be used.
3. Do not modify frozen files, models, thresholds, logs or existing figures. decisions.md append-only. No JSOC/network data downloads. No prospective data (t >= 2026-08-17). No labels touched beyond reading stored results.
4. No school name, city or state anywhere (IRIS rule). Author names = placeholders.
5. Every number in the .tex comes from an auto-generated macro file; no hand-typed numbers.
6. All output in a new folder paper_template/. Commit at each checkpoint and STOP.

STEP 1 — FORMAT RESEARCH (read-only) → paper_template/FORMAT_NOTES.md
 a) Read every PDF in Papers/ (and any other papers in the repo). For each: title, venue/type, section list, length (pages/words), number of figures/tables, how uncertainty is reported (CI, ±SD, p), how methods/data availability/AI or software use are disclosed. Then a summary table and the common structure for an astrophysics/space-weather paper (e.g. ApJ, Space Weather, Solar Physics style). Cite which paper each observation comes from.
 b) Official requirements, verified from official sources only (record URL + exact quoted text + date accessed): IRIS 2026-27 (iris.exstemplar.com): full-paper requirements (format, length, sections if stated), synopsis section word limits, video, anonymity rule, data-age rule, AI policy if any. ISEF 2027 (Society for Science rules book / Book.pdf if in the repo): AI rule 8, abstract rules (250 words), research plan sections, Form 2A AI disclosure + prompt log, what may not appear. If anything is not stated officially, write "NOT STATED" — do not infer.
 c) Recommend a section outline that satisfies both, and say which parts are IRIS-required vs conventional.
CHECKPOINT 1: report FORMAT_NOTES.md summary + URLs. STOP.

STEP 2 — NUMBERS + FIGURES
 a) scripts: paper_template/build_numbers.py parses the logs and writes numbers.tex (\newcommand macros, e.g. \TestOneRatio, \TestOneCIlo) plus numbers_sources.csv (macro, value, file, line, exact source text). A verify script re-parses and asserts every macro; it must pass.
   Required sources include: stage5_test.log (gate TSS/FAR, A vs B), euv_f2_replication.log (2021/23/24 twins), euv_confirm_tests.log (TEST 1 incl. s1/s4/s5, Model C test), euv_confirm_filter_retest.log, euv_extra_filter_test.log, sensitivity_combined.log, posthoc_twin_reuse.log, docs/posthoc_2026-09-28.md (C+ — label POST-HOC), Path A numbers in decisions.md, candidate logs #26–#29, persistence TSS (decisions.md). If candidate_inventory.md does not exist, build it first, read-only from decisions.md (every candidate tested on real labels: number, name, date, pre-reg commit or "not pre-registered", data set, Δ and CI, reading; exact total; reconcile with the "31 candidates" statement in the #25 entry).
 b) Figures (vector PDF, one script each in paper_template/figures/, colour-blind-safe palette used consistently across all figures, sans-serif ≥ 8 pt at final size, sized to \columnwidth or \textwidth, no chart junk, every figure readable in greyscale):
   F1 Method schematic (TikZ or matplotlib): SHARP → gate → alarm episodes → magnetic twins → AIA 94 Å CV_box → twins test / filter test / prospective test.
   F2 Data timeline: dev 2010–19, 2020 excluded, 2021/23/24 test, 2022 sensitivity, 2025–26 confirmation, prospective from 2026-08-17 (Look 1/Look 2 dates); mark which were pre-registered.
   F3 How CV_box is computed on ONE episode: box-mean 94 Å series, linear fit, residuals, SD/mean.
   F4 Example twin pair: 94 Å light curves (true vs false, matched gate score), with AIA cutout thumbnails ONLY if already stored locally. Pair chosen by a rule stated BEFORE looking (e.g. the TEST 1 pair whose ratio is closest to the median pair ratio); state the rule in the figure's \writebox and in decisions.md. No cherry-picking.
   F5 Forest plot of twin ratios with 95% CIs: dev, 2021/23/24 (pre-reg), 2025–26 (pre-reg), pooled s5, 2022 sensitivity, extra set; log x-axis, line at 1; marker shape = pre-registered / exploratory / sensitivity.
   F6 Trade-off: weighted true kept vs false removed for gate, A, C, C_CV, C+ (hollow marker, "post-hoc"), per set (2025–26 and 2021/23/24 test), with CIs where logged.
   F7 Overlap with flare history: median CV_box by C-flare-count bin, true vs false (posthoc 1d).
   F8 Path A: FAR with HEK vs SWPC labels (hourly and region, 2021/23/24) with CIs.
   F9 All candidates: Δ log-loss with CI, from candidate_inventory.md, line at 0.
   Tables: T1 data sets; T2 gate performance (+ persistence, + B&C reproduction); T3 pre-registered tests and mechanical readings; T4 filter results; T5 C+ (POST-HOC banner); T6 negative results.
 c) For every figure/table: report which logged numbers it reproduces (exact match).
CHECKPOINT 2: show figures (paths), verify-script output, MISSING list. STOP.

STEP 3 — LATEX SCAFFOLD
 a) paper_template/main.tex, article class (or the closest journal-like layout from Step 1), sections per the Step 1 outline. Define:
   \newcommand{\writebox}[1]{...} = a coloured framed box titled "STUDENTS WRITE" containing #1 (questions, available macros with sources, wording rules).
   \newcommand{\wordlimit}[2]{...} = box with section name and IRIS word limit.
 b) Include in the right places: Abstract (\wordlimit), Introduction, Background/related work (a list of papers to discuss with arXiv/DOI, each identifier VERIFIED on arXiv/ADS/publisher — students write the bib entries themselves; leave references.bib empty with a comment), Data, Methods (gate, episodes, CV_box, twins, bootstrap CIs, pre-registration timeline), Results (order: gate → Path A → magnetic trends null → twins by period → filter → Model C → C+ post-hoc → negative results), Discussion, Limitations (18 true regions; region reuse CI; flare-history overlap; 2021/23/24 not confirmed; number of candidates tested; Amrhein-style interpretation of intervals), Prospective test plan (Look 1/Look 2, readings, dates), Conclusion, AI-use disclosure (\writebox listing exactly what Claude Code, Claude chat and Codex did, from decisions.md), Data & code availability, Appendix (full candidate inventory, sensitivity tables).
 c) Wording rules to put in the relevant \writeboxes: "replicated" not "confirmed"/"discovered"; 2021/23/24 = "direction consistent, not confirmed"; every post-hoc item labelled post-hoc; never call periods "conflicting"; no causal claims; 2022 never pooled.
 d) A separate synopsis.tex with the IRIS sections, each a \wordlimit box listing which macros are relevant.
 e) Compile. Check what LaTeX is installed first (latexmk/pdflatex/tectonic). If nothing usable is installed, STOP and tell me the options and sizes — do not install anything without my OK.
 f) Quality checks: zero errors, list every overfull/underfull box warning and fix them, every figure fits its width, all \ref/\label resolve, page count, render each page to PNG and check visually that nothing overlaps or is cut off.
 g) Final verification report paper_template/VERIFY.md: every macro → source → match; every external identifier → URL checked; every Step 1 requirement → where the template handles it; compliance check (no prose written by AI; no school/city/state; no chat-only numbers).
CHECKPOINT 3: give the PDF path, VERIFY.md summary, page count, open issues. Commit. STOP.

**Status note (drafted by Claude AI):** the prospective-test amendment requested on 2026-10-05 has **not** been recorded. Its precondition failed: SWPC daily reports for 2026-08-17 and 2026-08-18 are cached (written 2026-09-21 19:43) and were parsed for the labels of pre-cutoff 2025–26 episodes. This awaits the user's decision. The paper scaffold uses no prospective data.

## 2026-10-05 — PAPER SCAFFOLD, STEP 1 DONE: paper_template/FORMAT_NOTES.md (drafted by Claude AI; research notes, not paper prose)
- **What was read:**
  - All 40 PDFs in `Papers/` and `output/`: 34 unique documents, 32 used for format statistics. The `doria_rosales_2026…` file is a different paper, and `Papers/2609.15026v1.pdf` is off-topic.
  - Official IRIS 2026–27 pages (iris.exstemplar.com, register.irisnationalfair.org).
  - Official ISEF 2027 documents (Book.pdf, Forms, Companion Guide 2026–2027, rule modifications), accessed 2026-10-05.
- **How it was done:** a read-only workflow of 5 paper readers, 2 rules researchers and 2 verifiers. The verifiers re-opened every official URL and confirmed each quotation and each NOT STATED item; their corrections are in the notes. Claude Code additionally checked the ISEF AI Use Table row "Use AI to collect data and write research plan." on the rendered Companion Guide page 6, where it is marked No / Never acceptable.
- **Facts flagged for the students (no interpretation):**
  - IRIS window ends 13 Oct 2026, 11:59 pm.
  - IRIS Rule 02 sets a 12-month data-age limit; how it applies to archival data is not stated.
  - ISEF: no research before January 2026; Rule 8 and the AI Use Table; Form 2A AI Usage Disclosure; prompt log in the Research Plan.
  - IRIS states no AI policy of its own.
  - IRIS abstract limits conflict (250 with a 300 hard cap vs 200–500).
  - The IRIS paper section list omits Results.
- No school, city or state name appears in the notes; quotes are under 15 words. No repository file other than this folder and this entry was changed.

## 2026-10-05 — PAPER SCAFFOLD: USER INSTRUCTIONS BEFORE STEP 2 (decided by: user; recorded verbatim) + STATUS OF PART A
**Verbatim (user):**

Decided by: user. This template is for our own reference only, not for submission.
A. First, explain the "decision on the 2026-08-17/18 flare reports": which files exist for t >= 2026-08-17, when and how they were obtained, and whether anything was read or computed from them. Facts only. If any prospective data was downloaded, list it and STOP.
B. Plan changes (record in decisions.md):
 1. Paper list in Background = "READING LIST (read before citing)". references.bib stays empty.
 2. Each figure's \writebox notes "made with code/graphics by Claude Code (AI)".
 3. Do not install LaTeX. Make paper_template/ Overleaf-ready, with a README on how to upload it.
If A is clean, go to Step 2.

(An earlier version of this message, with a longer list of plan changes, was interrupted by the user and replaced by the text above.)

**Status of A (drafted by Claude AI; facts from the read-only audit of 2026-10-05 and a re-check of file metadata):** A is **not clean**. Prospective-period data was downloaded: two SWPC daily event reports, `data/swpc_events/20260817events.txt` (3,280 bytes) and `data/swpc_events/20260818events.txt` (1,886 bytes).
- **When and how:** both were written 2026-09-21 19:43:42 IST by one ad-hoc Claude Code command, `swpc.download_range('2024-12-29','2026-08-18')`, during confirmation-set Step 1. That download range is recorded in decisions.md:1776 (commit 76fcb1a).
- **Purpose:** label follow-up for the last 2025–26 alarms.
- **Per the user's rule, Step 2 is NOT started.** The plan changes B1–B3 are recorded above and will be applied when Step 2 runs.

## 2026-10-05 — PROSPECTIVE TEST (2f62f88 / eb3e7d5) AND LOOK 2 (8aa1797): DISCLOSURE + AMENDMENT (decided by: user; recorded verbatim before any prospective data is used)
**Verbatim (user):**

Decided by: user. Prospective test: DISCLOSE AND KEEP 2026-08-17 as the start. Record verbatim in decisions.md (append-only), then commit:

1. DISCLOSURE: copy your Part A findings (files, sizes, timestamps, the 2026-09-21 swpc.download_range command, commit 76fcb1a, the three HARP 14993 alarms, check.log/nb_r4a_reanalysis.log use, the possibly printed X-flare list, the untracked figures/_model_features_all*.csv of unknown origin, and the metadata-only JSOC/NOAA queries) as a permanent disclosure under the prospective test. State that no SHARP, AIA, alarm or result for t >= 2026-08-17 exists, and that the start date (2026-08-17) was set by the end of the 2025–26 set, not by these reports.
2. NEW SECONDARY (cannot change the PRIMARY reading): the same PRIMARY CV_box twins statistic, CI and reading wording, recomputed excluding every episode with t on 2026-08-17 or 2026-08-18. Applies to Look 1 and, if used, the Look 2 fallback.
3. SIZE RULE wording: "fewer than 60 episodes have BF defined" means, for the amended PRIMARY, "fewer than 60 episodes have CV_box defined (fill >= 80%)".
4. FALLBACK: if Look 1 returns "TOO SMALL — DESCRIPTIVE ONLY", the same CV_box twins PRIMARY (same code, caliper 0.0747, CI, mechanical reading) runs ONCE on the Look 2 set, on my command "run the C+ confirmation once", not before 2027-03-15.
5. NEW SECONDARY (cannot change the PRIMARY reading): CV_box twins matched on gate score AND flare-history group (twins(c, by_group=True), as TEST 1 s1), on the Look 1 set (and the Look 2 set if the fallback applies).
6. From now on, every download for the prospective test is run by the students (they type the command), using code written by Claude Code.

Give the commit hash. Then "go" for Step 2 with B1–B3 applied.

### PERMANENT DISCLOSURE — prospective-period data obtained before the prospective test (facts; drafted by Claude AI from the read-only audit of 2026-10-05; decided to keep the start date by: user)
1. **Files on disk dated on or after 2026-08-17.** Exactly two, both NOAA SWPC daily event reports (flare lists) from the public NCEI archive, not JSOC. No later SWPC report is on disk.
   - `data/swpc_events/20260817events.txt`: 3,280 bytes, written 2026-09-21 19:43:42 IST.
   - `data/swpc_events/20260818events.txt`: 1,886 bytes, written 2026-09-21 19:43:42 IST.
2. **How they were obtained.** One ad-hoc Claude Code command on 2026-09-21, `swpc.download_range('2024-12-29','2026-08-18')`, run during confirmation-set Step 1. The range is recorded in decisions.md:1776 (commit 76fcb1a).
   - Purpose: label follow-up for the last 2025–26 alarms. The latest 2025–26 alarm is t = 2026-08-16 20:59:23 UTC. Its 24-h outcome window (t, t+24 h] reaches 2026-08-17 20:59:23 UTC, and its "delayed" window (t+24 h, t+48 h] reaches 2026-08-18 20:59:23 UTC.
3. **What was computed from them (by code).**
   - (a) The 24-h labels (`flared_M1_next_24h`) of the 103 hourly SHARP rows dated 2026-08-16, in `data/labelled_20260801_20260817.csv` and `data/labelled_20250101_20260817.csv`.
   - (b) `true_alarm` and `delayed` for the three latest 2025–26 alarms, all HARP 14993, with t = 2026-08-16 06:59:23, 09:59:23 and 20:59:23 UTC. These are in `data/euv_confirm/cohort_le2.csv` and `cohort_single.csv`.
     - The three are in the TEST 1 primary set: they count in the set totals and the matching pool, but are in no twin pair.
     - They are also used in TEST 2, the 2025–26 filter re-test, and the descriptive and post-hoc files.
   - (c) Aggregate counts that include all events of both days: `data/euv_confirm/logs/check.log` line 2 (XRA event totals 2024-12-29 → 2026-08-18) and `nb_r4a_reanalysis.log` line 84 (2026 B-class fraction).
   - (d) Several scripts parsed these days but kept only flares before each alarm (history windows), so their outputs do not depend on them.
4. **Possibly displayed.** `checks.py` printed every joinable X flare up to 2026-08-17 22:59 UTC to the session screen on 2026-09-21. That output was not saved, and the audit deliberately did not inspect it.
5. **Of unknown origin.** The untracked files `figures/_model_features_all{,2,3}.csv`, `_alarms_Cflares_all{,2}.csv`, `_model_comparison_alarms.csv` and `_turned_down_Cflares.csv` (written 2026-09-27/28) contain 48-h forward outcomes (e.g. maxflux48) for the three HARP 14993 alarms. No script in the repository writes them.
6. **Metadata-only queries reaching the boundary.**
   - JSOC keyword queries on 2026-09-21 (coverage check) returned T_REC and HARPNUM only, for the slot 2026.08.17_00:00:00 TAI (= 2026-08-16 23:59:23 UTC). Nothing was saved.
   - NOAA NCEI directory listings showing files through 2026-09-20.
   - One `cgem.lorentz` last-record query returned a T_REC dated 2026-08-18.
7. **What does not exist.** No SHARP record, AIA or HMI image, alarm episode, feature or result exists for t ≥ 2026-08-17. SHARP data end at 2026.08.16_23:00:00 TAI and the 2025–26 images at 2026-08-16 20:59:23 UTC. No prospective test, Look 1 or Look 2 has been run.
8. **Origin of the start date.** The start date 2026-08-17 was set by the end of the 2025–26 set, not by these reports. The coverage check found the latest SHARP T_REC at 2026-08-17 00:00:00 TAI with SHARP as the limiting source (decisions.md:1732–1736), and the confirmation set was frozen to "T_REC … up to but not including 2026-08-17 00:00 TAI" (decisions.md:1753).

### AMENDMENT — items 2–6 above, in force for Look 1 and Look 2 (decided by: user)
- **Item 2:** new SECONDARY on the Look 1 set (and the Look 2 fallback set if used): the PRIMARY CV_box twins statistic, CI and reading wording, recomputed with every episode with t on 2026-08-17 or 2026-08-18 removed. It cannot change the PRIMARY reading.
- **Item 3:** for the amended PRIMARY, the size rule reads "fewer than 60 episodes have CV_box defined (fill ≥ 80%)".
- **Item 4:** fallback. If Look 1 returns "TOO SMALL — DESCRIPTIVE ONLY", the CV_box twins PRIMARY runs ONCE on the Look 2 set, with the same code, caliper 0.0747, CI and mechanical reading. It runs on the user's command "run the C+ confirmation once", not before 2027-03-15.
- **Item 5:** new SECONDARY on the Look 1 set (and the Look 2 set if the fallback applies): CV_box twins matched on gate score AND flare-history group (`twins(c, by_group=True)`, as TEST 1 s1). It cannot change the PRIMARY reading.
- **Item 6:** from now on, every download for the prospective test is run by the students, who type the command, using code written by Claude Code.
- **Paper scaffold:** "go" for Step 2 with B1–B3 (8868647) applied.

## 2026-10-05 — PAPER SCAFFOLD STEP 2: FIGURE F4/F3 SELECTION RULES, STATED BEFORE LOOKING (rule idea decided by: user; exact wording drafted by Claude AI; recorded before any pair ratio, light curve or image is viewed)
- **F4 (example twin pair).**
  - Population: the 50 TEST 1 pairs in `data/euv_confirm/twins_le2.csv`.
  - For each pair i, r_i = stored primary_CV_box(true) / stored primary_CV_box(false), from `data/euv_confirm/results/<eid>.json`.
  - The chosen pair is the one with the **lower median** r_i: the 25th smallest of the 50. With 50 pairs, "closest to the median" is always a tie between the two middle pairs, so the lower one is taken. If two pairs have identical r_i, the one listed first in the file is chosen.
  - The figure plots both stored 94 Å box series (`data/euv_confirm/series/<eid>.csv`, valid primary frames) on the hours-before-t axis, and states both gate scores.
  - Thumbnails: the AIA 94 Å cutout frame nearest to t for each episode, only if the FITS file is already in `data/euv_confirm/aia/`. Nothing is downloaded.
  - The rule is applied by code. No other pair is plotted or viewed for selection.
- **F3 (CV_box on one episode).** The true episode of the F4 pair. The plotted linear fit and SD/mean must reproduce that episode's stored primary_CV_box exactly (relative difference ≤ 1e-12); otherwise STOP.

## 2026-10-05 — PAPER SCAFFOLD, STEP 2 DONE (CHECKPOINT 2): numbers, inventory, figures, tables (code by Claude Code (AI); no new analyses; B1–B3 of 8868647 applied where they belong to Step 2)
- **Numbers.**
  - `paper_template/build_numbers.py` reads 950 specs (`numbers_spec.csv`) plus the 147 Δ/CI values of the candidate inventory: **1,097 macros**. Each is taken from a committed file at git HEAD (file, line, exact context) and written to `numbers.tex` / `numbers.json` / `numbers_sources.csv`.
  - `verify_numbers.py` re-reads every source line: **1,097 macros, 0 failures; RESULT: PASS**.
  - Specs come from four extraction agents (gate / data / Path A; twins; filters / C+ / overlap; #26–#29), each checked mechanically, plus manually added held-out-test, phantom and timeline specs, and 6 table specs verified by the build.
- **Candidate inventory** (`paper_template/candidate_inventory.md` / `.csv`):
  - **35 distinct candidates tested on real labels, in 56 evaluation rows**, built by two independent agents.
  - Against "31 candidates" (decisions.md:5822): the builder finds exactly 31 before #25; the checker finds 30. The only difference is COMBO default (post-hoc), which is counted (POST-HOC).
  - Each row has a `status_class` set by a stated rule: development-years rows = EXPLORATORY (dev); held-out primary = PRE-REGISTERED CONFIRMATORY; pre-registered secondaries and sensitivity sets = PRE-REGISTERED SECONDARY; 2025–26 filter re-test = PRE-REGISTERED RE-TEST; post-hoc rows = POST-HOC. F9 and T6 both read this column.
- **Figures** (`paper_template/figures/F1–F9.pdf`, one script each; shared `figstyle.py`).
  - Style: dataviz-validated palette; status colours reserved for status; false alarms neutral grey; 8 pt sans-serif; width ≤ 453 pt (included at natural size); credit line "made with code written by Claude Code (AI)" on every figure.
  - F4/F3 example: the rule of 983bcae selected TEST 1 pair true 13708_20250830T1359 / false 12889_20250313T0659 (lower-median pair ratio). Both scripts reproduce the stored CV_box to 1e-12, and no unlogged example value is printed.
  - Reviewed twice by a reviewer agent (layout, status consistency, hard-coded numbers); all findings fixed.
- **Tables** `paper_template/tables/T1–T6.tex`: macros only; `gen_t6.py` regenerates T6 from the inventory.
- **Check:** `check_outputs.py` (writes `REPRODUCTION.md`) re-runs every figure and records the macros each one reads (F2 11, F5 28, F6 24, F7 26, F8 28, F9 151), checks every table macro and that no stray digit appears, and checks widths. **RESULT: PASS.**
- **MISSING:** `paper_template/MISSING.md` lists 10 absent numbers, 4 never-recorded readings, 3 values not yet made macros, 1 precision note, and the 3 chat-only numbers deliberately not used.
- **Compliance scan:** no school, city or state name in any scaffold file or figure text.

## 2026-10-05 — PAPER SCAFFOLD: STEP 3 GO + ADDITIONS (decided by: user; recorded verbatim before Step 3)
**Verbatim (user):**

go for Step 3 (decided by: user), with B1–B3 applied and these additions:
1. Before Step 3: state which data F6 uses. If F6 shows only post-hoc rule comparisons, keep the post-hoc banner and make sure T4 holds the pre-registered filter-test results (A vs A_CV on the extra set, C vs C_CV on 2025–26) with their recorded readings. If F6 mixes pre-registered and post-hoc points, mark them per point instead of the whole figure.
2. Do not compute any MISSING item. List them in the relevant \writebox as "not available".
3. No compiler available: build the Overleaf-ready folder and a zip, run all non-compile checks (refs/labels resolve by static scan, every \input/\includegraphics path exists, macros used = macros defined, no prose outside \writebox/\wordlimit, no school/city/state, no chat-only numbers), and write VERIFY.md.
4. README: steps to upload to Overleaf, compile, then download main.pdf + main.log into paper_template/overleaf_build/. When those files exist, run Step 3f (warnings, overfull boxes, page render check) on them.
Commit and STOP at Checkpoint 3.

## 2026-10-05 — PAPER SCAFFOLD, STEP 3 DONE (CHECKPOINT 3): LaTeX template, Overleaf zip, static checks (code by Claude Code (AI); no paper prose; no new analyses; not compiled — no LaTeX installed, none installed)
- **Addition 1 (F6).** F6 uses only POST-HOC numbers: the Trade* macros from docs/posthoc_2026-09-28.md section 1e (lines 268–326) plus set sizes. No point is pre-registered, so the whole-figure POST-HOC banner stays. T4 now carries the pre-registered filter-test results with their recorded readings:
  - A vs A_CV on the EUV-unseen extra set: "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)" (euv_extra_filter_test.log:32).
  - C vs C_CV on 2025–26: the same wording (euv_confirm_filter_retest.log:17).
  - Secondary readings: "not available (none recorded)".
- **Addition 2.** Every MISSING.md item appears as "not available" in the box where it belongs. Nothing was computed.
- **Addition 3.** New files in paper_template/:
  - main.tex, synopsis.tex, preamble.tex, rules.tex, reading_list.tex;
  - references.bib, empty on purpose;
  - tables T7 (twins sensitivity, post-hoc) and T8 (region reuse, post-hoc), from tables/gen_t7_t8.py;
  - build_tex.py, check_tex.py, check_build.py;
  - overleaf_upload.zip (25 files) and VERIFY.md.
  - check_tex.py runs the non-compile checks and PASSES:
    - every path exists and is in the zip;
    - braces and environments balance; no unescaped special character; character set OK;
    - every reference resolves; every command used is defined;
    - no text outside the boxes; captions are noun phrases;
    - no hand-typed numbers; no school, city, state or student name; no chat-only numbers;
    - every cited commit exists; the frozen-spec SHA matches.
  - The checker was mutation-tested: injected violations were caught.
- **Addition 4.** README.md gives the Overleaf upload/compile steps and says to download main.pdf and main.log into paper_template/overleaf_build/. check_build.py (Step 3f) reports "pending" until those files exist.
- **Numbers (1,138 macros, verify_numbers PASS).** 41 specs were added:
  - method constants and gate SVM parameters;
  - IRIS/ISEF limits from FORMAT_NOTES.md;
  - inventory totals;
  - prospective size rules (Look 1 PRIMARY, Look 2 C+) and the second prospective day;
  - gate-sensitivity N, positives and FAR (decisions.md:1584/1586; MISSING item 2 narrowed to the episode level).
- **Spec metadata corrected.**
  - ProspSizeMin now cites the amended rule (decisions.md:6663), not the superseded BF wording.
  - SetFillThreshold now cites the TEST 1 PRIMARY definition (decisions.md:4234).
  - Status changes: BCTable* → LITERATURE (Bobra & Couvidat); Reuse*Harps → POST-HOC.
- **Other changes.**
  - T6 is now a longtable, because T6a is taller than a page.
  - T4 reading rows: p{16cm} → p{14.5cm}.
  - T2 sensitivity cells filled.
  - T5 row renamed "Later sets pooled (includes 2022)".
  - F8 panel (b): status colours replaced by neutral styles, because Path A is descriptive (decisions.md:2341). F8_patha.pdf was regenerated; F1–F7 and F9 are byte-identical to Checkpoint 2.
  - check_outputs.py now re-runs every figure script into a temporary folder and requires a pixel match with the committed PDF (figstyle.save honours FIGSTYLE_OUTDIR), so a check no longer rewrites the figures or their creation dates.
  - Reading list: 24 journal DOIs (from arXiv metadata) were resolved on Crossref; all OK. Two papers listed under both arXiv and DOI are marked "same paper as".
- **Independent review: two workflows (4 + 2 agents).** All findings were checked against the sources before fixing. Fixed:
  - three pdfLaTeX-stopping characters (unescaped _ and &), now guarded in check_tex;
  - the s5 label wrongly showing 2022 as pooled;
  - pooled values that include 2022, now labelled with per-set or per-year macros listed: Stage 5 gate sensitivity, Path A phantom total and flips, F7 medians, pooled ρ, T5 later sets;
  - the prospective box: it mixed up the C+ "Look 1 descriptive" rule with the CV_box twins PRIMARY reading, and wrongly said no prospective data was analysed. Rewritten from decisions.md:5227–5232, 5380, 5381, 5451, 5499, 5500, 5954, 6005 and 6639–6666;
  - the AI-use disclosure: pre-registrations are now separate from descriptive/post-hoc entries, and the Claude AI drafts for #26–#29, 6004, 6639 and 6669 were added;
  - the synopsis now includes the wording rules;
  - wrong line citations corrected;
  - AI judgement words removed ("null result" heading, "few independent", "not comparable");
  - spelled-out counts removed.
  - Not adopted: none. Each reported problem was confirmed at its source.
- **Open for the user (not decided here).**
  1. "2022 never pooled" against items that pool 2022 by design or post hoc: the pre-registered Stage 5 gate sensitivity, F7 and pooled ρ, the Path A totals, and the T5 later-sets row. They are flagged in the boxes; whether to show them is the user's decision.
  2. The hypothesis wording at decisions.md:3837 was drafted by Claude AI. The paper must state it in the students' words, and the Introduction box says so.
  3. TestOneTrueHigher (39/50) has only the user's instruction line as its source (decisions.md:5529). The template lists SensTestOneTaVZeroTrueHigher (sensitivity_combined.log:16, post-hoc) instead.
  4. Page count and Step 3f wait for the Overleaf build.
- Untouched: frozen files, models, thresholds and logs. decisions.md was only appended to. No prospective data was used. No JSOC or data download; Crossref metadata lookups only.

## 2026-10-05 — PAPER SCAFFOLD: CHECKPOINT 3 ANSWERS (decided by: user; recorded verbatim before any change)
**Verbatim (user):**

Decided by: user (Checkpoint 3 answers).
1. 2022: the "never pooled" rule covers the twins and filter tests only. Keep the gate-sensitivity rows (label "pre-registered sensitivity, includes 2022"). Path A: main text uses 2021/23/24 values; 2021–24 totals go to the appendix labelled "includes 2022". C+: main text per set only; the 2021–26 combined row goes to the appendix labelled "includes 2022". F7/rho: list per-set rho values in the box (decisions.md 1d); the pooled rho goes to the appendix, labelled.
2. Hypothesis: keep the box rule that students write it in their own words; do not show the drafted text.
3. 39/50: keep sensitivity_combined.log:16 as the source, labelled "from the post-hoc sensitivity run (TEST 1 output printed ratio and CI only)".
Rebuild, rerun all checks, commit, STOP.

## 2026-10-05 — PAPER SCAFFOLD: CHECKPOINT 3 ANSWERS APPLIED (code by Claude Code (AI); no new analyses; not compiled)
- **1. 2022 scope.**
  - rules.tex now reads: "2022 never pooled in the twins and filter tests". Other values that include 2022 carry that label.
  - Gate-sensitivity rows are kept and labelled "pre-registered sensitivity, includes 2022": T1, T2, and the GateSens*/SetSens* facts in the Data and Gate boxes.
  - **Path A.** The main text keeps only 2021/23/24 values.
    - F8 panel (b) now shows the test years only, with no pooled total in the title.
    - The 2022 FARs, the 2022 phantom count and the 2021–24 totals (phantoms, HARPs, HEK-match counts, region flips) moved to the new appendix table T9, labelled "includes 2022".
  - **C+.** T5 is per set only. The 2021–26 later-sets combined row (Model C, C+) moved to T9, labelled.
  - **F7 and ρ.**
    - The per-set Spearman ρ with n (docs/posthoc_2026-09-28.md lines 216–220) are listed in the F7, C+ and Limitations boxes.
    - The pooled ρ (all, true-only, false-only) moved to T9, labelled.
    - The F7 title no longer prints the pooled ρ. The F7 caption and box label the figure "pooled over sets, includes 2022". F7 itself stays in the main text, as the answer names only the pooled ρ for the appendix.
- **2. Hypothesis.** The box rule is kept. The drafted text is not shown; only its location (decisions.md:3837) is cited.
- **3. 39/50.** The fact uses SensTestOneTaVZeroTrueHigher (sensitivity_combined.log:16), labelled "from the post-hoc sensitivity run (TEST 1 output printed ratio and CI only)".
- **Checks.** check_tex.py has two new guards. Both were mutation-tested.
  - None of the moved values may appear in the main text, its tables, its figure scripts or the synopsis, and T9 must sit in the appendix.
  - References are now resolved per document. The synopsis shares rules.tex, which now names T9 in plain text.
  - check_outputs.py's table digit check uses the same identifier rule as the generator (K2, T9 …).
  - Results: build_numbers (1,138 macros), verify_numbers, check_outputs (pixel reproduction) and check_tex all PASS.
  - The renamed generator, tables/gen_appendix_tables.py, makes T7–T9. numbers_spec used_in was updated for the moved macros.
- **Independent review: 3 finders, each finding checked by a skeptic.** 9 findings were confirmed and fixed, 9 were refuted. The fixes:
  - a C_CV combined row I had added to T9 (it was not part of the moved row, and it pooled 2022 into a filter-model count) was removed;
  - the T9 box now states the one overlap with F7 (the pooled class sizes);
  - the first T9 block now carries its label;
  - the AI-use disclosure now covers T1–T9.

## 2026-10-05 — DRAFT FACT-CHECK, POST-HOC INCREMENTAL TABLE, TERMS/ADITYA-L1 FACTS, PROSPECTIVE SECONDARY (decided by: user; recorded verbatim before anything else)
**Verbatim (user):**

Decided by: user. The Codex manuscript (Solar_Flare_Matched_Score_Research_Paper_REFERENCE.docx) is a private draft, not for submission. Do NOT edit, rewrite or improve its prose. Do these, in order; commit after each; STOP at the end.

1. FACT-CHECK LIST (review only, no new text for the paper):
   - Compare every factual statement, number, date, status label and "unavailable/not recorded" claim in the docx against the current repo (HEAD), decisions.md, the logs and paper_template/numbers_sources.csv.
   - Output paper_template/DRAFT_FACTCHECK.md as a table: section | quoted fragment (<= 15 words) | status (MATCH / OUTDATED / WRONG / UNSUPPORTED / OVERCLAIM) | correct value or fact | source file:line.
   - Flag especially: anything made outdated by #26–#29, candidate_inventory.md (35 candidates / 56 rows), b480d22 (prospective disclosure and amendment), the 2022 labelling rules (decisions.md:6768), the main-text Path A phantom count for 2021/23/24 (19, not 34), and any wording that breaks the user's rules ("confirmed"/"discovered", unlabelled post-hoc, "conflicting", 2022 pooled into twins/filter tests, causal claims).
   - Do not suggest replacement sentences. Facts and sources only.

2. INCREMENTAL TABLE (POST-HOC):
   - Using the frozen A, C, C_CV predictions only (no new features), on 2025–26 and on the 2021/23/24 test set, first reproduce the existing log-loss and AUC exactly.
   - Then add PR-AUC and Brier score, with HARP-bootstrap 95% CIs (2,000, seed 0), and the paired differences C−A and C_CV−C.
   - Label every new number POST-HOC. Add the values as macros plus one table (T10, appendix or Results) to the template.

3. TERMINOLOGY AND ADITYA-L1 FACTS (facts only, no prose):
   - paper_template/TERMS.md: standard solar-flare-forecasting terms used in our work (e.g. active region, polarity inversion line, true skill statistic, false-alarm ratio, EUV precursor, space weather), each with a one-line definition and a verified published source.
   - Verified facts on Aditya-L1 from official ISRO/IUCAA/ISSDC pages: launch date, instruments (SUIT wavelength range, SoLEXS, HEL1OS energy ranges), and data portal. Record URL + date accessed; mark anything unverifiable "NOT VERIFIED".

4. PRE-REGISTRATION AMENDMENT (record verbatim before any prospective data are analysed; first confirm none have been):
   - New SECONDARY for Look 1 (and the Look 2 fallback): CV_box twins built so that each true HARP is used at most once and no false HARP is reused (dependence-free pairs).
   - Same statistic, CI and reading wording as the PRIMARY. It cannot change the PRIMARY reading.

Report: commit hashes, the DRAFT_FACTCHECK.md summary counts by status, the T10 numbers, and any NOT VERIFIED items. STOP.

## 2026-10-05 — ITEM 2 DONE: POST-HOC INCREMENTAL TABLE T10 (code by Claude Code (AI); every new number POST-HOC; no new features, no refitting)
- **Reproduction first.** The logged weighted log-loss and AUC reproduced exactly to 4 dp (incremental_posthoc.log:5-7, 16):
  - 2025–26 (378 episodes): A, C and C_CV, against euv_confirm_filter_retest.log:7/9/10.
  - 2021/23/24 held-out test set (306 episodes): Model C, against docs/posthoc_2026-09-28.md:475. Model C is the only logged model there; the A and C_CV test-set log-loss/AUC are newly computed (POST-HOC).
- **New values (POST-HOC).** Weighted PR-AUC (average precision) and weighted Brier score, with HARP bootstrap 95% CIs (2,000, seed 0), plus paired C−A and C_CV−C on the same resamples (incremental_posthoc.log:8-12, 18-22). The PR-AUC and Brier calculations were cross-checked against a hand-written implementation.
- **Template.** 68 macros (Incr*), from 5f66228. Table T10 is in a new appendix section, and the Model C box points to it. build_numbers (1,206 macros), verify_numbers, check_outputs and check_tex all PASS.

## 2026-10-05 — ITEM 3 DONE: paper_template/TERMS.md (facts only; compiled by Claude Code (AI), each item researched and independently re-verified)
- **Terms.** 27 standard terms, each with a one-line definition and a published source. All 27 are VERIFIED: the DOI re-checked on Crossref or the official URL re-opened.
- **Aditya-L1 facts.** 21 facts from official ISRO, IUCAA, ISSDC, URSC and PRL pages, each with its URL, a verbatim evidence fragment (≤ 15 words) and the access date (2026-10-05):
  - launch: 2 September 2023, PSLV-C57;
  - halo-orbit insertion at L1: 6 January 2024;
  - payloads: 7;
  - SUIT: 200–400 nm, 11 filters;
  - SoLEXS: 2–22 keV;
  - HEL1OS: 10–150 keV;
  - data: ISSDC PRADAN (pradan.issdc.gov.in/al1), first public release 6 January 2025.
- **NOT VERIFIED.** 1 item: the MAG resolution in nT (not stated on any official page checked).
- **Official sources conflict.** On the ASPEX upper energy limit: ISSDC gives 6 MeV/n, PRL gives 5 MeV/n.

## 2026-10-05 — PROSPECTIVE PRE-REGISTRATION AMENDMENT: dependence-free CV_box twins SECONDARY (decided by: user; recorded verbatim BEFORE any prospective data are analysed)
**Precondition confirmed first.** Read-only checks by Claude Code (AI), 2026-10-05, after items 1–3: no prospective data (t ≥ 2026-08-17) have been analysed.
- The only files dated on or after 2026-08-17 are the two SWPC daily reports disclosed in b480d22 (data/swpc_events/20260817events.txt, 20260818events.txt).
- The latest alarm time t in any data CSV is 2026-08-16 20:59:23 UTC (data/euv_confirm/cohort_le2.csv and derived files).
- SHARP data end at 2026.08.16_23:00:00_TAI (data/raw_sharp_20260801_20260817.csv).
- No data file has changed since b480d22.
- data/prospective/ holds only development-period values (episodes up to 2019-04-16, computed 2026-09-27 for the BF/CV6 registration).
- No Look 1, Look 2 or prospective-test run exists in the log or git history.
- Item 2 (T10) re-read the stored 2025–26 cohort and labels and the local SWPC history windows exactly as the 2025–26 filter re-test did. It created no episode, feature or label for t ≥ 2026-08-17.

**Verbatim (user), item 4:**

4. PRE-REGISTRATION AMENDMENT (record verbatim before any prospective data are analysed; first confirm none have been):
   - New SECONDARY for Look 1 (and the Look 2 fallback): CV_box twins built so that each true HARP is used at most once and no false HARP is reused (dependence-free pairs).
   - Same statistic, CI and reading wording as the PRIMARY. It cannot change the PRIMARY reading.

**Open clarifications (drafted by Claude AI; NOT decided, nothing implemented; to be fixed by the user before Look 1 runs, not before 2026-11-10):**
- a) **Which episode of a true HARP.** A true HARP may have several eligible true episodes. Which one enters: the first in the seeded matching order, the earliest t, or another rule?
- b) **HARPs on both sides.** "No false HARP is reused" restricts the false side. May a HARP that is the true member of one pair be the false member of another pair?
- c) **Matching procedure.** Is it otherwise the PRIMARY matching (seeded order, greedy nearest gate score, caliper 0.0747, partner from a different HARP) with these constraints added, or a different pairing algorithm?
- d) **Interval.** The PRIMARY CI resamples pairs by true HARP. With one pair per true HARP, this is the same as resampling pairs. Confirm.
- e) **Size rule.** "Same statistic, CI and reading wording" does not state a size rule for this secondary. Does the PRIMARY size rule apply (b480d22 item 3), or a minimum number of pairs?

## 2026-10-05 — POST-HOC DESCRIPTIVE CHECK: TRUE ALARMS KEPT BY MODEL C BUT REMOVED BY C_CV (decided by: user; recorded verbatim before anything else)
**Verbatim (user):**

Decided by: user. POST-HOC DESCRIPTIVE CHECK on already-analysed data. No new features, no model refits, no new tests or rules, no prospective data (t >= 2026-08-17), no downloads. Label every output "POST-HOC, descriptive".

Goal: identify the TRUE alarms that the restlessness filter removed but the flare-history model kept, i.e. true episodes with p_C >= tau_C (kept by Model C) AND p_C_CV < tau_C_CV (removed by C_CV), using the frozen euv_extra fold models (mean of 5) and the exact frozen thresholds (tau_C 0.06256983158392139, tau_C_CV 0.06893616544608924).

1. Do this for each set separately: 2025–26 (primary interest), 2021/23/24 test, EUV-unseen extra, 2022 (never pooled), dev (out-of-fold). Report the exact count per set. First reproduce the existing posthoc §1c rejected-true-alarm counts and the C/C_CV kept counts (2025–26: C 54/56, C_CV 41/56); stop and report if anything mismatches.
2. For each such alarm, a table row: set, HARP, NOAA AR(s), alarm time t, gate score, CV_box, its percentile among false alarms of the same set, p_C, p_C_CV, n_C / n_M / n_X in the 48 h before t, largest flare and time since last C1+ flare before t, the M/X flare that made it true (class, start time, hours after t), whether a flare was in progress during the 24-h window, frame fill fraction, single- or two-region, whether it appears in a TEST 1 twin pair (and its twin's CV_box).
3. Group summary: how many share a HARP or NOAA AR (list the repeat regions), how many had a C1+ flare in the prior 24 h (should match §1c), median hours to the M/X flare compared with the true alarms that C_CV kept, and median CV_box compared with kept true alarms and with false alarms.
4. One figure: the 94 Å box light curves (mean-normalised, 24 h before t) for every removed true alarm in 2025–26, small multiples, each labelled HARP, flare class and hours to flare. Code-generated, labelled "made with code written by Claude Code (AI)".
5. Log to removed_true_alarms.log and docs/removed_true_alarms.md, append a short factual entry to decisions.md (append-only), commit, STOP. No interpretation or recommendations, facts only.

## 2026-10-05 — POST-HOC DESCRIPTIVE CHECK DONE: true alarms kept by Model C and removed by C_CV (code by Claude Code (AI); POST-HOC, descriptive; facts only)
- **Reproduced first, all identical** (removed_true_alarms.log):
  - frozen thresholds: tau_C 0.06256983158392139 and tau_C_CV 0.06893616544608924, as stated;
  - dev out-of-fold log-loss of C and C_CV;
  - every section 1c row (true rejected / kept by C_CV) of docs/posthoc_2026-09-28.md;
  - the section 1e true-kept counts, e.g. 2025–26: C 54/56, C_CV 41/56;
  - the TEST 1 pair file: 50 pairs, ratio 3.2624.
- **Removed true alarms per set** (never pooled):

  | set | removed | of true | also removed by both models |
  |---|---:|---:|---:|
  | 2025–26 | 13 | 56 | 2 |
  | 2021/23/24 test | 4 | 44 | 2 |
  | EUV-unseen extra | 2 | 32 | 3 |
  | 2022 | 5 | 28 | 1 |
  | dev, out-of-fold | 9 | 96 | 3 |

- **C1.0+ flare in the prior 24 h:** 11, 3, 2, 2, 7, equal to the section 1c counts in every set.
- **2025–26 alarms:** all 13 are true members of TEST 1 pairs. None of their M/X flares starts on or after 2026-08-17.
- **Outputs:**
  - docs/removed_true_alarms.md: per-alarm table and group summaries;
  - docs/removed_true_alarms_2025_26.png/.pdf: 13 light-curve panels;
  - removed_true_alarms.log.
- **Independent verification** (7 agents, own code, raw SWPC reports and joblib models):
  - counts and eid lists identical;
  - all 33 rows re-derived, 561 field comparisons, 0 mismatches.
  - Two confirmed presentation fixes were applied: field names in section 1, and the section 1e anchor for the kept counts.
- **Not changed:** no new features, refits, tests or rules; no prospective data; no downloads.

## 2026-10-06 — DOWNLOAD MISSING PAPERS + WRITE SECTION 2 "BACKGROUND AND RELATED WORK" (decided by: user; recorded verbatim before starting)
**Verbatim (user):**

PROJECT: <project folder> — DOWNLOAD MISSING PAPERS + WRITE SECTION 2 "BACKGROUND AND RELATED WORK".
Decided by: user. IRIS permits AI assistance; this use is disclosed in the paper's AI-use statement. Record this prompt verbatim in decisions.md (append-only) before starting.

HARD RULES (apply to both steps)
- decisions.md append-only; do not modify frozen files, models, logs, figures, tables or any existing section text.
- No JSOC or solar-data downloads; only paper PDFs from legal open sources.
- Never use Sci-Hub, LibGen, or any paywall workaround.
- Never delete files; move bad downloads to a _mismatch/ folder instead.
- No claim or number from memory; every factual statement in the section must be traced to a PDF on disk.
- No school name, city or state anywhere.
- Commit after each step.

================================================================
STEP A — DOWNLOAD MISSING PAPERS (legal open access only)
================================================================
A1. Inventory. For every item in paper_template/reading_list.json, check whether its full PDF is already on disk in: output/pdf/, output/pdf/active_region_comparisons_2026-09-25/, output/flare_forecast_literature/, Papers/, output/papers_downloaded/. Match by the TITLE on the PDF's first page (pdftotext), not by filename. Treat arXiv and journal versions of the same paper as one item. Report each item as ON DISK or MISSING.

A2. Download each MISSING paper only from legal open sources, in this order:
   (a) arXiv: https://arxiv.org/pdf/<arXiv id> — at most one request every 3 seconds (arXiv policy);
   (b) the publisher's page when the article is open access (e.g. SWSC, Frontiers, Science Advances, AGU Space Weather open-access articles);
   (c) a NASA ADS full-text link only if it points to an open-access copy.
   If a paper is paywalled with no open version, do NOT download it. Mark it "NOT OPEN ACCESS — students to request via library or author" and do not cite it in Step B.

A3. Save each download as output/papers_downloaded/<firstauthor>_<year>_<shortkey>.pdf. Verify the first-page title matches the expected title. If it does not match, move the file to output/papers_downloaded/_mismatch/ and report it.

A4. The file output/pdf/doria_rosales_2026_multimodal_forecast.pdf contains a different paper (Brevi et al., deuteron physics). Search decisions.md and the project notes for the title or identifier of the intended paper. If found and open access, download it (A2–A3). If it cannot be identified, report that and do not cite it. Do not delete or rename the wrong file.

A5. Write output/papers_downloaded/papers_manifest.csv with columns: key, title, first author, year, identifier (arXiv/DOI), source URL, sha256, local path, status (ON DISK / DOWNLOADED / NOT OPEN ACCESS / MISMATCH / NOT IDENTIFIED).

A6. Commit the PDFs and manifest; append a short factual entry to decisions.md. Report counts by status. Then continue to Step B, unless a download failed in a way you cannot explain — in that case STOP and report.

================================================================
STEP B — WRITE SECTION 2 "BACKGROUND AND RELATED WORK"
================================================================
OUTPUTS
- paper_template/sections/background.tex (LaTeX; natbib \citet / \citep; use \AA, $\geq$, --, ``...'' correctly).
- paper_template/sections/background_claims.csv.
- In main.tex, replace only the Background "STUDENTS WRITE" box with \input{sections/background}. Change nothing else.

LENGTH AND TONE
- About 900–1,200 words. Natural, clear academic tone: real terminology, each technical term explained once in plain words. Vary sentence length; avoid stiff filler.
- Do not repeat the Introduction verbatim; expand on it with more detail per study (what was studied, sample size, data, cadence, task, main finding).

STRUCTURE
2.1 Magnetic and sunspot-based flare forecasting — SHARPs (Bobra et al. 2014); Bobra & Couvidat 2015; Bloomfield et al. 2012; Leka et al. 2019 (operational comparison); Barnes et al. 2016; Campi et al. 2019; Falconer et al. 2012 (prior flaring with free energy); Jonas et al. 2018; Nishizuka et al. 2017/2018; any other relevant paper now on disk.
2.2 False alarms and how evaluation choices change measured skill — Camporeale & Berger 2025; Deshmukh et al. 2022 (two-stage false-alarm reduction); Wang et al. 2020 and Sun et al. 2022 (year/region splits, leakage); Chen et al. 2024 (review).
2.3 EUV/UV precursors and coronal variability — Leka et al. 2023; Dissauer et al. 2023 and 2025; Kniezewski et al. 2024; Harra et al. 2026; André-Hoffmann et al. (BADPIT); Zhong et al. 2026; Francisco et al. 2024.
2.4 Flare-label quality — Hu et al. 2025.
2.5 The gap (one paragraph): precursor studies compare flaring with flare-quiet regions, which also differ magnetically and in overall activity; forecasting studies report average skill over all regions; in the studies reviewed here, none tests EUV variability among alarms that a magnetic model rates as similarly hazardous. Use "in the studies reviewed here", never "no one has ever".

CITATION AND ACCURACY RULES
1. Cite ONLY papers whose full PDF is on disk after Step A. Do not cite NOT OPEN ACCESS, MISMATCH or NOT IDENTIFIED items.
2. Every factual claim and every number gets one row in background_claims.csv: claim as written | citation key | PDF path | page | verbatim supporting snippet (<= 40 words) | match type (EXACT quote / PARAPHRASE).
3. Direct quotes must be verbatim, with page number in the citation (\citep[p.~N]{key}). Use at most 3 direct quotes in the whole section.
4. State the scope of each study when it matters (e.g. number of events/regions, channels, cadence, forecast window, flaring vs flare-quiet design). Mark preprints as preprints.
5. No overclaims: do not say a paper "proves" or "shows" more than it states; do not describe a channel's temperature without its caveats (94 Å: Fe XVIII ≈6.3 MK plus cooler ≈1 MK emission — only if supported by a PDF on disk; otherwise omit temperatures).
6. Use citation keys in the form FirstauthorYEAR (e.g. Bobra2014, BobraCouvidat2015, Leka2019, Leka2023). If two papers share a key, add a/b. Keep keys consistent with the Introduction: Bobra2014, BobraCouvidat2015, Bloomfield2012, CamporealeBerger2025, AlatoomNikolaou2026, Deshmukh2022, Leka2023, Kniezewski2024, Harra2026, Nishizuka2017, Jonas2018, Leka2019, Wang2020, Hu2025.
7. Do NOT write references.bib entries (the students write those). Instead output paper_template/sections/background_keys.txt listing each key used with its title, authors, year and identifier, so the students can fetch the BibTeX from NASA ADS.

VERIFICATION
- Run an independent verifier agent (it must not see your reasoning, only the .tex, the CSV and the PDFs) that re-opens each PDF and checks every claims row: page, snippet present, claim supported, no overstatement. Fix or remove every failing claim, then re-run until zero failures.
- Static checks: every \citet/\citep key appears in background_keys.txt; braces balanced; no unescaped _ or &; no school/city/state; no number in the text that is not in the CSV.

REPORT AND STOP
- Commit; append a factual entry to decisions.md.
- Report: word count; papers cited (count and list); claims total, EXACT and PARAPHRASE counts, and claims removed by the verifier; papers not cited and why (NOT OPEN ACCESS / MISMATCH / NOT IDENTIFIED); the commit hash.
- STOP.

## 2026-10-06 — STEP A DONE: missing papers downloaded from legal open sources (code by Claude Code (AI))
- **Inventory.** 47 reading-list items = 45 distinct papers (the arXiv and journal copies of Deshmukh 2022 and of Camporeale & Berger 2025 count once each), matched by the first-page title (pdftotext), not by file name.
- **Status by paper:**
  - ON DISK 31;
  - DOWNLOADED 11;
  - NOT DOWNLOADED 2: Janssens 2025, open access at SWSC but the publisher refuses automated requests (HTTP 403); Amrhein et al. 2019, a Nature comment with no PDF on the publisher page;
  - NOT OPEN ACCESS 1: Efremov 2017, Springer paywall, no arXiv version;
  - NOT IDENTIFIED 1: the paper intended for output/pdf/doria_rosales_2026_multimodal_forecast.pdf. That file holds Brevi et al., arXiv:2602.11193, and was left in place unrenamed. No title or identifier of the intended paper was found in decisions.md or the project notes.
- **Sources.** Downloads are arXiv PDFs only, at ≥ 3 s between requests: Hudson 2023, Park 2010, Korsos 2014, Korsos 2015, Leka 2019 (paper III), Kniezewski 2025, Francisco 2024, Bobra 2014, Pietrow 2026; plus the arXiv versions of Georgoulis 2021 (FLARECAST, arXiv:2105.05993) and Tong 2018 (arXiv:1608.03109).
- **Checks.** Every download had its first-page title checked: 0 mismatches, so output/papers_downloaded/_mismatch/ is empty.
- **Manifest.** output/papers_downloaded/papers_manifest.csv lists key, title, first author, year, identifier, source URL, sha256, local path, status and note.
- No Sci-Hub, LibGen or paywall workaround; no solar-data download; no file deleted.

## 2026-10-06 — STEP B (interim commit): Section 2 "Background and related work" written (text drafted by Claude Code (AI); decided by: user)
- **Files.**
  - paper_template/sections/background.tex: about 1,199 words, subsections 2.1–2.5.
  - paper_template/sections/background_claims.csv: 121 rows (EXACT 2, PARAPHRASE 118, SYNTHESIS 1).
  - paper_template/sections/background_keys.txt: 27 keys.
  - paper_template/main.tex: only the Background "STUDENTS WRITE" box was replaced, by \input{sections/background}.
- **Papers cited (27, all with the PDF on disk).** AlatoomNikolaou2026, AndreHoffmann2026, Barnes2016, Bloomfield2012, Bobra2014, BobraCouvidat2015, Campi2019, CamporealeBerger2025, Chen2024, Deshmukh2022, Dissauer2023, Dissauer2025, Falconer2012, Francisco2024, Harra2026, Hu2025, Jonas2018, Kniezewski2024, Leka2019, Leka2019b, Leka2023, LekaBarnes2007, Nishizuka2017, Nishizuka2018, Sun2022, Wang2020, Zhong2026.
- **Deterministic checks: PASS.**
  - Every snippet is found on its stated PDF page (pdftotext) and is ≤ 40 words.
  - Every claim fragment appears verbatim in background.tex.
  - Every cited key is in the keys file and has a claims row.
  - Braces balance; there is no unescaped _ or &; there is no school, city or state name.
  - Every number in the text appears in a claims row.
- **Independent verification: NOT YET COMPLETE at this commit.** Five independent verifier agents (seeing only the .tex, the CSV and the PDFs) were still running when the user asked for the file immediately. Their results, any fixes or removals, and the final counts will be appended as a follow-up entry.
- **Known limits.**
  - preamble.tex does not load natbib, so background.tex defines fallback \citet/\citep with \providecommand; adding natbib and writing references.bib is the students' step.
  - main.tex is generated by build_tex.py, so a rebuild drops the \input line.
  - overleaf_upload.zip and check_tex.py were not updated.
  - No LaTeX installation on this machine, so the section was not test-compiled.

## 2026-10-06 — STEP B DONE: Section 2 independently verified, zero failures (text and checks by Claude Code (AI); decided by: user)
- Follows the interim entry above (commit cec3186). Three rounds of independent verification. Each round used fresh agents that saw only background.tex, background_claims.csv, background_keys.txt and the PDFs, never the drafting reasoning.
  - **Round 1:** 4 row verifiers and 1 coverage reviewer. 9 of 121 rows FAILED, and the coverage reviewer raised 12 substantive problems.
  - **Round 2:** all 123 rows PASS. The coverage reviewer found 2 MUST_FIX overgeneralisations:
    - CamporealeBerger2025: FARs > 90% only for X-class flares;
    - Kniezewski2024: the 4-hour rise only for the C- and M-class flares.
  - **Round 3:** all 125 rows PASS; coverage 0 MUST_FIX, 7 MINOR.
- **Claims removed by the verifier (4):**
  - Zhong2026 "in 14 events" (the count is ambiguous in the source);
  - Dissauer2025 "a preprint" (the reference list of AndreHoffmann2026, PDF p.20, cites it as ApJ 984, 153);
  - Kniezewski2024 as support for "groups differ magnetically" (its controls were matched by magnetic complexity, and it has no magnetic data);
  - AlatoomNikolaou2026 as an example of whole-test-set-only reporting (it analyses its false positives).
- **Claims corrected after verifier findings:**
  - Flare-class scope or conditions restored:
    - AlatoomNikolaou2026: false-positive regions had no ≥M flare;
    - CamporealeBerger2025: persistence comparison for M-class; FAR > 90% for X-class;
    - Falconer2012: 5–10× at a proxy of about 10^4 G;
    - Kniezewski2024: C- and M-class only.
  - Hedges restored:
    - Leka2019b: "appeared to improve", trends weak;
    - Sun2022: "argue";
    - Chen2024: "notes";
    - Bobra2014 / Zhong2026 wording.
  - Harra2026 timing changed to "a few minutes before the GOES X-ray maximum".
  - Hu2025: the label sources are now named (Science-Quality vs SWPC-FTP).
  - The gap paragraph and the SYNTHESIS sentence were rewritten. The gap is limited to the studies reviewed and to "a sample of alarms that a magnetic forecasting model rates as similarly hazardous". It acknowledges the magnetic-complexity matching of Kniezewski2024 and the same-region quiet epochs of Dissauer2025.
- **Final state:**
  - background.tex: about 1,203 words;
  - 27 papers cited, all PDFs on disk;
  - background_claims.csv: 125 rows (EXACT 2, PARAPHRASE 122, SYNTHESIS 1);
  - background_keys.txt: 27 keys.
  - Deterministic checks PASS: snippet on page and ≤ 40 words; claim fragments verbatim in the .tex; keys listed; braces; no unescaped _ or &; no school, city or state in the .tex, the CSV or the keys file; every number in a claims row.
- **Round-3 MINOR notes not applied** (text judged correct; listed for the students):
  - CamporealeBerger2025's FAR > 90% figure is at TSS-optimised thresholds;
  - Harra2026's variability peak is during the flare rise, and its high-free-energy sites come from a flare-prediction model, the closest single-region precedent to this project;
  - Leka2019b says "arguably weak";
  - the placement of "in an arXiv preprint" in the AndreHoffmann2026/Zhong2026 sentence;
  - two snippets could be stronger (Leka2023 p.25; Chen2024 title).
- **Not cited:**
  - NOT DOWNLOADED: Janssens2025, Amrhein2019;
  - NOT OPEN ACCESS: Efremov2017;
  - NOT IDENTIFIED: the paper intended for the doria_rosales file;
  - MISMATCH: none;
  - on disk but outside the scope or length of this section: Galvez2019, Georgoulis2012, Georgoulis2021, Hudson2023, Kniezewski2025, Korsos2014, Korsos2015, Korsos2019, Lee2020, Nishizuka2021, Park2010, Pietrow2026, Roy2025, Tong2018, Wang2022.

## 2026-10-06 — MERGED Section 2 installed; one independent verification round: 1 FAIL left unfixed by instruction (checks and claims by Claude Code (AI); decided by: user)
- **Merge source.** Commit 740ece8 (Claude Code, verified) plus corrections made in chat by Claude (AI, chat), approved by the user. The AI drafting is disclosed in the AI-use statement.
  - paper_template/sections/background_merged.tex (SHA-256 fcc143341f0dfbf1…, prefix checked) was copied verbatim over background.tex.
  - background_merged.tex is kept and committed. No wording was changed or trimmed.
- **Claims.** background_claims.csv was rebuilt with 172 rows: EXACT 1, PARAPHRASE 164, SYNTHESIS 3, PROJECT 4.
  - Every sentence and every cell of the comparison table tab:bg-compare has a row.
  - The PROJECT rows ("This work" cells; "That comparison is the subject of this project.") cite decisions.md lines 3079 and 3845.
  - The page column header states that pages are 1-based indices of the PDF on disk. These are the arXiv versions, except the journal-version PDFs of Deshmukh2022, LekaBarnes2007, Falconer2012, AlatoomNikolaou2026 and Harra2026.
  - Every page-pinned citation (Bobra2014, Bloomfield2012, Francisco2024, CamporealeBerger2025, Kniezewski2024, AndreHoffmann2026) points to an arXiv PDF, consistent with the section's footnote.
- **Changed rows.** No sentence of the merged text is word-for-word identical to 740ece8, so no earlier row was kept unchanged. All 172 rows were treated as changed or new.
- **Verification.** One independent round: 6 fresh verifiers that saw only the .tex, the CSV and the PDFs. All 172 rows were returned: 167 PASS, 1 FAIL, 4 UNVERIFIED.
  - The 4 UNVERIFIED rows are the PROJECT rows, whose source the verifiers may not read. Their snippets were checked deterministically against decisions.md lines 3079 and 3845.
- **FAIL (not fixed, as instructed): Hu2025, §2.4.**
  - Sentence: "In the 2023--2024 high-activity period, the science-quality-trained models did better on every measure except the logistic model's TSS, while SWPC-trained models had the lower false-alarm ratio in every test period."
  - PDF p.26: "During the high-activity period (2023–2024), when the positive-sample ratio exceeds 0.85, the Science-Quality trained models achieve better performance except for the TSS score of the logistic models. [...] Across all test periods, models trained with SWPC-FTP lists achieve lower FAR".
  - Table 15 (PDF p.43, 24 h, 2023–2024) gives logistic FAR 0.10 (science-quality) against 0.02 (SWPC), so FAR is a second exception.
  - "every measure" is not in the source and contradicts the sentence's own second clause.
- **Keys.** background_keys.txt now lists the journal versions confirmed on Crossref (2026-10-06):
  - Kniezewski2024: ApJL 977, L29, doi:10.3847/2041-8213/ad94dd;
  - AndreHoffmann2026: Sol. Phys. 301, 107, doi:10.1007/s11207-026-02701-6;
  - Dissauer2025: ApJ 984, 153, doi:10.3847/1538-4357/adbf13;
  - Zhong2026: ApJ 1000, 114, doi:10.3847/1538-4357/ae48e5.
  - The PDFs on disk are the arXiv versions, and page numbers refer to them.
- **Deterministic checks: PASS.**
  - Snippets are on the stated page and ≤ 40 words; PROJECT snippets are on the stated decisions.md line.
  - Every claim fragment appears verbatim in the .tex, and every sentence and table cell is covered.
  - Keys are listed; braces balance; there is no unescaped _ or & outside the tabular.
  - No school, city or state appears in the .tex, the CSV or the keys file.
  - Every number in the text is in a claims row.
- **Word count.** About 1,690 by the checker, of which about 1,530 is prose and about 140 the table.

## 2026-10-06 — Hu2025 row FAIL from 0ac1e3a resolved; wording by Claude (chat), user-approved.
- The one §2.4 sentence in background.tex was replaced verbatim as instructed; nothing else in the file was changed (word diff: only the replaced clause).
- Claims rows 130–131 (Hu2025) were updated to the new fragments. Both keep their PDF p.26 snippets.
- **Fresh independent verifier on rows 130–131 only: 2 PASS, 0 FAIL.** It cross-checked the claim against Appendix B Tables 12–17 (PDF pp.42–43):
  - the logistic TSS is the exception the authors note;
  - FAR favours SWPC-trained models in every period, which the sentence's "although" clause states.
- Deterministic checks: PASS (172 rows; EXACT 1, PARAPHRASE 164, SYNTHESIS 3, PROJECT 4).

## 2026-10-06 — Colour image versions of F3/F4 and a rule-selected image gallery (figures by Claude (AI, chat), at the user's request; rule recorded before any gallery pair was identified or viewed)
- **Why.** The user asked for more solar images and colour versions of the existing figures. Illustration only: no analysis, number, status label or reading changes.
- **F4 (colour).** Same pair as the 983bcae rule (true 13708_20250830T1359, false 12889_20250313T0659). Adds the stored HMI line-of-sight magnetogram at t (file nearest t) with the HARP outline, and shows the stored AIA 94 Å cutout nearest to and not after t in the standard AIA 94 colour table. One display scale for both AIA images and one for both magnetograms (±1000 G).
- **F3 (colour).** Same episode (true member of the F4 pair). Adds five AIA 94 Å thumbnails at the stored valid frames nearest to t−24, −18, −12, −6 and 0 h, on one display scale; the series and residual panels are unchanged and the stored CV_box must still be reproduced to 1e-12.
- **Gallery rule (new figure).** Rank the 50 TEST 1 pairs in data/euv_confirm/twins_le2.csv by r = CV_box(true)/CV_box(false), ascending, ties by file order (as examples.select_pair). Take the nearest-rank 10th, 35th, 65th and 90th percentiles: positions 5, 18, 33 and 45 (1-based). For each pair show the stored magnetogram nearest t and the stored AIA 94 Å cutout nearest to and not after t, for both members, with r printed. Pairs are not replaced or re-chosen after viewing, whatever they look like.
- Scripts go in paper_template/figures/ (f3_cvbox_color.py, f4_twin_pair_color.py, f10_gallery.py); outputs are new files, existing figure files are not overwritten.
- **Amendment (same day, after one gallery panel was seen).** For HARP 13726 (true member at the 10th percentile) the stored AIA frame nearest to and not after t (2025-09-03 20:59) has QUALITY 65536 and exposure 0 s; the pipeline marks it invalid (valid_primary = False) and it displays as a black panel. The image rule for F4 (colour) and the gallery is amended to: the stored frame nearest to and not after t **among frames with valid_primary = True** in data/euv_confirm/series/. This changes only that one panel (it becomes the 20:47 frame); the four pairs, their order and r are unchanged. In every other panel the nearest frame is already valid.

## 2026-10-07 — Physics study guide and fix list (AI use, drafted by Claude AI (Claude Code) at the user's request; to be entered in the prompt log)
- **File:** docs/physics_study_guide_2026-10-07.md. It is a reading map for the students, not paper text. It says explicitly that nothing in it may be copied into the abstract, paper, synopsis or video.
- **Physics sources.** Every physics point cites a PDF on disk and a page. The 70 supporting passages were collected by 5 agents and each was checked deterministically against its pdftotext page: 70 found, 0 failed.
  - No 94 Å temperature is stated beyond André-Hoffmann 2026 p.4 (about 0.6 MK to 5–6 MK). The Fe XVIII peak temperature is attributed to Lemen et al. 2012, which is not on disk.
- **ISEF table.** The guide summarises the Society for Science "Use of generative AI to support a research project" table (Oct 2025), fetched 2026-10-07. Rows marked never acceptable that apply to this project:
  - AI-written first draft of the paper or abstract (including the AI-written Section 2);
  - AI-provided citations backing claims;
  - AI data collection;
  - AI-produced conclusions or future steps (the C+ rule).
  - The guide lists student-only remedies and leaves every decision to the students.
- **Mechanical fixes listed (not applied):**
  - unclustered sign-test p-value (paper p.20 l.529);
  - Acknowledgements placeholder;
  - Amrhein and Campi reference TODOs, with values confirmed on Crossref 2026-10-07: Nature 567(7748):305–307; ApJ 883(2):150;
  - "å" typo in the Kniezewski title;
  - Kniezewski timing given two ways (2–3 h from their abstract vs rising from 4 h and peaking 1–2 h from their body);
  - Introduction numbers not covered by the Section 2 claim check.
- **Deliberately not included:** new analyses or future steps.

## 2026-10-09 — User clarification of pattern-discovery chronology (recorded by Codex at the user's request)

**User statement, verbatim:**
> but i only saw this pattern in test data
>
> 2010 to 2019
>
> then i implemented in 2020 to 2026

The user asked Codex to change this decision log after the discussion of the C+ rule's post-hoc status. The account recorded here is that the user identified the pattern in 2010–2019 data before applying it to later years. In this project's established terminology, 2010–2019 is the development period, not the held-out test period. The actual later evaluation cohorts are 2021/2023/2024, a separate 2022 sensitivity cohort, and 2025–2026; 2020 is excluded.

**Conflict requiring verification.** The 2026-09-28 C+ entry above records the complete protection rule as designed after inspection of all 2010–2026 alarms. That entry also explicitly records that the same pattern is visible in 2010–2019 alone. The user's current account and the earlier entry must both remain visible: discovering a pattern in development data and fixing the complete rule before examining later outcomes are separate chronology questions.

**Evidence status.** This is a clarification reported by the user on 2026-10-09, not a backdated pre-registration or an independently verified historical timestamp. No earlier dated record fixing the complete C+ rule before examination of later outcomes was supplied with this correction request. The chronology of that rule remains unresolved pending reconciliation with the original prompts, dated decisions and Git history. A development-only origin must not be rejected merely because the pattern also occurs in later data; equally, its presence in development data alone does not establish an untouched later evaluation.

**Scope.** This entry does not change any data, model, threshold, numerical result, original dated entry or registered test reading. It does not retrospectively reclassify the existing C+ evaluations as independent confirmation. The original restlessness hypothesis and the later C+ protection rule remain distinct analyses.

## 2026-10-09 — LOOK 1 RUNS EARLY: AMENDMENT OF RUN DATE AND END DATE ONLY (decided by: user; wording drafted by Claude Code (AI); recorded BEFORE any prospective data are downloaded or analysed)

**Decision (user).** Look 1 of the prospective test (2f62f88 / eb3e7d5, amended in b480d22 and 5a6d106) runs early. Only the run date and the end date E change.

- **Run date.** Look 1 runs once, on the user's command "run the prospective test once". The command may now be given before 2026-11-10; previously it was "not before 2026-11-10" (2f62f88, 8aa1797).
- **Set.** Alarm episodes with t in [2026-08-17 00:00 TAI, E], where **E = 2026-09-03 23:00 TAI**.
- **How E was set.** E uses the registered definition (2f62f88): E = min(2026-10-31 23:00 TAI, latest T_REC with complete SHARP + SWPC + GOES coverage, allowing 24 h of label follow-up after each t). It was measured on 2026-10-09 by a metadata-only check (`prospective_look1_coverage.py`, log `prospective_look1_coverage.log`):
  - **SHARP `hmi.sharp_cea_720s`.** Records exist at every daily 00:00 TAI slot from 2026-08-17 to 2026-09-04. The last slot with records is 2026-09-04 00:00 TAI (18 records), and no hour after it has records. The last full SHARP day is 2026-09-03. **SHARP is the limiting source.**
  - **Hourly check (counts only):** 429 of 432 hourly slots from 2026-08-17 00:00 to 2026-09-03 23:00 TAI have records. There are no records at 2026-08-19 19:00, 2026-08-26 19:00 and 2026-09-02 19:00 TAI (all Wednesdays). Missing hours are handled by the registered cohort rules (749208e), as in the 2025–26 set, where 627 of 14,232 hourly slots had no record in the downloaded file. Decided by: user ("approved with the missing hours").
  - **SWPC daily event reports** (NCEI file listing): 2026-08-15 → 2026-10-08, none missing.
  - **GOES-18 and GOES-19 XRS 1-min science files** (NCEI file listing): 2026-08-17 → 2026-10-08, none missing.
  - As with the 2025–26 set (e3e4075), the set ends at 23:00 TAI on the last full SHARP day. SWPC and GOES cover every episode's windows:
    - the 24-h label window;
    - the 48-h "delayed" window, reaching 2026-09-05 23:00 TAI at most;
    - the 48-h history window.
- **Reason.** A schedule change before the IRIS submission deadline.

**Evidence that no prospective data have been viewed** (Step 0, 2026-10-09; read-only, no file opened):
- The only files on disk with observation dates on or after 2026-08-17 are:
  - the two SWPC daily reports disclosed in b480d22 (`data/swpc_events/20260817events.txt`, `20260818events.txt`);
  - the items derived from them that b480d22 lists.
- Nothing has changed since the 2026-10-05 audit: no file under `data/` was modified after b480d22 (2026-10-05 16:00 IST).
- No SHARP record, AIA or HMI image, alarm episode, feature, label or result exists for t ≥ 2026-08-17.
- `data/prospective/` holds development-period values only.
- No solar-data file from the prospective period exists elsewhere in the user's home folder. This was checked by file name and modification time only.
- The 2026-10-09 coverage check returned only SHARP record counts per time slot and NCEI file names. No keyword value, flare report or image was downloaded or saved.

**Unchanged: every method rule.**
- **Gate, cohort rules and fallbacks:** 749208e (T1–T4, ≤ 2 regions). Frozen gate files and thresholds are used as hashed.
- **Labels:** SWPC originals on the true-flux scale; delayed episodes count as false (2f62f88).
- **Exclusion:** every HARP and every NOAA region present in `data/euv_full`, `euv_test`, `euv_confirm`, `euv_extra`, `euv_pilot` or `euv_cad` is excluded (2f62f88).
- **Download:** exactly as the 2025–26 confirmation download (2f62f88):
  - AIA 94 Å at 12-min cadence over (t − 24 h, t], as tracked im_patch cutouts;
  - HMI magnetogram and bitmap at t;
  - a dry run first;
  - one pending JSOC export at a time, on the user's account only.
  - The prospective SHARP query includes TOTUSJZ, QUALITY and LON_FWT (b2ca7ac).
- **EUV frame and fill rules:** as for the 2025–26 confirmation set (749208e, 2f62f88).
- **Size rule** (2f62f88, b480d22 item 3). It is label-blind and applied before any label is read:
  - fewer than 60 episodes with CV_box defined (fill ≥ 80%) → "TOO SMALL — DESCRIPTIVE ONLY", with the numbers given and no reading;
  - otherwise, the registered mechanical reading.
- **PRIMARY** (2f62f88, eb3e7d5):
  - CV_box magnetic twins: gate score, caliper 0.0747, TEST 1 code (ae1b174);
  - statistic: median true / median false;
  - 95% CI with pairs resampled by true HARP, 2,000 resamples, seed 0;
  - reading: "REPLICATED" / "DIRECTION CONSISTENT, NOT CONFIRMED" / "NOT REPLICATED".
- **Fallback:** if Look 1 returns "TOO SMALL — DESCRIPTIVE ONLY", the PRIMARY runs ONCE on the Look 2 set, on "run the C+ confirmation once", not before 2027-03-15 (b480d22 item 4).
- **SECONDARIES run in Look 1.** None can change the PRIMARY reading.
  - CV6 and BF(a), with the same statistic (eb3e7d5; implementation bb8a137, d2ed360).
  - Magnetic + flare-history twins for CV_box, CV6 and BF(a) (2f62f88, eb3e7d5, b480d22 item 5).
  - Counts of pairs with true > false, and the sign-test p (2f62f88).
  - The PRIMARY recomputed without episodes on 2026-08-17 and 2026-08-18 (b480d22 item 2).
  - COMBO-T outputs 1–3 (9a88d70; frozen models e17a8a3).
  - MR twins ratio, reported only (46207c7, b2ca7ac).
  - C+ rule, descriptive only and with no reading: D_false and D_true against Model C as defined in 8aa1797, with the exact frozen thresholds (784b1a8).
- **Region-reuse diagnostics** are reported as POST-HOC and cannot change any reading. They use the same code as `posthoc_twin_reuse.py`: unique true and false HARPs, their overlap, and the false-HARP, two-way and linked-group intervals.

**Changed by this amendment** (decided before any data are seen):
1. The run date and E, as above.
2. The dependence-free CV_box twins SECONDARY (5a6d106) is **DROPPED from Look 1**, because its clarifications a–e were never decided. Its registration for the Look 2 fallback is unchanged, and a–e must still be decided before any Look 2 data are analysed.

**Separation and single run.**
- Look 1 results are reported separately from the 2025–26 confirmation set (e3e4075, ae1b174). They are never pooled with it or with any earlier set.
- Look 1 runs once only: no re-run with different settings, sets or code. If an error is found after the run, it is reported in decisions.md, and any corrected result is labelled POST-HOC.
- Look 2's rules, data, dates (not before 2027-03-15), size rule and readings are unchanged (8aa1797, 784b1a8, b480d22). No Look 2 rule may be changed because of Look 1 results.

**Who runs what.**
- Every download for Look 1 (SHARP, SWPC, GOES XRS, AIA, HMI) is typed and run by the students (b480d22 item 6), using scripts written by Claude Code.
- The run log records who ran each command and when, and the file counts, sizes and hashes.

## 2026-10-10 — LOOK 1 ANALYSIS CODE: open choices decided (decided by: user; recorded verbatim) and code committed BEFORE any label is read (code by Claude Code (AI))
**Verbatim (user):**

D1–D10: defaults OK (D2 = A, as registered: numbers given, no reading).
D3a: TAI.
D11: OK — students run steps 8–10 with CONFIRM="run the prospective test once".
JSOC address YOUR_EMAIL_HERE belongs to [Lokesh / Kyros].
Record these answers in decisions.md, rerun the checks, commit code + passing reproduction log, add steps 8–10 to the run sheet, report the hash and stop.

**What the answers fix.** The choices are listed in LOOK1_ANALYSIS_DECISIONS.md (committed with this entry).
- **D1 / D11 — who runs it.**
  - The students run steps 8–10: compute, size rule, analysis.
  - The analysis also needs CONFIRM="run the prospective test once".
- **D2 = A — TOO SMALL.** If the size rule says TOO SMALL, every registered statistic is printed as DESCRIPTIVE, with no reading anywhere. The PRIMARY then falls back to Look 2 (b480d22 item 4).
- **D3 / D3a — the 2026-08-17/18 secondary.** Episodes are dropped by the TAI date of t (the T_REC date), and twins are re-matched.
- **D4 — pairs for the other measures.**
  - CV6, BF(a) and MR use the PRIMARY pairs (and the history-matched pairs for CV6/BF(a)).
  - Pairs with an undefined value are dropped, and CV6/BF(a) values ≤ 0 count as undefined.
- **D5 — sign test.** Two-sided binomial, ties excluded.
- **D6 — MR.** MR uses the 2025–26 SHARP chunk for window rows before 2026-08-17.
- **D7 — COMBO-T.**
  - Evaluable set: fill ≥ 0.80 and CV_box > 0.
  - Baseline: the frozen euv_extra Model C at its exact τ.
  - Output 3 bootstrap uses the joint finite mask.
  - The reliability table is unweighted.
- **D8 — C+.** The code that produced the logged 2025–26 numbers, with exact thresholds.
- **D9 — region reuse.** POST-HOC, run on the PRIMARY pairs (≥ 2 pairs).
- **D10 — undefined results.**
  - With 0 pairs, the result is "undefined" and no bootstrap is run.
  - If the PRIMARY ratio is undefined with ≥ 60 episodes, the TEST 1 code gives "NOT REPLICATED", and this is flagged.
- **JSOC address owner.** The answer was left as the placeholder "[Lokesh / Kyros]", so no owner is recorded. The address is kept unchanged, as instructed on 2026-10-09.

**Code (commit below; no prospective data used to write or test it — data/prospective_look1/ holds only an empty logs folder).**
- **prospective_look1_analysis.py** (sha256 db99241273c27445afa5ef9b1d72d72dd41ac1c623eccdee834b350d0512a451), steps 8–10. Registered code is imported, or lifted verbatim where it exists only inline; each lifted block names its source lines.
  - **compute** (label-blind): CV_box, CV6, BF(a) and MR per episode.
  - **sizerule** (label-blind; once).
  - **analysis** (once).
- **Run control, added after two independent code reviews (3 and 2 reviewers):**
  - **Gate:** RUN_BY must be exact; refuses under python -O; refuses unless the analysis code, every local module it uses and frozen/frozen_spec.json are committed and unchanged, and the committed prospective_look1_reproduce.log shows this code's closure sha256 with all checks passing.
  - **Order and hashes:** compute → sizerule → analysis is enforced with hashes of the cohort file and the compute outputs.
  - **Before any label is read:** label-free pre-checks run, then an exclusive marker is written, then an "ANALYSIS START" run-log line is committed to git automatically.
  - **On failure afterwards:** "ANALYSIS FAILED" is logged with no values, and Look 1 counts as used.
  - **Output:** the report is written line by line, and the PRIMARY is saved first. No unregistered statistic (all-episode ratios, C_CV results) is computed or kept.
- **prospective_look1_reproduce.py → prospective_look1_reproduce.log: 40 of 40 checks PASS** (closure sha256 d9c9bb6bd61cf266247a74a2c46c70583dfb6d6d9b6969c85a9f5b59dda9f612).
  - **TEST 1 (full precision):** 3.2624 [1.2956, 9.4887], 50 pairs, "REPLICATED"; history twins 2.8174 [1.0169, 6.8227], 47 pairs; sign tests 39/50 and 35/47.
  - **Region reuse:** the posthoc_twin_reuse.log output, byte-identical.
  - **Frozen-model results:** COMBO-T, C+, Model C and the C vs C_CV bootstrap reproduce their logs exactly.
  - **Dev 2010–19 only** (the registrations forbid computing these on 2025–26): CV6 and BF(a) per episode, and the twins ratios 2.1261, 1.2125 and 1.9661; MR per episode (547, all 42 columns) and E1 1.0814 [0.9193, 1.3109].
  - **Run-control tests (synthetic random labels; never real labels shuffled):**
    - 0, 1, 12, 59 and 387 episodes: no reading wording under TOO SMALL; a reading is printed when ≥ 60; second runs are refused.
    - An injected failure after labels are read is logged and blocks a re-run.
    - Label-free refusals leave no marker.
    - Direct calls on the real folder are refused.
- **Known limit:** step 8 (compute_step) was not run end-to-end in a test. Its parts were verified separately: euv_full.compute_episode as registered, and CV6/BF(a) and MR exactly on dev.

## 2026-10-11 — POST-HOC region-level checks of TEST 1 (requested by: user; code by Claude (AI); first computed informally on 2026-10-10, logged now)
- **Status:** POST-HOC, descriptive, on already-analysed 2025–26 data (twins_le2.csv, results/*.json). No data with t ≥ 2026-08-17 read. Not pre-registered; cannot change the TEST 1 reading.
- **Why:** reviewers asked whether the 3.26 ratio depends on a few regions. These checks were run on 2026-10-10 and the paper must not describe them as "not yet performed".
- **Code / output:** `posthoc_region_checks.py` → `posthoc_region_checks.log`.
- **Results:**
  - Region-level sign: of 18 true-alarm HARPs, the true alarm was more restless in most of its pairs for 14, evenly split for 2, opposite for 2. Two-sided sign test: 14/18 p = 0.031 (ties counted against); 14/16 p = 0.004 (ties excluded).
  - Leave-one-true-HARP-out twins ratio: 2.47 (without 14491) to 3.90 (without 14924).
  - Paired estimate (median of within-pair CV_box ratios): 2.86 [1.67, 5.32]; 2,000 resamples of true-alarm HARPs, seed 20261011 (one-way, like the registered interval).
- **Paper fixes recorded the same day:** TEST 2 thresholds cited to euv_confirm_tests.log (not thresholds.json); filter-model files cited as data/euv_extra/thresholds.json and data/euv_extra/model_hashes.json.
- **Code-side fixes (same day, at the user's request):**
  - Created `data/euv_confirm/thresholds.json` holding the TEST 2 thresholds (A 0.094958, C 0.100840), copied verbatim from `euv_confirm_tests.log:17`, so the paper's "exact values in thresholds.json" points to a real file. Not a new analysis; the log stays the original record. No frozen file was changed.
  - Added 10 rows to `paper_template/numbers_sources.csv` (PostRegMajority, PostRegSignP, PostRegSignPex, PostLooLo, PostLooHi, PostPaired, PostPairedLo, PostPairedHi, TestTwoTauA, TestTwoTauC) tracing the new post-hoc numbers and the TEST 2 thresholds to their logs.
- **Still needed in the paper (cannot be fixed in code):** Section 7 lists the sign test and leave-one-region-out as "not yet performed"; they now have been (post-hoc), so that wording must change.
