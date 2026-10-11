"""PHASE X (decisions.md 2026-09-25 pre-registration) -- EXPLORATORY on dev. Spatial 94 A measures from the files on disk:
R1 PIL running-difference kurtosis, R2 skew, R3 transient-brightening fraction (all minus the 20 control draws),
R4a-c whole-box counterparts. Frames processed exactly as euv_full.compute_episode (checked against the stored series).
Usage: python euv_spatial.py timing | run | eval"""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd

R, NDRAW = "data/euv_full", 20
OUT = f"{R}/spatial"


def _kurt_skew(x):
    from scipy.stats import kurtosis, skew
    x = x[np.isfinite(x)]
    return (float(kurtosis(x, fisher=True, bias=True)), float(skew(x, bias=True))) if len(x) >= 4 else (np.nan, np.nan)


def spatial_episode(ep, out_dir, valid="valid_primary", root=R):     # root: data/euv_test for the held-out test
    import sunpy.map, astropy.units as u
    from astropy.io import fits
    from astropy.time import Time
    from scipy import ndimage
    from sunpy.coordinates import propagate_with_solar_surface
    from aiapy.calibrate import update_pointing
    from aiapy.calibrate.utils import get_pointing_table
    from euv_run import register_cutout
    from euv_dctrl import samples, hmi_to_frame, frame_means
    from euv_pilot import SAT_DN
    from euv_full import hmi_files, trec_of
    warnings.filterwarnings("ignore")
    t0 = time.time(); h, t = ep["harpnum"], pd.Timestamp(ep["t"])
    mp, bp = hmi_files(f"{root}/hmi/{h}", ep["t_rec_tai"])
    mag = sunpy.map.Map(mp); bitmap = fits.open(bp)[-1].data
    S, short, n = samples(mag.data, bitmap)
    ny, nx = mag.data.shape
    centre = mag.pixel_to_world((nx - 1) / 2 * u.pix, (ny - 1) / 2 * u.pix)
    s = pd.read_csv(f"{root}/series/{ep['eid']}.csv", parse_dates=["t_obs", "t_rec"], float_precision="round_trip")
    rows = s[s[valid]].to_dict("records")                      # valid_sens = R4a_nf (flare check)
    files = {trec_of(p): p for p in glob.glob(f"{root}/aia/{h}/*.fits")}
    ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))
    V = np.full((len(rows), ny * nx), np.nan); IDX = np.full((len(rows), ny * nx), -1, np.int32)
    pil_same = not short                                           # pil_k == full PIL for every k: compute once
    sets = ["box"] + [f"pil_{k}" for k in range(NDRAW)] + [f"ctrl_{k}" for k in range(NDRAW)]
    pairs, cen, max_diff = [], [], 0.0
    for i, row in enumerate(rows):
        m = sunpy.map.Map(files[row["t_rec"]])
        exp = m.exposure_time.to_value("s"); raw = m.data.astype(float)
        if exp <= 0:
            raw[:] = np.nan; exp = 1.0
        raw[raw > SAT_DN] = np.nan
        try:
            m = update_pointing(m, pointing_table=ptab)
        except (IndexError, TypeError):                            # as compute_episode (header pointing kept)
            pass
        r = register_cutout(sunpy.map.Map(raw / exp, m.meta))
        idx = hmi_to_frame(mag, r)
        for k, val in frame_means(r.data, idx, S).items():         # check vs stored series
            a, b = val, row[k]
            max_diff = max(max_diff, 0.0 if (np.isnan(a) and np.isnan(b)) else abs(a - b) if np.isfinite(a - b) else np.inf)
        ok = idx >= 0; V[i, ok] = r.data.ravel()[idx[ok]]; IDX[i] = idx
        with propagate_with_solar_surface():
            px, py = r.world_to_pixel(centre.transform_to(r.coordinate_frame))
        cen.append((float(px.value), float(py.value)))
        if i and pd.Timedelta(0) < row["t_obs"] - rows[i - 1]["t_obs"] <= pd.Timedelta("24min"):
            d = V[i] - V[i - 1]
            p = dict(t_obs=row["t_obs"], dt_min=(row["t_obs"] - rows[i - 1]["t_obs"]).total_seconds() / 60,
                     shift_px=float(np.hypot(cen[i][0] - cen[i - 1][0], cen[i][1] - cen[i - 1][1])))
            p["kappa_box"], p["skew_box"] = _kurt_skew(d)
            kp = _kurt_skew(d[S["pil_0"]]) if pil_same else None
            for k in range(NDRAW):
                p[f"kappa_pil_{k}"], p[f"skew_pil_{k}"] = kp if pil_same else _kurt_skew(d[S[f"pil_{k}"]])
                p[f"kappa_ctrl_{k}"], p[f"skew_ctrl_{k}"] = _kurt_skew(d[S[f"ctrl_{k}"]])
            pairs.append(p)
    # R3: per-pixel threshold over all valid frames; brightenings = 8-connected patches covering >= 4 distinct AIA pixels
    with np.errstate(all="ignore"):
        nfin = np.isfinite(V).sum(0)
        thr = np.where(nfin >= 3, np.nanmean(V, 0) + 3 * np.nanstd(V, 0, ddof=1), np.inf)
    M = int(IDX.max()) + 2; fr = []
    for i in range(len(rows)):
        above = V[i] > thr
        lab, nl = ndimage.label(above.reshape(ny, nx), structure=np.ones((3, 3), int)); lab = lab.ravel()
        bright = np.zeros(lab.size, bool)
        if nl:
            sel = lab > 0
            key = np.unique(lab[sel].astype(np.int64) * M + IDX[i][sel])
            cnt = np.bincount((key // M).astype(int), minlength=nl + 1)
            bright = sel & (cnt[lab] >= 4)
        fin = np.isfinite(V[i]); f = dict(t_obs=rows[i]["t_obs"], n_bright_px=int(bright.sum()))
        for k in sets:
            P = S[k]; P = P[fin[P]]
            f[f"frac_{k}"] = float(bright[P].mean()) if len(P) else np.nan
        fr.append(f)
    P_, F_ = pd.DataFrame(pairs), pd.DataFrame(fr)
    P_.to_csv(f"{out_dir}/{ep['eid']}_pairs.csv", index=False); F_.to_csv(f"{out_dir}/{ep['eid']}_frames.csv", index=False)
    med = lambda c: float(np.nanmedian(P_[c])) if len(P_) and P_[c].notna().any() else np.nan
    mf = lambda c: float(np.nanmean(F_[c])) if len(F_) and F_[c].notna().any() else np.nan
    res = dict(eid=ep["eid"], harpnum=h, frames=len(rows), pairs=len(P_), n_pix=int(n), ctrl_short=bool(short), npix_box=ny * nx,
               max_frame_mean_diff=max_diff,
               R1=float(np.mean([med(f"kappa_pil_{k}") - med(f"kappa_ctrl_{k}") for k in range(NDRAW)])),
               R2=float(np.mean([med(f"skew_pil_{k}") - med(f"skew_ctrl_{k}") for k in range(NDRAW)])),
               R3=float(np.mean([mf(f"frac_pil_{k}") - mf(f"frac_ctrl_{k}") for k in range(NDRAW)])),
               R4a=med("kappa_box"), R4b=med("skew_box"), R4c=mf("frac_box"),
               shift_median=med("shift_px") if len(P_) else np.nan, elapsed_s=round(time.time() - t0, 1))
    json.dump(res, open(f"{out_dir}/{ep['eid']}.json", "w"))
    return res


def dev_episodes():
    from euv_full import episodes
    e = episodes(); done = {os.path.basename(p)[:-4] for p in glob.glob(f"{R}/series/*.csv")}
    return [dict(eid=x.eid, harpnum=int(x.harpnum), t=str(x.t), t_rec_tai=x.t_rec_tai) for x in e.itertuples() if x.eid in done]


def run_pool(eps, out_dir, workers=8, log=None, valid="valid_primary"):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    os.makedirs(out_dir, exist_ok=True); t0 = time.time(); res = []
    with ProcessPoolExecutor(workers) as pool:
        futs = {pool.submit(spatial_episode, e, out_dir, valid): e["eid"] for e in eps if not os.path.exists(f"{out_dir}/{e['eid']}.json")}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result(); res.append(r)
            assert r["max_frame_mean_diff"] < 1e-9, f"{r['eid']}: frame means not reproduced ({r['max_frame_mean_diff']})"
            if log and (i % 25 == 0 or i == len(futs)):
                msg = f"{pd.Timestamp.now():%H:%M} {i}/{len(futs)} episodes, elapsed {(time.time() - t0) / 3600:.2f} h"
                print(msg, flush=True); open(log, "a").write(msg + "\n")
    return res, time.time() - t0


def cv_fit(c, cols):                                              # = euv_step6.cv_fit
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from stage4_models import LR, K
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy()
    p = np.empty(len(c))
    for k in range(K):
        tr, te = f != k, f == k
        sc = StandardScaler().fit(c.loc[tr, cols])
        m = LogisticRegression(**LR).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]
    return p


def compare(coh, mask, col, name):                                # = euv_step6.analysis_set + compare (A vs A + col)
    from sklearn.metrics import roc_auc_score
    from stage4_models import wlogloss, A_COLS, SEED
    c = coh[mask].reset_index(drop=True).copy()
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    pA, pE = cv_fit(c, A_COLS), cv_fit(c, A_COLS + [col])
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    harps = np.unique(h); idx_of = {x: np.where(h == x)[0] for x in harps}
    rng, d = np.random.RandomState(SEED), []
    for _ in range(10000):
        ix = np.concatenate([idx_of[x] for x in rng.choice(harps, len(harps), replace=True)])
        d.append(wlogloss(y[ix], pA[ix], w[ix]) - wlogloss(y[ix], pE[ix], w[ix]))
    lo, hi = np.percentile(d, [2.5, 97.5]); llA, llE = wlogloss(y, pA, w), wlogloss(y, pE, w)
    return dict(candidate=name, episodes=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(harps),
                logloss_A=llA, logloss_A_plus=llE, delta_A_minus_Aplus=llA - llE, CI_lo=lo, CI_hi=hi,
                AUC_A=roc_auc_score(y, pA, sample_weight=w), AUC_A_plus=roc_auc_score(y, pE, sample_weight=w))


if __name__ == "__main__" and sys.argv[1:] == ["timing"]:
    eps = dev_episodes(); pick = sorted(np.random.RandomState(0).choice(len(eps), 10, replace=False))
    ten = [eps[i] for i in pick]
    d1, d2 = f"{R}/spatial_timing/single", f"{R}/spatial_timing/pool"; os.makedirs(d1, exist_ok=True)
    t0 = time.time(); single = [spatial_episode(e, d1) for e in ten]; w1 = time.time() - t0
    pool, w2 = run_pool(ten, d2)
    a = pd.DataFrame(single).set_index("eid").sort_index(); b = pd.DataFrame(pool).set_index("eid").sort_index()
    cols = ["R1", "R2", "R3", "R4a", "R4b", "R4c", "frames", "pairs", "max_frame_mean_diff"]
    same = all(np.allclose(a[c], b[c], rtol=0, atol=0, equal_nan=True) for c in cols) and all(
        pd.read_csv(f"{d1}/{e}_{k}.csv").equals(pd.read_csv(f"{d2}/{e}_{k}.csv")) for e in a.index for k in ["pairs", "frames"])
    print(a[["frames", "pairs", "npix_box", "max_frame_mean_diff", "elapsed_s"]].to_string())
    print(f"frame means reproduced (max |diff| over 10 episodes): {a.max_frame_mean_diff.max():.1e}; single == pool: {same}")
    mean_single, mean_pool = a.elapsed_s.mean(), b.elapsed_s.mean()
    print(f"single process: wall {w1:.0f} s, mean {mean_single:.1f} s/episode | pool (8): wall {w2:.0f} s, "
          f"mean {mean_pool:.1f} s/episode inside workers")
    for name, N in [("dev", 546), ("test", 313)]:
        print(f"projected {name} ({N} episodes): {N * mean_pool / 8 / 3600:.2f} h with 8 workers "
              f"({N * mean_single / 3600:.2f} h single process)")

if __name__ == "__main__" and sys.argv[1:] == ["run"]:
    res, wall = run_pool(dev_episodes(), OUT, log=f"{R}/logs/spatial.log")
    print(f"done: {len(res)} episodes in {wall / 3600:.2f} h")

if __name__ == "__main__" and sys.argv[1:] == ["eval"]:
    CANDS = ["R1", "R2", "R3", "R4a", "R4b", "R4c"]
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    res = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])[["eid", "primary_fill", "primary_dCV"]]
    res[["primary_fill", "primary_dCV"]] = res[["primary_fill", "primary_dCV"]].apply(pd.to_numeric, errors="coerce")
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/*.json")])
    assert len(sp) == 546 and (sp.max_frame_mean_diff < 1e-9).all(), "spatial results incomplete or frame means not reproduced"
    coh = coh.merge(res, on="eid", how="left").merge(sp[["eid"] + CANDS], on="eid", how="left")

    base = coh.primary_fill >= 0.80
    s6 = pd.read_csv(f"{R}/step6/compare.csv").set_index("set").loc["PRIMARY"]
    chk = compare(coh, base & coh.primary_dCV.notna(), "primary_dCV", "check")
    assert all(abs(chk[a] - s6[b]) < 1e-12 for a, b in [("delta_A_minus_Aplus", "delta_A_minus_E94"), ("CI_lo", "CI_lo"), ("CI_hi", "CI_hi")])
    print(f"check: step 6 PRIMARY reproduced (delta {chk['delta_A_minus_Aplus']:.4f}, CI [{chk['CI_lo']:.4f}, {chk['CI_hi']:.4f}])")
    print(f"check: frame means reproduced in all 546 episodes (max |diff| {sp.max_frame_mean_diff.max():.1e})")
    sh = pd.concat([pd.read_csv(p, usecols=["shift_px"]) for p in glob.glob(f"{OUT}/*_pairs.csv")]).shift_px
    print(f"check: frame-to-frame pointing shift of the patch centre (AIA px), {len(sh)} pairs: median {sh.median():.3f}, "
          f"95th pct {sh.quantile(.95):.3f}, max {sh.max():.3f}")
    rows = []
    for k in CANDS:
        m = base & coh[k].notna()
        r = compare(coh, m, k, k); r["excluded_undefined"] = int((base & coh[k].isna()).sum())
        r["excluded_eids"] = ";".join(coh.loc[base & coh[k].isna(), "eid"]); rows.append(r)
    T = pd.DataFrame(rows); T.to_csv(f"{OUT}/eval_compare.csv", index=False)
    pd.set_option("display.width", 250)
    print("\n1. n valid per candidate (primary 80% set = 541; excluded = value undefined)")
    print(T[["candidate", "episodes", "true", "false", "HARPs", "excluded_undefined", "excluded_eids"]].to_string(index=False))
    print("\n2. delta = LL(A) - LL(A + Rk), + = candidate helps; HARP bootstrap 10,000, seed 20260921; weighted AUC "
          "(dev 2010-2019, internal 5-fold CV, EXPLORATORY)")
    print(T[["candidate", "logloss_A", "logloss_A_plus", "delta_A_minus_Aplus", "CI_lo", "CI_hi", "AUC_A", "AUC_A_plus"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    pil = T[T.candidate.isin(["R1", "R2", "R3"])].set_index("candidate").delta_A_minus_Aplus
    best = pil.idxmax()
    print(f"\n3. selection rule (R1-R3): largest delta = {best} ({pil[best]:.4f}); qualifies (delta > 0): {bool(pil[best] > 0)}")

# ================================================================ R4a FLARE CHECK (decisions.md 2026-09-25; EXPLORATORY)
NF, WORKERS_NF = f"{R}/spatial_nf", os.cpu_count() - 1

if __name__ == "__main__" and sys.argv[1:] == ["nf_check"]:
    eps = dev_episodes(); five = [eps[i] for i in sorted(np.random.RandomState(0).choice(len(eps), 5, replace=False))]
    d1, d2 = f"{R}/spatial_nf_check/single", f"{R}/spatial_nf_check/pool"; os.makedirs(d1, exist_ok=True)
    print(f"workers = os.cpu_count() - 1 = {WORKERS_NF}")
    t0 = time.time(); single = [spatial_episode(e, d1, "valid_sens") for e in five]; w1 = time.time() - t0
    pool, w2 = run_pool(five, d2, workers=WORKERS_NF, valid="valid_sens")
    a = pd.DataFrame(single).set_index("eid").sort_index(); b = pd.DataFrame(pool).set_index("eid").sort_index()
    num = ["R1", "R2", "R3", "R4a", "R4b", "R4c", "frames", "pairs", "max_frame_mean_diff", "shift_median"]
    same = all(np.array_equal(a[c].to_numpy(float), b[c].to_numpy(float), equal_nan=True) for c in num) and all(
        pd.read_csv(f"{d1}/{e}_{k}.csv").equals(pd.read_csv(f"{d2}/{e}_{k}.csv")) for e in a.index for k in ["pairs", "frames"])
    print(a[["frames", "pairs", "max_frame_mean_diff", "elapsed_s"]].to_string())
    print(f"pool ({WORKERS_NF}) == single process exactly: {same}; single wall {w1:.0f} s, pool wall {w2:.0f} s")

if __name__ == "__main__" and sys.argv[1:2] == ["nf_run"]:
    w = int(sys.argv[2]) if len(sys.argv) > 2 else WORKERS_NF
    print(f"workers = {w}", flush=True)
    res, wall = run_pool(dev_episodes(), NF, workers=w, log=f"{R}/logs/spatial_nf.log", valid="valid_sens")
    print(f"done: {len(res)} episodes in {wall / 3600:.2f} h", flush=True)
    open(f"{R}/logs/spatial_nf.log", "a").write(f"done: {len(res)} episodes in {wall / 3600:.2f} h (this pass), workers {w}\n")

if __name__ == "__main__" and sys.argv[1:] == ["nf_eval"]:
    from scipy.stats import spearmanr
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    res = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])[["eid", "primary_fill", "sens_fill"]]
    res[["primary_fill", "sens_fill"]] = res[["primary_fill", "sens_fill"]].apply(pd.to_numeric, errors="coerce")
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/*.json")])[["eid", "R4a"]]
    nf = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{NF}/*.json")])
    assert len(nf) == 546 and (nf.max_frame_mean_diff < 1e-9).all(), "R4a_nf incomplete or frame means not reproduced"
    nf = nf[["eid", "R4a", "frames", "pairs"]].rename(columns={"R4a": "R4a_nf", "frames": "frames_nf", "pairs": "pairs_nf"})
    coh = coh.merge(res, on="eid", how="left").merge(sp, on="eid", how="left").merge(nf, on="eid", how="left")
    fl = {os.path.basename(p)[:-4]: int((lambda s: (s.valid_primary & s.flare).sum())(pd.read_csv(p, usecols=["valid_primary", "flare"])))
          for p in glob.glob(f"{R}/series/*.csv")}
    coh["flare_frames_in_R4a"] = coh.eid.map(fl)
    px = pd.read_csv(f"{OUT}/eval_compare.csv").set_index("candidate").loc["R4a"]    # check: module-level compare = Phase X
    chk = compare(coh, (coh.primary_fill >= 0.80) & coh.R4a.notna(), "R4a", "check")
    assert all(abs(chk[k] - px[k]) < 1e-12 for k in ["delta_A_minus_Aplus", "CI_lo", "CI_hi", "AUC_A", "AUC_A_plus"])
    print(f"check: Phase X R4a row reproduced (delta {chk['delta_A_minus_Aplus']:.4f}, CI [{chk['CI_lo']:.4f}, {chk['CI_hi']:.4f}])")
    m = (coh.sens_fill >= 0.80) & coh.R4a_nf.notna()
    und = coh.loc[(coh.sens_fill >= 0.80) & coh.R4a_nf.isna(), "eid"].tolist()
    assert coh.loc[m, "R4a"].notna().all() and (coh.loc[m, "primary_fill"] >= 0.80).all()
    c = coh[m]
    print(f"\n1. n valid: R4a_nf (sens fill >= 80%, defined) {m.sum()}: true {int(c.true_alarm.sum())} / false {int((c.true_alarm == 0).sum())} "
          f"(excluded undefined: {len(und)} {und}); Phase X R4a 541: 96 / 445")
    T = pd.DataFrame([compare(coh, m, "R4a", "A vs A+R4a (flare frames kept)"),
                      compare(coh, m, "R4a_nf", "A vs A+R4a_nf (flare frames removed)")])
    T.to_csv(f"{NF}/eval_nf_compare.csv", index=False); pd.set_option("display.width", 250)
    print("\n2. same episodes; delta = LL(A) - LL(A + x), + = helps; HARP bootstrap 10,000, seed 20260921; weighted AUC")
    print(T[["candidate", "episodes", "true", "false", "HARPs", "logloss_A", "logloss_A_plus", "delta_A_minus_Aplus", "CI_lo", "CI_hi",
             "AUC_A", "AUC_A_plus"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    S3 = pd.DataFrame([dict(measure=x, variable=v, n=len(c), rho=spearmanr(c[x], c[v])[0], p=spearmanr(c[x], c[v])[1])
                       for x in ["R4a", "R4a_nf"] for v in ["n_C", "n_M", "n_X", "score"]])
    S3.to_csv(f"{NF}/eval_nf_spearman.csv", index=False)
    print("\n3. Spearman rho with flare history and gate score (same episodes)")
    print(S3.to_string(index=False, formatters={"rho": "{:.4f}".format, "p": "{:.2e}".format}))
    print("\n4. episodes above the 99th percentile (same episodes; flare frame = valid_primary & flare, i.e. used by R4a)")
    for x in ["R4a", "R4a_nf"]:
        q = np.percentile(c[x], 99); top = c[c[x] > q]
        print(f"   {x}: p99 {q:.4f}; above: {len(top)}; with >= 1 flare frame: {int((top.flare_frames_in_R4a >= 1).sum())} "
              f"(flare frames per episode: {top.flare_frames_in_R4a.tolist()})")
    r, p = spearmanr(c.R4a, c.R4a_nf)
    print(f"\n5. Spearman rho(R4a, R4a_nf) = {r:.4f} (p {p:.2e}, n {len(c)})")
    q = dict(delta=T.iloc[1].delta_A_minus_Aplus, auc_up=T.iloc[1].AUC_A_plus > T.iloc[1].AUC_A)
    reading = ("R4a survives flare removal" if q["delta"] > 0 and q["auc_up"] else
               "R4a mostly reflected flares" if q["delta"] <= 0 else "neither condition met")
    print(f"\npre-stated reading (mechanical): delta(A - A+R4a_nf) = {q['delta']:.4f}, AUC(A+R4a_nf) > AUC(A): {q['auc_up']} -> \"{reading}\"")
