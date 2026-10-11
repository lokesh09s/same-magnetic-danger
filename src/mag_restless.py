"""Candidate #26 MAGNETIC RESTLESSNESS (MR) -- decisions.md 2026-09-30 (46207c7, amendment b2ca7ac). EXPLORATORY (dev).
Step 1 (label-blind): MR and all secondaries for the 547 dev episodes from the hourly SHARP chunk files on disk.
No label column is loaded: the cohort is read with usecols = harpnum, t, noaa_ars, fold.
  window records: T_REC (TAI -> UTC as build_dataset.py) in (t - 24 h, t], QUALITY == 0, |LON_FWT| <= 45 deg
  fit per parameter: least squares a + b*x + c*sin(2 pi x / 12) + d*cos(2 pi x / 12), x = hours relative to t
  CV_p = SD(residuals, ddof=1) / mean(values); undefined if mean <= 0 or SD = 0
  MR = mean over P = {TOTUSJH, TOTPOT, TOTUSJZ} of log10 CV_p, on records with all three finite; >= 18 records
Usage: python mag_restless.py step1   -> data/mag_restless/dev_mr.csv, tertiles.json, figures/mag_restless/, log on stdout
       python mag_restless.py quad    -> data/mag_restless/dev_mr_quad.csv (amendment A1, label-blind)"""
import io, json, os, sys, time
import numpy as np, pandas as pd
from astropy.time import Time
import chunks, swpc
from euv_pilot import flare_excluded

P = ["TOTUSJH", "TOTPOT", "TOTUSJZ"]
OTHER = ["USFLUX", "R_VALUE", "MEANSHR"]
MIN24, MIN12, LON_LIMIT, PERIOD = 18, 9, 45.0, 12.0
DEV_END = "2020-01-01"
OUT, FIG = "data/mag_restless", "figures/mag_restless"


def eid_of(h, t):
    return f"{h}_{t:%Y%m%dT%H%M}"


def load_episodes():
    """547 dev episodes, label-blind (only keys, regions and fold), plus the 541 euv_extra analysis-set flag."""
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", usecols=["harpnum", "t", "noaa_ars", "fold"], parse_dates=["t"])
    assert len(coh) == 547 and "true_alarm" not in coh.columns
    coh["eid"] = [eid_of(h, t) for h, t in zip(coh.harpnum, coh.t)]
    dr = pd.read_csv("data/euv_extra/dev_rows.csv", usecols=["eid"])
    assert len(dr) == 541 and set(dr.eid) <= set(coh.eid)
    coh["in541"] = coh.eid.isin(dr.eid)
    return coh


def load_sharp(harps):
    """Dev monthly chunk files only (chunks.py list; ad-hoc files are not read). Returns (records, info)."""
    raw_f = [p for a, p in chunks.files("raw_sharp") if a < DEV_END]
    ext_f = [p for a, p in chunks.files("raw_sharp_extra") if a < DEV_END]
    raw = pd.concat([pd.read_csv(p, usecols=["HARPNUM", "T_REC", "QUALITY", "LON_FWT"] + P[:2] + OTHER, dtype={"T_REC": str})
                     for p in raw_f], ignore_index=True)
    ext = pd.concat([pd.read_csv(p, usecols=["HARPNUM", "T_REC", "TOTUSJZ"], dtype={"T_REC": str}) for p in ext_f], ignore_index=True)
    raw, ext = raw[raw.HARPNUM.isin(harps)], ext[ext.HARPNUM.isin(harps)]
    k = ["HARPNUM", "T_REC"]
    info = dict(raw_files=len(raw_f), extra_files=len(ext_f), raw_rows=len(raw), extra_rows=len(ext),
                raw_dup_keys=int(raw.duplicated(k).sum()), raw_dup_identical=int(raw.duplicated().sum()),
                extra_dup_keys=int(ext.duplicated(k).sum()), extra_dup_identical=int(ext.duplicated().sum()))
    raw, ext = raw.drop_duplicates(k), ext.drop_duplicates(k)
    d = raw.merge(ext, on=k, how="left", indicator=True)
    info["raw_without_extra"] = int((d._merge == "left_only").sum()); d = d.drop(columns="_merge")
    d["QUALITY"] = pd.to_numeric(d.QUALITY, errors="raise").astype(np.int64)
    u = pd.unique(d.T_REC)
    utc = pd.to_datetime(Time([s.replace("_TAI", "").replace(".", "-", 2).replace("_", " ") for s in u],
                              format="iso", scale="tai").utc.isot)
    d["t_utc"] = d.T_REC.map(dict(zip(u, utc)))
    d["tai_hour"] = d.T_REC.str[11:13].astype(int)
    return d.sort_values(["HARPNUM", "t_utc"]).reset_index(drop=True), info


