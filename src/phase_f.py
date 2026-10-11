"""PHASE F (decisions.md 2026-09-25) -- EXPLORATORY / DESCRIPTIVE on dev 2010-2019 ONLY. Nothing after 2019 is read;
nothing in data/euv_test/ is touched. Workers = os.cpu_count() - 1. Bootstrap resamples are drawn in the parent from one
RandomState (same stream as the sequential step 6 loop) and evaluated in chunks on the pool -> identical to single process.
Usage: python phase_f.py F2 | F3 | F4 | F5 | F6 | F7"""
import glob, json, os, sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor

W = os.cpu_count() - 1
R, OUT = "data/euv_full", "data/phase_f"
DEV_END = pd.Timestamp("2019-12-31 23:59:59")
SEED_D, NB_D, SEED_R, NB_R = 20260921, 10000, 0, 2000
A_COLS = ["score", "n_C", "n_M", "n_X"]
warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)


def wlogloss(y, p, w):                                             # = stage4_models.wlogloss
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(np.sum(w * -(y * np.log(p) + (1 - y) * np.log(1 - p))) / np.sum(w))


# ================================================================ bootstrap statistics (run in workers)
def _dll(d, ix):
    return wlogloss(d["y"][ix], d["pA"][ix], d["w"][ix]) - wlogloss(d["y"][ix], d["pE"][ix], d["w"][ix])


def op_stats(y, w, k):
    tk = (w * y * k).sum() / (w * y).sum() if (w * y).sum() else np.nan
    fr = (w * (1 - y) * ~k).sum() / (w * (1 - y)).sum() if (w * (1 - y)).sum() else np.nan
    pr = (w * y * k).sum() / (w * k).sum() if k.any() else np.nan
    return tk, fr, pr


def _op(d, ix):
    return [op_stats(d["y"][ix], d["w"][ix], k[ix]) for k in d["kept"]]


def med_ratio(t, f, mode):
    mt, mf = np.nanmedian(t) if len(t) else np.nan, np.nanmedian(f) if len(f) else np.nan
    if mode == "log":
        return 10 ** (mt - mf)
    if mode == "diff":
        return mt - mf
    return mt / mf if mf != 0 else np.nan


def _ratio_all(d, ix):
    x, y = d["x"][ix], d["y"][ix]
    return med_ratio(x[y == 1], x[y == 0], d["mode"])


def _ratio_pairs(d, ix):
    return med_ratio(d["xt"][ix], d["xf"][ix], d["mode"])


def _rate(d, ix):
    y, w, g = d["y"][ix], d["w"][ix], d["g"][ix]
    return [(w * y * (g == k)).sum() / (w * (g == k)).sum() if (w * (g == k)).sum() else np.nan for k in d["levels"]]


STATS = {"dll": _dll, "op": _op, "ratio_all": _ratio_all, "ratio_pairs": _ratio_pairs, "rate": _rate}


def _chunk(job):
    fn, d, C = job
    g = d["groups"]
    return [STATS[fn](d, np.concatenate([g[j] for j in row])) for row in C]


def choices(n, nboot, seed):
    rng = np.random.RandomState(seed)
    return np.array([rng.choice(n, n, replace=True) for _ in range(nboot)], dtype=np.int64)


def boot_many(jobs, pool):
    """jobs: key -> (fn, data, nboot, seed); all chunks of all jobs go to the pool at once (candidates run concurrently)."""
    futs = {}
    for key, (fn, d, nb, seed) in jobs.items():
        futs[key] = [pool.submit(_chunk, (fn, d, ch)) for ch in np.array_split(choices(len(d["groups"]), nb, seed), W)]
    return {k: [r for f in fs for r in f.result()] for k, fs in futs.items()}


def pct(v):
    v = np.asarray(v, float)
    return (np.nanpercentile(v, 2.5), np.nanpercentile(v, 97.5)) if np.isfinite(v).any() else (np.nan, np.nan)


