"""Candidate #29 FLICKER + BRIGHTNESS LEVEL (FBL) -- decisions.md 2026-09-30 (b3b0c3a, amendment 83973d1). EXPLORATORY (dev).
L = log10(mean box brightness, DN/s per pixel, over the valid primary frames) = log10 of CV_box's denominator (euv_dctrl.cv).
Primary C_CV + L; secondaries (s1) C_CV + L + centred L x log10 CV_box, (s2) C_CV + S1 (stored, already log10).
Usage: python fbl.py step1 <scratch dir outside the repo>   label-blind L, checks, crash test on SYNTHETIC labels (scratch deleted)
       python fbl.py step2                                  dev evaluation E1-E3, run once (reads the real labels)"""
import hashlib, json, os, shutil, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from minirocket import base_frame, CCV, SEED

SER, OUT = "data/euv_full/series", "data/fbl"
TOL, DRIFT, MIN_N = 1e-12, 0.1, 10
STOP_SENTENCE = ("Feature testing on the 94 Å data is closed after candidate #29; no further 94 Å features will be tested on "
                 "2010–2026 data.")
warnings.filterwarnings("ignore")
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def level(eid):
    """-> (L, mean, detrended SD recomputed with euv_pilot.detrended_sd, n valid, reason). Valid = valid_primary rows with finite box,
    in file order (the frames euv_dctrl.cv used for CV_box)."""
    from euv_pilot import detrended_sd
    p = f"{SER}/{eid}.csv"
    if not os.path.exists(p):
        return np.nan, np.nan, np.nan, 0, "no series file"
    s = pd.read_csv(p, usecols=["t_obs", "box", "valid_primary"], parse_dates=["t_obs"])
    v = s[s.valid_primary.astype(bool) & np.isfinite(s.box)]
    if not len(v):
        return np.nan, np.nan, np.nan, 0, "no valid frame"
    m = float(np.mean(v.box.to_numpy()))
    sd = detrended_sd(v.t_obs.to_numpy(), v.box.to_numpy()) if len(v) >= 3 else np.nan
    return (np.log10(m) if m > 0 else np.nan), m, sd, len(v), ("" if m > 0 else "mean <= 0")