def fit(x, v, harmonic=True, quad=False):
    """-> (CV, 12-h amplitude as % of mean, reason). reason is '' when defined. quad adds t^2 (MR_quad, amendment A1)."""
    X = np.column_stack([np.ones_like(x), x] + ([x ** 2] if quad else [])
                        + ([np.sin(2 * np.pi * x / PERIOD), np.cos(2 * np.pi * x / PERIOD)] if harmonic else []))
    beta = np.linalg.lstsq(X, v, rcond=None)[0]
    sd, m = np.std(v - X @ beta, ddof=1), float(np.mean(v))
    amp = float(np.hypot(beta[-2], beta[-1]) / m * 100) if harmonic and m > 0 else np.nan
    if m <= 0:
        return np.nan, amp, "mean <= 0"
    if sd <= 1e-12 * m:                     # "residual SD = 0" up to floating-point round-off of an exact fit
        return np.nan, amp, "residual SD = 0"
    return float(sd / m), amp, ""


def mr(x, V, n_min, harmonic=True, quad=False):
    """V: records x P (all finite). -> (MR, {p: log10 CV_p}, {p: amp}, reason)."""
    if len(x) < n_min:
        return np.nan, {}, {}, f"< {n_min} records"
    l, a, why = {}, {}, []
    for j, p in enumerate(P):
        cv, amp, r = fit(x, V[:, j], harmonic, quad)
        l[p], a[p] = (np.log10(cv) if np.isfinite(cv) else np.nan), amp
        if r:
            why.append(f"{p}: {r}")
    return (float(np.mean(list(l.values()))) if not why else np.nan), l, a, "; ".join(why)


def episode(e, g, ev):
    t = e.t
    x_all = ((g.t_utc - t) / pd.Timedelta(hours=1)).to_numpy(float)
    w24 = (x_all > -24) & (x_all <= 0)
    q_ok, lon_ok = (g.QUALITY == 0).to_numpy(), (g.LON_FWT.abs() <= LON_LIMIT).to_numpy()
    keep = w24 & q_ok & lon_ok
    fin = np.isfinite(g[P].to_numpy(float)).all(axis=1)
    r = dict(eid=e.eid, harpnum=e.harpnum, t=t, fold=e.fold, in541=e.in541, year=t.year,
             n_window=int(w24.sum()), n_q_removed=int((w24 & ~q_ok).sum()),
             n_q_removed_tai0618=int((w24 & ~q_ok & g.tai_hour.isin([6, 18]).to_numpy()).sum()),
             n_lon_removed=int((w24 & q_ok & ~lon_ok).sum()),
             n_P=int((keep & fin).sum()), n_P_no_lon_cut=int((w24 & q_ok & fin).sum()))
    sel = keep & fin
    V = g[P].to_numpy(float)
    r["MR"], lc, amp, r["reason_MR"] = mr(x_all[sel], V[sel], MIN24)
    r["MR_lin"], _, _, r["reason_MR_lin"] = mr(x_all[sel], V[sel], MIN24, harmonic=False)
    r["MR_quad"], _, _, r["reason_MR_quad"] = mr(x_all[sel], V[sel], MIN24, quad=True)
    for p in P:
        r[f"amp_{p}"] = amp.get(p, np.nan)
    # single-parameter secondaries (own finite records)
    for p in P + OTHER:
        v = g[p].to_numpy(float); s = keep & np.isfinite(v)
        if s.sum() < MIN24:
            r[f"lcv_{p}"], r[f"reason_{p}"], a = np.nan, f"< {MIN24} records", np.nan
        else:
            cv, a, why = fit(x_all[s], v[s])
            r[f"lcv_{p}"], r[f"reason_{p}"] = (np.log10(cv) if np.isfinite(cv) else np.nan), why
        if p in OTHER:
            r[f"amp_{p}"] = a
    # 12-h window
    s12 = sel & (x_all > -12)
    r["n_P_12h"] = int(s12.sum())
    r["MR_12h"], _, _, r["reason_MR_12h"] = mr(x_all[s12], V[s12], MIN12)
    # flare-excluded (euv_full.py call: swpc.load(t - 2 d, t), the episode's noaa_ars)
    regions = {int(z) for z in str(e.noaa_ars).split(",") if z.strip()}
    idx = np.where(sel)[0]
    ex = flare_excluded(g.t_utc.iloc[idx].reset_index(drop=True), ev, regions)[0] if len(idx) else np.zeros(0, bool)
    nf = idx[~ex]
    r["n_flare_removed"], r["n_P_nf"] = int(ex.sum()), len(nf)
    r["MR_nf"], _, _, r["reason_MR_nf"] = mr(x_all[nf], V[nf], MIN24)
    # MR without the longitude cut (only to count episodes whose value/evaluability the cut changes)
    s0 = w24 & q_ok & fin
    r["MR_no_lon_cut"], _, _, _ = mr(x_all[s0], V[s0], MIN24)
    return r