# ================================================================ data (dev only)
def load_base():
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    assert len(coh) == 547 and coh.t.max() <= DEV_END
    coh["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(coh.harpnum, coh.t)]
    num = ["primary_fill", "sens_fill", "primary_dCV", "sens_dCV", "primary_CV_box", "primary_CV_PIL", "primary_CV_ctrl"]
    res = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])[["eid"] + num]
    res[num] = res[num].apply(pd.to_numeric, errors="coerce")
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/spatial/*.json")])[["eid", "R1", "R2", "R3", "R4a", "R4b", "R4c", "npix_box"]]
    nf = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/spatial_nf/*.json")])[["eid", "R4a"]].rename(columns={"R4a": "R4a_nf"})
    coh = coh.merge(res, on="eid", how="left").merge(sp, on="eid", how="left").merge(nf, on="eid", how="left")
    coh["P"] = coh.primary_fill >= 0.80; coh["S"] = coh.sens_fill >= 0.80
    return coh


def twins():
    return pd.read_csv(f"{R}/step6/twins_PRIMARY.csv")


# ================================================================ step 6 procedure + operating point
def tau_keep(p, y, w, keep=0.88):                                  # = diag_operating_point.tau_keep
    t = pd.DataFrame(dict(p=p[y == 1], w=w[y == 1])).sort_values("p", ascending=False)
    cum = t.w.cumsum() / t.w.sum()
    return float(t.p.iloc[int(np.argmax(cum.to_numpy() >= keep))])


def prep(coh, mask):
    c = coh[mask].reset_index(drop=True).copy()
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    return c


def cand_jobs(name, c, cols):
    from sklearn.metrics import roc_auc_score
    from euv_spatial import cv_fit
    pA, pE = cv_fit(c, A_COLS), cv_fit(c, A_COLS + cols)
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    groups = [np.where(h == x)[0] for x in np.unique(h)]
    tA, tE = tau_keep(pA, y, w), tau_keep(pE, y, w); kA, kE = pA >= tA, pE >= tE
    base = dict(candidate=name, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups),
                logloss_A=wlogloss(y, pA, w), logloss_Ax=wlogloss(y, pE, w), AUC_A=roc_auc_score(y, pA, sample_weight=w),
                AUC_Ax=roc_auc_score(y, pE, sample_weight=w), tau_A=tA, tau_Ax=tE)
    base["delta"] = base["logloss_A"] - base["logloss_Ax"]
    for tag, k in [("A", kA), ("Ax", kE)]:
        tk, fr, pr = op_stats(y, w, k)
        base.update({f"true_kept_{tag}": tk, f"false_removed_{tag}": fr, f"precision_{tag}": pr, f"FAR_{tag}": 1 - pr,
                     f"true_kept_n_{tag}": f"{int((k & (y == 1)).sum())}/{int(y.sum())}",
                     f"false_removed_n_{tag}": f"{int((~k & (y == 0)).sum())}/{int((y == 0).sum())}"})
    jobs = {(name, "dll"): ("dll", dict(y=y, w=w, pA=pA, pE=pE, groups=groups), NB_D, SEED_D),
            (name, "op"): ("op", dict(y=y, w=w, kept=[kA, kE], groups=groups), NB_R, SEED_R)}
    return base, jobs


def evaluate(cands, pool):
    """cands: list of (name, c, cols). Returns one row per candidate (bootstraps of all candidates run concurrently)."""
    bases, jobs = [], {}
    for name, c, cols in cands:
        b, j = cand_jobs(name, c, cols); bases.append(b); jobs.update(j)
    B = boot_many(jobs, pool); rows = []
    for b in bases:
        n = b["candidate"]; b["CI_lo"], b["CI_hi"] = pct(B[(n, "dll")])
        op = np.array(B[(n, "op")], float)                           # resamples x models(A, Ax) x (tk, fr, pr)
        for mi, tag in enumerate(["A", "Ax"]):
            for si, s in enumerate(["true_kept", "false_removed", "precision"]):
                b[f"{s}_{tag}_CI"] = "[%.4f, %.4f]" % pct(op[:, mi, si])
            b[f"FAR_{tag}_CI"] = "[%.4f, %.4f]" % tuple(1 - np.array(pct(op[:, mi, 2]))[::-1])
        b["dfr"] = b["false_removed_Ax"] - b["false_removed_A"]
        b["dfr_CI"] = "[%+.4f, %+.4f]" % pct(op[:, 1, 1] - op[:, 0, 1])
        rows.append(b)
    return pd.DataFrame(rows)


def show_eval(T, title):
    print(f"\n{title}\n(dev 2010-2019, internal 5-fold CV, EXPLORATORY; delta = LL(A) - LL(A+x), + = helps; HARP bootstrap "
          f"{NB_D}, seed {SEED_D})")
    print(T[["candidate", "n", "true", "false", "HARPs", "logloss_A", "logloss_Ax", "delta", "CI_lo", "CI_hi", "AUC_A", "AUC_Ax"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"operating point (>= 88% weighted true kept, tau in-sample; weighted %, counts; CI HARP bootstrap {NB_R}, seed {SEED_R})")
    for _, r in T.iterrows():
        for tag, lab in [("A", "A"), ("Ax", "A+x")]:
            print(f"  {r.candidate:>14s} {lab:4s} tau {r[f'tau_{tag}']:.4f}  true kept {r[f'true_kept_n_{tag}']} {r[f'true_kept_{tag}']:.4f} "
                  f"{r[f'true_kept_{tag}_CI']}  false removed {r[f'false_removed_n_{tag}']} {r[f'false_removed_{tag}']:.4f} "
                  f"{r[f'false_removed_{tag}_CI']}  precision {r[f'precision_{tag}']:.4f} {r[f'precision_{tag}_CI']}  "
                  f"FAR {r[f'FAR_{tag}']:.4f} {r[f'FAR_{tag}_CI']}")
        print(f"  {r.candidate:>14s} false removed (A+x) - A: {r.dfr:+.4f} {r.dfr_CI}")


def ratio_jobs(key, coh_set, col, mode, tw):
    """all-episode ratio (HARP bootstrap) and twins ratio (pairs resampled by true HARP), 2,000, seed 0."""
    c = coh_set[coh_set[col].notna()].reset_index(drop=True)
    h, y, x = c.harpnum.to_numpy(), c.true_alarm.to_numpy(), c[col].to_numpy(float)
    ga = [np.where(h == v)[0] for v in np.unique(h)]
    v = coh_set.set_index("eid")[col]
    p = tw.assign(xt=tw.true_eid.map(v), xf=tw.false_eid.map(v)).dropna(subset=["xt", "xf"]).reset_index(drop=True)
    gp = [np.where(p.true_harp.to_numpy() == v_)[0] for v_ in p.true_harp.unique()]
    est = dict(measure=key, n=len(c), n_true=int(y.sum()), n_false=int((y == 0).sum()), med_true=np.median(x[y == 1]),
               med_false=np.median(x[y == 0]), ratio_all=med_ratio(x[y == 1], x[y == 0], mode), pairs=len(p),
               twin_med_true=p.xt.median(), twin_med_false=p.xf.median(),
               ratio_twins=med_ratio(p.xt.to_numpy(), p.xf.to_numpy(), mode), mode=mode)
    jobs = {(key, "all"): ("ratio_all", dict(x=x, y=y, mode=mode, groups=ga), NB_R, SEED_R),
            (key, "tw"): ("ratio_pairs", dict(xt=p.xt.to_numpy(), xf=p.xf.to_numpy(), mode=mode, groups=gp), NB_R, SEED_R)}
    return est, jobs


def ratios(specs, pool):
    ests, jobs = [], {}
    for key, cs, col, mode in specs:
        e, j = ratio_jobs(key, cs, col, mode, twins()); ests.append(e); jobs.update(j)
    B = boot_many(jobs, pool)
    for e in ests:
        k = e["measure"]
        e["all_CI"] = "[%.4f, %.4f]" % pct(B[(k, "all")]); e["twins_CI"] = "[%.4f, %.4f]" % pct(B[(k, "tw")])
        e["undefined_resamples"] = int(np.sum(~np.isfinite(np.asarray(B[(k, "all")], float)))) + \
            int(np.sum(~np.isfinite(np.asarray(B[(k, "tw")], float))))
    T = pd.DataFrame(ests)
    print("ratio = true / false of medians ('log': 10^(median diff) on the linear scale; 'diff': median true - median false); "
          f"CI HARP bootstrap {NB_R}, seed {SEED_R}; twins = step 6 PRIMARY pairs with both values defined, resampled by true HARP")
    print(T[["measure", "mode", "n", "n_true", "n_false", "med_true", "med_false", "ratio_all", "all_CI", "pairs", "twin_med_true",
             "twin_med_false", "ratio_twins", "twins_CI", "undefined_resamples"]].to_string(index=False, float_format=lambda v: f"{v:.4g}"))
    return T


def spear(c, xs, vs):
    from scipy.stats import spearmanr
    rows = []
    for x in xs:
        for v in vs:
            m = c[x].notna() & c[v].notna()
            r, p = spearmanr(c.loc[m, x], c.loc[m, v])
            rows.append(dict(measure=x, variable=v, n=int(m.sum()), rho=r, p=p))
    T = pd.DataFrame(rows)
    print(T.to_string(index=False, formatters={"rho": "{:.4f}".format, "p": "{:.2e}".format}))
    return T


# ================================================================ per-episode computations (workers)
def _frames_values(eid):
    f = pd.read_csv(f"{R}/spatial/{eid}_frames.csv")
    pil = f[[f"frac_pil_{k}" for k in range(20)]].mean(axis=1)
    return eid, float(np.nanmedian(f.frac_box)), float(np.nanmedian(pil)) if pil.notna().any() else np.nan, \
        float(np.nanmedian(f.n_bright_px))


def _size(args):
    eid, npix = args
    s = pd.read_csv(f"{R}/series/{eid}.csv", usecols=["valid_primary", "box"])
    b = s.loc[s.valid_primary, "box"]
    f = pd.read_csv(f"{R}/spatial/{eid}_frames.csv", usecols=["n_bright_px"])
    return eid, float(np.log10(np.median(b * npix))) if len(b) else np.nan, float(np.median(f.n_bright_px / npix)) if len(f) else np.nan


def _level(eid):
    s = pd.read_csv(f"{R}/series/{eid}.csv", parse_dates=["t_obs"])
    r = s[[f"pil_{k}" for k in range(20)]].mean(axis=1) / s[[f"ctrl_{k}" for k in range(20)]].mean(axis=1)
    out = [eid]
    for col in ["valid_primary", "valid_sens"]:
        m = s[col] & np.isfinite(r) & (r > 0)
        if m.sum() >= 3:
            lr = np.log10(r[m].to_numpy()); th = (s.t_obs[m] - s.t_obs[m].iloc[0]).dt.total_seconds().to_numpy() / 3600
            out += [float(np.log10(np.median(r[m]))), float(np.polyfit(th, lr, 1)[0])]
        else:
            out += [np.nan, np.nan]
    return tuple(out)


def _hmi_keys(args):
    from astropy.io import fits
    from euv_full import hmi_files
    eid, h, trec = args
    m, _ = hmi_files(f"{R}/hmi/{h}", trec)
    hd = fits.getheader(m, 1)
    return eid, float(hd["AREA_ACR"]), float(hd["USFLUX"])


# ================================================================ items
def item_F2(pool, coh):
    rows = pool.map(_frames_values, coh.loc[coh.P & coh.R4a.notna(), "eid"].tolist(), chunksize=8)
    fv = pd.DataFrame(list(rows), columns=["eid", "bright_box", "bright_pil", "n_bright_px_med"])
    c = coh[coh.P].merge(fv, on="eid", how="left")
    fv.to_csv(f"{OUT}/F2_episode_values.csv", index=False)
    print(f"F2: primary-valid episodes {int(coh.P.sum())} (true {int(coh[coh.P].true_alarm.sum())}, false {int((coh[coh.P].true_alarm == 0).sum())})")
    T = ratios([("box brightening fraction", c, "bright_box", "ratio"), ("PIL brightening fraction", c, "bright_pil", "ratio"),
                ("CV_box", c, "primary_CV_box", "ratio"), ("CV_PIL", c, "primary_CV_PIL", "ratio"),
                ("CV_ctrl", c, "primary_CV_ctrl", "ratio")], pool)
    T.to_csv(f"{OUT}/F2_ratios.csv", index=False)
    print("\ncontext (user): BADPIT ~5x brightenings (2 ARs, 12 s cadence); Kniezewski et al. 2024 ratios > 1, \"flare-active ARs' "
          "ratio never drops to 1 (possible inherent variability)\" (3 min cadence). Cadence deviation here: 12 min.")


def item_F3(pool, coh):
    import swpc
    print("1. B-class (K2 true flux in [1e-7, 1e-6)) events per year, deduplicated, and how many carry a region number")
    cov = []
    for y in range(2010, 2020):
        fl, _ = swpc.load(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31 23:59"))
        b = fl[fl.cls == "B"]
        cov.append(dict(year=y, B_events=len(b), with_region=int(b.noaa_ar.notna().sum()),
                        frac_with_region=b.noaa_ar.notna().mean() if len(b) else np.nan))
    cov = pd.DataFrame(cov); cov.to_csv(f"{OUT}/F3_B_coverage.csv", index=False)
    print(cov.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    fl, _ = swpc.fetch(pd.Timestamp("2010-04-28"), DEV_END, verbose=False)                     # joinable events, dev only
    by_ar = {k: v[["start", "cls"]].sort_values("start") for k, v in fl.groupby("noaa_ar")}
    cnt = []
    for e in coh.itertuples():                                     # = build_dataset.label history join, [t-48h, t)
        prev = [g[(g.start >= e.t - pd.Timedelta(hours=48)) & (g.start < e.t)] for ar in
                [int(a) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()] if (g := by_ar.get(ar)) is not None]
        p = pd.concat(prev).drop_duplicates() if prev else pd.DataFrame(columns=["start", "cls"])
        cnt.append({k: int((p.cls == k).sum()) for k in "BCMX"})
    cnt = pd.DataFrame(cnt)
    ok = all((cnt[k].to_numpy() == coh[f"n_{k}"].to_numpy()).all() for k in "CMX")
    print(f"\ncheck: the join reproduces the cohort n_C, n_M, n_X for all {len(coh)} episodes: {ok}"); assert ok
    coh = coh.assign(n_B=cnt.B.to_numpy(), n_BC=cnt.B.to_numpy() + cnt.C.to_numpy())
    coh[["eid", "n_B"]].to_csv(f"{OUT}/F3_n_B.csv", index=False)
    c = prep(coh, coh.P & coh.R4a.notna())
    print(f"\n2. n_B on the R4a set ({len(c)}): median {c.n_B.median():.1f}, IQR [{c.n_B.quantile(.25):.1f}, {c.n_B.quantile(.75):.1f}], "
          f"max {c.n_B.max()}, zero {int((c.n_B == 0).sum())}")
    print("\n3. Spearman (R4a set)"); S = spear(c, ["R4a"], ["n_B", "n_BC", "n_C"]); S.to_csv(f"{OUT}/F3_spearman.csv", index=False)
    # parallel == single-process check on one candidate (A + R4a)
    from euv_spatial import cv_fit
    pA, pE = cv_fit(c, A_COLS), cv_fit(c, A_COLS + ["R4a"]); y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    harps = np.unique(h); idx = {x: np.where(h == x)[0] for x in harps}; rng, seq = np.random.RandomState(SEED_D), []
    for _ in range(NB_D):
        ix = np.concatenate([idx[x] for x in rng.choice(harps, len(harps), replace=True)])
        seq.append(wlogloss(y[ix], pA[ix], w[ix]) - wlogloss(y[ix], pE[ix], w[ix]))
    par = boot_many({"k": ("dll", dict(y=y, w=w, pA=pA, pE=pE, groups=[idx[x] for x in harps]), NB_D, SEED_D)}, pool)["k"]
    d = np.max(np.abs(np.array(seq) - np.array(par)))
    print(f"\ncheck: parallel ({W} workers) vs single-process bootstrap for A + R4a: max |diff| = {d}"); assert d == 0
    T = evaluate([("n_B", c, ["n_B"]), ("n_B + R4a", c, ["n_B", "R4a"]), ("R4a", c, ["R4a"])], pool)
    px = pd.read_csv(f"{R}/spatial/eval_compare.csv").set_index("candidate").loc["R4a"]
    r = T.set_index("candidate").loc["R4a"]
    assert abs(r.delta - px.delta_A_minus_Aplus) < 1e-12 and abs(r.CI_lo - px.CI_lo) < 1e-12 and abs(r.CI_hi - px.CI_hi) < 1e-12
    print("check: restated A + R4a equals Phase X (315ca5b)")
    T.to_csv(f"{OUT}/F3_eval.csv", index=False); show_eval(T, "4. step 6 procedure on the R4a set")


def item_F4(pool, coh):
    import swpc
    fl, _ = swpc.fetch(pd.Timestamp("2010-04-28"), DEV_END, verbose=False)
    m1 = fl[fl.flux >= 1e-5]; by = {int(a): np.sort(g.start.values) for a, g in m1.groupby("noaa_ar")}
    span = pd.read_csv("data/stage2/oof_scores_dev.csv", usecols=["harpnum", "t_rec_utc"], parse_dates=["t_rec_utc"])
    assert span.t_rec_utc.max() <= DEV_END
    end = span.groupby("harpnum").t_rec_utc.max()
    rows = []
    for e in coh.itertuples():
        s = np.sort(np.concatenate([by.get(int(a), np.array([], "datetime64[ns]")) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()]))
        after = s[(s > np.datetime64(e.t)) & (s <= np.datetime64(end[e.harpnum]))]
        first = pd.Timestamp(after[0]) if len(after) else pd.NaT
        rows.append(dict(eid=e.eid, span_end=end[e.harpnum], first_M1_after=first,
                         lead_h=(first - e.t).total_seconds() / 3600 if len(after) else np.nan))
    d = coh.merge(pd.DataFrame(rows), on="eid")
    d["JUST_FLARED"] = (d.n_M + d.n_X) >= 1; d["QUIET_NOW"] = (d.n_C + d.n_M + d.n_X) == 0
    d["TOO_EARLY"] = d.lead_h > 24; d["NEVER"] = d.lead_h.isna(); d["M1_in_24h"] = d.lead_h <= 24
    d.to_csv(f"{OUT}/F4_classes.csv", index=False)
    f, t = d[d.true_alarm == 0], d[d.true_alarm == 1]
    print(f"F4: false {len(f)}, true {len(t)}; check: false episodes with a region M1+ in (t, t+24h]: {int(f.M1_in_24h.sum())}; "
          f"true episodes with one: {int(t.M1_in_24h.sum())}/{len(t)}")
    cl = ["JUST_FLARED", "QUIET_NOW", "TOO_EARLY", "NEVER"]
    print("\nclass counts among false episodes (classes overlap across the history/future axes):")
    for k in cl:
        print(f"  {k:12s} {int(f[k].sum()):4d} / {len(f)} = {f[k].mean():.4f}")
    hist = np.where(f.JUST_FLARED, "JUST_FLARED", np.where(f.QUIET_NOW, "QUIET_NOW", "C-only history"))
    fut = np.where(f.TOO_EARLY, "TOO_EARLY", np.where(f.NEVER, "NEVER", "other"))
    X = pd.crosstab(pd.Series(hist, name="history [t-48h, t)"), pd.Series(fut, name="future"), margins=True)
    print("\noverlaps (false episodes):"); print(X.to_string())
    x = f.loc[f.TOO_EARLY, "lead_h"]
    print(f"\nTOO_EARLY lead (h): n {len(x)}, median {x.median():.1f}, IQR [{x.quantile(.25):.1f}, {x.quantile(.75):.1f}]; "
          f"of which delayed (M1+ in (t+24h, t+48h]): {int(f.loc[f.TOO_EARLY, 'delayed'].sum())}")
    print(f"true episodes: zero prior flares (n_C = n_M = n_X = 0): {int(t.QUIET_NOW.sum())}/{len(t)}; JUST_FLARED: {int(t.JUST_FLARED.sum())}/{len(t)}")
    rows = []
    for grp, sub in [(k, f[f[k]]) for k in cl] + [("all false", f), ("true", t)]:
        r = dict(group=grp, n=len(sub))
        for col, lab in [("primary_dCV", "dCV"), ("R4a", "R4a")]:
            v = sub.loc[sub.P & sub[col].notna(), col]
            r.update({f"{lab}_n": len(v), f"{lab}_median": v.median(), f"{lab}_Q1": v.quantile(.25), f"{lab}_Q3": v.quantile(.75)})
        rows.append(r)
    M = pd.DataFrame(rows); M.to_csv(f"{OUT}/F4_class_medians.csv", index=False)
    print("\nmedian [IQR] of dCV (primary) and R4a per class (primary-valid episodes with a value)")
    print(M.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    g = np.where(d.QUIET_NOW, 0, 1); y, w, h = d.true_alarm.to_numpy(), d.weight.to_numpy(), d.harpnum.to_numpy()
    groups = [np.where(h == v)[0] for v in np.unique(h)]
    B = np.array(boot_many({"r": ("rate", dict(y=y, w=w, g=g, levels=[0, 1], groups=groups), NB_R, SEED_R)}, pool)["r"], float)
    print(f"\ntrue-rate per history group (all {len(d)} episodes; weighted 1/n per HARP as Stage 4; CI HARP bootstrap {NB_R}, seed {SEED_R})")
    for i, (k, lab) in enumerate([(0, "zero history (n_C = n_M = n_X = 0)"), (1, "any history")]):
        m = g == k; rate = (w * y * m).sum() / (w * m).sum()
        print(f"  {lab:36s} episodes {int(m.sum()):3d}, true {int(y[m].sum()):3d}; weighted rate {rate:.4f} [{pct(B[:, i])[0]:.4f}, {pct(B[:, i])[1]:.4f}]")


def item_F5(pool, coh):
    dv = pd.read_csv("data/stage2/oof_scores_dev.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"])
    c0 = coh[coh.P & coh.R4a.notna()].merge(dv, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left")
    assert c0.t_rec_tai.notna().all()
    sz = pd.DataFrame(list(pool.map(_size, list(zip(c0.eid, c0.npix_box)), chunksize=8)), columns=["eid", "S1", "S2"])
    hk = pd.DataFrame(list(pool.map(_hmi_keys, list(zip(c0.eid, c0.harpnum, c0.t_rec_tai)), chunksize=8)), columns=["eid", "AREA_ACR", "USFLUX"])
    c1 = coh[coh.P].merge(sz, on="eid", how="left").merge(hk, on="eid", how="left")
    c1[["eid", "S1", "S2", "AREA_ACR", "USFLUX"]].to_csv(f"{OUT}/F5_values.csv", index=False)
    print(f"F5: episodes with S1/S2 {int(c1.S1.notna().sum())}/{int(c1.S2.notna().sum())} of {len(c1)} primary-valid")
    T = ratios([("S1 log10 total 94 A emission", c1, "S1", "log"), ("S2 bright-pixel fraction", c1, "S2", "ratio")], pool)
    T.to_csv(f"{OUT}/F5_ratios.csv", index=False)
    print("\nSpearman"); spear(c1, ["S1", "S2"], ["AREA_ACR", "USFLUX", "score", "R4a"]).to_csv(f"{OUT}/F5_spearman.csv", index=False)
    E = evaluate([("S1 (size)", prep(c1, c1.S1.notna()), ["S1"]), ("S2 (size)", prep(c1, c1.S2.notna()), ["S2"])], pool)
    E.to_csv(f"{OUT}/F5_eval.csv", index=False); show_eval(E, "step 6 procedure")


def item_F6(pool, coh):
    lv = pd.DataFrame(list(pool.map(_level, coh.loc[coh.primary_fill.notna(), "eid"].tolist(), chunksize=8)),
                      columns=["eid", "B1", "B2", "B1_nf", "B2_nf"])
    c = coh.merge(lv, on="eid", how="left"); lv.to_csv(f"{OUT}/F6_values.csv", index=False)
    cp, cn = c[c.P & c.B1.notna()], c[c.S & c.B1_nf.notna()]
    print(f"F6: primary set {len(cp)} (true {int(cp.true_alarm.sum())}), flare-excluded set {len(cn)} (true {int(cn.true_alarm.sum())})")
    T = ratios([("B1 PIL/ctrl level", c[c.P], "B1", "log"), ("B2 PIL/ctrl slope", c[c.P], "B2", "diff"),
                ("B1_nf", c[c.S], "B1_nf", "log"), ("B2_nf", c[c.S], "B2_nf", "diff")], pool)
    T.to_csv(f"{OUT}/F6_ratios.csv", index=False)
    print("\nSpearman (primary set for B1/B2, flare-excluded set for B1_nf/B2_nf)")
    S = pd.concat([spear(cp, ["B1", "B2"], ["n_C", "score", "R4a"]), spear(cn, ["B1_nf", "B2_nf"], ["n_C", "score", "R4a"])])
    S.to_csv(f"{OUT}/F6_spearman.csv", index=False)
    E = evaluate([("B1", prep(c, c.P & c.B1.notna()), ["B1"]), ("B2", prep(c, c.P & c.B2.notna()), ["B2"]),
                  ("B1_nf", prep(c, c.S & c.B1_nf.notna()), ["B1_nf"]), ("B2_nf", prep(c, c.S & c.B2_nf.notna()), ["B2_nf"])], pool)
    E.to_csv(f"{OUT}/F6_eval.csv", index=False); show_eval(E, "step 6 procedure")
    print("\ncontext (user): Leka et al. 2023 found mean intensity \"surprisingly poor\" at whole-region level; "
          "the PIL-relative level was not tested there.")


def item_F7(pool, coh):
    nb = pd.read_csv(f"{OUT}/F3_n_B.csv"); f5 = pd.read_csv(f"{OUT}/F5_values.csv"); f6 = pd.read_csv(f"{OUT}/F6_values.csv")
    c = coh.merge(nb, on="eid", how="left").merge(f5[["eid", "S1", "S2"]], on="eid", how="left").merge(f6, on="eid", how="left")
    P, S = c.P, c.S
    cands = [("trends (B)", prep(c, pd.Series(True, index=c.index)), ["rel_slope_usflux", "rel_slope_totusjh"]),
             ("dCV_94", prep(c, P & c.primary_dCV.notna()), ["primary_dCV"])]
    cands += [(k, prep(c, P & c[k].notna()), [k]) for k in ["R1", "R2", "R3", "R4a", "R4b", "R4c"]]
    cands += [("R4a_nf", prep(c, S & c.R4a_nf.notna()), ["R4a_nf"]), ("n_B", prep(c, P & c.R4a.notna()), ["n_B"]),
              ("n_B + R4a (combination)", prep(c, P & c.R4a.notna()), ["n_B", "R4a"]),
              ("S1 (size)", prep(c, P & c.S1.notna()), ["S1"]), ("S2 (size)", prep(c, P & c.S2.notna()), ["S2"]),
              ("B1", prep(c, P & c.B1.notna()), ["B1"]), ("B2", prep(c, P & c.B2.notna()), ["B2"]),
              ("B1_nf", prep(c, S & c.B1_nf.notna()), ["B1_nf"]), ("B2_nf", prep(c, S & c.B2_nf.notna()), ["B2_nf"])]
    T = evaluate(cands, pool).set_index("candidate")
    # checks against committed results
    s4 = pd.read_csv("data/stage4/cv_primary.csv").set_index("fold").loc["pooled"]
    assert abs(T.loc["trends (B)", "delta"] - s4.delta_A_minus_B) < 1e-12 and abs(T.loc["trends (B)", "AUC_Ax"] - s4.AUC_B) < 1e-12
    s6 = pd.read_csv(f"{R}/step6/compare.csv").set_index("set").loc["PRIMARY"]
    assert all(abs(T.loc["dCV_94", a] - s6[b]) < 1e-12 for a, b in [("delta", "delta_A_minus_E94"), ("CI_lo", "CI_lo"), ("CI_hi", "CI_hi")])
    px = pd.read_csv(f"{R}/spatial/eval_compare.csv").set_index("candidate")
    for k in ["R1", "R2", "R3", "R4a", "R4b", "R4c"]:
        assert all(abs(T.loc[k, a] - px.loc[k, b]) < 1e-12 for a, b in [("delta", "delta_A_minus_Aplus"), ("CI_lo", "CI_lo"), ("CI_hi", "CI_hi")])
    nfc = pd.read_csv(f"{R}/spatial_nf/eval_nf_compare.csv").iloc[1]
    assert all(abs(T.loc["R4a_nf", a] - nfc[b]) < 1e-12 for a, b in [("delta", "delta_A_minus_Aplus"), ("CI_lo", "CI_lo"), ("CI_hi", "CI_hi")])
    opd = pd.read_csv(f"{R}/spatial_nf/oppoint_dev.csv").set_index("model")
    assert abs(T.loc["R4a_nf", "false_removed_Ax"] - opd.loc["A+R4a_nf", "false_removed"]) < 1e-12 \
        and T.loc["R4a_nf", "false_removed_Ax_CI"] == opd.loc["A+R4a_nf", "false_removed_CI"] \
        and T.loc["R4a_nf", "false_removed_A_CI"] == opd.loc["A", "false_removed_CI"]
    for k in ["n_B", "n_B + R4a (combination)"]:
        f3 = pd.read_csv(f"{OUT}/F3_eval.csv").set_index("candidate").rename(index={"n_B + R4a": "n_B + R4a (combination)"})
        assert abs(T.loc[k, "delta"] - f3.loc[k, "delta"]) < 1e-12
    print("checks: restated rows equal Stage 4 (pooled delta, AUC), step 6, Phase X, the R4a flare check, 04b6f4f "
          "(R4a_nf operating point), and F3/F5/F6 of this phase")
    T = T.reset_index(); T.to_csv(f"{OUT}/F7_summary.csv", index=False)
    print("\nF7 SUMMARY — every candidate evaluated on dev (EXPLORATORY; internal 5-fold CV; no selection)")
    print(f"delta = LL(A) - LL(A+x); CI HARP bootstrap {NB_D}, seed {SEED_D}; false removed at >= 88% weighted true kept "
          f"(tau in-sample), weighted with CI (HARP bootstrap {NB_R}, seed {SEED_R}) and counts")
    out = T.assign(CI=lambda z: z.apply(lambda r: f"[{r.CI_lo:.4f}, {r.CI_hi:.4f}]", axis=1),
                   fr_Ax=lambda z: z.apply(lambda r: f"{r.false_removed_Ax:.4f} {r.false_removed_Ax_CI} ({r.false_removed_n_Ax})", axis=1),
                   fr_A=lambda z: z.apply(lambda r: f"{r.false_removed_A:.4f} ({r.false_removed_n_A})", axis=1))
    print(out[["candidate", "n", "true", "false", "delta", "CI", "AUC_A", "AUC_Ax", "fr_A", "fr_Ax"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("Stage 4 committed trends CI used 1,000 resamples: [-0.0114, 0.0253] (Stage 4 delta is A - B)")


if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] in {"F2", "F3", "F4", "F5", "F6", "F7"}:
    os.makedirs(OUT, exist_ok=True)
    it = sys.argv[1]; t0 = time.time()
    print(f"PHASE F {it} -- EXPLORATORY / DESCRIPTIVE, dev 2010-2019 only; workers = os.cpu_count() - 1 = {W}")
    coh = load_base()
    with ProcessPoolExecutor(W) as pool:
        globals()[f"item_{it}"](pool, coh)
    print(f"\n{it} wall time {time.time() - t0:.1f} s on {W} worker processes (os.cpu_count() = {os.cpu_count()})")
