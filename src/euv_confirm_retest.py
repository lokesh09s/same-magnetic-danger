"""2025-26 RE-TEST: CV_box as a filter on top of model C (decisions.md 2026-09-27, 25fcd66). Frozen euv_extra models only.
checks: label-blind Step 1 (a-d). run: only after the user's "run the 2025-26 filter re-test once".
Usage: python euv_confirm_retest.py checks | run"""
import glob, hashlib, json, sys, time, warnings
import numpy as np, pandas as pd, joblib
from euv_confirm_tests import log_r

T, X = "data/euv_confirm", "data/euv_extra"
NAMES = ["A", "A_CV", "C", "C_CV"]
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
warnings.filterwarnings("ignore")
LABEL_FREE = ["harpnum", "t", "score", "n_C", "n_M", "n_X", "noaa_ars"]


def load_models():
    hs = json.load(open(f"{X}/model_hashes.json"))
    bad = [f for f, v in hs.items() if H(f) != v]
    assert not bad, f"hash mismatch: {bad}"
    assert H(f"{X}/thresholds.json") == "7a34507c20d37756906e4ad6dfaf9069c48ad74bff5b42521a4dd4f1c573c6ad"
    TH = json.load(open(f"{X}/thresholds.json"))
    M = {m: [(d["scaler"], d["model"], d["cols"]) for d in (joblib.load(f"{X}/models/{m}_fold{k}.joblib") for k in range(5))] for m in NAMES}
    return hs, TH, M


def evaluable(cols):
    c = pd.read_csv(f"{T}/cohort_le2.csv", usecols=cols, parse_dates=["t"])
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
    r[["primary_fill", "primary_CV_box"]] = r[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce")
    c = c.merge(r, on="eid", how="left")
    c["logR"] = log_r(c, pd.Timestamp("2024-12-29"), pd.Timestamp("2026-08-18 23:59"))      # TEST 2: all 387 le2 episodes, same window
    t1 = c[(c.primary_fill >= 0.80) & c.primary_CV_box.notna()]                                 # TEST 1 evaluable rule (ae1b174)
    e = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True)
    e["log10_CV_box"] = np.log10(e.primary_CV_box)
    e["weight"] = 1 / e.groupby("harpnum").harpnum.transform("size")
    return c, t1, e


pred = lambda ms, c: np.mean([m.predict_proba(sc.transform(c[cols]))[:, 1] for sc, m, cols in ms], axis=0)

if __name__ == "__main__" and sys.argv[1:] == ["checks"]:
    hs, TH, M = load_models()
    c, t1, e = evaluable(LABEL_FREE)                             # no true_alarm / delayed column is read
    print("STEP 1 — LABEL-BLIND CHECKS (true_alarm and delayed not read; no outcome printed)")
    miss = sorted(set(t1.eid) ^ set(e.eid))
    print(f"a) evaluable set: {len(e)} episodes, {e.harpnum.nunique()} HARPs; TEST 1 evaluable set: {len(t1)} episodes, {t1.harpnum.nunique()} HARPs; "
          f"mismatch: {len(miss)} {miss}" + (" (reason: CV_box <= 0 or non-finite)" if miss else ""))
    need = sorted({col for m in NAMES for _, _, cols in M[m] for col in cols})
    na = {col: int(e[col].isna().sum()) if col in e else "MISSING COLUMN" for col in need}
    c2 = c.copy(); c2["logR2"] = log_r(c2, pd.Timestamp("2024-12-29"), pd.Timestamp("2026-08-18 23:59"))
    cons = bool(((c.logR < np.log1p(48)) == ((c.n_C + c.n_M + c.n_X) >= 1)).all())
    print(f"b) model input columns {need}: missing values {na}; R: euv_confirm_tests.log_r, the function TEST 2 used, on all 387 le2 "
          f"episodes with TEST 2's event window 2024-12-29 -> 2026-08-18 23:59 (C1+ = K2 flux >= 1e-6, start in (t-48h, t), cap 48); "
          f"repeat identical {bool(np.array_equal(c.logR, c2.logR2))}; (R < 48) <=> (n_C+n_M+n_X >= 1) for all 387: {cons}")
    print(f"c) hash checks: {len(hs)} files in model_hashes.json match; thresholds.json matches 7a34507c...; frozen tau "
          + ", ".join(f"{m} {TH[m]['tau']:.6f}" for m in NAMES))
    w = e.weight.to_numpy(); keep = {}
    for m in NAMES:
        k = pred(M[m], e) >= TH[m]["tau"]; keep[m] = (float((w * k).sum() / w.sum()), int(k.sum()))
    print("d) BASELINE GUARD — weighted % of ALL evaluable episodes with p >= tau (label-blind): "
          + "; ".join(f"{m} {100 * keep[m][0]:.2f}% ({keep[m][1]}/{len(e)})" for m in NAMES))
    guard = keep["C"][0] > 0.95
    print(f"   C keeps > 95% of all episodes: {guard} -> " + ("BASELINE THRESHOLD DOES NOT FILTER — TEST NOT RUN" if guard else "guard passed"))
    json.dump(dict(n=len(e), harps=int(e.harpnum.nunique()), keep={m: keep[m][0] for m in NAMES}, guard_fail=guard),
              open(f"{T}/retest_checks.json", "w"), indent=1)