def plot(ex, sharp, path):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 2 * len(ex), figsize=(5.2 * len(ex), 7.2), sharex=True)
    for k, (lab, e) in enumerate(ex):
        g = sharp[sharp.HARPNUM == e.harpnum]
        x = ((g.t_utc - e.t) / pd.Timedelta(hours=1)).to_numpy(float)
        s = (x > -24) & (x <= 0) & (g.QUALITY == 0).to_numpy() & (g.LON_FWT.abs() <= LON_LIMIT).to_numpy() & np.isfinite(g[P].to_numpy(float)).all(1)
        xs, xx = x[s], np.linspace(-24, 0, 300)
        for j, p in enumerate(P):
            v = g[p].to_numpy(float)[s]
            X = lambda z: np.column_stack([np.ones_like(z), z, np.sin(2 * np.pi * z / PERIOD), np.cos(2 * np.pi * z / PERIOD)])
            b = np.linalg.lstsq(X(xs), v, rcond=None)[0]; bl = np.polyfit(xs, v, 1)
            a0, a1 = ax[j, 2 * k], ax[j, 2 * k + 1]
            a0.plot(xs, v, "o", ms=3.5, color="#2a6fb0"); a0.plot(xx, X(xx) @ b, "-", color="#c0392b", lw=1.4, label="trend + 12-h sinusoid")
            a0.plot(xx, np.polyval(bl, xx), "--", color="#7f8c8d", lw=1, label="linear only")
            a1.axhline(0, color="#bbb", lw=0.8); a1.plot(xs, v - X(xs) @ b, "o-", ms=3, lw=0.8, color="#2a6fb0")
            a0.set_ylabel(p, fontsize=8); a0.tick_params(labelsize=7); a1.tick_params(labelsize=7)
            if j == 0:
                a0.set_title(f"{lab}: HARP {e.harpnum}, t = {e.t:%Y-%m-%d %H:%M} UTC\nMR = {e.MR:.3f}; series + fits", fontsize=8)
                a1.set_title("residuals (trend + 12-h fit)", fontsize=8)
                if k == 0:
                    a0.legend(fontsize=6, loc="best")
        ax[2, 2 * k].set_xlabel("hours relative to t", fontsize=8); ax[2, 2 * k + 1].set_xlabel("hours relative to t", fontsize=8)
    fig.suptitle("Candidate #26 MR, label-blind examples (MR 10th / 50th / 90th percentile of the 547 dev episodes); records: QUALITY == 0, |LON_FWT| <= 45", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def compute():
    coh = load_episodes()
    sharp, info = load_sharp(set(coh.harpnum))
    by = {h: g.reset_index(drop=True) for h, g in sharp.groupby("HARPNUM")}
    empty = sharp.iloc[:0]
    rows = []
    for e in coh.itertuples():
        ev, _ = swpc.load(e.t - pd.Timedelta("2D"), e.t)
        rows.append(episode(e, by.get(e.harpnum, empty), ev))
    return pd.DataFrame(rows), sharp, info


def step1():
    t0 = time.time(); os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    d, sharp, info = compute()
    d.drop(columns=["MR_quad", "reason_MR_quad"]).to_csv(f"{OUT}/dev_mr.csv", index=False)
    f4 = lambda v: f"{v:.4f}"
    print("CANDIDATE #26 MR — STEP 1, LABEL-BLIND (EXPLORATORY (dev)); decisions.md 46207c7 + amendment b2ca7ac")
    print(f"label columns loaded: none (cohort usecols = harpnum, t, noaa_ars, fold). Episodes: {len(d)} dev; analysis set (euv_extra dev_rows): {int(d.in541.sum())}")
    print("\n== SHARP input (dev monthly chunk files, chunks.py; restricted to the dev HARPs)")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"  after de-duplication: {len(sharp)} records for {sharp.HARPNUM.nunique()} HARPs")
    print("\n== Window records, (t - 24 h, t], all 547 episodes")
    W = d[["n_window", "n_q_removed", "n_q_removed_tai0618", "n_lon_removed"]].sum()
    print(f"  records in windows: {W.n_window}; removed by QUALITY != 0: {W.n_q_removed} "
          f"(of which at TAI 06:00/18:00: {W.n_q_removed_tai0618}); removed by |LON_FWT| > 45 (after QUALITY): {W.n_lon_removed}")
    print(f"  episodes with >= 1 record removed by the longitude cut: {int((d.n_lon_removed > 0).sum())}")
    ev_no, ev_yes = d.MR_no_lon_cut.notna(), d.MR.notna()
    print(f"  MR defined without the longitude cut: {int(ev_no.sum())}; with it: {int(ev_yes.sum())}; "
          f"made undefined by the cut: {int((ev_no & ~ev_yes).sum())}; MR value changed by the cut (defined both ways): "
          f"{int((ev_no & ev_yes & (d.MR_no_lon_cut != d.MR)).sum())}")
    print("\n== Records per episode used for MR (QUALITY == 0, |LON_FWT| <= 45, all of P finite)")
    for name, s in [("547", d), ("541", d[d.in541])]:
        print(f"  {name}: median {s.n_P.median():.1f}, min {s.n_P.min()}, max {s.n_P.max()}; 12-h window median {s.n_P_12h.median():.1f}, min {s.n_P_12h.min()}")
    print("\n== Undefined counts and reasons")
    feats = ["MR", "MR_lin", "MR_12h", "MR_nf"] + [f"lcv_{p}" for p in P + OTHER]
    for name, s in [("547", d), ("541", d[d.in541])]:
        print(f"  -- {name} episodes")
        for f in feats:
            rc = f"reason_{f[4:]}" if f.startswith("lcv_") else f"reason_{f}"
            u = s[s[f].isna()]
            why = u[rc].replace("", "other").value_counts().to_dict() if len(u) else {}
            print(f"  {f:13s} defined {int(s[f].notna().sum()):4d}  undefined {len(u):3d}  {why}")
    print(f"  MR_nf: records removed as flare-affected (sum) {int(d.n_flare_removed.sum())}; episodes with >= 1 removed {int((d.n_flare_removed > 0).sum())}")
    q = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    print("\n== MR percentiles (log10 units)")
    for name, s in [("547", d), ("541", d[d.in541])]:
        v = s.MR.dropna()
        print(f"  {name} (n {len(v)}): " + ", ".join(f"p{k} {np.percentile(v, k):.4f}" for k in q))
    print("\n== Secondaries, medians (547)")
    print("  " + ", ".join(f"{f} {d[f].median():.4f}" for f in feats))
    print("\n== MR by year (drift check; 547)")
    Y = d.groupby("year").agg(episodes=("eid", "size"), defined=("MR", "count"), MR_median=("MR", "median"),
                              MR_p25=("MR", lambda v: v.quantile(0.25)), MR_p75=("MR", lambda v: v.quantile(0.75)),
                              records_median=("n_P", "median")).reset_index()
    print(Y.to_string(index=False, float_format=f4))
    print("\n== Fitted 12-h amplitude sqrt(c^2 + d^2) / mean x 100 (%), 24-h fit, per parameter (547, defined fits)")
    for p in P + OTHER:
        v = d[f"amp_{p}"].dropna()
        print(f"  {p:8s} n {len(v)}: median {v.median():.4f}%, p25 {v.quantile(0.25):.4f}%, p75 {v.quantile(0.75):.4f}%")
    a = d[d.in541 & d.MR.notna()].MR
    cuts = [float(a.quantile(1 / 3)), float(a.quantile(2 / 3))]
    json.dump(dict(set="541 analysis set, MR defined", n=int(len(a)), cut_1_3=cuts[0], cut_2_3=cuts[1]), open(f"{OUT}/tertiles.json", "w"), indent=1)
    print(f"\n== E4 tertile cut points (label-blind; 541 set with MR defined, n {len(a)}): 1/3 {cuts[0]:.6f}, 2/3 {cuts[1]:.6f} -> {OUT}/tertiles.json")
    dd = d[d.MR.notna()]
    ex = []
    for k in (10, 50, 90):
        target = np.percentile(dd.MR, k); e = dd.loc[(dd.MR - target).abs().idxmin()]
        ex.append((f"p{k}", e)); print(f"  example p{k}: {e.eid} (MR {e.MR:.4f}; target {target:.4f}; records {e.n_P})")
    plot(ex, sharp, f"{FIG}/mr_examples_p10_p50_p90.png")
    print(f"  figure: {FIG}/mr_examples_p10_p50_p90.png")
    print(f"\nwall {time.time() - t0:.1f} s")


