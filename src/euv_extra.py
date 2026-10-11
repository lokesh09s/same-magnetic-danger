"""EUV-UNSEEN FOLLOW-UP VALIDATION — CV_box as a false-alarm filter (decisions.md 2026-09-26, 338c0aa / 8cace14).
Label-blind set construction, dev models/thresholds, download, computation. NO evaluation here.
Usage: python euv_extra.py sets | models | plan | download | verify | compute"""
import glob, hashlib, json, os, re, sys, time, warnings
import numpy as np, pandas as pd

ROOT = "data/euv_extra"
EUV_DIRS = ["data/euv_full", "data/euv_test", "data/euv_confirm", "data/euv_pilot", "data/euv_cad"]
SPEC = json.load(open("frozen/frozen_spec.json"))
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
ars = lambda v: {int(x) for x in str(v).split(",") if x.strip().isdigit()}
os.makedirs(f"{ROOT}/logs", exist_ok=True)
warnings.filterwarnings("ignore")
SETS = {"primary": [2021, 2023, 2024], "s2022": [2022]}


def excluded_ids():
    """HARPs and NOAA regions appearing anywhere in the EUV directories (decisions.md 8cace14)."""
    from astropy.io import fits
    harps, regions, src = set(), set(), {}
    eid = re.compile(r"^(\d+)_\d{8}T\d{4}")
    for root in EUV_DIRS:
        for dp, dns, fns in os.walk(root):
            for n in dns + fns:
                if n.isdigit():
                    harps.add(int(n))
                m = eid.match(n)
                if m:
                    harps.add(int(m.group(1)))
                m = re.match(r"hmi\.sharp_720s\.(\d+)\.", n)
                if m:
                    harps.add(int(m.group(1)))
                p = os.path.join(dp, n)
                if n.startswith("hmi") and n.endswith(".fits") and os.path.isfile(p):
                    try:
                        hd = fits.getheader(p, 1)
                        if "HARPNUM" in hd:
                            harps.add(int(hd["HARPNUM"]))
                        regions |= ars(hd.get("NOAA_ARS", ""))
                    except Exception:
                        pass
                if n.endswith(".csv") and os.path.isfile(p):
                    cols = pd.read_csv(p, nrows=0).columns
                    for c in cols:
                        if c.lower() == "harpnum":
                            harps |= set(pd.to_numeric(pd.read_csv(p, usecols=[c])[c], errors="coerce").dropna().astype(int))
                        if c.lower() == "noaa_ars":
                            for v in pd.read_csv(p, usecols=[c])[c].dropna():
                                regions |= ars(v)
    src["harps_from_dirs"], src["regions_from_dirs"] = len(harps), len(regions)
    extra = set()
    for f in ["data/labelled_20100501_20250101.csv", "data/labelled_20250101_20260817.csv"]:
        l = pd.read_csv(f, usecols=["harpnum", "noaa_ars"], low_memory=False)
        for v in l.loc[l.harpnum.isin(harps), "noaa_ars"].dropna().unique():
            extra |= ars(v)
    src["regions_added_from_labelled_rows_of_excluded_HARPs"] = len(extra - regions)
    return harps, regions | extra, src


