"""PROSPECTIVE PRE-REGISTRATION (decisions.md 2026-09-27, 2f62f88; clarification bb8a137): bursty fraction BF and late-window
restlessness CV6. Step 1 = dev 2010-2019, LABEL-BLIND compute from files on disk (data/euv_full); no downloads (the aiapy pointing
table is a JSOC keyword query, allowed). Frame loop = euv_spatial.spatial_episode / euv_masks.mask_episode (same files, SAT_DN,
update_pointing, register_cutout, hmi_to_frame): per-pixel stack on the alarm-time HMI grid, the same pixels and weighting as CV_box.
Usage: python prospective_measures.py selftest | step1_run | step1_report"""
import glob, hashlib, json, os, sys, time, warnings
import numpy as np, pandas as pd

R, OUT = "data/euv_full", "data/prospective"
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
warnings.filterwarnings("ignore")


def bf(V, fill):
    """BF from a frames x box-pixels stack (NaN = not finite). -> (BF, kept pixel fraction, undefined rule or '')."""
    if not fill >= 0.80:
        return np.nan, np.nan, "fill"
    keep = np.isfinite(V).sum(0) >= 0.80 * len(V)                  # c) finite in >= 80% of valid frames
    kf = float(keep.mean())
    if kf < 0.80:
        return np.nan, kf, "pixels"
    X = V[:, keep]
    floor, mean = np.nanpercentile(X, 5, axis=0), np.nanmean(X, axis=0)   # d) numpy default (linear) over finite values
    return float(1 - floor.sum() / mean.sum()), kf, ""


def cv6(s, t):
    """CV_box (euv_dctrl.cv) on valid_primary frames with T_REC in (t-6h, t]; fill over the 30 slots t-5h48m..t (valid frame within
    +-6 min, the existing fill rule). -> (CV6, fill6)."""
    from euv_dctrl import cv
    v = s[s.valid_primary & (s.t_rec > t - pd.Timedelta("6h")) & (s.t_rec <= t)]; tv = v.t_obs.to_numpy()
    slots = pd.date_range(t - pd.Timedelta("6h") + pd.Timedelta("12min"), t, freq="12min").to_numpy(); assert len(slots) == 30
    fill = float(np.mean([len(tv) > 0 and np.abs(tv - sl).min() <= np.timedelta64(6, "m") for sl in slots]))
    return (cv(tv, v.box.to_numpy()) if fill >= 0.80 else np.nan), fill


def stack(ep):
    """Per-pixel stack (frame loop copied from euv_spatial.spatial_episode) on the alarm-time HMI grid.
    -> (series, V frames x pixels [DN/s], IDX flat AIA index per frame/pixel, exptime per frame, max box-mean |diff|, CDELT1_HMI, (ny, nx))."""
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
    h, t = ep["harpnum"], pd.Timestamp(ep["t"])
    mp, bp = hmi_files(f"{R}/hmi/{h}", ep["t_rec_tai"])
    mag = sunpy.map.Map(mp); bitmap = fits.open(bp)[-1].data
    S, _, _ = samples(mag.data, bitmap)
    ny, nx = mag.data.shape
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
        except (IndexError, TypeError):                            # as compute_episode (header pointing kept)
            pass
        r = register_cutout(sunpy.map.Map(raw / exp, m.meta))
        idx = hmi_to_frame(mag, r)
        a, b = frame_means(r.data, idx, {"box": S["box"]})["box"], row["box"]
        box_diff = max(box_diff, 0.0 if (np.isnan(a) and np.isnan(b)) else abs(a - b) if np.isfinite(a - b) else np.inf)
        ok = idx >= 0; V[i, ok] = r.data.ravel()[idx[ok]]; IDX[i] = idx
    e = np.array([row["exptime"] for row in rows], float)
    return s, V, IDX, e, box_diff, float(mag.meta["cdelt1"]), (ny, nx)


