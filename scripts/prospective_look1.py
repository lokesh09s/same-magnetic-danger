"""LOOK 1 (EARLY) — downloads and label-blind data build (decisions.md daff479; code by Claude Code (AI)).
Every subcommand is TYPED AND RUN BY A STUDENT (b480d22 item 6): it refuses to run unless RUN_BY is exactly "Lokesh" or "Kyros",
and it appends who ran it, when, the git HEAD and the output file counts, sizes and SHA-256 to prospective_look1_early.log.
Nothing here prints a label, a flare, a flare count or a positive count (the size rule is label-blind, 2f62f88).
Set: t in [2026-08-17 00:00 TAI, 2026-09-03 23:00 TAI]. Outputs: data/prospective_look1/ and the SHARP chunk files in data/.
Order (one at a time; read each printout before the next):
  RUN_BY=<name> python prospective_look1.py dryrun     0. plan only, no network
  RUN_BY=<name> python prospective_look1.py swpc       1. SWPC daily reports 2026-08-15 .. 2026-09-05
  RUN_BY=<name> python prospective_look1.py goes       2. GOES XRS, only for empty-report days (as 2025-26)
  RUN_BY=<name> python prospective_look1.py sharp      3. SHARP keywords + extras (TOTUSJZ ...) and labels
  RUN_BY=<name> python prospective_look1.py cohort     4. frozen gate, cohort rules, earlier-EUV exclusion (no download)
  RUN_BY=<name> python prospective_look1.py plan       5. the registered EUV dry run (nothing submitted)
  RUN_BY=<name> python prospective_look1.py download   6. AIA 94 A cutouts + HMI magnetogram/bitmap, one export at a time
  RUN_BY=<name> python prospective_look1.py verify     7. file checks"""
import glob, hashlib, json, os, re, subprocess, sys, time, warnings
from datetime import datetime, timezone
import numpy as np, pandas as pd

START, END_EXCL, E_TAI = "2026-08-17", "2026-09-04", "2026.09.03_23:00_TAI"
OVERRIDE = f"{END_EXCL}|{E_TAI}"                       # final chunk queried to E inclusive (as 2025-26: e3e4075)
SWPC_LO, SWPC_HI = "2026-08-15", "2026-09-05"          # 48 h history before START .. 48 h ("delayed") after E
CHUNKS = [("2026-08-17", "2026-09-01"), ("2026-09-01", "2026-09-04")]   # = chunks.months(START, END_EXCL)
TAG = "20260817_20260904"
RAW, LAB = f"data/raw_sharp_{TAG}.csv", f"data/labelled_{TAG}.csv"
ROOT, RUNLOG, AMEND = "data/prospective_look1", "prospective_look1_early.log", "daff479"
EUV_DIRS = ["data/euv_full", "data/euv_test", "data/euv_confirm", "data/euv_extra", "data/euv_pilot", "data/euv_cad"]  # 2f62f88
SHOW = re.compile(r"JSOC record set|SHARP rows retrieved|^merged |expected hourly records|^in: |^after |label window overlaps|"
                  r"history_incomplete|^saved data/labelled|^\[\d+/\d+\] .* rows|^done")      # label-free lines only
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
warnings.filterwarnings("ignore")
os.makedirs(f"{ROOT}/logs", exist_ok=True)

WHO = os.environ.get("RUN_BY", "")
if WHO not in ("Lokesh", "Kyros"):        # exact, case-sensitive; requested by the students before any step was run
    sys.exit('Refusing to run: RUN_BY must be exactly "Lokesh" or "Kyros", e.g.  RUN_BY="Lokesh" .venv/bin/python prospective_look1.py swpc')
if subprocess.run(["git", "merge-base", "--is-ancestor", AMEND, "HEAD"]).returncode != 0:
    sys.exit(f"Refusing to run: the Look 1 amendment ({AMEND}) is not in this checkout.")
HEAD = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
CMD = " ".join(sys.argv[1:])