def quad():
    """Amendment A1 (label-blind): MR_quad. Recomputes Step 1, requires every Step 1 column to be identical to dev_mr.csv,
    and writes only eid, MR_quad and its reason to dev_mr_quad.csv (the Step 1 outputs are not overwritten)."""
    t0 = time.time()
    d, _, _ = compute()
    old = pd.read_csv(f"{OUT}/dev_mr.csv", keep_default_na=False, na_values=[""])
    new = pd.read_csv(io.StringIO(d.drop(columns=["MR_quad", "reason_MR_quad"]).to_csv(index=False)), keep_default_na=False, na_values=[""])
    assert list(old.columns) == list(new.columns) and old.equals(new), "Step 1 not reproduced"
    print("CANDIDATE #26 MR — MR_quad (amendment A1, 5cce108), LABEL-BLIND (EXPLORATORY (dev)); no label column loaded")
    print(f"Step 1 reproduced: all {old.shape[1]} columns of {OUT}/dev_mr.csv identical for {len(old)} episodes")
    d[["eid", "MR_quad", "reason_MR_quad"]].to_csv(f"{OUT}/dev_mr_quad.csv", index=False)
    q = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    for name, s in [("547", d), ("541", d[d.in541])]:
        v, u = s.MR_quad.dropna(), s[s.MR_quad.isna()]
        print(f"  {name}: defined {len(v)}, undefined {len(u)} {u.reason_MR_quad.value_counts().to_dict() if len(u) else {}}")
        print(f"    MR_quad percentiles: " + ", ".join(f"p{k} {np.percentile(v, k):.4f}" for k in q))
        both = s[s.MR.notna() & s.MR_quad.notna()]
        print(f"    MR_quad − MR: median {(both.MR_quad - both.MR).median():.4f}, p10 {(both.MR_quad - both.MR).quantile(0.1):.4f}, "
              f"p90 {(both.MR_quad - both.MR).quantile(0.9):.4f}; Spearman rho(MR, MR_quad) {both.MR.corr(both.MR_quad, method='spearman'):.4f} (n {len(both)})")
    print(f"  MR_quad by year (547) medians: " + ", ".join(f"{y} {v:.4f}" for y, v in d.groupby('year').MR_quad.median().items()))
    print(f"\nwall {time.time() - t0:.1f} s")


