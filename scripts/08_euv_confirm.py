"""2025-26 CONFIRMATION SET -- download + LABEL-BLIND computation only (decisions.md 2026-09-26, d95e147).
No label is printed or inspected; nothing is evaluated. Output root data/euv_confirm/.
Usage: python euv_confirm.py check | cohort | plan | download | verify | compute"""
import glob, hashlib, json, os, sys, time, warnings
import numpy as np, pandas as pd
import euv_full

ROOT = euv_full.R = "data/euv_confirm"                 # euv_full.log() writes under R
LAB = "data/labelled_20250101_20260817.csv"
LAB_SHA = "1f6673956db3599616fe4d04fbd14b285a383737156a49d393f6c5d617c49263"
SPEC = json.load(open("frozen/frozen_spec.json"))
os.makedirs(f"{ROOT}/logs", exist_ok=True)
warnings.filterwarnings("ignore")
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def overlap_harps():
    split = pd.read_csv("frozen/split.csv")
    return set(pd.read_csv(LAB, usecols=["harpnum"]).harpnum) & set(split.harpnum)


def episodes_confirm():
    """union of the single and <=2 cohorts' episodes (harpnum, t, noaa_ars, t_rec_tai, eid); no label column."""
    e = pd.concat([pd.read_csv(f"{ROOT}/cohort_{s}.csv", usecols=["harpnum", "t", "noaa_ars"], parse_dates=["t"]) for s in ["single", "le2"]])
    e["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(e.harpnum, e.t)]
    e = e.drop_duplicates("eid")
    lab = pd.read_csv(LAB, usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"], low_memory=False)
    e = e.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert e.t_rec_tai.notna().all()
    return e.sort_values(["harpnum", "t"]).reset_index(drop=True)


if __name__ == "__main__" and sys.argv[1:] == ["check"]:
    import swpc
    assert H(LAB) == LAB_SHA, "confirmation labelled file changed"
    print(f"labelled file hash verified ({LAB_SHA[:8]}...)")
    fl, _ = swpc.load(pd.Timestamp("2024-12-29"), pd.Timestamp("2026-08-18 23:59"))
    print(f"GOES scale: swpc.FLARE_SCALE = {swpc.FLARE_SCALE}; XRA events 2024-12-29 -> 2026-08-18: {len(fl)}; by satellite "
          f"{fl.obs.value_counts().to_dict()}")
    old = fl[fl.obs.isin(swpc.OLD_SCALE_SATS)]; new = fl[fl.obs.isin(swpc.TRUE_SCALE_SATS)]
    print(f"  events from GOES-13/14/15 (the /0.7 satellites): {len(old)}; GOES-16+ events: {len(new)}, of which flux != reported "
          f"(i.e. /0.7 applied): {int((new.flux != new.flux_reported).sum())}; other observatories: {len(fl) - len(old) - len(new)}")
    ov = overlap_harps()
    print(f"overlapping HARPs (in frozen/split.csv, i.e. 2010-2024): {len(ov)} {sorted(ov)}"); assert len(ov) == 6

if __name__ == "__main__" and sys.argv[1:] == ["cohort"]:
    import joblib, cohort, swpc
    assert H(LAB) == LAB_SHA and H("src/cohort.py") == SPEC["cohort"]["code_sha256"]
    F, THR = SPEC["gate"]["features"], SPEC["gate"]["threshold"]
    lab = pd.read_csv(LAB, parse_dates=["t_rec_utc"], low_memory=False)
    lab = lab[~lab.harpnum.isin(overlap_harps())].reset_index(drop=True)
    assert lab.t_rec_utc.dt.year.isin([2025, 2026]).all()
    d = lab[~lab[F].isna().any(axis=1)].reset_index(drop=True)
    X = d[F].to_numpy(float); dv = np.zeros(len(d))
    for v in SPEC["gate"]["fold_models"].values():
        assert H(v["path"]) == v["sha256"]; g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
    d["score"] = dv / len(SPEC["gate"]["fold_models"])
    missing = swpc.label_missing_days()
    print(f"confirmation rows after excluding the 6 overlapping HARPs: {len(lab)} ({lab.harpnum.nunique()} HARPs); scorable {len(d)}")
    for name, sf in [("single", lambda z: z.noaa_ar_count == 1), ("le2", lambda z: z.noaa_ar_count <= 2)]:
        s = d[sf(d)]
        hl = lab[lab.harpnum.isin(set(s.harpnum))]
        c, x, eps = cohort.build(s[["harpnum", "t_rec_utc", "score"]].merge(s.drop(columns="score"), on=["harpnum", "t_rec_utc"]), hl, THR, missing)
        c.to_csv(f"{ROOT}/cohort_{name}.csv", index=False); x.to_csv(f"{ROOT}/exclusions_{name}.csv", index=False)
        print(f"  subset {name}: eligible episodes {len(c)}, HARPs {c.harpnum.nunique()}")          # nothing else is printed

if __name__ == "__main__" and sys.argv[1:] == ["plan"]:
    from euv_full import expected_frames
    e = episodes_confirm()
    aia = sum(expected_frames(g) for _, g in e.groupby("harpnum")); hmi = 2 * len(e); H_ = e.harpnum.nunique()
    x = pd.read_csv("data/euv_test/exports.csv")
    bpf = x.bytes.sum() / x.files.sum()
    model = lambda n_exp, files: 72 * n_exp + 0.2 * files
    t_model = model(len(x), x.files.sum()) / 3600; ratio = 7.24 / t_model
    est_h = (model(H_, aia) + model(H_, hmi)) / 3600 * ratio
    print(f"DRY RUN (nothing submitted): union episodes {len(e)}, HARPs {H_}; exports {2 * H_} ({H_} HMI + {H_} AIA); expected files "
          f"AIA {aia}, HMI {hmi}; estimated {(aia + hmi) * bpf / 1e9:.2f} GB (test-year bytes/file {bpf / 1e6:.3f} MB); "
          f"estimated {est_h:.2f} h (prep model x {ratio:.2f}, the test-year wall/model ratio). Test years: 12.19 GB for 313 episodes.")

if __name__ == "__main__" and sys.argv[1:] == ["download"]:
    from euv_full import run_pipeline, log
    eps = episodes_confirm(); t0 = time.time()
    log(f"CONFIRMATION DOWNLOAD start: {len(eps)} episodes, {eps.harpnum.nunique()} HARPs (download only)")
    run_pipeline(eps, ROOT, progress_every=1800, compute=False)
    log(f"CONFIRMATION DOWNLOAD done: wall {(time.time() - t0) / 3600:.2f} h")

if __name__ == "__main__" and sys.argv[1:] == ["verify"]:
    from astropy.io import fits
    from euv_full import expected_frames, valid_fits, hmi_files, trec_of
    eps = episodes_confirm(); rows = []
    for h, g in eps.groupby("harpnum"):
        hd, ad = f"{ROOT}/hmi/{h}", f"{ROOT}/aia/{h}"
        ok = sum(1 for x in g.t_rec_tai if (lambda mb: mb[0] and mb[1] and all(int(fits.getheader(f, 1)["HARPNUM"]) == h and
                 str(fits.getheader(f, 1)["T_REC"])[:19] == x[:19] for f in mb))(hmi_files(hd, x) if os.path.isdir(hd) else (None, None)))
        files = sorted(glob.glob(f"{ad}/*.fits")) if os.path.isdir(ad) else []
        lo, hi = g.t.min() - pd.Timedelta("24h") + pd.Timedelta("11min"), g.t.max() + pd.Timedelta("1min")
        good = [p for p in files if valid_fits(p)]
        wl = [p for p in good if int(fits.getheader(p, 1 if len(fits.open(p)) > 1 else 0).get("WAVELNTH", -1)) == 94]
        inr = [p for p in wl if lo <= trec_of(p) <= hi]
        rows.append(dict(harpnum=h, episodes=len(g), hmi_pairs_ok=ok, aia_expected=expected_frames(g), aia_files=len(files),
                         aia_ok=len(inr), GB=(sum(os.path.getsize(p) for p in files) + sum(os.path.getsize(p) for p in glob.glob(f"{hd}/*.fits"))) / 1e9))
    v = pd.DataFrame(rows); v.to_csv(f"{ROOT}/verify_per_harp.csv", index=False)
    print(f"HARPs {len(v)}, episodes {v.episodes.sum()}; HMI pairs OK {v.hmi_pairs_ok.sum()}/{v.episodes.sum()}; AIA files {v.aia_files.sum()}, "
          f"valid 94 A in range {v.aia_ok.sum()} of expected {v.aia_expected.sum()}; {v.GB.sum():.2f} GB")
    s = v[v.aia_ok < v.aia_expected]
    print(f"short HARPs: {len(s)} ({int((s.aia_expected - s.aia_ok).sum())} frames); < 97%: "
          f"{s.loc[s.aia_ok < 0.97 * s.aia_expected, ['harpnum', 'aia_ok', 'aia_expected']].values.tolist()}; "
          f"no AIA: {v.loc[v.aia_files == 0, 'harpnum'].tolist()}; HMI missing: {v.loc[v.hmi_pairs_ok < v.episodes, 'harpnum'].tolist()}")
    if os.path.exists(f"{ROOT}/failed.csv"):
        print(pd.read_csv(f"{ROOT}/failed.csv").to_string(index=False))


def confirm_episode(ep):
    from euv_full import compute_episode
    from euv_spatial import spatial_episode
    h, e = ep["harpnum"], ep["eid"]; err = ""
    try:
        if not os.path.exists(f"{ROOT}/results/{e}.json"):
            r = compute_episode(ep, f"{ROOT}/hmi/{h}", f"{ROOT}/aia/{h}", f"{ROOT}/series")
            json.dump({k: str(v) for k, v in r.items()}, open(f"{ROOT}/results/{e}.json", "w"))
        for d, v in [("spatial", "valid_primary"), ("spatial_nf", "valid_sens")]:
            if not os.path.exists(f"{ROOT}/{d}/{e}.json"):
                spatial_episode(ep, f"{ROOT}/{d}", v, root=ROOT)
    except Exception as x:
        err = repr(x)
    return e, err


if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    for d in ["series", "results", "spatial", "spatial_nf"]:
        os.makedirs(f"{ROOT}/{d}", exist_ok=True)
    eps = episodes_confirm(); W = os.cpu_count() - 1; t0 = time.time(); log = f"{ROOT}/logs/compute.log"; errs = []
    jobs = [dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai, noaa_ars=str(x.noaa_ars)) for x in eps.itertuples()
            if os.path.isdir(f"{ROOT}/aia/{int(x.harpnum)}")]
    open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} compute start: {len(jobs)} of {len(eps)} episodes (with AIA), workers {W}\n")
    with ProcessPoolExecutor(W) as pool:
        futs = [pool.submit(confirm_episode, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            e, err = f.result()
            if err:
                errs.append((e, err)); open(log, "a").write(f"ERROR {e}: {err}\n")
            if i % 25 == 0 or i == len(jobs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(jobs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    open(log, "a").write(f"compute done: {len(jobs)} episodes, {len(errs)} errors, wall {(time.time() - t0) / 3600:.2f} h, workers {W}\n")
    pd.DataFrame(errs, columns=["eid", "error"]).to_csv(f"{ROOT}/compute_errors.csv", index=False)

if __name__ == "__main__" and sys.argv[1:2] == ["reexport"]:
    # re-export check (user 2026-09-26; same procedure as the test-year check f3d6489): AIA once per HARP into
    # data/euv_confirm/reexport/<H>/; files not already in aia/<H> are copied there (kept); nothing deleted or overwritten
    import shutil
    from euv_full import aia_spec, submit, wait, download, expected_frames, valid_fits, log
    eps = episodes_confirm(); rows = []
    for h in [int(x) for x in sys.argv[2:]]:
        g = eps[eps.harpnum == h]; dest = f"{ROOT}/reexport/{h}"
        ds, proc = aia_spec(h, g, f"{ROOT}/hmi/{h}")
        r = submit(ds, proc); prep = wait(r); nb, dl = download(r, dest)
        old = {os.path.basename(p) for p in glob.glob(f"{ROOT}/aia/{h}/*.fits") if valid_fits(p)}
        new = {os.path.basename(p) for p in glob.glob(f"{dest}/*.fits") if valid_fits(p)}
        for f in sorted(new - old):
            shutil.copy2(f"{dest}/{f}", f"{ROOT}/aia/{h}/{f}")
        rows.append(dict(harpnum=h, request_id=r.id, prep_s=round(prep, 1), expected=expected_frames(g), before=len(old),
                         reexport=len(new), new_frames_added=len(new - old), missing_in_reexport=len(old - new)))
        log(f"re-export HARP {h}: {rows[-1]}")
    pd.DataFrame(rows).to_csv(f"{ROOT}/reexport.csv", index=False); print(pd.DataFrame(rows).to_string(index=False))