if __name__ == "__main__" and sys.argv[1:] == ["run"]:
    # RUN ONCE (user: "run the 2025-26 filter re-test once"; implementation 6aecccf). Everything is computed before printing.
    from concurrent.futures import ProcessPoolExecutor
    from sklearn.metrics import roc_auc_score
    from phase_f import boot_many, pct, wlogloss, W
    t00 = time.time()
    hs, TH, M = load_models()                                   # re-verifies all hashes
    _, _, e = evaluable(LABEL_FREE + ["true_alarm"])             # delayed episodes already have true_alarm = 0
    assert len(e) == 378 and e.harpnum.nunique() == 101
    y, w, h = e.true_alarm.to_numpy(), e.weight.to_numpy(), e.harpnum.to_numpy(); groups = [np.where(h == v)[0] for v in np.unique(h)]
    P = {m: pred(M[m], e) for m in NAMES}; K = {m: P[m] >= TH[m]["tau"] for m in NAMES}
    rows = []
    for m in NAMES:
        k = K[m]
        rows.append(dict(model=m, tau=TH[m]["tau"], true_kept=f"{int((k & (y == 1)).sum())}/{int(y.sum())}",
                         true_kept_w=(w * y * k).sum() / (w * y).sum() if y.sum() else np.nan,
                         false_kept=int((k & (y == 0)).sum()), false_removed=f"{int((~k & (y == 0)).sum())}/{int((y == 0).sum())}",
                         false_removed_w=(w * (1 - y) * ~k).sum() / (w * (1 - y)).sum() if (y == 0).any() else np.nan,
                         AUC=roc_auc_score(y, P[m], sample_weight=w) if 0 < y.sum() < len(y) else np.nan, logloss=wlogloss(y, P[m], w)))
    CT = pd.DataFrame(rows)
    jobs = {"op": ("op", dict(y=y, w=w, kept=[K[m] for m in NAMES], groups=groups), 2000, 0),
            "dA": ("dll", dict(y=y, w=w, pA=P["A"], pE=P["A_CV"], groups=groups), 10000, 20260921),
            "dC": ("dll", dict(y=y, w=w, pA=P["C"], pE=P["C_CV"], groups=groups), 10000, 20260921)}
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    op = np.array(B["op"], float)                                # resamples x 4 models x (true kept, false removed, precision)
    cmp_rows = []
    for a, b, ia, ib in [("C", "C_CV", 2, 3), ("A", "A_CV", 0, 1)]:   # lines copied verbatim from euv_extra.py filter (5abc40a)
        df_pt = CT.false_removed_w[ib] - CT.false_removed_w[ia]; dt_pt = CT.true_kept_w[ib] - CT.true_kept_w[ia]
        dfb, dtb = op[:, ib, 1] - op[:, ia, 1], op[:, ib, 0] - op[:, ia, 0]; ok = np.isfinite(dfb) & np.isfinite(dtb)
        (fl, fh), (tl, th) = (np.percentile(dfb[ok], [2.5, 97.5]), np.percentile(dtb[ok], [2.5, 97.5])) if ok.any() else ((np.nan,) * 2, (np.nan,) * 2)
        ll = B["dA"] if a == "A" else B["dC"]; dl = CT.logloss[ia] - CT.logloss[ib]; lo, hi = pct(ll)
        cmp_rows.append(dict(comparison=f"{a} vs {b}", D_false_pts=100 * df_pt, D_false_lo=100 * fl, D_false_hi=100 * fh,
                             D_true_pts=100 * dt_pt, D_true_lo=100 * tl, D_true_hi=100 * th, resamples_used=int(ok.sum()),
                             dlogloss=dl, dlogloss_lo=lo, dlogloss_hi=hi, AUC_base=CT.AUC[ia], AUC_cv=CT.AUC[ib]))
    CM = pd.DataFrame(cmp_rows)
    comp = e.assign(year=e.t.dt.year, regions=e.noaa_ars.astype(str).str.count(",") + 1).groupby(["year", "regions"]).size()
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
    CT.to_csv(f"{T}/retest_models.csv", index=False); CM.to_csv(f"{T}/retest_comparisons.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print("2025-26 RE-TEST: CV_box AS A FILTER ON TOP OF MODEL C — pre-registered re-test on an already-analysed set, NOT an untouched test. RUN ONCE.")
    print(f"hashes re-verified: {len(hs)} files + thresholds.json. Set: {len(e)} evaluable <= 2-region episodes (true {int(y.sum())}, false {int((y == 0).sum())}, "
          f"HARPs {len(groups)}); weights 1/n per HARP; delayed = false; frozen models, no refitting")
    print("composition (year / regions at t: episodes): " + ", ".join(f"{yy}/{rr}: {v}" for (yy, rr), v in comp.items()))
    print("\nper model at its frozen tau (weighted fractions; 'true alarm episodes kept'):")
    print(CT.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\nPRIMARY = C vs C_CV; SECONDARY = A vs A_CV. D_false = weighted % false alarms removed (CV model minus base); D_true = weighted % true alarm "
          "episodes kept (CV model minus base); percentage points; paired HARP bootstrap 2,000, seed 0. Delta log-loss = base - CV model; HARP bootstrap 10,000, seed 20260921.")
    print(CM.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\nPRE-STATED READING (mechanical; PRIMARY C vs C_CV): D_false {p.D_false_pts:+.2f} pts [{p.D_false_lo:+.2f}, {p.D_false_hi:+.2f}], "
          f"D_true {p.D_true_pts:+.2f} pts [{p.D_true_lo:+.2f}, {p.D_true_hi:+.2f}], resamples_used {p.resamples_used} -> \"{reading}\"")
    print(f"wall {time.time() - t00:.1f} s, workers {W}")