if __name__ == "__main__" and sys.argv[1:] == ["sets"]:
    import joblib, cohort, swpc
    assert H(SPEC["data"]["labelled_file"]) == SPEC["data"]["labelled_sha256"] and H("src/cohort.py") == SPEC["cohort"]["code_sha256"]
    F, THR = SPEC["gate"]["features"], SPEC["gate"]["threshold"]
    exH, exR, src = excluded_ids()
    json.dump(dict(harps=sorted(exH), regions=sorted(exR), sources=src), open(f"{ROOT}/excluded_ids.json", "w"))
    split = pd.read_csv("frozen/split.csv")
    full = pd.read_csv(SPEC["data"]["labelled_file"], parse_dates=["t_rec_utc"], low_memory=False)
    lab = full[full.harpnum.isin(set(split.loc[split["set"] == "test", "harpnum"]))]
    lab = lab[lab.t_rec_utc.dt.year.isin([2021, 2022, 2023, 2024])]
    lab = lab[~lab[F].isna().any(axis=1)].reset_index(drop=True)
    X = lab[F].to_numpy(float); dv = np.zeros(len(lab))
    for v in SPEC["gate"]["fold_models"].values():
        assert H(v["path"]) == v["sha256"]; g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
    lab["score"] = dv / 5
    reg_of_harp = full.groupby("harpnum").noaa_ars.apply(lambda s: set().union(*[ars(v) for v in s.dropna()]))
    tp = pd.read_csv("data/stage5/cohort_test_primary.csv", usecols=["harpnum", "t"], parse_dates=["t"])
    tp_keys = set(zip(tp.harpnum, tp.t))
    missing = swpc.label_missing_days(); rows = []
    for sname, years in SETS.items():
        d = lab[lab.t_rec_utc.dt.year.isin(years) & (lab.noaa_ar_count <= 2)]
        hl = full[full.harpnum.isin(set(d.harpnum))]
        c, x, eps = cohort.build(d[["harpnum", "t_rec_utc", "score"]].merge(d.drop(columns="score"), on=["harpnum", "t_rec_utc"]), hl, THR, missing)
        c.to_csv(f"{ROOT}/cohort_{sname}_all_eligible.csv", index=False)
        for e in x.itertuples():
            rows.append(dict(set=sname, harpnum=e.harpnum, t=e.t, year=pd.Timestamp(e.t).year, n_regions=np.nan, reason=f"not eligible (cohort): {e.reason}"))
        for e in c.itertuples():
            if (e.harpnum, e.t) in tp_keys:
                r = "in cohort_test_primary.csv"
            elif e.harpnum in exH:
                r = "HARP in EUV directories"
            elif reg_of_harp.get(e.harpnum, set()) & exR:
                r = "NOAA region in EUV directories"
            else:
                r = "INCLUDED"
            rows.append(dict(set=sname, harpnum=e.harpnum, t=e.t, year=e.t.year, n_regions=len(ars(e.noaa_ars)), reason=r))
    M = pd.DataFrame(rows); M.to_csv(f"{ROOT}/manifest.csv", index=False)
    print(f"excluded-ID sources: {src}; excluded HARPs {len(exH)}, excluded NOAA regions {len(exR)}")
    for sname in SETS:
        m = M[M.set == sname]
        print(f"\nset {sname}: candidate eligible episodes {int((~m.reason.str.startswith('not eligible')).sum())}; exclusions by rule: "
              f"{m[m.reason != 'INCLUDED'].reason.str.replace(r'not eligible \\(cohort\\): .*', 'not eligible (cohort T1-T4/T2)', regex=True).value_counts().to_dict()}")
        inc = m[m.reason == "INCLUDED"]
        print(f"  INCLUDED: {len(inc)} episodes, {inc.harpnum.nunique()} HARPs; by year {inc.groupby('year').agg(ep=('harpnum', 'size'), HARPs=('harpnum', 'nunique')).to_dict('index')}; "
              f"single-region {int((inc.n_regions == 1).sum())}, two-region {int((inc.n_regions == 2).sum())}")
    inc = M[(M.set == "primary") & (M.reason == "INCLUDED")]
    size_ok = len(inc) >= 100 and inc.harpnum.nunique() >= 30
    print(f"\nSIZE RULE (PRIMARY >= 100 episodes and >= 30 HARPs): {len(inc)} episodes, {inc.harpnum.nunique()} HARPs -> "
          f"{'PASS' if size_ok else 'too small; not run'}")
    print(f"manifest sha256 {H(f'{ROOT}/manifest.csv')}; excluded_ids sha256 {H(f'{ROOT}/excluded_ids.json')}")

