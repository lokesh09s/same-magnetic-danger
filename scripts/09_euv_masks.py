"""EXPLORATORY (decisions.md 2026-09-26, bebbfe6): three localised 94 A areas -- M1 SG-PIL, M2 CORE, M3 SPOT.
DEV 2010-2019 ONLY. Frames processed exactly as euv_spatial.spatial_episode (valid_primary rows of the stored series).
Usage: python euv_masks.py selftest | timing | run | report | eval"""
import glob, json, math, os, sys, time, warnings
import numpy as np, pandas as pd

R, OUT = "data/euv_full", "data/euv_full/masks"
MASKS = ["SG", "CORE", "SPOT"]
BONF = (0.833, 99.167)


# ================================================================ masks (label-blind, alarm-time magnetogram / window)
def sg_blocks(B, mm_px):
    from euv_pilot import pil_mask
    B = np.nan_to_num(B); ny, nx = B.shape; by, bx = ny // 4, nx // 4
    if by < 2 or bx < 2:
        return None
    r = B[:by * 4, :bx * 4].reshape(by, 4, bx, 4).mean(axis=(1, 3))
    g = np.hypot(*np.gradient(r, 4 * mm_px))
    nl = np.zeros(r.shape, bool)
    s = r[:, :-1] * r[:, 1:] < 0; nl[:, :-1] |= s; nl[:, 1:] |= s
    s = r[:-1, :] * r[1:, :] < 0; nl[:-1, :] |= s; nl[1:, :] |= s
    pil = pil_mask(B)[:by * 4, :bx * 4].reshape(by, 4, bx, 4).all(axis=(1, 3))
    return dict(r=r, g=g, nl=nl, pil=pil, keep=nl & pil & (g > 50))


def sg_pil(B, mm_px):
    """M1: HMI pixels of 4x4 blocks on a sign change, entirely inside the PIL mask, with |grad| > 50 G/Mm."""
    ny, nx = B.shape; d = sg_blocks(B, mm_px)
    if d is None:
        return np.array([], int)
    m = np.zeros((ny, nx), bool); by, bx = d["keep"].shape
    m[:by * 4, :bx * 4] = np.repeat(np.repeat(d["keep"], 4, 0), 4, 1)
    return np.flatnonzero(m)


def spot(B):
    """M3: |B| >= 1000 G (NaN pixels excluded)."""
    with np.errstate(invalid="ignore"):
        return np.flatnonzero(np.abs(B) >= 1000)