def episode(ep):
    """Step 1: per-pixel stack, box-mean check, BF, CV6, full-window CV_box check."""
    from euv_dctrl import cv
    t0 = time.time(); t = pd.Timestamp(ep["t"])
    s, V, _, _, box_diff, _, (ny, nx) = stack(ep)
    v = s[s.valid_primary]
    cvb = cv(v.t_obs.to_numpy(), v.box.to_numpy())
    B, kf, why = bf(V, ep["primary_fill"]); c6, f6 = cv6(s, t)
    res = dict(eid=ep["eid"], frames=len(V), npix_box=ny * nx, box_diff=box_diff, cv_box_repro=cvb,
               cv_box_diff=abs(cvb - ep["primary_CV_box"]), BF=B, BF_kept_px_frac=kf, BF_undefined=why, CV6=c6, fill6=f6,
               CV6_undefined="" if np.isfinite(c6) else "fill6", elapsed_s=round(time.time() - t0, 1))
    json.dump(res, open(f"{OUT}/dev/{ep['eid']}.json", "w"))
    return res


def dev_eps():
    """LABEL-BLIND episode list: data/stage3/cohort_dev.csv read with usecols (true_alarm / delayed never read)."""
    c = pd.read_csv("data/stage3/cohort_dev.csv", usecols=["harpnum", "t", "noaa_ars", "score", "n_C"], parse_dates=["t"])
    assert len(c) == 547
    lab = pd.read_csv("data/labelled_20100501_20250101.csv", usecols=["harpnum", "t_rec_utc", "t_rec_tai"], parse_dates=["t_rec_utc"], low_memory=False)
    c = c.merge(lab, left_on=["harpnum", "t"], right_on=["harpnum", "t_rec_utc"], how="left", validate="one_to_one").drop(columns="t_rec_utc")
    assert c.t_rec_tai.notna().all()
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    num = ["primary_fill", "primary_CV_box"]
    r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{R}/results/*.json")])
    r = r[r.eid.notna()][["eid"] + num]; r[num] = r[num].apply(pd.to_numeric, errors="coerce")
    c = c.merge(r, on="eid", how="left", validate="one_to_one")
    c["has_series"] = [os.path.exists(f"{R}/series/{e}.csv") for e in c.eid]
    return c


def selftest():
    rng = np.random.RandomState(0)
    const = np.full((120, 50), 7.0)
    burst = const.copy(); burst[rng.rand(120, 50) < 0.1] += 20.0
    b0, b1 = bf(const, 1.0)[0], bf(burst, 1.0)[0]
    assert abs(b0) < 1e-15, b0
    assert b1 > 0, b1
    holes = burst.copy(); holes[:, :15] = np.nan                   # 70% of pixels kept -> undefined; fill 0.79 -> undefined
    assert bf(holes, 1.0)[2] == "pixels" and bf(burst, 0.79)[2] == "fill"
    return b0, b1


# ================================================================ BF label-blind noise diagnostic (21e9e89; implementation 721ffa9)
G_DN, READ_DN = 1.975, 1.14                                        # AIA 94 A, aiapy V3 table (as 5af931b)


def sim_pixel(V, e, rng):
    """No real variability: each stack pixel = its own mean (DN/s) + Poisson photons + Gaussian read noise per frame; same NaN pattern."""
    mu = np.clip(np.nan_to_num(np.nanmean(V, 0)), 0, None); X = np.full(V.shape, np.nan)
    for f in range(len(V)):
        lam = mu * e[f] / G_DN; x = (G_DN * rng.poisson(lam) + READ_DN * rng.standard_normal(lam.size)) / e[f]
        fin = np.isfinite(V[f]); X[f, fin] = x[fin]
    return X


def sim_aia(V, IDX, e, rng):
    """Option (a) noise: one draw per AIA pixel per frame, shared by the stack pixels mapping to it (lambda from their mean mu_p)."""
    mu = np.nan_to_num(np.nanmean(V, 0)); X = np.full(V.shape, np.nan)
    for f in range(len(V)):
        fin = np.isfinite(V[f]); _, inv = np.unique(IDX[f, fin], return_inverse=True)
        lam = np.clip(np.bincount(inv, weights=mu[fin]) / np.bincount(inv), 0, None) * e[f] / G_DN
        X[f, fin] = ((G_DN * rng.poisson(lam) + READ_DN * rng.standard_normal(lam.size)) / e[f])[inv]
    return X


def blocks(V, shape, k):
    """Option (a): k x k blocks of the HMI grid (partial edge blocks kept); block value = nanmean of its pixels."""
    (ny, nx), F = shape, len(V)
    A = np.pad(V.reshape(F, ny, nx), ((0, 0), (0, -ny % k), (0, -nx % k)), constant_values=np.nan)
    return np.nanmean(A.reshape(F, A.shape[1] // k, k, A.shape[2] // k, k), axis=(2, 4)).reshape(F, -1)


def bf_family(X, keep, e, sel_mean):
    """BF, option (b) and option (c, C = 100 / 300 DN per exposure, pixels selected on sel_mean) over the kept pixels of X."""
    Y = X[:, keep]; floor, mean = np.nanpercentile(Y, 5, axis=0), np.nanmean(Y, axis=0)
    fin = np.isfinite(Y).astype(float); n = fin.sum(0)
    sig = np.sqrt((G_DN * np.clip(mean, 0, None) * (fin.T @ (1 / e)) + READ_DN ** 2 * (fin.T @ (1 / e ** 2))) / n)
    out = {"BF": float(1 - floor.sum() / mean.sum()), "BF_b": float(1 - (floor + 1.645 * sig).sum() / mean.sum())}
    for C in (100, 300):
        m = sel_mean * np.median(e) >= C
        out[f"BF_c{C}"] = float(1 - floor[m].sum() / mean[m].sum()) if m.any() else np.nan
        out[f"frac_c{C}"] = float(m.mean())
    return out


def noise_episode(ep):
    t0 = time.time()
    s, V, IDX, e, box_diff, cdelt, shape = stack(ep)
    B, kf, why = bf(V, ep["primary_fill"])
    keep = np.isfinite(V).sum(0) >= 0.80 * len(V); sel = np.nanmean(V[:, keep], axis=0)
    real = bf_family(V, keep, e, sel)
    Xn = sim_pixel(V, e, np.random.RandomState(0)); Bn = bf(Xn, ep["primary_fill"])[0]; noise = bf_family(Xn, keep, e, sel); del Xn
    k = int(round(2.4 / cdelt)); Ba, kfa, whya = bf(blocks(V, shape, k), ep["primary_fill"])
    Xa = sim_aia(V, IDX, e, np.random.RandomState(0)); Ban = bf(blocks(Xa, shape, k), ep["primary_fill"])[0]; del Xa
    res = dict(eid=ep["eid"], box_diff=box_diff, BF_repro=B, BF_family_equal=real["BF"] == B, box_mean=float(s[s.valid_primary].box.mean()),
               BF_noise=Bn, k=k, BF_a=Ba, BF_a_kept_frac=kfa, BF_a_undefined=whya, BF_a_noise=Ban,
               **{f"{kk}_real": v for kk, v in real.items() if kk != "BF"}, **{f"{kk}_noise": v for kk, v in noise.items() if kk.startswith("BF_")},
               elapsed_s=round(time.time() - t0, 1))
    json.dump(res, open(f"{OUT}/noise/{ep['eid']}.json", "w"))
    return res


if __name__ == "__main__" and sys.argv[1:] == ["selftest"]:
    print("BF self-test (synthetic 120-frame x 50-pixel cubes): constant cube -> BF %.3g; cube with added bursts -> BF %.4f; "
          "undefined rules (pixels kept < 80%%, fill < 80%%) trigger" % selftest())

if __name__ == "__main__" and sys.argv[1:] == ["step1_run"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    selftest(); os.makedirs(f"{OUT}/dev", exist_ok=True); os.makedirs(f"{OUT}/logs", exist_ok=True)
    c = dev_eps(); w = os.cpu_count() - 1; log = f"{OUT}/logs/step1_run.log"; t0 = time.time()
    eps = [dict(eid=e.eid, harpnum=int(e.harpnum), t=str(e.t), t_rec_tai=e.t_rec_tai, primary_fill=float(e.primary_fill),
                primary_CV_box=float(e.primary_CV_box)) for e in c[c.has_series].itertuples() if not os.path.exists(f"{OUT}/dev/{e.eid}.json")]
    open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} start: {len(eps)} episodes to compute, workers {w}\n")
    with ProcessPoolExecutor(w) as pool:
        futs = [pool.submit(episode, e) for e in eps]
        for i, f in enumerate(as_completed(futs), 1):
            f.result()
            if i % 25 == 0 or i == len(futs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(futs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    open(log, "a").write(f"done: {len(eps)} episodes in {(time.time() - t0) / 3600:.2f} h, workers {w}\n")

if __name__ == "__main__" and sys.argv[1:] == ["step1_report"]:
    from scipy.stats import spearmanr
    c = dev_eps(); J = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/dev/*.json")])
    assert len(J) == int(c.has_series.sum()) == 546, (len(J), int(c.has_series.sum()))
    # ---- checks first: STOP on any failure (no value is reported)
    fb, fc = J[~(J.box_diff < 1e-9)], J[~(J.cv_box_diff < 1e-9)]
    if len(fb) or len(fc):
        print(f"STOP: per-frame box means not reproduced in {len(fb)} episodes {fb.eid.tolist()}; CV_box not reproduced in {len(fc)} {fc.eid.tolist()}")
        sys.exit(1)
    b0, b1 = selftest()
    d = c.merge(J, on="eid", how="left")
    d["BF_undefined"] = np.where(~d.has_series, "no series", d.BF_undefined.fillna(""))
    d["CV6_undefined"] = np.where(~d.has_series, "no series", d.CV6_undefined.fillna(""))
    wall = pd.to_numeric(open(f"{OUT}/logs/step1_run.log").read().split("done: ")[-1].split(" in ")[1].split(" h")[0])
    print("PROSPECTIVE PRE-REGISTRATION — STEP 1: DEV 2010-2019, LABEL-BLIND (true_alarm and delayed never read). 2f62f88 + bb8a137.")
    print(f"checks: BF self-test: constant cube -> BF {b0:.3g}; cube with added bursts -> BF {b1:.4f}; undefined rules trigger. "
          f"Per-episode (all {len(J)} with stored series): per-frame box means of the per-pixel stack reproduce the stored series "
          f"(max |diff| {J.box_diff.max():.1e}); euv_dctrl.cv on the full 24-h valid_primary frames reproduces stored CV_box "
          f"(max |diff| {J.cv_box_diff.max():.1e})")
    print(f"\nepisodes: {len(d)} (stored series {int(d.has_series.sum())}; without stored series {int((~d.has_series).sum())}: "
          f"{d.loc[~d.has_series, 'eid'].tolist()})")
    for m in ["BF", "CV6"]:
        u = d[f"{m}_undefined"]; x = d[m].dropna()
        print(f"  {m}: defined {int(d[m].notna().sum())}, undefined {int(d[m].isna().sum())} by rule {u[u != ''].value_counts().to_dict()}; "
              f"median {x.median():.4f}, IQR [{x.quantile(.25):.4f}, {x.quantile(.75):.4f}]")
    print(f"  BF kept-pixel fraction (episodes with fill >= 80%): median {d.BF_kept_px_frac.median():.4f}, min {d.BF_kept_px_frac.min():.4f}")
    print("\nSpearman rho (label-free; pairwise complete)")
    for m in ["BF", "CV6"]:
        for v in ["primary_CV_box", "n_C", "score"]:
            k = d[m].notna() & d[v].notna(); r, p = spearmanr(d.loc[k, m], d.loc[k, v])
            print(f"  {m} vs {v:14s}: rho {r:+.4f} (p {p:.2e}, n {int(k.sum())})")
    k = d.BF.notna() & d.CV6.notna(); r, p = spearmanr(d.loc[k, "BF"], d.loc[k, "CV6"])
    print(f"  BF vs CV6           : rho {r:+.4f} (p {p:.2e}, n {int(k.sum())})")
    d[["eid", "harpnum", "t", "has_series", "primary_fill", "primary_CV_box", "frames", "npix_box", "BF", "BF_kept_px_frac", "BF_undefined",
       "CV6", "fill6", "CV6_undefined", "box_diff", "cv_box_diff"]].to_csv(f"{OUT}/dev_values.csv", index=False)
    print(f"\nsaved {OUT}/dev_values.csv sha256 {H(f'{OUT}/dev_values.csv')}")
    print(f"wall (compute) {wall:.2f} h, workers {os.cpu_count() - 1}")

if __name__ == "__main__" and sys.argv[1:] == ["noise_run"]:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    os.makedirs(f"{OUT}/noise", exist_ok=True)
    d = pd.read_csv(f"{OUT}/dev_values.csv"); c = dev_eps().merge(d[["eid", "BF"]], on="eid", how="left")
    c = c[c.BF.notna()]; assert len(c) == 541
    w = 5; log = f"{OUT}/logs/noise_run.log"; t0 = time.time()                   # 5 workers: ~2.9 GB per median episode, largest ~3x
    eps = [dict(eid=e.eid, harpnum=int(e.harpnum), t=str(e.t), t_rec_tai=e.t_rec_tai, primary_fill=float(e.primary_fill))
           for e in c.itertuples() if not os.path.exists(f"{OUT}/noise/{e.eid}.json")]
    open(log, "a").write(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} start: {len(eps)} episodes to compute, workers {w}\n")
    with ProcessPoolExecutor(w) as pool:
        futs = [pool.submit(noise_episode, e) for e in eps]
        for i, f in enumerate(as_completed(futs), 1):
            f.result()
            if i % 25 == 0 or i == len(futs):
                open(log, "a").write(f"{pd.Timestamp.now():%H:%M} {i}/{len(futs)}, elapsed {(time.time() - t0) / 3600:.2f} h\n")
    open(log, "a").write(f"done: {len(eps)} episodes in {(time.time() - t0) / 3600:.2f} h, workers {w}\n")

if __name__ == "__main__" and sys.argv[1:] == ["noise_report"]:
    from scipy.stats import spearmanr
    d = pd.read_csv(f"{OUT}/dev_values.csv", float_precision="round_trip")
    J = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{OUT}/noise/*.json")]).merge(d[["eid", "BF", "primary_CV_box"]], on="eid")
    assert len(J) == 541
    bad = J[~(J.box_diff < 1e-9) | ~((J.BF_repro - J.BF).abs() < 1e-12) | ~J.BF_family_equal]
    if len(bad):
        print(f"STOP: stack or BF not reproduced in {len(bad)} episodes {bad.eid.tolist()}"); sys.exit(1)
    q = lambda x: f"median {x.median():.4f}, IQR [{x.quantile(.25):.4f}, {x.quantile(.75):.4f}]"
    rho = lambda a, b: "rho %+.4f (p %.2e, n %d)" % (*spearmanr(J[a], J[b], nan_policy="omit"), int((J[a].notna() & J[b].notna()).sum()))
    J["ratio"] = J.BF_noise / J.BF
    print("BF LABEL-BLIND NOISE DIAGNOSTIC (21e9e89; implementation 721ffa9). Dev 2010-2019, 541 episodes with BF defined; no labels read.")
    print(f"checks: per-frame box means of the rebuilt stack reproduce the stored series (max |diff| {J.box_diff.max():.1e}); recomputed BF equals "
          f"dev_values.csv (max |diff| {(J.BF_repro - J.BF).abs().max():.1e}) for all 541")
    print(f"noise model: g {G_DN} DN/photon, read noise {READ_DN} DN, per-frame EXPTIME, Poisson photons + Gaussian read noise, same NaN pattern, "
          f"RandomState(0) per episode\n")
    print(f"BF (data):   {q(J.BF)}")
    print(f"BF_noise:    {q(J.BF_noise)}")
    print(f"BF_noise / BF: median {J.ratio.median():.4f}, IQR [{J.ratio.quantile(.25):.4f}, {J.ratio.quantile(.75):.4f}]")
    print(f"Spearman BF vs BF_noise: {rho('BF', 'BF_noise')}")
    print(f"Spearman BF vs box-mean brightness (mean of the stored box series, DN/s): {rho('BF', 'box_mean')}")
    rule = "BF IS NOISE-DOMINATED" if J.ratio.median() > 0.5 else "BF NOISE CONTRIBUTION ACCEPTABLE"
    print(f"\nMECHANICAL RULE (median BF_noise / BF > 0.5): median {J.ratio.median():.4f} -> \"{rule}\"")
    if rule == "BF IS NOISE-DOMINATED":
        print("\nOPTIONS for a noise-robust BF (label-blind; NOT chosen). Each: value on the data, value with no real variability (noise only), "
              "median per-episode ratio noise / data, episodes defined, Spearman with CV_box on the data")
        J["BF_a_ratio"] = J.BF_a_noise / J.BF_a
        print(f"  (a) macropixels k x k HMI pixels (k {sorted(J.k.unique().tolist())}, ~4x4 AIA px): defined {int(J.BF_a.notna().sum())} "
              f"(undefined {J.BF_a_undefined[J.BF_a_undefined != ''].value_counts().to_dict()})")
        print(f"      data {q(J.BF_a)}; noise {q(J.BF_a_noise)}; ratio median {J.BF_a_ratio.median():.4f}; vs CV_box {rho('BF_a', 'primary_CV_box')}")
        J["BF_b_ratio"] = J.BF_b_noise / J.BF_b_real
        print(f"  (b) floor_i + 1.645 sigma_noise,i (no cap): defined {int(J.BF_b_real.notna().sum())}")
        print(f"      data {q(J.BF_b_real)}; noise {q(J.BF_b_noise)}; ratio median {J.BF_b_ratio.median():.4f}; data < 0 in {int((J.BF_b_real < 0).sum())}; "
              f"vs CV_box {rho('BF_b_real', 'primary_CV_box')}")
        for C in (100, 300):
            J[f"c{C}_ratio"] = J[f"BF_c{C}_noise"] / J[f"BF_c{C}_real"]
            print(f"  (c) pixels with mean x median EXPTIME >= {C} DN: kept-pixel fraction passing {q(J[f'frac_c{C}_real'])}; episodes with >= 1 pixel "
                  f"{int(J[f'BF_c{C}_real'].notna().sum())}")
            print(f"      data {q(J[f'BF_c{C}_real'])}; noise {q(J[f'BF_c{C}_noise'])}; ratio median {J[f'c{C}_ratio'].median():.4f}; "
                  f"vs CV_box {rho(f'BF_c{C}_real', 'primary_CV_box')}")
    J.to_csv(f"{OUT}/noise_values.csv", index=False)
    print(f"\nsaved {OUT}/noise_values.csv sha256 {H(f'{OUT}/noise_values.csv')}")
    t_start = pd.Timestamp(open(f"{OUT}/logs/noise_run.log").read().split(" start:")[0])
    t_end = pd.Timestamp.fromtimestamp(max(os.path.getmtime(p) for p in glob.glob(f"{OUT}/noise/*.json")))       # local time, as the log
    print(f"wall (compute, pool): {t_start:%H:%M} to {t_end:%H:%M} local = {(t_end - t_start).total_seconds() / 3600:.2f} h, 5 workers; sum of per-episode "
          f"times {J.elapsed_s.sum() / 3600:.2f} h. 1 episode (71_20100702T2059) failed in the pool on a transient JSOC pointing-table query timeout "
          f"(OSError, Errno 60) and was recomputed in a separate process with the same code")

if __name__ == "__main__" and sys.argv[1:] == ["step2"]:
    # DEV EXPLORATION (EXPLORATORY; 2f62f88 Step 2; BF = option (a), eb3e7d5; implementation d2ed360)
    from concurrent.futures import ProcessPoolExecutor
    from sklearn.metrics import roc_auc_score
    from phase_f import load_base, prep, boot_many, ratio_jobs, pct, wlogloss, A_COLS, W
    from euv_heldout import fit_folds
    from euv_confirm_tests import log_r
    t00 = time.time(); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    dv = load_base()
    dv["logR"] = log_r(dv, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"))
    nv = pd.read_csv(f"{OUT}/noise_values.csv", float_precision="round_trip")[["eid", "BF_a"]]
    pv = pd.read_csv(f"{OUT}/dev_values.csv", float_precision="round_trip")[["eid", "CV6"]]
    dv = dv.merge(nv, on="eid", how="left").merge(pv, on="eid", how="left")
    dv["CV_box"] = np.where(dv.P & (dv.primary_CV_box > 0), dv.primary_CV_box, np.nan)
    # ---- checks (STOP on failure)
    llC = wlogloss(dv.true_alarm.to_numpy(), fit_folds(dv, A_COLS + ["logR"])[1], dv.weight.to_numpy())
    assert round(llC, 4) == 0.3356, f"LL(C) {llC} does not reproduce Step B dev 0.3356"
    TX = json.load(open("data/euv_extra/thresholds.json"))
    MEAS = [("BF(a)", "BF_a"), ("CV6", "CV6"), ("CV_box", "CV_box")]
    tw = pd.read_csv("data/euv_full/step6/twins_PRIMARY.csv"); assert len(tw) == 81
    rows, jobs, twr = [], {}, []
    for name, col in MEAS:
        c = prep(dv, dv[col].notna() & (dv[col] > 0)); c["lx"] = np.log10(c[col])
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy(); groups = [np.where(h == v)[0] for v in np.unique(h)]
        P = {m: fit_folds(c, cols)[1] for m, cols in [("A", A_COLS), ("A+x", A_COLS + ["lx"]), ("C", A_COLS + ["logR"]), ("C+x", A_COLS + ["logR", "lx"])]}
        if name == "CV_box":
            for m, k in [("A", "A"), ("A+x", "A_CV"), ("C", "C"), ("C+x", "C_CV")]:
                assert wlogloss(y, P[m], w) == TX[k]["dev_oof_logloss"], f"{m} does not reproduce euv_extra {k}"
        for base in ["A", "C"]:
            key = f"{name} {base}"
            jobs[key] = ("dll", dict(y=y, w=w, pA=P[base], pE=P[base + "+x"], groups=groups), 10000, 20260921)
            rows.append(dict(measure=name, comparison=f"{base} vs {base} + log10({name})", n=len(c), true=int(y.sum()), false=int((y == 0).sum()),
                             HARPs=len(groups), LL_base=wlogloss(y, P[base], w), LL_plus=wlogloss(y, P[base + "+x"], w),
                             AUC_base=roc_auc_score(y, P[base], sample_weight=w), AUC_plus=roc_auc_score(y, P[base + "+x"], sample_weight=w)))
        e, j = ratio_jobs(name, dv.assign(**{col: dv[col].where(dv[col] > 0)}), col, "ratio", tw); jobs[(name, "tw")] = j[(name, "tw")]; twr.append(e)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    T = pd.DataFrame(rows); T["delta"] = T.LL_base - T.LL_plus
    T["CI_lo"], T["CI_hi"] = zip(*[pct(B[f"{r.measure} {r.comparison.split()[0]}"]) for r in T.itertuples()])
    R = pd.DataFrame(twr); R["tw_CI_lo"], R["tw_CI_hi"] = zip(*[pct(B[(m, "tw")]) for m in R.measure])
    f2 = pd.read_csv("data/phase_f/F2_ratios.csv", float_precision="round_trip").set_index("measure").loc["CV_box"]
    cb = R.set_index("measure").loc["CV_box"]
    assert cb.pairs == f2.pairs and cb.ratio_twins == f2.ratio_twins and "[%.4f, %.4f]" % (cb.tw_CI_lo, cb.tw_CI_hi) == f2.twins_CI, "CV_box twins not reproduced"
    print("PROSPECTIVE PRE-REGISTRATION — STEP 2: DEV EXPLORATION (EXPLORATORY; dev 2010-2019; internal 5-fold CV). 2f62f88; BF = option (a) eb3e7d5; "
          "implementation d2ed360")
    print(f"checks: LL(C) on dev 547 = {llC:.4f} (Step B 0.3356); CV_box twins ratio and CI reproduce data/phase_f/F2_ratios.csv; on the CV_box set, "
          f"A / A + log10 CV_box / C / C + log10 CV_box reproduce data/euv_extra/thresholds.json dev log-loss exactly")
    print("\nTWINS RATIO on the step 6 gate-score pairs (data/euv_full/step6/twins_PRIMARY.csv, 81 pairs; both values defined): median true / median "
          "false; CI pairs resampled by true HARP, 2,000, seed 0")
    print(R[["measure", "pairs", "twin_med_true", "twin_med_false", "ratio_twins", "tw_CI_lo", "tw_CI_hi"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\nDELTA LOG-LOSS = LL(base) - LL(base + log10 x), + = x helps; Step 6 settings (Stage 4 folds, 1/n per HARP within the set, training-fold "
          "StandardScaler, L2 logistic C = 1); C = A + log(1+R) (Step B); HARP bootstrap 10,000, seed 20260921; weighted AUC")
    print(T[["measure", "comparison", "n", "true", "false", "HARPs", "LL_base", "LL_plus", "delta", "CI_lo", "CI_hi", "AUC_base", "AUC_plus"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\nwall {time.time() - t00:.1f} s, workers {W}")