def all_levels():
    """L for the 547 dev episodes (label-free: oof_cohort_dev usecols harpnum, t) + the stored CV_box / S1."""
    import glob
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t"], parse_dates=["t"])
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    rows = [dict(eid=e, year=t.year, **dict(zip(["L", "mean", "sd", "n_valid", "reason"], level(e)))) for e, t in zip(coh.eid, coh.t)]
    d = pd.DataFrame(rows)
    res = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_full/results/*.json")])[["eid", "primary_CV_box"]]
    res["primary_CV_box"] = pd.to_numeric(res.primary_CV_box, errors="coerce")
    return d.merge(res, on="eid", how="left", validate="1:1")


def fit_inter(c, cols):
    """= euv_heldout.fit_folds, plus a product column of L and log10_CV_box centred on each training fold."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from stage4_models import LR, K
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy()
    p = np.empty(len(c))
    for k in range(K):
        tr, te = f != k, f == k
        X = c[cols].copy()
        X["LxV"] = (c.L - c.L[tr].mean()) * (c.log10_CV_box - c.log10_CV_box[tr].mean())
        sc = StandardScaler().fit(X[tr])
        m = LogisticRegression(**LR).fit(sc.transform(X[tr]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(X[te]))[:, 1]
    return p


def frame(d):
    """The 541 analysis set with L and S1 attached (label-free)."""
    c = base_frame()
    c = c.merge(d[["eid", "L"]], on="eid", how="left", validate="1:1")
    s1 = pd.read_csv("data/phase_f/F5_values.csv", float_precision="round_trip")[["eid", "S1"]]
    c = c.merge(s1, on="eid", how="left", validate="1:1")
    c["year"] = c.t.dt.year
    return c


def evaluate(c, synthetic=False):
    """E1 (primary + s1 + s2), E2 (primary), E3 (descriptive). -> dict(qualifies, tau88, models, p)."""
    from sklearn.metrics import roc_auc_score
    from scipy.stats import binomtest, spearmanr
    from phase_f import tau_keep, op_stats, boot_many, ratio_jobs, pct, wlogloss, prep, W, NB_D, SEED_D, NB_R, SEED_R
    from euv_heldout import fit_folds
    from euv_f2_replication import twins
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    grp = lambda hh: [np.where(hh == v)[0] for v in np.unique(hh)]
    _, pB = fit_folds(c, CCV)
    mL, pL = fit_folds(c, CCV + ["L"])
    pI = fit_inter(c, CCV + ["L"])
    cs = c if c.S1.notna().all() else prep(c, c.S1.notna())
    pBs = pB if len(cs) == len(c) else fit_folds(cs, CCV)[1]
    _, pS = fit_folds(cs, CCV + ["S1"])
    ys, ws = cs.true_alarm.to_numpy(), cs.weight.to_numpy()
    jobs = {"primary": ("dll", dict(y=y, w=w, pA=pB, pE=pL, groups=grp(h)), NB_D, SEED_D),
            "s1": ("dll", dict(y=y, w=w, pA=pB, pE=pI, groups=grp(h)), NB_D, SEED_D),
            "s2": ("dll", dict(y=ys, w=ws, pA=pBs, pE=pS, groups=grp(cs.harpnum.to_numpy())), NB_D, SEED_D)}
    kept, e2 = [], []
    for keep in (0.88, 0.95):
        tB, tL = tau_keep(pB, y, w, keep), tau_keep(pL, y, w, keep); kB, kL = pB >= tB, pL >= tL; kept += [kB, kL]
        e2.append((keep, tB, tL, op_stats(y, w, kB), op_stats(y, w, kL), (int((kB & (y == 1)).sum()), int((~kB & (y == 0)).sum())),
                   (int((kL & (y == 1)).sum()), int((~kL & (y == 0)).sum()))))
    jobs["E2"] = ("op", dict(y=y, w=w, kept=kept, groups=grp(h)), NB_R, SEED_R)
    cc = c.assign(linL=10 ** c.L); T = {"T_a": twins(cc)[0], "T_b": twins(cc, by_group=True)[0]}; e3 = []
    for tn, tw in T.items():
        e, j = ratio_jobs(f"10^L {tn}", cc, "linL", "ratio", tw); jobs.update(j)
        v = cc.set_index("eid").L; xt, xf = tw.true_eid.map(v), tw.false_eid.map(v)
        up, dn = int((xt > xf).sum()), int((xt < xf).sum())
        e.update(twins=tn, true_higher=up, false_higher=dn, ties=len(tw) - up - dn, sign_p=binomtest(up, up + dn, 0.5).pvalue if up + dn else np.nan)
        e3.append(e)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    rho = {v: spearmanr(c.L, c[v]) for v in ["log10_CV_box", "score", "n_C", "n_M", "logR", "year"]}
    auc = lambda yy, p, ww: roc_auc_score(yy, p, sample_weight=ww)
    L_, pr, f4 = [], None, lambda v: f"{v:.4f}"
    pr = L_.append
    llB = wlogloss(y, pB, w)
    pr(f"\n== E1: Δ = LL(C_CV) − LL(model) (+ = helps); HARP bootstrap {NB_D}, seed {SEED_D}; AUC weighted")
    rows = [("PRIMARY C_CV + L", y, w, pB, pL, "primary"), ("s1 C_CV + L + L×log10CV_box (centred on the training fold)", y, w, pB, pI, "s1"),
            ("s2 C_CV + S1 (stored, log10 total brightness)", ys, ws, pBs, pS, "s2")]
    d1 = None
    for name, yy, ww, pa, pe, key in rows:
        lo, hi = pct(B[key]); d = wlogloss(yy, pa, ww) - wlogloss(yy, pe, ww); d1 = d if key == "primary" else d1
        pr(f"  {name}: n {len(yy)} (true {int(yy.sum())}); LL(C_CV) {wlogloss(yy, pa, ww):.4f}, LL(model) {wlogloss(yy, pe, ww):.4f}; "
           f"Δ {d:+.4f} [{lo:+.4f}, {hi:+.4f}]; AUC {auc(yy, pa, ww):.4f} -> {auc(yy, pe, ww):.4f}")
    co = pd.DataFrame([dict(fold=k, **dict(zip(cols, m.coef_[0]))) for k, (sc, m, cols) in enumerate(mL)])
    pr("  PRIMARY coefficients per fold (per 1 SD, training-fold StandardScaler):")
    pr(co.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    op = np.array(B["E2"], float)
    pr(f"\n== E2 MATCHED RETENTION (primary): dev OOF tau per model (tau_keep); weighted; paired HARP bootstrap {NB_R}, seed {SEED_R}")
    for i, (keep, tB, tL, sB, sL, nB, nL) in enumerate(e2):
        dd = op[:, 2 * i + 1, 1] - op[:, 2 * i, 1]
        pr(f"  target {keep:.2f}: C_CV tau {tB:.6f} true kept {nB[0]}/{int(y.sum())} ({sB[0]:.4f} w), false removed {nB[1]}/{int((y == 0).sum())} "
           f"({sB[1]:.4f} w) | C_CV + L tau {tL:.6f} true kept {nL[0]}/{int(y.sum())} ({sL[0]:.4f} w), false removed {nL[1]}/{int((y == 0).sum())} ({sL[1]:.4f} w)")
        pr(f"     false removed (C_CV + L − C_CV): {(sL[1] - sB[1]) * 100:+.2f} points [{np.nanpercentile(dd, 2.5) * 100:+.2f}, {np.nanpercentile(dd, 97.5) * 100:+.2f}]")
    pr("\n== E3 DESCRIPTIVE")
    R3 = pd.DataFrame(e3); R3["tw_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "tw")]) for m in R3.measure]; R3["all_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "all")]) for m in R3.measure]
    pr(f"  twins ratio of 10^L (mean DN/s per pixel): T_a = twins(c), T_b = twins(c, by_group=True); ratio_jobs mode 'ratio'; CI pairs by true HARP {NB_R}, seed {SEED_R}")
    pr(R3[["twins", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI", "true_higher", "false_higher", "ties", "sign_p", "ratio_all", "all_CI"]]
       .to_string(index=False, float_format=f4))
    for v, (r_, p_) in rho.items():
        pr(f"  Spearman rho(L, {v}) = {r_:.4f} (p {p_:.2e}, n {len(c)})")
    q = d1 > 0 and (e2[0][4][1] - e2[0][3][1]) > 0
    reading = "QUALIFIES FOR A HELD-OUT TEST (dev only; not confirmation)" if q else "NOT ELIGIBLE"
    pr(f"\nQUALIFICATION RULE (pre-stated, mechanical): E1 Δ {d1:+.4f} > 0 is {d1 > 0}; E2 (88%) {(e2[0][4][1] - e2[0][3][1]) * 100:+.2f} points > 0 is "
       f"{(e2[0][4][1] - e2[0][3][1]) > 0} -> \"{reading}\"")
    if not q:
        pr(f"STOPPING RULE (decided by: user, b3b0c3a): \"{STOP_SENTENCE}\"")
    if synthetic:
        print(f"E1-E3 code paths ran on the synthetic labels, including the report ({len(L_)} lines built, not printed); values not reported")
    else:
        print("\n".join(L_))
    return dict(qualifies=q, tau88=tau_keep(pL, y, w, 0.88), models=mL, p=pL)


def freeze(c, out, root):
    import joblib
    md = f"{root}/models"; os.makedirs(md, exist_ok=False); hashes = {}
    for k, (sc, m, cols) in enumerate(out["models"]):
        fn = f"{md}/C_CV_L_fold{k}.joblib"; joblib.dump({"scaler": sc, "model": m, "cols": cols}, fn); hashes[fn] = H(fn)
    fn = f"{root}/thresholds.json"; json.dump(dict(C_CV_L=dict(cols=CCV + ["L"], tau=out["tau88"])), open(fn, "x"), indent=1); hashes[fn] = H(fn)
    fn = f"{root}/dev_rows_C_CV_L.csv"; assert not os.path.exists(fn)
    c[["eid", "harpnum", "t", "fold", "weight", "L"]].assign(p_oof=out["p"]).to_csv(fn, index=False); hashes[fn] = H(fn)
    json.dump(hashes, open(f"{root}/model_hashes.json", "x"), indent=1)
    return hashes


def verify(c, p_oof, root):
    """Reload each fold model from disk and predict its own fold. -> max |diff| vs the in-run OOF predictions."""
    import joblib
    f, p = c.fold.to_numpy(), np.full(len(c), np.nan)
    for k in range(5):
        d = joblib.load(f"{root}/models/C_CV_L_fold{k}.joblib"); te = f == k
        p[te] = d["model"].predict_proba(d["scaler"].transform(c.loc[te, d["cols"]]))[:, 1]
    return float(np.max(np.abs(p - p_oof)))


def step1(scratch):
    t0 = time.time()
    scratch = os.path.abspath(scratch); repo = os.path.abspath(".")
    assert not (scratch + os.sep).startswith(repo + os.sep), "the scratch folder must be outside the repository"
    os.makedirs(OUT, exist_ok=True)
    print("CANDIDATE #29 FBL — STEP 1, LABEL-BLIND + SYNTHETIC CRASH TEST (EXPLORATORY (dev)); decisions.md b3b0c3a + 83973d1")
    print("units (code check, 83973d1 item 5): box = mean over the box pixels of register_cutout(raw DN / EXPTIME s) -> DN/s per pixel")
    d = all_levels()
    d.to_csv(f"{OUT}/dev_L.csv", index=False)
    print(f"label columns loaded: none. Dev episodes {len(d)}: L defined {int(d.L.notna().sum())}, undefined {int(d.L.isna().sum())} "
          f"{d.loc[d.L.isna(), 'reason'].value_counts().to_dict()}")
    # ---- reproduction check: CV_box_stored x mean = detrended SD (1e-12 relative); STOP on failure
    k = d[d.primary_CV_box.notna() & d.sd.notna()]
    rel = np.abs(k.primary_CV_box * k["mean"] - k.sd) / k.sd
    print(f"reproduction check (stored CV_box x mean vs detrended SD recomputed with euv_pilot.detrended_sd): {len(k)} episodes; "
          f"max relative difference {rel.max():.3e}; failures at {TOL:g}: {int((rel > TOL).sum())}")
    if (rel > TOL).any():
        print(f"FAILED at {TOL:g} relative -> STOP (tolerance not loosened); worst: {k.loc[rel.idxmax(), 'eid']}"); sys.exit(1)
    c = frame(d)
    assert c.L.notna().all() and c.S1.notna().all(), "L or S1 undefined in the 541 set"
    print(f"analysis set 541: L defined 541; S1 defined {int(c.S1.notna().sum())}")
    q = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    for name, v in [("547 (defined)", d.L.dropna()), ("541", c.L)]:
        print(f"  L percentiles {name}: " + ", ".join(f"p{x} {np.percentile(v, x):.4f}" for x in q))
    Y = d[d.L.notna()].groupby("year").L.agg(["size", "median"]).rename(columns={"size": "n"})
    print("\n== L by year (547, defined): median and n")
    print(Y.to_string(float_format=lambda v: f"{v:.4f}"))
    Yk = Y[Y.n >= MIN_N]
    drift = float(Yk["median"].max() - Yk["median"].min())
    print(f"drift over years with n >= {MIN_N} ({list(Yk.index)}): max − min of yearly medians = {drift:.4f} dex -> "
          f"{'FLAG: drift > 0.1 dex' if drift > DRIFT else 'not flagged (<= 0.1 dex)'}. The flag cannot separate instrument degradation "
          f"from cycle phase or episode selection; flag only, the definition does not change.")
    # ---- crash test on SYNTHETIC labels
    y = np.random.RandomState(12345).binomial(1, 96 / 541, len(c))
    print(f"\n== CRASH TEST, SYNTHETIC LABELS: numpy RandomState(12345).binomial(1, 96/541, 541) -> {int(y.sum())} ones; no real label read; "
          f"C_CV reproduction check skipped; freeze/reload in a scratch folder outside the repository, deleted afterwards")
    t1 = time.time()
    out = evaluate(c.assign(true_alarm=y), synthetic=True)
    root = os.path.join(scratch, "fbl_freeze_test"); os.makedirs(root)
    hs = freeze(c, out, root); dd = verify(c.assign(true_alarm=y), out["p"], root); shutil.rmtree(root)
    print(f"freeze wrote {len(hs)} hashed files to the scratch folder; reload check max abs difference {dd!r}; scratch folder deleted: {not os.path.exists(root)}; "
          f"crash test wall {time.time() - t1:.1f} s")
    print(f"\nwall total {time.time() - t0:.1f} s")


def step2():
    from phase_f import tau_keep, wlogloss
    from euv_heldout import fit_folds
    t0 = time.time()
    print("CANDIDATE #29 FBL — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md b3b0c3a + 83973d1")
    d = all_levels()
    stored = pd.read_csv(f"{OUT}/dev_L.csv", float_precision="round_trip")
    assert (stored.eid == d.eid).all() and np.array_equal(stored.L.to_numpy(), d.L.to_numpy(), equal_nan=True), "L differs from Step 1; STOP"
    c = frame(d)
    lab = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t", "true_alarm"], parse_dates=["t"])
    lab["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(lab.harpnum, lab.t)]
    c = c.merge(lab[["eid", "true_alarm"]], on="eid", how="left", validate="1:1")
    y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
    TX = json.load(open("data/euv_extra/thresholds.json"))["C_CV"]
    _, pB = fit_folds(c, CCV)
    assert wlogloss(y, pB, w) == TX["dev_oof_logloss"] and tau_keep(pB, y, w) == TX["tau"], "C_CV does not reproduce the frozen euv_extra C_CV; STOP"
    print(f"checks: L identical to Step 1 ({OUT}/dev_L.csv); C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL {TX['dev_oof_logloss']:.10f}, "
          f"tau {TX['tau']:.10f}); episodes {len(c)} (true {int(y.sum())}, false {int((y == 0).sum())}), HARPs {c.harpnum.nunique()}")
    out = evaluate(c)
    if out["qualifies"]:                                                # freeze + reload check BEFORE any held-out computation
        hashes = freeze(c, out, OUT)
        print(f"\nFROZEN (before any held-out computation): C_CV + L fold models, tau (dev OOF, 88%) {out['tau88']:.10f}")
        for fn, hh in hashes.items():
            print(f"  sha256 {hh}  {fn}")
        dd = verify(c, out["p"], OUT)
        print(f"RELOAD CHECK: max abs difference {dd!r}")
        if dd != 0:
            print("NOT IDENTICAL -> STOP"); sys.exit(1)
    print(f"\nwall total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    if sys.argv[1:2] == ["step1"] and len(sys.argv) == 3:
        step1(sys.argv[2])
    elif sys.argv[1:] == ["step2"]:
        step2()
    else:
        sys.exit(__doc__)