def logrun(msg):
    print(msg)
    open(RUNLOG, "a").write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC | run by {WHO} | HEAD {HEAD} | {CMD} | {msg}\n")


def files_line(paths):
    paths = [p for p in paths if os.path.isfile(p)]
    return f"{len(paths)} files, {sum(os.path.getsize(p) for p in paths) / 1e6:.3f} MB"


def hash_lines(paths):
    for p in paths:
        open(RUNLOG, "a").write(f"    sha256 {H(p)}  {os.path.getsize(p):>11,d} B  {p}\n")


def swpc_days():
    return pd.date_range(SWPC_LO, SWPC_HI, freq="D")


def empty_days():
    return [d for d in swpc_days() if os.path.exists(f := f"data/swpc_events/{d:%Y%m%d}events.txt")
            and "NO EVENT REPORTS" in open(f, encoding="latin-1").read()]


def episodes():
    """INCLUDED Look 1 episodes (harpnum, t, noaa_ars, t_rec_tai, eid); no label column (as euv_confirm.episodes_confirm)."""
    e = pd.read_csv(f"{ROOT}/cohort_le2.csv", usecols=["harpnum", "t", "noaa_ars"], parse_dates=["t"])
    e["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(e.harpnum, e.t)]
    lab = pd.read_csv(LAB, usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"], low_memory=False)
    e = e.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all()
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


sub = sys.argv[1:]

if sub == ["dryrun"]:
    cached = [d for d in swpc_days() if os.path.exists(f"data/swpc_events/{d:%Y%m%d}events.txt")]
    clash = [p for a, b in CHUNKS for k in ("raw_sharp", "raw_sharp_extra", "labelled") for p in [f"data/{k}_{a}_{b}.csv".replace("-", "")] if os.path.exists(p)]
    logrun("DRY RUN (no network, nothing written except this log line)")
    print(f"  1 swpc : {len(swpc_days())} days {SWPC_LO}..{SWPC_HI}; already cached {len(cached)} "
          f"({', '.join(f'{d:%m-%d}' for d in cached)}); to download {len(swpc_days()) - len(cached)} small text files (~2 KB each)")
    print(f"  2 goes : only for SWPC days whose report says NO EVENT REPORTS (decided after step 1); 2025-26 needed none")
    for a, b in CHUNKS:
        end = E_TAI if b == END_EXCL else b.replace("-", ".") + "_TAI"
        print(f"  3 sharp: hmi.sharp_cea_720s[][{a.replace('-', '.')}_TAI-{end}@1h] keywords only (+ extras incl. TOTUSJZ; QUALITY, LON_FWT in the main set)")
    print("           expected about 6,000-8,000 raw rows in total (~0.8 MB raw + ~0.7 MB extras); labelled file ~0.3 MB")
    print(f"  4 cohort / 5 plan / 6 download / 7 verify: after step 3; step 5 is the registered EUV dry run (episodes, exports, GB, hours)")
    print(f"  output files already on disk (must be none): {clash or 'none'}")

elif sub == ["swpc"]:
    import swpc
    t0 = time.time(); missing = swpc.download_range(SWPC_LO, SWPC_HI)
    paths = [f"data/swpc_events/{d:%Y%m%d}events.txt" for d in swpc_days()]
    logrun(f"SWPC {SWPC_LO}..{SWPC_HI}: {files_line(paths)} on disk; archive 404 days: {[f'{d:%Y-%m-%d}' for d in missing] or 'none'}; "
           f"empty-report days: {len(empty_days())}; wall {time.time() - t0:.0f} s")
    hash_lines([p for p in paths if os.path.exists(p)])

elif sub == ["goes"]:
    e = empty_days()
    if not e:
        logrun("GOES: no SWPC report in 2026-08-15..2026-09-05 says NO EVENT REPORTS -> no GOES file needed; nothing downloaded (as 2025-26)")
    else:
        import goes_xrs
        before = set(glob.glob("data/goes_xrs/*.nc")); rows = [goes_xrs.day_max(d) for d in e]
        new = sorted(set(glob.glob("data/goes_xrs/*.nc")) - before)
        logrun(f"GOES: {len(e)} empty-report days {[f'{d:%Y-%m-%d}' for d in e]}; downloaded {files_line(new)}. "
               "STOP: data/goes_empty_days.csv must be updated by the goes_xrs.py rules (E, H, I) before step 3; tell Claude Code.")
        hash_lines(new)

elif sub == ["sharp"]:
    env = dict(os.environ, JSOC_END_OVERRIDE=OVERRIDE, FLARE_SOURCE="swpc")
    outs = [f"data/{k}_{a}_{b}.csv".replace("-", "") for a, b in CHUNKS for k in ("raw_sharp_extra", "raw_sharp", "labelled")]
    if any(os.path.exists(p) for p in outs + [RAW, LAB]):
        sys.exit(f"Refusing to run: output files already exist: {[p for p in outs + [RAW, LAB] if os.path.exists(p)]}")
    if empty_days() and not os.environ.get("GOES_DONE"):
        sys.exit("Refusing to run: empty SWPC days exist; finish step 2 with Claude Code first.")
    t0 = time.time()

    def run(args, logname):
        for attempt in range(1, 6):                       # same retry rule as run_all.py
            r = subprocess.run([sys.executable] + args, capture_output=True, text=True, env=env)
            open(f"{ROOT}/logs/{logname}", "a").write(f"--- attempt {attempt}, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n{r.stdout}\n{r.stderr}\n")
            if r.returncode == 0:
                return r.stdout
            if attempt == 5 or not any(k in r.stderr for k in ("timed out", "Timeout", "URLError", "Connection", "IncompleteRead", "503", "502")):
                sys.exit(f"{' '.join(args)} FAILED (see {ROOT}/logs/{logname}); nothing else run. Tell Claude Code.")
            time.sleep(60 * attempt)

    out = run(["fetch_extra.py", START, END_EXCL], "fetch_extra.log")
    print("\n".join(l for l in out.splitlines() if SHOW.search(l)))
    for a, b in CHUNKS:
        out = run(["build_dataset.py", a, b], f"build_{a}_{b}.log".replace("-", ""))
        print(f"chunk {a}..{b}:\n  " + "\n  ".join(l.strip() for l in out.splitlines() if SHOW.search(l.strip())))

    def dedup(df, key):                                   # run_all.py: JSOC ranges include both ends -> identical boundary copies
        for _, g in df[df.duplicated(key, keep=False)].groupby(key):
            assert len(g.astype(str).drop_duplicates()) == 1, f"non-identical duplicates {g.iloc[0][key].tolist()}"
        return df.drop_duplicates(key).reset_index(drop=True), int(df.duplicated(key).sum())

    raw, n1 = dedup(pd.concat([pd.read_csv(f"data/raw_sharp_{a}_{b}.csv".replace("-", ""), low_memory=False) for a, b in CHUNKS], ignore_index=True), ["HARPNUM", "T_REC"])
    lab, n2 = dedup(pd.concat([pd.read_csv(f"data/labelled_{a}_{b}.csv".replace("-", ""), low_memory=False) for a, b in CHUNKS], ignore_index=True), ["harpnum", "t_rec_tai"])
    tr = pd.to_datetime(raw.T_REC.str.replace("_TAI", ""), format="%Y.%m.%d_%H:%M:%S")
    assert tr.min() >= pd.Timestamp("2026-08-17 00:00") and tr.max() <= pd.Timestamp("2026-09-03 23:00"), (tr.min(), tr.max())
    raw.to_csv(RAW, index=False); lab.to_csv(LAB, index=False)
    logrun(f"SHARP {START} 00:00 .. {E_TAI}: raw {len(raw)} rows ({raw.HARPNUM.nunique()} HARPs, T_REC {tr.min()} .. {tr.max()} TAI), "
           f"labelled {len(lab)} rows; boundary duplicates dropped raw {n1} / labelled {n2}; {files_line(outs + [RAW, LAB])}; wall {(time.time() - t0) / 60:.1f} min")
    hash_lines(outs + [RAW, LAB])

elif sub == ["cohort"]:
    import joblib, cohort, swpc, euv_extra
    SPEC = json.load(open("frozen/frozen_spec.json"))
    assert H("cohort.py") == SPEC["cohort"]["code_sha256"], "cohort.py differs from the frozen code"
    F, THR = SPEC["gate"]["features"], SPEC["gate"]["threshold"]
    lab = pd.read_csv(LAB, parse_dates=["t_rec_utc"], low_memory=False)
    d = lab[~lab[F].isna().any(axis=1)].reset_index(drop=True)
    X = d[F].to_numpy(float); dv = np.zeros(len(d))
    for v in SPEC["gate"]["fold_models"].values():
        assert H(v["path"]) == v["sha256"]; g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
    d["score"] = dv / len(SPEC["gate"]["fold_models"])
    s = d[d.noaa_ar_count <= 2]                                              # 749208e: <= 2 regions
    c, x, _ = cohort.build(s[["harpnum", "t_rec_utc", "score"]].merge(s.drop(columns="score"), on=["harpnum", "t_rec_utc"]),
                           lab[lab.harpnum.isin(set(s.harpnum))], THR, swpc.label_missing_days())
    euv_extra.EUV_DIRS = EUV_DIRS                                           # the six directories named in 2f62f88
    exH, exR, src = euv_extra.excluded_ids()
    prev = pd.read_csv("data/labelled_20250101_20260817.csv", usecols=["harpnum", "noaa_ars"], low_memory=False)
    both = pd.concat([lab[["harpnum", "noaa_ars"]], prev])
    reg = both.groupby("harpnum").noaa_ars.apply(lambda v: set().union(*[euv_extra.ars(z) for z in v.dropna()]))
    c["reason"] = ["HARP in EUV directories" if h in exH else "NOAA region in EUV directories" if reg.get(h, set()) & exR else "INCLUDED"
                   for h in c.harpnum]
    c.to_csv(f"{ROOT}/cohort_le2_all_eligible.csv", index=False); x.to_csv(f"{ROOT}/exclusions_le2.csv", index=False)
    inc = c[c.reason == "INCLUDED"].drop(columns="reason"); inc.to_csv(f"{ROOT}/cohort_le2.csv", index=False)
    json.dump(dict(harps=sorted(exH), regions=sorted(exR), sources=src), open(f"{ROOT}/excluded_ids.json", "w"))
    nreg = lambda df: len(set().union(*[euv_extra.ars(v) for v in df.noaa_ars.dropna()])) if len(df) else 0
    logrun(f"COHORT (label-blind): scorable rows {len(d)}, <=2-region rows {len(s)}; eligible episodes {len(c)} ({c.harpnum.nunique()} HARPs, "
           f"{nreg(c)} NOAA regions); not eligible by cohort rules {len(x)}; excluded by the earlier-EUV rule: "
           f"{c[c.reason != 'INCLUDED'].groupby('reason').harpnum.agg(['size', 'nunique']).rename(columns={'size': 'episodes', 'nunique': 'HARPs'}).to_dict('index') or 'none'}; "
           f"INCLUDED {len(inc)} episodes, {inc.harpnum.nunique()} HARPs, {nreg(inc)} NOAA regions")
    hash_lines([f"{ROOT}/cohort_le2.csv", f"{ROOT}/cohort_le2_all_eligible.csv", f"{ROOT}/exclusions_le2.csv", f"{ROOT}/excluded_ids.json"])

elif sub == ["plan"]:
    from euv_full import expected_frames
    e = episodes(); aia = sum(expected_frames(g) for _, g in e.groupby("harpnum")); hmi = 2 * len(e); H_ = e.harpnum.nunique()
    x = pd.read_csv("data/euv_test/exports.csv"); bpf = x.bytes.sum() / x.files.sum()
    model = lambda n_exp, files: 72 * n_exp + 0.2 * files                     # same estimate as euv_confirm.py plan
    ratio = 7.24 / (model(len(x), x.files.sum()) / 3600)
    logrun(f"EUV DRY RUN (nothing submitted): episodes {len(e)}, HARPs {H_}; exports {2 * H_} ({H_} HMI + {H_} AIA); expected files "
           f"AIA {aia}, HMI {hmi}; estimated {(aia + hmi) * bpf / 1e9:.2f} GB; estimated {(model(H_, aia) + model(H_, hmi)) / 3600 * ratio:.2f} h")

elif sub == ["download"]:
    import euv_full
    euv_full.R = ROOT
    eps = episodes(); t0 = time.time()
    logrun(f"EUV DOWNLOAD start: {len(eps)} episodes, {eps.harpnum.nunique()} HARPs; JSOC account {euv_full.EMAIL}; one pending export at a time")
    euv_full.run_pipeline(eps, ROOT, progress_every=1800, compute=False)
    paths = sorted(glob.glob(f"{ROOT}/aia/*/*.fits") + glob.glob(f"{ROOT}/hmi/*/*.fits"))
    logrun(f"EUV DOWNLOAD done: {files_line(paths)}; wall {(time.time() - t0) / 3600:.2f} h")

elif sub == ["verify"]:
    from astropy.io import fits
    from euv_full import expected_frames, valid_fits, hmi_files, trec_of
    eps = episodes(); rows = []
    for h, g in eps.groupby("harpnum"):                                      # same checks as euv_confirm.py verify
        hd, ad = f"{ROOT}/hmi/{h}", f"{ROOT}/aia/{h}"
        ok = sum(1 for x in g.t_rec_tai if (lambda mb: mb[0] and mb[1] and all(int(fits.getheader(f, 1)["HARPNUM"]) == h and
                 str(fits.getheader(f, 1)["T_REC"])[:19] == x[:19] for f in mb))(hmi_files(hd, x) if os.path.isdir(hd) else (None, None)))
        files = sorted(glob.glob(f"{ad}/*.fits")) if os.path.isdir(ad) else []
        lo, hi = g.t.min() - pd.Timedelta("24h") + pd.Timedelta("11min"), g.t.max() + pd.Timedelta("1min")
        wl = [p for p in files if valid_fits(p) and int(fits.getheader(p, 1 if len(fits.open(p)) > 1 else 0).get("WAVELNTH", -1)) == 94]
        rows.append(dict(harpnum=h, episodes=len(g), hmi_pairs_ok=ok, aia_expected=expected_frames(g), aia_files=len(files),
                         aia_ok=sum(lo <= trec_of(p) <= hi for p in wl)))
    v = pd.DataFrame(rows); v.to_csv(f"{ROOT}/verify_per_harp.csv", index=False)
    paths = sorted(glob.glob(f"{ROOT}/aia/*/*.fits") + glob.glob(f"{ROOT}/hmi/*/*.fits"))
    digest = hashlib.sha256("".join(H(p) for p in paths).encode()).hexdigest()
    logrun(f"VERIFY: HARPs {len(v)}, episodes {v.episodes.sum()}; HMI pairs OK {v.hmi_pairs_ok.sum()}/{v.episodes.sum()}; AIA files {v.aia_files.sum()}, "
           f"valid 94 A in range {v.aia_ok.sum()} of expected {v.aia_expected.sum()}; {files_line(paths)}; sha256 of all file hashes {digest}")
    print(v[v.aia_ok < v.aia_expected].to_string(index=False) if (v.aia_ok < v.aia_expected).any() else "no HARP short of frames")

else:
    sys.exit(__doc__)
