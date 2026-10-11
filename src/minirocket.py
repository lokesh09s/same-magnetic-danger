"""Candidate #27 MINIROCKET ON THE 94 A LIGHT CURVE (MRKT) -- decisions.md 2026-09-30 (16569b6, amendment b1fbd2e). EXPLORATORY (dev).
Curve: stored primary box series (data/euv_full/series/<eid>.csv, valid_primary frames) on the 120-slot 12-min grid over (t-24h, t]
(nearest valid frame within 6 min, ties to the earlier frame), linear interpolation (edges: nearest), / mean of real-frame slots - 1.
Curve model: MiniRocket (sktime 1.2.0, defaults, random_state) -> StandardScaler -> weighted L2 LogisticRegression, C from
{1e-4, 1e-3, 1e-2, 1e-1} by grouped 3-fold CV (HARP) on weighted log-loss. Stacking per outer fold k: inner grouped 5-fold OOF curve
scores -> stacker C_CV + logit(curve score) (stage4 LR) on the outer training set; curve model on the whole outer training set scores fold k.
Usage: python minirocket.py step1    label-blind curves + figure + crash test on SYNTHETIC labels (nothing saved from the crash test)
       python minirocket.py step2    dev evaluation E1-E4, run once (reads the real labels)"""
import glob, hashlib, json, os, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor

SER, OUT, FIG = "data/euv_full/series", "data/minirocket", "figures/minirocket"
SEED, E4_SEEDS, GRID, NSLOT = 20260921, [1, 2, 3, 4, 5], [1e-4, 1e-3, 1e-2, 1e-1], 120
CCV = ["score", "n_C", "n_M", "n_X", "logR", "log10_CV_box"]      # = euv_extra C_CV columns (A_COLS + logR + log10_CV_box)
CLIP = 1e-6
warnings.filterwarnings("ignore")


# ================================================================ curves (label-free)
def curve(eid, t):
    """-> (relative curve [120], filled mask [120], reason). reason '' when defined."""
    p = f"{SER}/{eid}.csv"
    if not os.path.exists(p):
        return None, None, "no series file"
    s = pd.read_csv(p, usecols=["t_obs", "box", "valid_primary"], parse_dates=["t_obs"])
    s = s[s.valid_primary.astype(bool) & s.box.notna()].sort_values("t_obs", kind="stable")
    slots = pd.date_range(t - pd.Timedelta("24h") + pd.Timedelta("12min"), t, freq="12min").to_numpy()   # = euv_full.py fill rule
    assert len(slots) == NSLOT
    tv, bv = s.t_obs.to_numpy(), s.box.to_numpy(float)
    val, filled = np.full(NSLOT, np.nan), np.zeros(NSLOT, bool)
    for i, sl in enumerate(slots):
        if len(tv):
            d = np.abs(tv - sl); j = int(np.argmin(d))                 # first minimum = the earlier frame on a tie
            if d[j] <= np.timedelta64(6, "m"):
                val[i], filled[i] = bv[j], True
    if not filled.any():
        return None, filled, "no filled slot"
    m = val[filled].mean()
    if m <= 0:
        return None, filled, "mean <= 0"
    idx = np.arange(NSLOT)
    return np.interp(idx, idx[filled], val[filled]) / m - 1, filled, ""


