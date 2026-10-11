"""EXPLORATORY — "new vs repeat" brightening locations (decisions.md 2026-09-27, 912ac93). DEV 2010-2019 (candidate #24).
Frame processing and the R3 brightening definition copied from euv_spatial.spatial_episode (checked against the stored
series box means and the stored spatial / spatial_nf n_bright_px). Outputs in data/novelty/ only; at most 4 workers.
Usage: python euv_novelty.py selftest | compute | eval"""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd

R, OUT, WORKERS = "data/euv_full", "data/novelty", 4
warnings.filterwarnings("ignore")


def bright_frames(V, IDX, ny, nx):
    """= euv_spatial.spatial_episode R3 block: per-pixel mean + 3 SD (ddof 1, >= 3 finite) over the given frames;
    8-connected on the HMI grid; a patch is bright if it covers >= 4 distinct AIA pixels. -> list of bool arrays."""
    from scipy import ndimage
    with np.errstate(all="ignore"):
        nfin = np.isfinite(V).sum(0)
        thr = np.where(nfin >= 3, np.nanmean(V, 0) + 3 * np.nanstd(V, 0, ddof=1), np.inf)
    M = int(IDX.max()) + 2; out = []
    for i in range(len(V)):
        above = V[i] > thr
        lab, nl = ndimage.label(above.reshape(ny, nx), structure=np.ones((3, 3), int)); lab = lab.ravel()
        bright = np.zeros(lab.size, bool)
        if nl:
            sel = lab > 0
            key = np.unique(lab[sel].astype(np.int64) * M + IDX[i][sel])
            cnt = np.bincount((key // M).astype(int), minlength=nl + 1)
            bright = sel & (cnt[lab] >= 4)
        out.append(bright)
    return out


def f_new(bright):
    """NEW = bright pixel-frames whose pixel was not bright in any earlier frame (frames in time order)."""
    seen, new, tot = None, 0, 0
    for b in bright:
        seen = np.zeros(b.size, bool) if seen is None else seen
        new += int((b & ~seen).sum()); tot += int(b.sum()); seen |= b
    return (new / tot if tot else np.nan), new, tot


def novelty_episode(ep):
    import sunpy.map
    from astropy.io import fits
    from astropy.time import Time
    from aiapy.calibrate import update_pointing
    from aiapy.calibrate.utils import get_pointing_table
    from euv_run import register_cutout
    from euv_dctrl import samples, hmi_to_frame, frame_means
    from euv_pilot import SAT_DN
    from euv_full import hmi_files, trec_of
    warnings.filterwarnings("ignore")
    t0 = time.time(); h, t = ep["harpnum"], pd.Timestamp(ep["t"])
    mp, bp = hmi_files(f"{R}/hmi/{h}", ep["t_rec_tai"])
    mag = sunpy.map.Map(mp); bitmap = fits.open(bp)[-1].data
    S, _, _ = samples(mag.data, bitmap); ny, nx = mag.data.shape
    s = pd.read_csv(f"{R}/series/{ep['eid']}.csv", parse_dates=["t_obs", "t_rec"], float_precision="round_trip")
    rows = s[s.valid_primary].to_dict("records")
    files = {trec_of(p): p for p in glob.glob(f"{R}/aia/{h}/*.fits")}
    ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))
    V = np.full((len(rows), ny * nx), np.nan); IDX = np.full((len(rows), ny * nx), -1, np.int32); box_diff = 0.0
    for i, row in enumerate(rows):
        m = sunpy.map.Map(files[row["t_rec"]])
        exp = m.exposure_time.to_value("s"); raw = m.data.astype(float)
        if exp <= 0:
            raw[:] = np.nan; exp = 1.0
        raw[raw > SAT_DN] = np.nan
        try:
            m = update_pointing(m, pointing_table=ptab)
        except (IndexError, TypeError):
            pass
        r = register_cutout(sunpy.map.Map(raw / exp, m.meta))
        idx = hmi_to_frame(mag, r)
        a, b = frame_means(r.data, idx, {"box": S["box"]})["box"], row["box"]
        box_diff = max(box_diff, 0.0 if (np.isnan(a) and np.isnan(b)) else abs(a - b) if np.isfinite(a - b) else np.inf)
        ok = idx >= 0; V[i, ok] = r.data.ravel()[idx[ok]]; IDX[i] = idx
    assert box_diff < 1e-9, f"{ep['eid']}: box means not reproduced ({box_diff})"
    res = dict(eid=ep["eid"], frames=len(rows), box_diff=box_diff)
    sens = np.array([bool(r_["valid_sens"]) for r_ in rows])
    for tag, sel, d in [("", np.ones(len(rows), bool), "spatial"), ("_nf", sens, "spatial_nf")]:
        br = bright_frames(V[sel], IDX[sel], ny, nx)
        stored = pd.read_csv(f"{R}/{d}/{ep['eid']}_frames.csv", usecols=["n_bright_px"]).n_bright_px.to_numpy()
        assert np.array_equal(np.array([int(b.sum()) for b in br]), stored), f"{ep['eid']}{tag}: n_bright_px not reproduced"
        res[f"F_new{tag}"], res[f"new{tag}"], res[f"bright_total{tag}"] = f_new(br)
    res["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(res, open(f"{OUT}/{ep['eid']}.json", "w"))
    return res


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    ny = nx = 20; n = 60; IDX = np.tile(np.arange(ny * nx, dtype=np.int32), (n, 1))
    spot = lambda y, x: np.array([(y + dy) * nx + x + dx for dy in range(3) for dx in range(3)])
    V = np.zeros((n, ny * nx))
    for k in [5, 15, 25, 35, 45]:
        V[k, spot(8, 8)] = 100.0                                   # one spot flashes 5 times
    fa = f_new(bright_frames(V, IDX, ny, nx))
    V = np.zeros((n, ny * nx))
    for k, (y, x) in zip([5, 15, 25, 35, 45], [(1, 1), (1, 15), (8, 8), (15, 1), (15, 15)]):
        V[k, spot(y, x)] = 100.0                                   # five different spots, once each
    fb = f_new(bright_frames(V, IDX, ny, nx))
    assert fa[0] == 0.2 and fa[2] == 45, f"one spot x5: {fa}"; assert fb[0] == 1.0 and fb[2] == 45, f"five spots: {fb}"
    print(f"selftest passed: one spot flashing 5 times -> F_new {fa[0]} ({fa[1]}/{fa[2]}); five different spots once each -> F_new {fb[0]}")

if __name__ == "__main__" and sys.argv[1:] == ["compute"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from scipy.stats import spearmanr
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    c = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t"], parse_dates=["t"])        # no label column read
    dv = pd.read_csv("data/stage2/oof_scores_dev.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"])
    c = c.merge(dv, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one")
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    rs = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")]); rs = rs[rs.eid.notna()]
    for col in ["primary_fill", "primary_CV_box"]:
        rs[col] = pd.to_numeric(rs[col], errors="coerce")
    c = c.merge(rs[["eid", "primary_fill", "primary_CV_box"]], on="eid", how="left"); c = c[c.primary_fill >= 0.80].reset_index(drop=True)
    jobs = [dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai) for x in c.itertuples()
            if not os.path.exists(f"{OUT}/{x.eid}.json")]
    log = f"{OUT}/compute.log"; open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} start: {len(jobs)} of {len(c)} episodes, workers {WORKERS}\n")
    with ProcessPoolExecutor(WORKERS) as pool:
        for i, f in enumerate(as_completed([pool.submit(novelty_episode, j) for j in jobs]), 1):
            f.result()                                          # an assertion in a worker stops the run
            if i % 25 == 0 or i == len(jobs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(jobs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    N = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/*.json")])
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/spatial/*.json")])[["eid", "R4c"]]
    d = c[["eid", "primary_CV_box"]].merge(N, on="eid", how="left").merge(sp, on="eid", how="left")
    d.to_csv(f"{OUT}/dev_novelty.csv", index=False)
    x = d.F_new.dropna()
    print(f"LABEL-BLIND REPORT (no labels read): primary 80% set {len(d)}; computed {int(d.frames.notna().sum())}; box-mean check max |diff| "
          f"{d.box_diff.max():.1e}; n_bright_px reproduced for spatial and spatial_nf in every episode (asserted)")
    print(f"F_new: median {x.median():.4f}, IQR [{x.quantile(.25):.4f}, {x.quantile(.75):.4f}]; undefined (no bright pixel-frames) {int(d.F_new.isna().sum())}; "
          f"F_new_nf undefined {int(d.F_new_nf.isna().sum())}")
    for v, lab in [("R4c", "R4c"), ("primary_CV_box", "log10 CV_box")]:
        m = d.F_new.notna() & d[v].notna() & (d[v] > 0 if v == "primary_CV_box" else True)
        yv = np.log10(d.loc[m, v]) if v == "primary_CV_box" else d.loc[m, v]
        r, p = spearmanr(d.loc[m, "F_new"], yv); print(f"  Spearman rho(F_new, {lab}) = {r:+.4f} (p {p:.2e}, n {int(m.sum())})")
    print(f"wall {time.time() - t0:.1f} s ({(time.time() - t0) / 3600:.2f} h), workers {WORKERS}")

if __name__ == "__main__" and sys.argv[1:] == ["eval"]:
    from concurrent.futures import ProcessPoolExecutor
    from sklearn.metrics import roc_auc_score
    from euv_heldout import fit_folds
    from phase_f import load_base, prep, boot_many, pct, wlogloss, ratio_jobs, A_COLS
    t0 = time.time(); pd.set_option("display.width", 250)
    dv = load_base().merge(pd.read_csv(f"{OUT}/dev_novelty.csv")[["eid", "F_new", "F_new_nf"]], on="eid", how="left")
    dv["log10_CV_box"] = np.where(dv.primary_CV_box > 0, np.log10(dv.primary_CV_box), np.nan)

    def job(name, c, base, full):
        pb, pf = fit_folds(c, base)[1], fit_folds(c, full)[1]
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
        est = dict(test=name, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(np.unique(h)), LL_base=wlogloss(y, pb, w),
                   LL_full=wlogloss(y, pf, w), AUC_base=roc_auc_score(y, pb, sample_weight=w), AUC_full=roc_auc_score(y, pf, sample_weight=w))
        est["delta"] = est["LL_base"] - est["LL_full"]
        return est, {name: ("dll", dict(y=y, w=w, pA=pb, pE=pf, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}

    cP = prep(dv, dv.P & dv.F_new.notna()); cN = prep(dv, dv.S & dv.F_new_nf.notna())
    cB = prep(dv, dv.P & dv.F_new.notna() & dv.log10_CV_box.notna())
    specs = [("PRIMARY A vs A+F_new", cP, A_COLS, A_COLS + ["F_new"]), ("s: A vs A+F_new_nf (sens 80%)", cN, A_COLS, A_COLS + ["F_new_nf"]),
             ("s: A+log10 CV_box vs +F_new", cB, A_COLS + ["log10_CV_box"], A_COLS + ["log10_CV_box", "F_new"])]
    ests, jobs = [], {}
    for s in specs:
        e, j = job(*s); ests.append(e); jobs.update(j)
    with ProcessPoolExecutor(WORKERS) as pool:
        B = boot_many(jobs, pool)
        er, jr = ratio_jobs("F_new | 81 gate-score twins", dv[dv.P], "F_new", "ratio", pd.read_csv(f"{R}/step6/twins_PRIMARY.csv")); RB = boot_many(jr, pool)
    for e in ests:
        e["CI_lo"], e["CI_hi"] = pct(B[e["test"]])
    T = pd.DataFrame(ests); T.to_csv(f"{OUT}/eval.csv", index=False)
    co = [m.coef_[0][-1] for _, m, _ in fit_folds(cP, A_COLS + ["F_new"])[0]]
    print("EXPLORATORY (dev 2010-2019 only); delta = LL(base) - LL(base + x), + = helps; HARP bootstrap 10,000, seed 20260921")
    print(T.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    neg = int(sum(v < 0 for v in co))
    print(f"F_new coefficient per fold (per 1 SD): {[round(float(v), 4) for v in co]}; negative (predicted direction) in {neg}/5 folds -> "
          f"{'matches' if neg >= 4 else 'does not match'} the predicted direction in >= 4 of 5")
    print(f"F_new twins ratio (F2 code; 2,000, seed 0): all {er['ratio_all']:.4f} {'[%.4f, %.4f]' % pct(RB[(er['measure'], 'all')])}; "
          f"81 twins {er['ratio_twins']:.4f} {'[%.4f, %.4f]' % pct(RB[(er['measure'], 'tw')])} (medians {er['twin_med_true']:.4f} / {er['twin_med_false']:.4f}, {er['pairs']} pairs)")
    r = T.iloc[0]; el = r.delta > 0 and r.CI_lo > 0 and r.AUC_full > r.AUC_base
    print(f"PRE-STATED READING (mechanical): delta {r.delta:+.4f}, CI lower {r.CI_lo:+.4f}, AUC {r.AUC_base:.4f} -> {r.AUC_full:.4f} -> "
          f"\"{'ELIGIBLE FOR FOLLOW-UP' if el else 'NOT ELIGIBLE'}\"")
    print(f"wall {time.time() - t0:.1f} s, workers {WORKERS}")
