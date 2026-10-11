# Look 1 (early) — run sheet

Amendment daff479 · download script b8ad61d · RUN_BY rule 21ed533. Set: t in [2026-08-17 00:00 TAI, **2026-09-03 23:00 TAI**].

**Rules for every step**
- Run one step at a time, in order, in Terminal, from the project folder:
  ```
  cd "<project folder>"
  ```
- Paste the printed output to Claude Code before running the next step.
- Do **not** open any of these until the size rule has run:
  - `data/swpc_events/202608{19–31}events.txt` and `data/swpc_events/202609{01–05}events.txt`;
  - `data/labelled_2026*.csv`;
  - `data/prospective_look1/logs/build_*.log`;
  - `data/prospective_look1/cohort_le2*.csv`;
  - any `data/goes_xrs/g1[89]_2026*.nc`.
- If a step fails or stops, **do not re-run it**. Paste the output to Claude Code.

| # | Who | Command | Expect | Stop if |
|---|---|---|---|---|
| 0 | **Lokesh** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1.py dryrun` | `1 swpc : 22 days 2026-08-15..2026-09-05; already cached 4 (08-15, 08-16, 08-17, 08-18); to download 18 …`. Two `3 sharp:` lines, the second ending `-2026.09.03_23:00_TAI@1h]`. `output files already on disk (must be none): none` | the last line is not `none`; or the end is not `2026.09.03_23:00_TAI` |
| 1 | **Lokesh** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1.py swpc` | `SWPC 2026-08-15..2026-09-05: 22 files, ~0.04 MB on disk; archive 404 days: none; empty-report days: 0; wall … s` | not 22 files; any 404 day; empty-report days > 0; an error |
| 2 | **Lokesh** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1.py goes` | `GOES: no SWPC report in 2026-08-15..2026-09-05 says NO EVENT REPORTS -> no GOES file needed; nothing downloaded (as 2025-26)` | any other message (it then says STOP itself) |
| 3 | **Kyros** | `RUN_BY="Kyros" .venv/bin/python prospective_look1.py sharp` | per chunk: label-free lines (`SHARP rows retrieved`, `after QUALITY==0`, `after \|LON_FWT\|<=45`, `after mapping!=missing`, `saved data/labelled_…`). Last line: `SHARP 2026-08-17 00:00 .. 2026.09.03_23:00_TAI: raw ~6,000–8,000 rows (… HARPs, T_REC 2026-08-17 00:00:00 .. 2026-09-03 23:00:00 TAI), labelled … rows; boundary duplicates dropped raw ~18 / labelled …; 8 files, ~2–3 MB` (a few minutes) | `FAILED` or `Refusing`; the T_REC end is not `2026-09-03 23:00:00`; raw rows < 3,000 |
| 4 | **Lokesh** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1.py cohort` | `COHORT (label-blind): scorable rows …; eligible episodes … (… HARPs, … NOAA regions); not eligible by cohort rules …; excluded by the earlier-EUV rule: {…}; INCLUDED n episodes, h HARPs, r NOAA regions` (n estimated 5–20; a few minutes) | `INCLUDED 0`; any assertion or hash error |
| 5 | **Kyros** | `RUN_BY="Kyros" .venv/bin/python prospective_look1.py plan` | `EUV DRY RUN (nothing submitted): episodes n, HARPs h; exports 2h …; estimated ~0.04 GB per episode; ~0.08 h per HARP` | episodes ≠ step 4's INCLUDED n; more than 5 GB or 6 h |
| 6 | **Kyros** | `RUN_BY="Kyros" .venv/bin/python prospective_look1.py download` | `EUV DOWNLOAD start: n episodes, h HARPs; JSOC account YOUR_EMAIL_HERE; one pending export at a time`, progress lines, then `EUV DOWNLOAD done: … files, … MB; wall … h` (~4–5 min per HARP) | an error or traceback, or it stops: do not re-run, paste the output. **Not finished by 12 Oct → Look 1 is reported as pending** |
| 7 | **Lokesh** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1.py verify` | `VERIFY: HARPs h, episodes n; HMI pairs OK n/n; AIA files …, valid 94 A in range … of expected …; … ; sha256 …`, then `no HARP short of frames` | HMI pairs < n; any HARP with no AIA files or below 97% of its expected frames |

After step 7, STOP. Steps 8–10 use `prospective_look1_analysis.py` (committed; see decisions.md 2026-10-10). Either student may run them: put your own name in RUN_BY. The script refuses to run if any of its code has changed since the commit.

| # | Who | Command | Expect | Stop if |
|---|---|---|---|---|
| 8 | **Lokesh or Kyros** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1_analysis.py compute` (label-blind) | `COMPUTE (label-blind): episodes n; with AIA n; CV_box compute errors 0 []; CV_box defined (fill >= 80%) …; CV6 defined …; BF(a) defined …; block k != 5: 0; box-mean check \|diff\| >= 1e-9: 0; MR defined …; … wall … min` (about 10–20 min; makes JSOC pointing-table keyword queries) | a `STOP:` line; any compute error; `block k != 5` or `box-mean` not 0; `Refusing` |
| 9 | **Lokesh or Kyros** | `RUN_BY="Lokesh" .venv/bin/python prospective_look1_analysis.py sizerule` (label-blind, once) | `SIZE RULE (label-blind; 2f62f88, b480d22 item 3): N of M episodes have CV_box defined (fill >= 80%) -> "TOO SMALL — DESCRIPTIVE ONLY" …` or `-> at least 60: …` | `Refusing`. Paste the output to Claude Code. Do not run step 10 until you have decided to say "run the prospective test once" |
| 10 | **Lokesh or Kyros** | `RUN_BY="Lokesh" CONFIRM="run the prospective test once" .venv/bin/python prospective_look1_analysis.py analysis` (**RUN ONCE**) | `ANALYSIS START …` (a git commit "Look 1 ANALYSIS START" is made automatically before any label is read), then the report lines, then `ANALYSIS DONE (run once) …`. Report saved in `data/prospective_look1/analysis_report.txt` | `Refusing` before START: nothing was read, so fix and retry is allowed. `ANALYSIS FAILED` or `ANALYSIS STOPPED`: **do not re-run**; tell Claude Code |