def base_frame():
    """The 541 dev rows (order, folds, weights of dev_rows.csv) with the C_CV inputs. No label column is read."""
    from euv_confirm_tests import log_r
    dr = pd.read_csv("data/euv_extra/dev_rows.csv", parse_dates=["t"], float_precision="round_trip")
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t", "score", "n_C", "n_M", "n_X", "noaa_ars"],
                      parse_dates=["t"], float_precision="round_trip")
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    res = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_full/results/*.json")])[["eid", "primary_CV_box", "primary_fill"]]
    res[["primary_CV_box", "primary_fill"]] = res[["primary_CV_box", "primary_fill"]].apply(pd.to_numeric, errors="coerce")
    c = dr.merge(coh.drop(columns=["harpnum", "t"]), on="eid", how="left", validate="1:1").merge(res, on="eid", how="left", validate="1:1")
    assert len(c) == 541 and c[["score", "primary_CV_box"]].notna().all().all() and "true_alarm" not in c.columns
    c["log10_CV_box"] = np.log10(c.primary_CV_box)
    c["logR"] = log_r(c, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"))
    return c


def build_curves(c):
    rows, X = [], np.full((len(c), 1, NSLOT), np.nan)
    for i, e in enumerate(c.itertuples()):
        v, f, why = curve(e.eid, e.t)
        rows.append(dict(eid=e.eid, n_filled=int(f.sum()) if f is not None else 0, reason=why))
        if v is not None:
            X[i, 0] = v
    return X, pd.DataFrame(rows)


# ================================================================ models
def wll(y, p, w):
    from phase_f import wlogloss
    return wlogloss(y, p, w)


def logit(p):
    p = np.clip(p, CLIP, 1 - CLIP)
    return np.log(p / (1 - p))


def fit_curve(X, y, w, h, seed):
    """Curve model with C* from grouped 3-fold CV on weighted log-loss (ties -> smaller C); refit on all of X."""
    from sklearn.model_selection import GroupKFold
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sktime.transformations.panel.rocket import MiniRocket
    P = {C: np.full(len(y), np.nan) for C in GRID}
    for tr, te in GroupKFold(n_splits=3).split(X, y, h):
        mr = MiniRocket(random_state=seed).fit(X[tr])
        Ftr, Fte = np.asarray(mr.transform(X[tr])), np.asarray(mr.transform(X[te]))
        sc = StandardScaler().fit(Ftr); Ztr, Zte = sc.transform(Ftr), sc.transform(Fte)
        for C in GRID:
            lr = LogisticRegression(penalty="l2", C=C, solver="lbfgs", max_iter=10000).fit(Ztr, y[tr], sample_weight=w[tr])
            P[C][te] = lr.predict_proba(Zte)[:, 1]
    ll = {C: wll(y, P[C], w) for C in GRID}
    cstar = min(GRID, key=lambda C: (ll[C], C))
    mr = MiniRocket(random_state=seed).fit(X)
    F = np.asarray(mr.transform(X)); sc = StandardScaler().fit(F)
    lr = LogisticRegression(penalty="l2", C=cstar, solver="lbfgs", max_iter=10000).fit(sc.transform(F), y, sample_weight=w)
    return dict(minirocket=mr, scaler=sc, lr=lr, C=cstar, n_features=F.shape[1])


def predict_curve(m, X):
    return m["lr"].predict_proba(m["scaler"].transform(np.asarray(m["minirocket"].transform(X))))[:, 1]


def outer_fold(job):
    """One outer fold k for one MiniRocket seed: (a) inner OOF scores, (b) stacker, (c) outer curve model -> fold-k predictions."""
    from threadpoolctl import threadpool_limits
    from sklearn.model_selection import GroupKFold
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from stage4_models import LR
    k, seed, X, y, w, h, fold, CC, keep_models = job
    t0 = time.time()
    with threadpool_limits(1):
        iO, iT = np.where(fold != k)[0], np.where(fold == k)[0]
        s_in, c_in = np.full(len(iO), np.nan), []
        for tr, te in GroupKFold(n_splits=5).split(iO, y[iO], h[iO]):
            m = fit_curve(X[iO[tr]], y[iO[tr]], w[iO[tr]], h[iO[tr]], seed); s_in[te] = predict_curve(m, X[iO[te]]); c_in.append(m["C"])
        Z = np.column_stack([CC[iO], logit(s_in)])
        sc = StandardScaler().fit(Z); st = LogisticRegression(**LR).fit(sc.transform(Z), y[iO], sample_weight=w[iO])
        m = fit_curve(X[iO], y[iO], w[iO], h[iO], seed)
        sT = predict_curve(m, X[iT])
        pT = st.predict_proba(sc.transform(np.column_stack([CC[iT], logit(sT)])))[:, 1]
    out = dict(k=k, seed=seed, idx=iT, p=pT, curve=sT, C_outer=m["C"], C_inner=c_in, n_features=m["n_features"], secs=time.time() - t0,
               stacker_coef=dict(zip(CCV + ["logit_curve"], st.coef_[0])))
    if keep_models:
        out["models"] = dict(curve=m, stack_scaler=sc, stacker=st)
    return out


def run_pipeline(c, X, y, seeds, keep_seed=None, workers=None):
    """-> {seed: dict(p=OOF stacked predictions, curve=OOF curve scores, folds=[...])} over the 5 outer folds."""
    from phase_f import W
    w, h, fold, CC = c.weight.to_numpy(), c.harpnum.to_numpy(), c.fold.to_numpy(), c[CCV].to_numpy(float)
    jobs = [(k, s, X, y, w, h, fold, CC, s == keep_seed) for s in seeds for k in range(5)]
    res = {s: dict(p=np.full(len(c), np.nan), curve=np.full(len(c), np.nan), folds=[]) for s in seeds}
    with ProcessPoolExecutor(workers or W) as pool:
        for r in pool.map(outer_fold, jobs):
            R = res[r["seed"]]; R["p"][r["idx"]] = r["p"]; R["curve"][r["idx"]] = r["curve"]; R["folds"].append(r)
    for s, R in res.items():
        assert np.isfinite(R["p"]).all() and np.isfinite(R["curve"]).all(), f"seed {s}: missing OOF predictions"
        R["folds"].sort(key=lambda r: r["k"])
    return res


# ================================================================ steps
def plot_examples(c, X, info, path):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    pick = np.sort(np.random.RandomState(SEED).choice(len(c), 6, replace=False))
    fig, ax = plt.subplots(2, 3, figsize=(12, 6.2), sharex=True)
    hrs = -24 + 0.2 * np.arange(1, NSLOT + 1)
    for a, i in zip(ax.ravel(), pick):
        e = c.iloc[i]; v, f, _ = curve(e.eid, e.t)
        a.plot(hrs, X[i, 0], "-", color="#2a6fb0", lw=1.2)
        a.plot(hrs[f], X[i, 0][f], "o", ms=2.6, color="#2a6fb0", label="real-frame slot")
        if (~f).any():
            a.plot(hrs[~f], X[i, 0][~f], "o", ms=4, mfc="white", color="#c0392b", label="interpolated slot")
        a.axhline(0, color="#bbb", lw=0.8)
        a.set_title(f"HARP {e.harpnum}, t = {e.t:%Y-%m-%d %H:%M} UTC; interpolated {NSLOT - int(f.sum())}", fontsize=8)
        a.tick_params(labelsize=7)
    ax[0, 0].legend(fontsize=7); [a.set_xlabel("hours relative to t", fontsize=8) for a in ax[1]]
    [a.set_ylabel("box brightness / mean − 1", fontsize=8) for a in ax[:, 0]]
    fig.suptitle("Candidate #27 MRKT: six 94 Å relative box curves (dev episodes drawn with RandomState(20260921); label-blind)", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return [c.eid.iloc[i] for i in pick]


def step1():
    t0 = time.time(); os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)
    print("CANDIDATE #27 MRKT — STEP 1, LABEL-BLIND (EXPLORATORY (dev)); decisions.md 16569b6 + amendment b1fbd2e")
    c = base_frame()
    print(f"label columns loaded: none (dev_rows.csv; oof_cohort_dev.csv usecols = harpnum, t, score, n_C, n_M, n_X, noaa_ars; "
          f"euv_full results json: primary_CV_box, primary_fill). Episodes: {len(c)}")
    X, info = build_curves(c)
    und = info[info.reason != ""]
    print(f"\n== Curves: defined {int((info.reason == '').sum())}, undefined {len(und)} {und.reason.value_counts().to_dict()}")
    assert (np.round(info.n_filled / NSLOT, 4) == c.primary_fill.round(4)).all(), "filled-slot count does not reproduce primary_fill"
    print(f"check: filled slots / 120 reproduces the stored primary_fill for all {len(c)} episodes")
    ni = NSLOT - info.n_filled
    print(f"interpolated slots per episode: median {ni.median():.1f}, mean {ni.mean():.2f}, min {ni.min()}, max {ni.max()}; "
          f"episodes with 0: {int((ni == 0).sum())}; distribution {ni.value_counts().sort_index().to_dict()}")
    rel = X[:, 0]
    print(f"relative curve values: median {np.median(rel):.4f}, p1 {np.percentile(rel, 1):.4f}, p99 {np.percentile(rel, 99):.4f}, "
          f"min {rel.min():.4f}, max {rel.max():.4f}")
    pd.concat([info, pd.DataFrame(rel, columns=[f"s{i:03d}" for i in range(NSLOT)])], axis=1).to_csv(f"{OUT}/curves.csv", index=False)
    ex = plot_examples(c, X, info, f"{FIG}/examples.png")
    print(f"figure {FIG}/examples.png: {ex}")
    # ---- crash test on SYNTHETIC labels (nothing saved, nothing frozen)
    y = np.random.RandomState(12345).binomial(1, 96 / 541, len(c))
    print(f"\n== CRASH TEST, SYNTHETIC LABELS: numpy RandomState(12345).binomial(1, 96/541, 541) -> {int(y.sum())} ones; "
          f"no real label read; C_CV reproduction check skipped; no file saved; no model frozen")
    t1 = time.time()
    res = run_pipeline(c, X, y, [SEED] + E4_SEEDS)
    t2 = time.time()
    fs = [r for R in res.values() for r in R["folds"]]
    print(f"full nested pipeline ran for {len(res)} MiniRocket seeds x 5 outer folds; OOF predictions finite for all 541 in every seed; "
          f"MiniRocket features {sorted({r['n_features'] for r in fs})}")
    print(f"wall for the pipeline {t2 - t1:.1f} s ({(t2 - t1) / 60:.1f} min); per outer fold task median {np.median([r['secs'] for r in fs]):.1f} s")
    # the E1-E3 code paths on the synthetic predictions (values not printed: synthetic labels carry no information)
    evaluate(c.assign(true_alarm=y), res, synthetic=True)
    print(f"\nwall total {time.time() - t0:.1f} s")


def evaluate(c, res, synthetic=False):
    """E1-E4 from the pipeline output. synthetic=True runs every code path but prints nothing but a completion line."""
    from sklearn.metrics import roc_auc_score
    from scipy.stats import binomtest, spearmanr
    from phase_f import tau_keep, op_stats, boot_many, ratio_jobs, pct, W, NB_D, SEED_D, NB_R, SEED_R
    from euv_heldout import fit_folds
    from euv_f2_replication import twins
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    groups = [np.where(h == v)[0] for v in np.unique(h)]
    _, pB = fit_folds(c, CCV)
    _, pV = fit_folds(c, ["log10_CV_box"])
    R = res[SEED]; pS = R["p"]
    jobs = {("dll", s): ("dll", dict(y=y, w=w, pA=pB, pE=res[s]["p"], groups=groups), NB_D, SEED_D) for s in res}
    kept, e2 = [], []
    for keep in (0.88, 0.95):
        tB, tS = tau_keep(pB, y, w, keep), tau_keep(pS, y, w, keep); kB, kS = pB >= tB, pS >= tS; kept += [kB, kS]
        e2.append((keep, tB, tS, op_stats(y, w, kB), op_stats(y, w, kS), (int((kB & (y == 1)).sum()), int((~kB & (y == 0)).sum())),
                   (int((kS & (y == 1)).sum()), int((~kS & (y == 0)).sum()))))
    jobs["E2"] = ("op", dict(y=y, w=w, kept=kept, groups=groups), NB_R, SEED_R)
    cc = c.assign(curve=R["curve"]); T = {"T_a": twins(cc)[0], "T_b": twins(cc, by_group=True)[0]}; e3 = []
    for tn, tw in T.items():
        e, j = ratio_jobs(f"curve {tn}", cc, "curve", "ratio", tw); jobs.update(j)
        v = cc.set_index("eid").curve; xt, xf = tw.true_eid.map(v), tw.false_eid.map(v)
        up, dn = int((xt > xf).sum()), int((xt < xf).sum())
        e.update(twins=tn, true_higher=up, false_higher=dn, ties=len(tw) - up - dn, sign_p=binomtest(up, up + dn, 0.5).pvalue if up + dn else np.nan)
        e3.append(e)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    rho = {v: spearmanr(R["curve"], c[v]) for v in ["log10_CV_box", "n_C", "logR", "score"]}
    auc = lambda p: roc_auc_score(y, p, sample_weight=w)
    L = []                                                              # report lines; printed only for real labels
    pr = lambda *x: L.append(" ".join(str(v) for v in x))
    f4 = lambda v: f"{v:.4f}"
    llB = wll(y, pB, w)
    pr(f"\n== E1 PRIMARY (MiniRocket random_state {SEED}): Δ = LL(C_CV) − LL(C_CV + curve) (+ = curve helps); HARP bootstrap {NB_D}, seed {SEED_D}")
    lo, hi = pct(B[("dll", SEED)]); d1 = llB - wll(y, pS, w)
    pr(f"  LL(C_CV) {llB:.4f}, LL(C_CV + curve) {wll(y, pS, w):.4f}; Δ {d1:+.4f} [{lo:+.4f}, {hi:+.4f}]; weighted AUC {auc(pB):.4f} -> {auc(pS):.4f}")
    Cs = pd.Series([r["C_outer"] for r in R["folds"]] + [x for r in R["folds"] for x in r["C_inner"]]).value_counts().sort_index().to_dict()
    pr(f"  chosen C (5 outer + 25 inner curve models): {Cs}; MiniRocket features {R['folds'][0]['n_features']}")
    co = pd.DataFrame([dict(fold=r["k"], **r["stacker_coef"]) for r in R["folds"]])
    pr("  stacker coefficients per outer fold (per 1 SD, training-fold StandardScaler):")
    pr(co.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    op = np.array(B["E2"], float)
    pr(f"\n== E2 MATCHED RETENTION: dev OOF tau per model (tau_keep); weighted; paired HARP bootstrap {NB_R}, seed {SEED_R}")
    for i, (keep, tB, tS, sB, sS, nB, nS) in enumerate(e2):
        d = op[:, 2 * i + 1, 1] - op[:, 2 * i, 1]
        pr(f"  target {keep:.2f}: C_CV tau {tB:.6f} true kept {nB[0]}/{int(y.sum())} ({sB[0]:.4f} w), false removed {nB[1]}/{int((y == 0).sum())} "
              f"({sB[1]:.4f} w) | C_CV + curve tau {tS:.6f} true kept {nS[0]}/{int(y.sum())} ({sS[0]:.4f} w), false removed {nS[1]}/{int((y == 0).sum())} ({sS[1]:.4f} w)")
        pr(f"     false removed (C_CV + curve − C_CV): {(sS[1] - sB[1]) * 100:+.2f} points [{np.nanpercentile(d, 2.5) * 100:+.2f}, {np.nanpercentile(d, 97.5) * 100:+.2f}]")
    pr("\n== E3 DESCRIPTIVE")
    pr(f"  curve-score-only OOF weighted AUC {auc(R['curve']):.4f}; CV_box-only OOF weighted AUC (fit_folds on log10_CV_box) {auc(pV):.4f}")
    R3 = pd.DataFrame(e3); R3["tw_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "tw")]) for m in R3.measure]; R3["all_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "all")]) for m in R3.measure]
    pr(f"  curve-score twins (T_a = twins(c), T_b = twins(c, by_group=True); ratio_jobs mode 'ratio' on the OOF curve score; CI pairs by true HARP {NB_R}, seed {SEED_R})")
    pr(R3[["twins", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI", "true_higher", "false_higher", "ties", "sign_p", "ratio_all", "all_CI"]]
          .to_string(index=False, float_format=f4))
    for v, (r_, p_) in rho.items():
        pr(f"  Spearman rho(curve score, {v}) = {r_:.4f} (p {p_:.2e}, n {len(c)})")
    pr(f"\n== E4 STABILITY: E1 with MiniRocket random_state in {E4_SEEDS} (primary stays {SEED})")
    e4 = []
    for s in [SEED] + E4_SEEDS:
        lo_, hi_ = pct(B[("dll", s)]); d = llB - wll(y, res[s]["p"], w); e4.append(d)
        pr(f"  random_state {s}: LL(C_CV + curve) {wll(y, res[s]['p'], w):.4f}; Δ {d:+.4f} [{lo_:+.4f}, {hi_:+.4f}]; AUC {auc(res[s]['p']):.4f}")
    q = d1 > 0 and (e2[0][4][1] - e2[0][3][1]) > 0
    reading = "QUALIFIES FOR A HELD-OUT TEST (dev only; not confirmation)" if q else "NOT ELIGIBLE"
    pr(f"\nQUALIFICATION RULE (pre-stated, mechanical): E1 Δ {d1:+.4f} > 0 is {d1 > 0}; E2 (88%) {(e2[0][4][1] - e2[0][3][1]) * 100:+.2f} points > 0 is "
          f"{(e2[0][4][1] - e2[0][3][1]) > 0} -> \"{reading}\"")
    if synthetic:
        print(f"E1-E4 code paths ran on the synthetic predictions, including the report ({len(L)} lines built, not printed); values not reported")
        return None
    print("\n".join(L))
    return dict(qualifies=q, tau88=tau_keep(pS, y, w, 0.88), pS=pS)


def freeze(c, res, tau88, pS, root):
    """Write the 5 outer-fold pipelines (primary seed), tau and the dev rows; never overwrite. -> {file: sha256}."""
    import joblib
    H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    md = f"{root}/models"; os.makedirs(md, exist_ok=False); hashes = {}
    for r in res[SEED]["folds"]:
        fn = f"{md}/MRKT_fold{r['k']}.joblib"; joblib.dump(r["models"], fn); hashes[fn] = H(fn)
    fn = f"{root}/thresholds.json"
    json.dump(dict(C_CV_curve=dict(tau=tau88, seed=SEED, cols=CCV + ["logit_curve"], clip=CLIP, grid=GRID)), open(fn, "x"), indent=1); hashes[fn] = H(fn)
    fn = f"{root}/dev_rows_MRKT.csv"; assert not os.path.exists(fn)
    c[["eid", "harpnum", "t", "fold", "weight"]].assign(p_oof=pS).to_csv(fn, index=False); hashes[fn] = H(fn)
    json.dump(hashes, open(f"{root}/model_hashes.json", "x"), indent=1)
    return hashes


def verify(c, X, p_oof, root):
    """Reload each fold's frozen pipeline and predict that fold's dev episodes (single-thread BLAS, as the workers). -> max |diff|."""
    import joblib
    from threadpoolctl import threadpool_limits
    fold, CC, p = c.fold.to_numpy(), c[CCV].to_numpy(float), np.full(len(c), np.nan)
    with threadpool_limits(1):
        for k in range(5):
            m, iT = joblib.load(f"{root}/models/MRKT_fold{k}.joblib"), np.where(fold == k)[0]
            Z = np.column_stack([CC[iT], logit(predict_curve(m["curve"], X[iT]))])
            p[iT] = m["stacker"].predict_proba(m["stack_scaler"].transform(Z))[:, 1]
    return float(np.max(np.abs(p - p_oof)))


def step2():
    from phase_f import tau_keep
    from euv_heldout import fit_folds
    t0 = time.time()
    print("CANDIDATE #27 MRKT — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md 16569b6 + b1fbd2e")
    c = base_frame()
    lab = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t", "true_alarm"], parse_dates=["t"])
    lab["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(lab.harpnum, lab.t)]
    c = c.merge(lab[["eid", "true_alarm"]], on="eid", how="left", validate="1:1")
    y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
    TX = json.load(open("data/euv_extra/thresholds.json"))["C_CV"]
    _, pB = fit_folds(c, CCV)
    from phase_f import wlogloss
    assert wlogloss(y, pB, w) == TX["dev_oof_logloss"] and tau_keep(pB, y, w) == TX["tau"], "C_CV does not reproduce the frozen euv_extra C_CV; STOP"
    print(f"checks: C_CV OOF reproduces the frozen euv_extra C_CV exactly (LL {TX['dev_oof_logloss']:.10f}, tau {TX['tau']:.10f}); "
          f"episodes {len(c)} (true {int(y.sum())}, false {int((y == 0).sum())}), HARPs {c.harpnum.nunique()}")
    X, info = build_curves(c)
    assert (info.reason == "").all()
    stored = pd.read_csv(f"{OUT}/curves.csv", float_precision="round_trip")
    assert (stored.eid.to_numpy() == c.eid.to_numpy()).all() and np.array_equal(stored[[f"s{i:03d}" for i in range(NSLOT)]].to_numpy(), X[:, 0])
    print(f"check: curves identical to the Step 1 file {OUT}/curves.csv")
    t1 = time.time()
    res = run_pipeline(c, X, y, [SEED] + E4_SEEDS, keep_seed=SEED)
    print(f"pipeline wall {time.time() - t1:.1f} s")
    out = evaluate(c, res)
    if out["qualifies"]:                                                # freeze BEFORE any held-out step (amendment b1fbd2e item 3)
        hashes = freeze(c, res, out["tau88"], out["pS"], OUT)
        print(f"\nFROZEN (before any held-out computation): 5 outer-fold pipelines (curve model + stacker), tau (dev OOF, 88%) {out['tau88']:.10f}")
        for fn, hh in hashes.items():
            print(f"  sha256 {hh}  {fn}")
        d = verify(c, X, res[SEED]["p"], OUT)                           # user addition bf2dbc4
        print(f"RELOAD CHECK: frozen models reloaded from disk reproduce the dev outer-OOF predictions: max abs difference {d!r}")
        if d != 0:
            print("NOT IDENTICAL -> STOP"); sys.exit(1)
    print(f"\nwall total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    if sys.argv[1:] == ["step1"]:
        step1()
    elif sys.argv[1:] == ["step2"]:
        step2()
    else:
        sys.exit(__doc__)