SEC = ["lcv_TOTUSJH", "lcv_TOTPOT", "lcv_TOTUSJZ", "MR_lin", "lcv_USFLUX", "lcv_R_VALUE", "lcv_MEANSHR", "MR_12h", "MR_nf", "MR_quad"]


def step2():
    """Dev evaluation E1-E5, run once (46207c7 + b2ca7ac + 5cce108). Reads labels. EXPLORATORY (dev)."""
    import hashlib, joblib
    from concurrent.futures import ProcessPoolExecutor
    from scipy.stats import binomtest, spearmanr
    from sklearn.metrics import roc_auc_score
    from phase_f import load_base, prep, tau_keep, wlogloss, op_stats, boot_many, ratio_jobs, pct, A_COLS, W, NB_D, SEED_D, NB_R, SEED_R
    from euv_heldout import fit_folds
    from euv_confirm_tests import log_r
    from euv_f2_replication import twins
    t0 = time.time(); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    C_COLS, TX = A_COLS + ["logR"], json.load(open("data/euv_extra/thresholds.json"))
    feats = ["MR"] + SEC
    # ---- data: the euv_extra dev set, built exactly as `euv_extra.py models`
    dv = load_base()
    mr_ = pd.read_csv(f"{OUT}/dev_mr.csv", float_precision="round_trip")[["eid", "MR"] + [f for f in SEC if f != "MR_quad"]]
    mq = pd.read_csv(f"{OUT}/dev_mr_quad.csv", float_precision="round_trip")[["eid", "MR_quad"]]
    dv = dv.merge(mr_, on="eid", how="left", validate="1:1").merge(mq, on="eid", how="left", validate="1:1")
    c = prep(dv, dv.P & np.isfinite(dv.primary_CV_box) & (dv.primary_CV_box > 0))
    c["log10_CV_box"] = np.log10(c.primary_CV_box)
    c["logR"] = log_r(c, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"))
    dr = pd.read_csv("data/euv_extra/dev_rows.csv", float_precision="round_trip")
    assert (c.eid.to_numpy() == dr.eid.to_numpy()).all() and np.allclose(c.weight, dr.weight, rtol=0, atol=0), "541 set differs from dev_rows.csv"
    assert c.MR.notna().all(), "MR undefined in the analysis set"
    y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
    _, pC = fit_folds(c, C_COLS)
    assert wlogloss(y, pC, w) == TX["C"]["dev_oof_logloss"] and tau_keep(pC, y, w) == TX["C"]["tau"], "C does not reproduce euv_extra"
    print("CANDIDATE #26 MR — STEP 2, DEV EVALUATION, RUN ONCE (EXPLORATORY (dev)); decisions.md 46207c7 + b2ca7ac + 5cce108")
    print(f"checks: analysis set = data/euv_extra/dev_rows.csv (541, same order, same weights); MR defined for all 541; "
          f"model C OOF reproduces the frozen euv_extra C exactly (LL {TX['C']['dev_oof_logloss']:.10f}, tau {TX['C']['tau']:.10f})")
    print(f"analysis set: {len(c)} episodes (true {int(y.sum())}, false {int((y == 0).sum())}), {c.harpnum.nunique()} HARPs")
    for f in feats:
        c[f"lin_{f}"] = 10 ** c[f]                                  # E1 ratio on the linear scale: median(10^x true) / median(10^x false)
    T = {"T_a": twins(c)[0], "T_b": twins(c, by_group=True)[0]}
    jobs, e1, e2 = {}, [], []
    # ---- E1 twins (all features), E2 delta log-loss (all features)
    for f in feats:
        for tn, tw in T.items():
            e, j = ratio_jobs(f"{f} {tn}", c, f"lin_{f}", "ratio", tw); jobs.update(j)
            v = c.set_index("eid")[f]; xt, xf = tw.true_eid.map(v), tw.false_eid.map(v); ok = xt.notna() & xf.notna()
            up, dn = int((xt[ok] > xf[ok]).sum()), int((xt[ok] < xf[ok]).sum())
            e.update(feature=f, twins=tn, true_higher=up, false_higher=dn, ties=int(ok.sum()) - up - dn,
                     sign_p=binomtest(up, up + dn, 0.5).pvalue if up + dn else np.nan); e1.append(e)
        s = prep(c, c[f].notna()); ys, ws, hs = s.true_alarm.to_numpy(), s.weight.to_numpy(), s.harpnum.to_numpy()
        pb = pC if len(s) == len(c) else fit_folds(s, C_COLS)[1]
        ms, pe = fit_folds(s, C_COLS + [f])
        jobs[(f, "dll")] = ("dll", dict(y=ys, w=ws, pA=pb, pE=pe, groups=[np.where(hs == v_)[0] for v_ in np.unique(hs)]), NB_D, SEED_D)
        e2.append(dict(feature=f, n=len(s), true=int(ys.sum()), false=int((ys == 0).sum()), HARPs=len(np.unique(hs)), LL_C=wlogloss(ys, pb, ws),
                       LL_Cx=wlogloss(ys, pe, ws), AUC_C=roc_auc_score(ys, pb, sample_weight=ws), AUC_Cx=roc_auc_score(ys, pe, sample_weight=ws)))
        if f == "MR":
            msMR, pMR = ms, pe
    # ---- E3 matched retention (primary)
    groups = [np.where(h == v_)[0] for v_ in np.unique(h)]
    kept, e3 = [], []
    for keep in (0.88, 0.95):
        tC, tE = tau_keep(pC, y, w, keep), tau_keep(pMR, y, w, keep); kC, kE = pC >= tC, pMR >= tE
        kept += [kC, kE]; e3.append(dict(target=keep, tau_C=tC, tau_CMR=tE, C=op_stats(y, w, kC), CMR=op_stats(y, w, kE),
                                          n=dict(C=(int((kC & (y == 1)).sum()), int((~kC & (y == 0)).sum())), CMR=(int((kE & (y == 1)).sum()), int((~kE & (y == 0)).sum())))))
    jobs["E3"] = ("op", dict(y=y, w=w, kept=kept, groups=groups), NB_R, SEED_R)
    # ---- E4 CV_box twins within MR tertiles (+ CV_box on the full T_a pairs, reference)
    tc = json.load(open(f"{OUT}/tertiles.json")); cut = [tc["cut_1_3"], tc["cut_2_3"]]
    tert = np.where(c.MR <= cut[0], 1, np.where(c.MR <= cut[1], 2, 3))
    e4 = []
    for k in (0, 1, 2, 3):
        ck = c if k == 0 else c[tert == k].reset_index(drop=True)
        twk = twins(ck)[0]
        e, j = ratio_jobs(f"CV_box tertile {k}" if k else "CV_box all T_a", ck, "primary_CV_box", "ratio", twk); jobs.update(j)
        e.update(tertile=k, episodes=len(ck), n_true=int(ck.true_alarm.sum())); e4.append(e)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    f4 = lambda v: f"{v:.4f}"
    # ---- report E1
    print(f"\n== E1 TWINS: ratio = median(10^x true) / median(10^x false) (phase_f.ratio_jobs mode 'ratio' on 10^x); pairs built on the 541 set "
          f"(T_a = twins(c), T_b = twins(c, by_group=True)), kept if both values defined; CI: pairs resampled by true HARP, {NB_R}, seed {SEED_R}; "
          f"sign test two-sided, ties excluded")
    R1 = pd.DataFrame(e1)
    R1["tw_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "tw")]) for m in R1.measure]; R1["all_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "all")]) for m in R1.measure]
    print(f"   T_a pairs {len(T['T_a'])}, T_b pairs {len(T['T_b'])} (of {int(y.sum())} true episodes)")
    print(R1[["feature", "twins", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI", "true_higher", "false_higher", "ties", "sign_p",
              "ratio_all", "all_CI"]].to_string(index=False, float_format=f4))
    # ---- report E2
    R2 = pd.DataFrame(e2); R2["delta"] = R2.LL_C - R2.LL_Cx
    R2["CI"] = ["[%.4f, %.4f]" % pct(B[(f, "dll")]) for f in R2.feature]
    print(f"\n== E2 Δ log-loss = LL(C) − LL(C + x) (+ = x helps); C = {C_COLS}; both fitted on the set with x defined (Stage 4 folds, weights 1/n per HARP "
          f"recomputed on that set, training-fold StandardScaler, stage4 LR); OOF; HARP bootstrap {NB_D}, seed {SEED_D}; AUC weighted")
    print(R2[["feature", "n", "true", "false", "HARPs", "LL_C", "LL_Cx", "delta", "CI", "AUC_C", "AUC_Cx"]].to_string(index=False, float_format=f4))
    # ---- report E3
    op = np.array(B["E3"], float)                                       # resamples x [C88, CMR88, C95, CMR95] x (tk, fr, pr)
    print(f"\n== E3 MATCHED RETENTION (primary MR): dev OOF tau per model (tau_keep); weighted; paired HARP bootstrap {NB_R}, seed {SEED_R}")
    for i, r in enumerate(e3):
        d = op[:, 2 * i + 1, 1] - op[:, 2 * i, 1]
        print(f"  target {r['target']:.2f}: C tau {r['tau_C']:.6f} true kept {r['n']['C'][0]}/{int(y.sum())} ({r['C'][0]:.4f} w), false removed "
              f"{r['n']['C'][1]}/{int((y == 0).sum())} ({r['C'][1]:.4f} w) | C+MR tau {r['tau_CMR']:.6f} true kept {r['n']['CMR'][0]}/{int(y.sum())} "
              f"({r['CMR'][0]:.4f} w), false removed {r['n']['CMR'][1]}/{int((y == 0).sum())} ({r['CMR'][1]:.4f} w)")
        print(f"     false removed (C+MR − C): {(r['CMR'][1] - r['C'][1]) * 100:+.2f} points [{np.nanpercentile(d, 2.5) * 100:+.2f}, {np.nanpercentile(d, 97.5) * 100:+.2f}]")
    # ---- report E4
    print(f"\n== E4 OVERLAP (analysis set, pooled, unweighted Spearman)")
    for v in ["log10_CV_box", "n_C", "n_M", "logR", "score"]:
        r_, p_ = spearmanr(c.MR, c[v]); print(f"  rho(MR, {v}) = {r_:.4f} (p {p_:.2e}, n {len(c)})")
    R4 = pd.DataFrame(e4); R4["tw_CI"] = ["[%.4f, %.4f]" % pct(B[(m, "tw")]) for m in R4.measure]
    print(f"  CV_box twins within MR tertiles (cut points {cut[0]:.6f}, {cut[1]:.6f} from Step 1; twins rebuilt inside each tertile, T_a matching; "
          f"ratio_jobs mode 'ratio'; CI pairs by true HARP {NB_R}, seed {SEED_R}); DESCRIPTIVE, no reading. Tertile 0 = all 541 (reference)")
    print(R4[["tertile", "episodes", "n_true", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI"]].to_string(index=False, float_format=f4))
    # ---- E5
    print("\n== E5 UNDEFINED COUNTS BY LABEL (true / false)")
    for name, s in [("547", dv), ("541", c)]:
        print(f"  {name} (true {int(s.true_alarm.sum())}, false {int((s.true_alarm == 0).sum())}): " +
              "; ".join(f"{f} {int((s[f].isna() & (s.true_alarm == 1)).sum())}/{int((s[f].isna() & (s.true_alarm == 0)).sum())}" for f in feats))
    # ---- mechanical reading
    ra = R1[(R1.feature == "MR") & (R1.twins == "T_a")].iloc[0]; dMR = float(R2.loc[R2.feature == "MR", "delta"].iloc[0])
    q = ra.ratio_twins > 1 and dMR > 0
    reading = "QUALIFIES FOR THE HELD-OUT TEST (dev only; not confirmation)" if q else "NOT ELIGIBLE"
    print(f"\nQUALIFICATION RULE (pre-stated, mechanical): E1 T_a ratio {ra.ratio_twins:.4f} > 1 is {ra.ratio_twins > 1}; E2 Δ {dMR:+.4f} > 0 is {dMR > 0} "
          f"-> \"{reading}\"")
    R1.to_csv(f"{OUT}/eval_E1.csv", index=False); R2.to_csv(f"{OUT}/eval_E2.csv", index=False); R4.to_csv(f"{OUT}/eval_E4.csv", index=False)
    if q:                                                               # freeze C+MR before any held-out computation
        md = f"{OUT}/models"; os.makedirs(md, exist_ok=False); hashes = {}
        for k, (sc, mdl, cl) in enumerate(msMR):
            fn = f"{md}/C_MR_fold{k}.joblib"; joblib.dump({"scaler": sc, "model": mdl, "cols": cl}, fn); hashes[fn] = H(fn)
        tau = tau_keep(pMR, y, w, 0.88); tk, fr, _ = op_stats(y, w, pMR >= tau)
        fn = f"{OUT}/thresholds.json"; assert not os.path.exists(fn)
        json.dump(dict(C_MR=dict(cols=C_COLS + ["MR"], tau=tau, dev_oof_logloss=wlogloss(y, pMR, w), dev_oof_true_kept_w=tk, dev_oof_false_removed_w=fr)),
                  open(fn, "w"), indent=1); hashes[fn] = H(fn)
        c[["eid", "harpnum", "t", "fold", "weight", "MR"]].to_csv(f"{OUT}/dev_rows_C_MR.csv", index=False); hashes[f"{OUT}/dev_rows_C_MR.csv"] = H(f"{OUT}/dev_rows_C_MR.csv")
        json.dump(hashes, open(f"{OUT}/model_hashes.json", "x"), indent=1)
        print(f"\nFROZEN (before any held-out computation): C+MR fold models, tau (dev OOF, 88%) {tau:.10f} (true kept {tk:.4f} w, false removed {fr:.4f} w)")
        for fn, hh in hashes.items():
            print(f"  sha256 {hh}  {fn}")
    print(f"\nwall {time.time() - t0:.1f} s, workers {W}")


def selftest():
    """Synthetic series: the fit recovers a known 12-h amplitude and the residual SD of added noise."""
    rng = np.random.RandomState(0); x = -np.arange(22, dtype=float)[::-1]
    v = 100 + 0.5 * x + 3 * np.sin(2 * np.pi * x / 12 + 0.7) + rng.normal(0, 0.01, len(x))
    cv, amp, why = fit(x, v)
    assert why == "" and abs(amp - 3 / np.mean(v) * 100) < 0.01 and cv < 2e-4, (cv, amp)
    assert fit(x, -v)[2] == "mean <= 0" and np.isnan(fit(x, np.full(len(x), 5.0))[0])
    assert mr(x[:5], np.ones((5, 3)), MIN24)[3] == f"< {MIN24} records"
    vq = v + 0.05 * x ** 2
    assert fit(x, vq, quad=True)[0] < 2e-4 < fit(x, vq)[0] and abs(fit(x, vq, quad=True)[1] - 3 / np.mean(vq) * 100) < 0.01
    print("selftest OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    elif sys.argv[1:] == ["quad"]:
        quad()
    elif sys.argv[1:] == ["step2"]:
        step2()
    elif sys.argv[1:] == ["step1"]:
        step1()
    else:
        sys.exit(__doc__)