if __name__ == "__main__" and sys.argv[1:] == ["models"]:
    import joblib
    from phase_f import load_base, prep, tau_keep, wlogloss, A_COLS
    from euv_heldout import fit_folds
    from euv_confirm_tests import log_r
    os.makedirs(f"{ROOT}/models", exist_ok=True)
    dv = load_base()
    m = dv.P & np.isfinite(dv.primary_CV_box) & (dv.primary_CV_box > 0)
    c = prep(dv, m); c["log10_CV_box"] = np.log10(c.primary_CV_box)
    c["logR"] = log_r(c, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"))
    y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
    MODELS = {"A": A_COLS, "A_CV": A_COLS + ["log10_CV_box"], "C": A_COLS + ["logR"], "C_CV": A_COLS + ["logR", "log10_CV_box"]}
    px = pd.read_csv("data/euv_full/spatial/eval_compare.csv", float_precision="round_trip").set_index("candidate").loc["R4a"]
    out, hashes = {}, {}
    for name, cols in MODELS.items():
        ms, p = fit_folds(c, cols)
        if name == "A":
            assert abs(wlogloss(y, p, w) - px.logloss_A) < 1e-12, "A on the dev 541 set does not reproduce Phase X"
        tau = tau_keep(p, y, w); k = p >= tau
        out[name] = dict(cols=cols, tau=tau, dev_oof_weighted_true_kept=float((w * y * k).sum() / (w * y).sum()),
                         dev_oof_logloss=wlogloss(y, p, w))
        for f, (sc, mdl, cl) in enumerate(ms):
            fn = f"{ROOT}/models/{name}_fold{f}.joblib"
            assert not os.path.exists(fn), f"{fn} exists; never overwrite"
            joblib.dump({"scaler": sc, "model": mdl, "cols": cl}, fn); hashes[fn] = H(fn)
    c[["eid", "harpnum", "t", "fold", "weight"]].to_csv(f"{ROOT}/dev_rows.csv", index=False)
    json.dump(out, open(f"{ROOT}/thresholds.json", "w"), indent=1)
    hashes[f"{ROOT}/dev_rows.csv"] = H(f"{ROOT}/dev_rows.csv"); hashes[f"{ROOT}/thresholds.json"] = H(f"{ROOT}/thresholds.json")
    json.dump(hashes, open(f"{ROOT}/model_hashes.json", "w"), indent=1)
    print(f"dev rows: {len(c)} episodes, {c.harpnum.nunique()} HARPs (primary 80% set, CV_box finite and > 0); check: A reproduces Phase X dev log-loss")
    for name, o in out.items():
        print(f"  {name:5s} cols {o['cols']}: tau {o['tau']:.6f}; dev OOF weighted true alarm episodes kept {o['dev_oof_weighted_true_kept']:.4f}")
    for f, h in hashes.items():
        print(f"  sha256 {h}  {f}")


def set_episodes(s):
    """INCLUDED episodes of a set (harpnum, t, noaa_ars, t_rec_tai, eid); no label column read."""
    M = pd.read_csv(f"{ROOT}/manifest.csv", parse_dates=["t"]); M = M[(M.set == s) & (M.reason == "INCLUDED")]
    c = pd.read_csv(f"{ROOT}/cohort_{s}_all_eligible.csv", usecols=["harpnum", "t", "noaa_ars"], parse_dates=["t"])
    e = M[["harpnum", "t"]].merge(c, on=["harpnum", "t"], how="left", validate="one_to_one")
    lab = pd.read_csv(SPEC["data"]["labelled_file"], usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"], low_memory=False)
    e = e.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all() and e.noaa_ars.notna().all()
    e["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(e.harpnum, e.t)]
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


if __name__ == "__main__" and sys.argv[1:] == ["plan"]:
    from euv_full import expected_frames
    x = pd.read_csv("data/euv_test/exports.csv"); bpf = x.bytes.sum() / x.files.sum()
    model = lambda n_exp, files: 72 * n_exp + 0.2 * files; ratio = 7.24 / (model(len(x), x.files.sum()) / 3600)
    tot = [0, 0]
    for s in ["primary", "s2022"]:
        e = set_episodes(s); Hn = e.harpnum.nunique()
        aia = sum(expected_frames(g) for _, g in e.groupby("harpnum")); hmi = 2 * len(e)
        gb, hrs = (aia + hmi) * bpf / 1e9, (model(Hn, aia) + model(Hn, hmi)) / 3600 * ratio
        tot = [tot[0] + gb, tot[1] + hrs]
        print(f"DRY RUN {s}: {len(e)} episodes, {Hn} HARPs; exports {2 * Hn} ({Hn} HMI + {Hn} AIA); files AIA {aia}, HMI {hmi}; "
              f"~{gb:.2f} GB, ~{hrs:.2f} h")
    print(f"total ~{tot[0]:.2f} GB, ~{tot[1]:.2f} h (test-year bytes/file {bpf / 1e6:.3f} MB; prep model x {ratio:.2f}); order: primary, then 2022")

if __name__ == "__main__" and sys.argv[1:] == ["download"]:
    import euv_full
    euv_full.R = ROOT                                             # logs under data/euv_extra/logs
    for s in ["primary", "s2022"]:                                # PRIMARY first, then 2022; one pending export at a time
        e = set_episodes(s); t0 = time.time()
        euv_full.log(f"EUV-EXTRA DOWNLOAD {s} start: {len(e)} episodes, {e.harpnum.nunique()} HARPs (download only)")
        euv_full.run_pipeline(e, f"{ROOT}/{s}", progress_every=1800, compute=False)
        euv_full.log(f"EUV-EXTRA DOWNLOAD {s} done: wall {(time.time() - t0) / 3600:.2f} h")

if __name__ == "__main__" and sys.argv[1:] == ["verify"]:
    from astropy.io import fits
    from euv_full import expected_frames, valid_fits, hmi_files, trec_of
    for s in ["primary", "s2022"]:
        R_ = f"{ROOT}/{s}"; eps = set_episodes(s); rows = []
        for h, g in eps.groupby("harpnum"):
            hd, ad = f"{R_}/hmi/{h}", f"{R_}/aia/{h}"
            ok = 0
            for x in g.t_rec_tai:
                mb = hmi_files(hd, x) if os.path.isdir(hd) else (None, None)
                ok += bool(mb[0] and mb[1] and all(int(fits.getheader(f, 1)["HARPNUM"]) == h and str(fits.getheader(f, 1)["T_REC"])[:19] == x[:19] for f in mb))
            files = sorted(glob.glob(f"{ad}/*.fits")) if os.path.isdir(ad) else []
            lo, hi = g.t.min() - pd.Timedelta("24h") + pd.Timedelta("11min"), g.t.max() + pd.Timedelta("1min")
            good = [p for p in files if valid_fits(p) and int(fits.getheader(p, 1 if len(fits.open(p)) > 1 else 0).get("WAVELNTH", -1)) == 94
                    and lo <= trec_of(p) <= hi]
            rows.append(dict(harpnum=h, episodes=len(g), hmi_ok=ok, aia_expected=expected_frames(g), aia_files=len(files), aia_ok=len(good),
                             GB=(sum(os.path.getsize(p) for p in files) + sum(os.path.getsize(p) for p in glob.glob(f"{hd}/*.fits"))) / 1e9))
        v = pd.DataFrame(rows); v.to_csv(f"{R_}/verify_per_harp.csv", index=False); sh = v[v.aia_ok < v.aia_expected]
        print(f"{s}: HARPs {len(v)}, episodes {v.episodes.sum()}; HMI pairs OK {v.hmi_ok.sum()}/{v.episodes.sum()}; AIA valid {v.aia_ok.sum()} of "
              f"expected {v.aia_expected.sum()} (files {v.aia_files.sum()}); {v.GB.sum():.2f} GB; short HARPs {len(sh)} "
              f"({int((sh.aia_expected - sh.aia_ok).sum())} frames); < 97%: {sh.loc[sh.aia_ok < 0.97 * sh.aia_expected, ['harpnum', 'aia_ok', 'aia_expected']].values.tolist()}; "
              f"no AIA {v.loc[v.aia_files == 0, 'harpnum'].tolist()}; failures file: {os.path.exists(f'{R_}/failed.csv')}")


def extra_episode(args):
    from euv_full import compute_episode
    ep, R_ = args; h, e = ep["harpnum"], ep["eid"]; err = ""
    try:
        if not os.path.exists(f"{R_}/results/{e}.json"):
            r = compute_episode(ep, f"{R_}/hmi/{h}", f"{R_}/aia/{h}", f"{R_}/series")
            json.dump({k: str(v) for k, v in r.items()}, open(f"{R_}/results/{e}.json", "w"))
    except Exception as x:
        err = repr(x)
    return e, err


if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    W = os.cpu_count() - 1; t0 = time.time(); log = f"{ROOT}/logs/compute.log"; errs = []; jobs = []
    for s in ["primary", "s2022"]:
        R_ = f"{ROOT}/{s}"
        for d in ["series", "results"]:
            os.makedirs(f"{R_}/{d}", exist_ok=True)
        jobs += [(dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, noaa_ars=str(x.noaa_ars)), R_)
                 for x in set_episodes(s).itertuples() if os.path.isdir(f"{R_}/aia/{int(x.harpnum)}")]
    open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} compute start: {len(jobs)} episodes (with AIA), workers {W}\n")
    with ProcessPoolExecutor(W) as pool:
        futs = [pool.submit(extra_episode, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            e, err = f.result()
            if err:
                errs.append((e, err)); open(log, "a").write(f"ERROR {e}: {err}\n")
            if i % 25 == 0 or i == len(jobs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(jobs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    open(log, "a").write(f"compute done: {len(jobs)} episodes, {len(errs)} errors, wall {(time.time() - t0) / 3600:.2f} h, workers {W}\n")
    pd.DataFrame(errs, columns=["eid", "error"]).to_csv(f"{ROOT}/compute_errors.csv", index=False)

if __name__ == "__main__" and sys.argv[1:] == ["counts"]:
    num = ["frames", "primary_fill", "sens_fill", "primary_CV_box", "primary_dCV", "sens_dCV", "excl_quality", "excl_exposure", "excl_flare"]
    for s in ["primary", "s2022"]:
        e = set_episodes(s); R_ = f"{ROOT}/{s}"
        r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R_}/results/*.json")])
        r = r[["eid"] + num] if len(r) else pd.DataFrame(columns=["eid"] + num)
        r[num] = r[num].apply(pd.to_numeric, errors="coerce"); d = e.merge(r, on="eid", how="left")
        P = d.primary_fill >= 0.8; ok = P & np.isfinite(d.primary_CV_box) & (d.primary_CV_box > 0)
        print(f"{s} (counts only; no label read): episodes {len(d)}, with results {int(d.frames.notna().sum())}, no result {int(d.frames.isna().sum())}; "
              f"frames {int(d.frames.sum())}, QUALITY!=0 {int(d.excl_quality.sum())}, exposure {int(d.excl_exposure.sum())}, flare (sens only) {int(d.excl_flare.sum())}; "
              f"primary fill >= 80%: {int(P.sum())}; of these CV_box undefined / <= 0: {int((P & ~ok).sum())}; evaluable (fill ok, CV_box > 0): {int(ok.sum())} "
              f"({d.loc[ok, 'harpnum'].nunique()} HARPs); flare-excluded fill >= 80%: {int((d.sens_fill >= 0.8).sum())}")

if __name__ == "__main__" and sys.argv[1:2] == ["reexport"]:
    # re-export check (user 2026-09-27; same procedure as f3d6489 / 9655e1c): AIA once into <root>/reexport/<H>/;
    # files not already in aia/<H> are copied there (kept); nothing deleted or overwritten
    import shutil, euv_full
    from euv_full import aia_spec, submit, wait, download, expected_frames, valid_fits
    euv_full.R = ROOT
    s, rows = sys.argv[2], []
    R_ = f"{ROOT}/{s}"; eps = set_episodes(s)
    for h in [int(x) for x in sys.argv[3:]]:
        g = eps[eps.harpnum == h]; dest = f"{R_}/reexport/{h}"
        ds, proc = aia_spec(h, g, f"{R_}/hmi/{h}")
        r = submit(ds, proc); prep = wait(r); nb, dl = download(r, dest)
        old = {os.path.basename(p) for p in glob.glob(f"{R_}/aia/{h}/*.fits") if valid_fits(p)}
        new = {os.path.basename(p) for p in glob.glob(f"{dest}/*.fits") if valid_fits(p)}
        for f in sorted(new - old):
            shutil.copy2(f"{dest}/{f}", f"{R_}/aia/{h}/{f}")
        rows.append(dict(set=s, harpnum=h, request_id=r.id, prep_s=round(prep, 1), expected=expected_frames(g), before=len(old),
                         reexport=len(new), new_frames_added=len(new - old), missing_in_reexport=len(old - new)))
        euv_full.log(f"re-export {s} HARP {h}: {rows[-1]}")
    pd.DataFrame(rows).to_csv(f"{R_}/reexport.csv", index=False); print(pd.DataFrame(rows).to_string(index=False))

if __name__ == "__main__" and sys.argv[1:] == ["filter"]:
    # PRE-REGISTERED FILTER TEST (338c0aa; implementation f7c6646) -- RUN ONCE
    import joblib
    from concurrent.futures import ProcessPoolExecutor
    from sklearn.metrics import roc_auc_score
    from phase_f import boot_many, wlogloss, ratio_jobs, pct, A_COLS, W
    from euv_confirm_tests import log_r
    from euv_f2_replication import twins
    t00 = time.time(); os.makedirs(f"{ROOT}/filter_test", exist_ok=True); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    hs = json.load(open(f"{ROOT}/model_hashes.json"))
    assert all(H(f) == v for f, v in hs.items()) and H(f"{ROOT}/thresholds.json") == "7a34507c20d37756906e4ad6dfaf9069c48ad74bff5b42521a4dd4f1c573c6ad"
    TH = json.load(open(f"{ROOT}/thresholds.json"))
    NAMES = ["A", "A_CV", "C", "C_CV"]
    MOD = {m: [(d["scaler"], d["model"], d["cols"]) for d in (joblib.load(f"{ROOT}/models/{m}_fold{k}.joblib") for k in range(5))] for m in NAMES}
    pred = lambda ms, c: np.mean([m.predict_proba(sc.transform(c[cols]))[:, 1] for sc, m, cols in ms], axis=0)
    print("PRE-REGISTERED FILTER TEST (338c0aa) — EUV-unseen follow-up validation, not an untouched test. RUN ONCE.")
    print(f"integrity: {len(hs)} model/threshold/dev-row files match their recorded SHA-256; frozen tau: "
          + ", ".join(f"{m} {TH[m]['tau']:.6f}" for m in NAMES))
    pool = ProcessPoolExecutor(W); summary = []
    for s, lab in [("primary", "PRIMARY 2021/2023/2024"), ("s2022", "SENSITIVITY 2022 (reported separately; never pooled)")]:
        M = pd.read_csv(f"{ROOT}/manifest.csv", parse_dates=["t"]); M = M[(M.set == s) & (M.reason == "INCLUDED")]
        coh = pd.read_csv(f"{ROOT}/cohort_{s}_all_eligible.csv", parse_dates=["t"])
        c = M[["harpnum", "t"]].merge(coh, on=["harpnum", "t"], how="left", validate="one_to_one")
        c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
        r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{ROOT}/{s}/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
        r[["primary_fill", "primary_CV_box"]] = r[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce")
        c = c.merge(r, on="eid", how="left"); n_inc = len(c)
        c = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True)
        c["log10_CV_box"] = np.log10(c.primary_CV_box)
        c["logR"] = log_r(c, pd.Timestamp("2020-12-29"), pd.Timestamp("2025-01-01"))
        assert ((c.logR < np.log1p(48)) == ((c.n_C + c.n_M + c.n_X) >= 1)).all(), "R window inconsistent with history counts"
        c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy(); groups = [np.where(h == v)[0] for v in np.unique(h)]
        P = {m: pred(MOD[m], c) for m in NAMES}; K = {m: P[m] >= TH[m]["tau"] for m in NAMES}
        comp = c.assign(year=c.t.dt.year, regions=c.noaa_ars.astype(str).str.count(",") + 1).groupby(["year", "regions"]).size()
        print(f"\n=== {lab}: INCLUDED {n_inc}; evaluable (fill >= 80%, CV_box > 0) {len(c)} (true {int(y.sum())}, false {int((y == 0).sum())}, "
              f"HARPs {len(groups)}); label-blind exclusions {n_inc - len(c)}")
        print("composition (year, regions at t -> episodes): " + ", ".join(f"{yy}/{rr}: {v}" for (yy, rr), v in comp.items()))
        rows = []
        for m in NAMES:
            k = K[m]
            rows.append(dict(model=m, tau=TH[m]["tau"], true_kept=f"{int((k & (y == 1)).sum())}/{int(y.sum())}",
                             true_kept_w=(w * y * k).sum() / (w * y).sum() if y.sum() else np.nan,
                             false_kept=int((k & (y == 0)).sum()), false_removed=f"{int((~k & (y == 0)).sum())}/{int((y == 0).sum())}",
                             false_removed_w=(w * (1 - y) * ~k).sum() / (w * (1 - y)).sum() if (y == 0).any() else np.nan,
                             AUC=roc_auc_score(y, P[m], sample_weight=w) if 0 < y.sum() < len(y) else np.nan, logloss=wlogloss(y, P[m], w)))
        CT = pd.DataFrame(rows); CT.to_csv(f"{ROOT}/filter_test/{s}_counts.csv", index=False)
        print("per model at its frozen tau (weighted fractions; 'true alarm episodes kept'):")
        print(CT.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        jobs = {"op": ("op", dict(y=y, w=w, kept=[K[m] for m in NAMES], groups=groups), 2000, 0),
                "dA": ("dll", dict(y=y, w=w, pA=P["A"], pE=P["A_CV"], groups=groups), 10000, 20260921),
                "dC": ("dll", dict(y=y, w=w, pA=P["C"], pE=P["C_CV"], groups=groups), 10000, 20260921)}
        B = boot_many(jobs, pool); op = np.array(B["op"], float)            # resamples x 4 models x (true kept, false removed, precision)
        cmp_rows = []
        for a, b, ia, ib in [("A", "A_CV", 0, 1), ("C", "C_CV", 2, 3)]:
            df_pt = CT.false_removed_w[ib] - CT.false_removed_w[ia]; dt_pt = CT.true_kept_w[ib] - CT.true_kept_w[ia]
            dfb, dtb = op[:, ib, 1] - op[:, ia, 1], op[:, ib, 0] - op[:, ia, 0]; ok = np.isfinite(dfb) & np.isfinite(dtb)
            (fl, fh), (tl, th) = (np.percentile(dfb[ok], [2.5, 97.5]), np.percentile(dtb[ok], [2.5, 97.5])) if ok.any() else ((np.nan,) * 2, (np.nan,) * 2)
            ll = B["dA"] if a == "A" else B["dC"]; dl = CT.logloss[ia] - CT.logloss[ib]; lo, hi = pct(ll)
            cmp_rows.append(dict(set=s, comparison=f"{a} vs {b}", D_false_pts=100 * df_pt, D_false_lo=100 * fl, D_false_hi=100 * fh,
                                 D_true_pts=100 * dt_pt, D_true_lo=100 * tl, D_true_hi=100 * th, resamples_used=int(ok.sum()),
                                 dlogloss=dl, dlogloss_lo=lo, dlogloss_hi=hi, AUC_base=CT.AUC[ia], AUC_cv=CT.AUC[ib]))
        CM = pd.DataFrame(cmp_rows); CM.to_csv(f"{ROOT}/filter_test/{s}_comparisons.csv", index=False)
        print("D_false = weighted % false alarms removed (model with CV_box minus without); D_true = weighted % true alarm episodes kept (same); "
              "percentage points; paired HARP bootstrap 2,000, seed 0; delta log-loss = base - CV model (+ = CV helps), HARP bootstrap 10,000, seed 20260921")
        print(CM.drop(columns="set").to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        tw, nt = twins(c); e, j = ratio_jobs(f"{s} CV_box twins", c, "primary_CV_box", "ratio", tw); RB = boot_many(j, pool)
        print(f"CV_box twins ratio (step 6 twins code; median true / median false; pairs by true HARP, 2,000, seed 0): {len(tw)} pairs of {nt} true; "
              f"twins {e['ratio_twins']:.4f} {'[%.4f, %.4f]' % pct(RB[(e['measure'], 'tw')])} (medians {e['twin_med_true']:.4f} / {e['twin_med_false']:.4f}); "
              f"all episodes {e['ratio_all']:.4f} {'[%.4f, %.4f]' % pct(RB[(e['measure'], 'all')])}")
        if s == "primary":
            p = CM.iloc[0]
            if y.sum() == 0 or (y == 0).sum() == 0 or p.resamples_used == 0:
                reading = "INCONCLUSIVE"
            elif p.D_false_lo > 0 and p.D_true_lo >= -10:
                reading = "CONFIRMED SAFE FILTER"
            elif p.D_false_lo > 0 and p.D_true_pts >= -10:
                reading = "MEETS OPERATING CRITERION"
            elif p.D_false_lo > 0:
                reading = "REMOVES FALSE ALARMS BUT LOSES TOO MANY TRUE ALARMS (point estimate)"
            else:
                reading = "NOT CONFIRMED"
            summary.append(f"PRE-STATED READING (mechanical; PRIMARY, A vs A_CV): D_false {p.D_false_pts:+.2f} pts [{p.D_false_lo:+.2f}, {p.D_false_hi:+.2f}], "
                           f"D_true {p.D_true_pts:+.2f} pts [{p.D_true_lo:+.2f}, {p.D_true_hi:+.2f}] -> \"{reading}\"")
    pool.shutdown()
    print("\n" + "\n".join(summary)); print(f"wall {time.time() - t00:.1f} s, workers {W}")