def core(V):
    """M2: top 1% of pixels by per-pixel nanmedian over the valid frames; stable order."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nanmedian(V, axis=0)
    fin = np.flatnonzero(np.isfinite(med))
    k = math.ceil(0.01 * len(fin))
    return np.sort(fin[np.argsort(-med[fin], kind="stable")][:k])


def mask_mean(v, P):                                                 # = euv_dctrl.frame_means formula for one set
    return np.nanmean(v[P]) if len(P) and np.isfinite(v[P]).any() else np.nan


# ================================================================ per episode
def mask_episode(ep, out_dir, root=R):
    import sunpy.map
    from astropy.io import fits
    from astropy.time import Time
    from aiapy.calibrate import update_pointing
    from aiapy.calibrate.utils import get_pointing_table
    from euv_run import register_cutout
    from euv_dctrl import samples, hmi_to_frame, frame_means, cv
    from euv_pilot import SAT_DN
    from euv_full import hmi_files, trec_of
    warnings.filterwarnings("ignore")
    t0 = time.time(); h, t = ep["harpnum"], pd.Timestamp(ep["t"])
    mp, bp = hmi_files(f"{root}/hmi/{h}", ep["t_rec_tai"])
    mag = sunpy.map.Map(mp); bitmap = fits.open(bp)[-1].data
    S, _, _ = samples(mag.data, bitmap)
    ny, nx = mag.data.shape
    mm_px = float(mag.meta["cdelt1"]) * float(mag.meta["rsun_ref"]) / float(mag.meta["rsun_obs"]) / 1e6
    M = {"SG": sg_pil(mag.data, mm_px), "SPOT": spot(mag.data)}
    s = pd.read_csv(f"{root}/series/{ep['eid']}.csv", parse_dates=["t_obs", "t_rec"], float_precision="round_trip")
    rows = s[s.valid_primary].to_dict("records")
    files = {trec_of(p): p for p in glob.glob(f"{root}/aia/{h}/*.fits")}
    ptab = get_pointing_table("JSOC", time_range=(Time(t - pd.Timedelta("26h")), Time(t + pd.Timedelta("2h"))))
    V = np.full((len(rows), ny * nx), np.nan); fr, box_diff = [], 0.0
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
        fm = frame_means(r.data, idx, {"box": S["box"], "SG": M["SG"], "SPOT": M["SPOT"]})
        a, b = fm["box"], row["box"]
        box_diff = max(box_diff, 0.0 if (np.isnan(a) and np.isnan(b)) else abs(a - b) if np.isfinite(a - b) else np.inf)
        ok = idx >= 0; V[i, ok] = r.data.ravel()[idx[ok]]
        fr.append(dict(t_obs=row["t_obs"], valid_sens=bool(row["valid_sens"]), box=fm["box"], SG=fm["SG"], SPOT=fm["SPOT"]))
    M["CORE"] = core(V)
    F = pd.DataFrame(fr); F["CORE"] = [mask_mean(V[i], M["CORE"]) for i in range(len(rows))]
    F.to_csv(f"{out_dir}/{ep['eid']}_frames.csv", index=False)
    cvb = cv(F.t_obs.to_numpy(), F.box.to_numpy())
    cvb_diff = abs(cvb - ep["primary_CV_box"])
    assert box_diff < 1e-9, f"{ep['eid']}: frame box means not reproduced ({box_diff})"
    assert cvb_diff < 1e-9, f"{ep['eid']}: CV_box not reproduced ({cvb_diff})"
    res = dict(eid=ep["eid"], harpnum=h, frames=len(rows), frames_sens=int(F.valid_sens.sum()), npix_box=ny * nx, mm_px=mm_px,
               box_diff=box_diff, cv_box_diff=cvb_diff)
    for k in MASKS:
        res[f"n_{k}"] = len(M[k])
        for ver, sel in [("", np.ones(len(F), bool)), ("_nf", F.valid_sens.to_numpy())]:
            y = F.loc[sel, k].to_numpy(); tt = F.loc[sel, "t_obs"].to_numpy()
            c = cv(tt, y) if len(M[k]) and np.isfinite(y).sum() >= 3 else np.nan
            res[f"CV_{k}{ver}"] = c
            res[f"lcv_{k}{ver}"] = float(np.log10(c)) if np.isfinite(c) and c > 0 else np.nan
    for a, b in [("SG", "SPOT"), ("SG", "CORE"), ("CORE", "SPOT")]:
        n = min(len(M[a]), len(M[b]))
        res[f"ov_{a}_{b}"] = len(np.intersect1d(M[a], M[b])) / n if n else np.nan
    res["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(res, open(f"{out_dir}/{ep['eid']}.json", "w"))
    return res


def dev_eps():
    from euv_spatial import dev_episodes
    st = {}
    for p in glob.glob(f"{R}/results/*.json"):
        d = json.load(open(p))
        if "eid" in d:                                               # results/ also holds step4_choice.json
            st[d["eid"]] = pd.to_numeric(d.get("primary_CV_box"), errors="coerce")
    return [dict(e, primary_CV_box=float(st[e["eid"]])) for e in dev_episodes()]


def run_pool(eps, out_dir, workers):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    os.makedirs(out_dir, exist_ok=True); t0 = time.time(); res = []
    with ProcessPoolExecutor(workers) as pool:
        futs = [pool.submit(mask_episode, e, out_dir) for e in eps if not os.path.exists(f"{out_dir}/{e['eid']}.json")]
        for i, f in enumerate(as_completed(futs), 1):
            res.append(f.result())                               # an assertion in a worker stops the run here
            if i % 25 == 0 or i == len(futs):
                open(f"{R}/logs/masks.log", "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(futs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    return res, time.time() - t0


# ================================================================ modes
if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    mm = 0.362; x = np.arange(64)
    sharp = np.tile(np.where(x < 32, 1500.0, -1500.0), (64, 1))
    smooth = np.tile(14.0 * (31.5 - x), (64, 1))                   # 14 G/px = 38.7 G/Mm at 0.362 Mm/px
    ds = sg_blocks(smooth, mm)
    assert len(sg_pil(sharp, mm)) > 0, "sharp bipole: SG-PIL empty"
    assert (ds["nl"] & ds["pil"]).any() and ds["g"][ds["nl"] & ds["pil"]].max() < 50, "smooth: NL inside PIL with g < 50 expected"
    assert len(sg_pil(smooth, mm)) == 0, "smooth bipole: SG-PIL not empty"
    B = np.array([[1000.0, -1000.0, 999.999, np.nan, 1500.0, -999.0]])
    assert spot(B).tolist() == [0, 1, 4], "SPOT threshold"
    rng = np.random.RandomState(0); V = rng.rand(5, 250); V[:, 200:] = np.nan; V[:, [3, 7, 11]] = 5.0
    c1, c2 = core(V), core(V)
    assert len(c1) == math.ceil(0.01 * 200) == 2 and (c1 == c2).all() and c1.tolist() == [3, 7], "CORE count / ties / determinism"
    print(f"selftest passed: SG-PIL sharp {len(sg_pil(sharp, mm))} px, smooth 0 px (NL inside PIL max g "
          f"{ds['g'][ds['nl'] & ds['pil']].max():.1f} G/Mm); SPOT >= 1000 G incl.; CORE ceil(1%) = 2, stable ties, deterministic")

if __name__ == "__main__" and sys.argv[1:] == ["timing"]:
    eps = dev_eps(); three = [eps[i] for i in sorted(np.random.RandomState(0).choice(len(eps), 3, replace=False))]
    d = f"{R}/masks_timing"; os.makedirs(d, exist_ok=True); t0 = time.time()
    res = [mask_episode(e, d) for e in three]
    for r in res:
        print(f"{r['eid']}: frames {r['frames']}, n_SG {r['n_SG']}, n_CORE {r['n_CORE']}, n_SPOT {r['n_SPOT']}, "
              f"box diff {r['box_diff']:.1e}, CV_box diff {r['cv_box_diff']:.1e}, {r['elapsed_s']} s")
    m = np.mean([r["elapsed_s"] for r in res]); w = os.cpu_count() - 1
    print(f"single process: {time.time() - t0:.0f} s for 3; projected 546 episodes with {w} workers ~ {546 * m * 1.5 / w / 3600:.2f} h "
          f"(x1.5 pool contention, from the Phase X timing)")

if __name__ == "__main__" and sys.argv[1:] == ["run"]:
    w = os.cpu_count() - 1
    open(f"{R}/logs/masks.log", "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} start, workers {w}\n")
    res, wall = run_pool(dev_eps(), OUT, w)
    open(f"{R}/logs/masks.log", "a").write(f"done: {len(res)} episodes (this pass) in {wall / 3600:.2f} h, workers {w}\n")

if __name__ == "__main__" and sys.argv[1:] == ["report"]:
    J = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/*.json")])
    rs = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])[["eid", "primary_fill", "sens_fill"]]
    rs[["primary_fill", "sens_fill"]] = rs[["primary_fill", "sens_fill"]].apply(pd.to_numeric, errors="coerce")
    J = J.merge(rs, on="eid", how="left"); P, S = J.primary_fill >= 0.8, J.sens_fill >= 0.8
    print(f"LABEL-BLIND REPORT (no labels read): {len(J)} dev episodes; checks: max box diff {J.box_diff.max():.1e}, "
          f"max CV_box diff {J.cv_box_diff.max():.1e}")
    for k in MASKS:
        n = J[f"n_{k}"]
        print(f"  {k:4s} pixels: median {n.median():.0f}, min {n.min()}, max {n.max()}; empty {int((n == 0).sum())}/{len(J)}; "
              f"undefined log10 CV: all {int(J[f'lcv_{k}'].isna().sum())}, primary 80% set {int((P & J[f'lcv_{k}'].isna()).sum())}/{int(P.sum())}, "
              f"flare-excluded 80% set {int((S & J[f'lcv_{k}_nf'].isna()).sum())}/{int(S.sum())}")
    for a, b in [("SG", "SPOT"), ("SG", "CORE"), ("CORE", "SPOT")]:
        o = J[f"ov_{a}_{b}"]
        print(f"  overlap {a} & {b} / smaller mask: median {o.median():.4f} (n {int(o.notna().sum())} episodes with both non-empty)")

if __name__ == "__main__" and sys.argv[1:] == ["eval"]:
    from concurrent.futures import ProcessPoolExecutor
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    from euv_spatial import cv_fit
    from phase_f import load_base, prep, boot_many, wlogloss, ratio_jobs, pct, A_COLS, W
    from euv_f2_replication import twins as hist_twins
    LAB = {"SG": "SG-PIL", "CORE": "brightest core", "SPOT": "SPOT"}      # output names (user, 2026-09-26)
    t00 = time.time(); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    dv = load_base()
    J = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/*.json")])
    assert len(J) == 546 and (J.box_diff < 1e-9).all() and (J.cv_box_diff < 1e-9).all()
    dv = dv.merge(J[["eid"] + [f"{p}_{k}{v}" for p in ["CV", "lcv"] for k in MASKS for v in ["", "_nf"]]], on="eid", how="left")
    dv["lcv_box"] = np.log10(dv.primary_CV_box)

    def jobs_for(name, c, base, full):
        pA, pE = cv_fit(c, base), cv_fit(c, full); y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
        groups = [np.where(h == v)[0] for v in np.unique(h)]
        est = dict(test=name, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups),
                   logloss_base=wlogloss(y, pA, w), logloss_full=wlogloss(y, pE, w),
                   AUC_base=roc_auc_score(y, pA, sample_weight=w), AUC_full=roc_auc_score(y, pE, sample_weight=w))
        est["delta"] = est["logloss_base"] - est["logloss_full"]
        return est, {name: ("dll", dict(y=y, w=w, pA=pA, pE=pE, groups=groups), 10000, 20260921)}

    def evaluate(specs, pool):
        ests, jobs = [], {}
        for s in specs:
            e, j = jobs_for(*s); ests.append(e); jobs.update(j)
        B = boot_many(jobs, pool)
        for e in ests:
            b = np.asarray(B[e["test"]], float)
            e["CI95_lo"], e["CI95_hi"] = np.percentile(b, [2.5, 97.5]); e["CI9833_lo"], e["CI9833_hi"] = np.percentile(b, list(BONF))
        return pd.DataFrame(ests)

    fmt = lambda v: f"{v:.4f}"
    with ProcessPoolExecutor(W) as pool:
        px = pd.read_csv(f"{R}/spatial/eval_compare.csv", float_precision="round_trip").set_index("candidate").loc["R4a"]
        ck = evaluate([("check R4a", prep(dv, dv.P & dv.R4a.notna()), A_COLS, A_COLS + ["R4a"])], pool).iloc[0]
        assert ck.delta == px.delta_A_minus_Aplus and ck.CI95_lo == px.CI_lo and ck.CI95_hi == px.CI_hi, "Phase X R4a not reproduced"
        print(f"check: modified compare reproduces Phase X R4a exactly (delta {ck.delta:.4f}, 95% CI [{ck.CI95_lo:.4f}, {ck.CI95_hi:.4f}])")
        print("\nPRIMARY (dev 2010-2019, internal 5-fold CV, EXPLORATORY): A vs A + log10 CV_M; delta = LL(A) - LL(A+M), + = helps; "
              "HARP bootstrap 10,000, seed 20260921; 95% and Bonferroni 98.33% CI from the same resamples")
        for k in MASKS:
            print(f"  {LAB[k]}: primary 80% set {int(dv.P.sum())}, excluded label-blind (undefined) {int((dv.P & dv[f'lcv_{k}'].isna()).sum())}")
        T = evaluate([(LAB[k], prep(dv, dv.P & dv[f"lcv_{k}"].notna()), A_COLS, A_COLS + [f"lcv_{k}"]) for k in MASKS], pool)
        print(T.to_string(index=False, float_format=fmt))
        for _, r in T.iterrows():
            el = r.delta > 0 and r.CI9833_lo > 0 and r.AUC_full > r.AUC_base
            print(f"  pre-stated reading {r.test}: delta {r.delta:+.4f}, 98.33% CI lower {r.CI9833_lo:+.4f}, AUC {r.AUC_base:.4f} -> "
                  f"{r.AUC_full:.4f} -> \"{'ELIGIBLE for independent confirmation' if el else 'NOT ELIGIBLE'}\"")
        print("\nSECONDARY (descriptive; cannot change any reading)")
        print("s1: A + log10 CV_box vs A + log10 CV_box + log10 CV_M")
        T1 = evaluate([(f"s1 {LAB[k]}", prep(dv, dv.P & dv[f"lcv_{k}"].notna() & dv.lcv_box.notna()), A_COLS + ["lcv_box"],
                        A_COLS + ["lcv_box", f"lcv_{k}"]) for k in MASKS], pool)
        print(T1[["test", "n", "true", "false", "logloss_base", "logloss_full", "delta", "CI95_lo", "CI95_hi", "AUC_base", "AUC_full"]]
              .to_string(index=False, float_format=fmt))
        print("\ns2: CV_M ratios, true / false of medians (F2 ratio code; 2,000, seed 0)")
        tw81 = pd.read_csv(f"{R}/step6/twins_PRIMARY.csv"); twh, _ = hist_twins(dv[dv.P], by_group=True)
        ests, jobs = [], {}
        for lab, tw in [("81 gate-score twins", tw81), (f"{len(twh)} same-flare-history twins", twh)]:
            for k in MASKS:
                e, j = ratio_jobs(f"{LAB[k]} | {lab}", dv[dv.P], f"CV_{k}", "ratio", tw); ests.append(e); jobs.update(j)
        B = boot_many(jobs, pool)
        for e in ests:
            e["all_CI"] = "[%.4f, %.4f]" % pct(B[(e["measure"], "all")]); e["twins_CI"] = "[%.4f, %.4f]" % pct(B[(e["measure"], "tw")])
        T2 = pd.DataFrame(ests)
        print(T2[["measure", "n", "n_true", "n_false", "med_true", "med_false", "ratio_all", "all_CI", "pairs", "twin_med_true",
                  "twin_med_false", "ratio_twins", "twins_CI"]].to_string(index=False, float_format=fmt))
        print("\ns3: flare-excluded version (valid_sens frames, sens_fill >= 0.80): A vs A + log10 CV_M_nf")
        for k in MASKS:
            print(f"  {LAB[k]}: flare-excluded 80% set {int(dv.S.sum())}, excluded label-blind {int((dv.S & dv[f'lcv_{k}_nf'].isna()).sum())}")
        T3 = evaluate([(f"s3 {LAB[k]} (flare-excluded)", prep(dv, dv.S & dv[f"lcv_{k}_nf"].notna()), A_COLS, A_COLS + [f"lcv_{k}_nf"]) for k in MASKS], pool)
        print(T3.to_string(index=False, float_format=fmt))
    print("\ns4: Spearman rho (PRIMARY set of each mask, unweighted)")
    rows = []
    for k in MASKS:
        c = dv[dv.P & dv[f"lcv_{k}"].notna()]
        for v in ["n_C", "n_M", "n_X", "score", "lcv_box"]:
            r, p = spearmanr(c[f"lcv_{k}"], c[v]); rows.append(dict(measure=f"log10 CV {LAB[k]}", variable=v, n=len(c), rho=r, p=p))
    T4 = pd.DataFrame(rows); print(T4.to_string(index=False, formatters={"rho": "{:.4f}".format, "p": "{:.2e}".format}))
    for nm, t in [("primary", T), ("s1", T1), ("s2", T2), ("s3", T3), ("s4", T4)]:
        t.to_csv(f"{OUT}/eval_{nm}.csv", index=False)
    print(f"\nwall {time.time() - t00:.1f} s, workers {W}")
