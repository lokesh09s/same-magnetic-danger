"""2025-26 CONFIRMATION TESTS (decisions.md 2026-09-26 pre-registration). RUN ONCE.
TEST 1: CV_box magnetic-twins ratio (<= 2 set, primary 80% fill) + secondaries s1-s5.
TEST 2: Step B, A vs C = A + log(1 + R) (dev-fitted; mean of 5 fold models) + operating points at tau_A / tau_C."""
import glob, hashlib, json, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from sklearn.metrics import roc_auc_score
import joblib, swpc
from phase_f import load_base, prep, boot_many, pct, ratio_jobs, wlogloss, A_COLS, W
from euv_f2_replication import twins
from euv_heldout import fit_folds, predict

T, D = "data/euv_confirm", "data/euv_full"
SPEC = json.load(open("frozen/frozen_spec.json")); H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
fmt = lambda v: f"{v:.4f}"


def conf_cohort(s):
    c = pd.read_csv(f"{T}/cohort_{s}.csv", parse_dates=["t"])
    c["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(c.harpnum, c.t)]
    num = ["primary_fill", "primary_CV_box"]
    r = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/results/*.json")])[["eid"] + num]
    r[num] = r[num].apply(pd.to_numeric, errors="coerce")
    sp = pd.DataFrame([json.load(open(p)) for p in glob.glob(f"{T}/spatial/*.json")])[["eid", "R4a"]]
    return c.merge(r, on="eid", how="left").merge(sp, on="eid", how="left")


def log_r(c, lo, hi):
    """Step B feature: hours since the region's most recent C1+ (K2, joinable SWPC) flare start in (t-48h, t), cap 48; log(1+R)."""
    fl, _ = swpc.fetch(lo, hi, verbose=False)
    by = {int(a): np.sort(g.start.values) for a, g in fl[fl.flux >= 1e-6].groupby("noaa_ar")}
    out = []
    for e in c.itertuples():
        s = np.concatenate([by.get(int(a), np.array([], "datetime64[us]")) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()])
        t = np.datetime64(e.t); s = s[(s > t - np.timedelta64(48, "h")) & (s < t)]
        R = (t - s.max()) / np.timedelta64(1, "h") if len(s) else 48.0
        out.append(float(np.log1p(min(R, 48.0))))
    return np.array(out)


def ratio_block(label, cset, tw, pool):
    e, j = ratio_jobs(label, cset, "primary_CV_box", "ratio", tw); B = boot_many(j, pool)
    e["all_CI"] = "[%.4f, %.4f]" % pct(B[(label, "all")]); e["tw_CI_lo"], e["tw_CI_hi"] = pct(B[(label, "tw")])
    return e


def wtss_curve(p, y, w):
    th = np.unique(p)[::-1]
    tpr = np.array([(w * y * (p >= t)).sum() / (w * y).sum() for t in th])
    fpr = np.array([(w * (1 - y) * (p >= t)).sum() / (w * (1 - y)).sum() for t in th])
    return th, tpr, fpr


if __name__ == "__main__":
    t00 = time.time(); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    pool = ProcessPoolExecutor(W)
    le2, single = conf_cohort("le2"), conf_cohort("single")
    assert len(le2) == 387 and len(single) == 165
    # ============================================================ TEST 1
    print("=== TEST 1 — CV_box magnetic twins, 2025-26, <= 2 set, primary 80% fill (delayed = false)")
    c1 = le2[(le2.primary_fill >= 0.80) & le2.primary_CV_box.notna()].reset_index(drop=True)
    tw, nt = twins(c1); tw.to_csv(f"{T}/twins_le2.csv", index=False)
    print(f"set: {len(c1)} episodes (true {int(c1.true_alarm.sum())}, false {int((c1.true_alarm == 0).sum())}, HARPs {c1.harpnum.nunique()}); "
          f"twins: {len(tw)} pairs of {nt} true; max |score diff| {tw.score_diff.abs().max():.4f}; by history group {tw.group.value_counts().to_dict()}")
    P = ratio_block("PRIMARY CV_box twins (<= 2)", c1, tw, pool)
    reading1 = ("REPLICATED" if P["ratio_twins"] > 1 and P["tw_CI_lo"] > 1 else
                "direction consistent, not confirmed" if P["ratio_twins"] > 1 else "NOT REPLICATED")
    tw_h, _ = twins(c1, by_group=True)
    S1 = ratio_block("s1 same-flare-history twins (<= 2)", c1, tw_h, pool)
    c4 = single[(single.primary_fill >= 0.80) & single.primary_CV_box.notna()].reset_index(drop=True)
    tw4, nt4 = twins(c4)
    S4 = ratio_block("s4 single-region subset twins", c4, tw4, pool)
    # s5 pooled: 2021-24 existing 40 pairs + 2025-26 primary pairs
    tt = pd.read_csv("data/stage5/cohort_test_primary.csv", parse_dates=["t"]); tt["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(tt.harpnum, tt.t)]
    rt = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_test/results/*.json")])[["eid", "primary_CV_box"]]
    rt["primary_CV_box"] = pd.to_numeric(rt.primary_CV_box, errors="coerce"); tt = tt.merge(rt, on="eid", how="left")
    tw_t = pd.read_csv("data/euv_test/f2_replication/twins_test_primary.csv")
    assert len(tw_t) == 40
    pool_set = pd.concat([tt[["eid", "harpnum", "true_alarm", "primary_CV_box"]], c1[["eid", "harpnum", "true_alarm", "primary_CV_box"]]], ignore_index=True)
    assert pool_set.eid.is_unique and not set(tt.harpnum) & set(c1.harpnum)
    S5 = ratio_block("s5 POOLED 2021-24 (40 pairs) + 2025-26 primary pairs — includes 2021-24 data already analysed (ec00afb); "
                     "not a confirmation", pool_set, pd.concat([tw_t, tw], ignore_index=True), pool)
    R1 = pd.DataFrame([P, S1, S4, S5])
    print("ratio = median(true) / median(false); twins CI: pairs resampled by true HARP, 2,000, seed 0; all-episodes CI: HARP bootstrap 2,000, seed 0")
    print(R1[["measure", "n", "n_true", "n_false", "med_true", "med_false", "ratio_all", "all_CI", "pairs", "twin_med_true", "twin_med_false",
              "ratio_twins", "tw_CI_lo", "tw_CI_hi"]].to_string(index=False, float_format=fmt))
    print(f"s4 single-region twins: {len(tw4)} pairs of {nt4} true")
    print(f"PRE-STATED READING (mechanical, PRIMARY): ratio {P['ratio_twins']:.4f} [{P['tw_CI_lo']:.4f}, {P['tw_CI_hi']:.4f}] -> \"{reading1}\"")
    # s3 R4a: dev-fitted fold models as 2021-24 (dev 541 set)
    dv = load_base()
    cd = prep(dv, dv.P & dv.R4a.notna()); ma, pa = fit_folds(cd, A_COLS); me, pe = fit_folds(cd, A_COLS + ["R4a"])
    px = pd.read_csv(f"{D}/spatial/eval_compare.csv", float_precision="round_trip").set_index("candidate").loc["R4a"]
    assert abs(wlogloss(cd.true_alarm.to_numpy(), pa, cd.weight.to_numpy()) - px.logloss_A) < 1e-12
    assert abs(wlogloss(cd.true_alarm.to_numpy(), pe, cd.weight.to_numpy()) - px.logloss_A_plus) < 1e-12
    c3 = c1[c1.R4a.notna()].reset_index(drop=True).copy(); c3["weight"] = 1 / c3.groupby("harpnum").harpnum.transform("size")
    y, w, h = c3.true_alarm.to_numpy(), c3.weight.to_numpy(), c3.harpnum.to_numpy(); qA, qE = predict(ma, c3), predict(me, c3)
    B = boot_many({"d": ("dll", dict(y=y, w=w, pA=qA, pE=qE, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}, pool)["d"]
    lo, hi = pct(B); d3 = wlogloss(y, qA, w) - wlogloss(y, qE, w)
    print(f"\ns3 R4a (dev 541 fold models; mean of 5): n {len(c3)} (true {int(y.sum())}, false {int((y == 0).sum())}, HARPs {len(np.unique(h))}); "
          f"LL(A) {wlogloss(y, qA, w):.4f}, LL(A+R4a) {wlogloss(y, qE, w):.4f}, delta {d3:.4f} [{lo:.4f}, {hi:.4f}]; AUC "
          f"{roc_auc_score(y, qA, sample_weight=w):.4f} -> {roc_auc_score(y, qE, sample_weight=w):.4f} -> "
          f"\"{'adds information' if d3 > 0 and lo > 0 else 'does not add information (condition not met)'}\"")
    # ============================================================ TEST 2 — Step B
    print("\n=== TEST 2 — STEP B: A vs C = A + log(1 + R); dev-fitted; test prediction = mean of 5 fold models")
    for k, v in SPEC["models"]["fold_models"].items():
        if k.startswith("A_"):
            assert H(f"data/stage4/models/{k}.joblib") == v
    A = [(lambda d_: (d_["scaler"], d_["model"], d_["cols"]))(joblib.load(f"data/stage4/models/A_fold{k}.joblib")) for k in range(5)]
    coh = pd.read_csv("data/stage4/oof_cohort_dev.csv", parse_dates=["t"])
    coh["logR"] = log_r(coh, pd.Timestamp("2010-04-28"), pd.Timestamp("2019-12-31 23:59"))
    assert ((coh.logR < np.log1p(48)) == ((coh.n_C + coh.n_M + coh.n_X) >= 1)).all(), "R window inconsistent with history counts (dev)"
    mA, pA_dev = fit_folds(coh, A_COLS)
    assert np.abs(pA_dev - coh.p_A).max() < 1e-12 and all(np.array_equal(a[1].coef_, b[1].coef_) for a, b in zip(mA, A))
    mC, pC_dev = fit_folds(coh, A_COLS + ["logR"])
    y, w, h = coh.true_alarm.to_numpy(), coh.weight.to_numpy(), coh.harpnum.to_numpy()
    thA, tprA, fprA = wtss_curve(pA_dev, y, w); iA = int(np.argmax(tprA - fprA)); tauA, tprA_star = thA[iA], tprA[iA]
    thC, tprC, fprC = wtss_curve(pC_dev, y, w); ok = np.where(tprC >= tprA_star)[0]; iC = int(ok[0]); tauC = thC[iC]
    Bd = boot_many({"d": ("dll", dict(y=y, w=w, pA=pA_dev, pE=pC_dev, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}, pool)["d"]
    ld = wlogloss(y, pA_dev, w) - wlogloss(y, pC_dev, w); lod, hid = pct(Bd)
    print(f"checks: frozen A fold models hash-verified; refit A reproduces them and Stage 4 p_A; dev R window consistent with history counts")
    print(f"dev (EXPLORATORY, OOF, 547 episodes): LL(A) {wlogloss(y, pA_dev, w):.4f}, LL(C) {wlogloss(y, pC_dev, w):.4f}, delta {ld:.4f} "
          f"[{lod:.4f}, {hid:.4f}]; AUC {roc_auc_score(y, pA_dev, sample_weight=w):.4f} -> {roc_auc_score(y, pC_dev, sample_weight=w):.4f}")
    print(f"frozen dev thresholds: tau_A {tauA:.6f} (max weighted TSS {tprA[iA] - fprA[iA]:.4f}, weighted TPR {tprA_star:.4f}, FPR {fprA[iA]:.4f}); "
          f"tau_C {tauC:.6f} (highest threshold with weighted TPR >= {tprA_star:.4f}: TPR {tprC[iC]:.4f}, FPR {fprC[iC]:.4f})")
    rows = []
    for lab, c in [("PRIMARY <= 2, all eligible", le2), ("single-region (descriptive)", single)]:
        c = c.copy(); c["logR"] = log_r(c, pd.Timestamp("2024-12-29"), pd.Timestamp("2026-08-18 23:59"))
        assert ((c.logR < np.log1p(48)) == ((c.n_C + c.n_M + c.n_X) >= 1)).all(), "R window inconsistent with history counts (2025-26)"
        c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy(); qA, qC = predict(A, c), predict(mC, c)
        B = boot_many({"d": ("dll", dict(y=y, w=w, pA=qA, pE=qC, groups=[np.where(h == v)[0] for v in np.unique(h)]), 10000, 20260921)}, pool)["d"]
        lo, hi = pct(B); kA, kC = qA >= tauA, qC >= tauC
        r = dict(set=lab, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(np.unique(h)), LL_A=wlogloss(y, qA, w),
                 LL_C=wlogloss(y, qC, w), delta=wlogloss(y, qA, w) - wlogloss(y, qC, w), CI_lo=lo, CI_hi=hi,
                 AUC_A=roc_auc_score(y, qA, sample_weight=w), AUC_C=roc_auc_score(y, qC, sample_weight=w),
                 FA_A=int((kA & (y == 0)).sum()), FA_C=int((kC & (y == 0)).sum()),
                 FA_A_w=(w * (1 - y) * kA).sum() / (w * (1 - y)).sum(), FA_C_w=(w * (1 - y) * kC).sum() / (w * (1 - y)).sum(),
                 TK_A=int((kA & (y == 1)).sum()), TK_C=int((kC & (y == 1)).sum()),
                 TPR_A_w=(w * y * kA).sum() / (w * y).sum(), TPR_C_w=(w * y * kC).sum() / (w * y).sum())
        rows.append(r)
    R2 = pd.DataFrame(rows)
    print("delta = LL(A) - LL(C), + = C better; HARP bootstrap 10,000, seed 20260921; false alarms = false episodes still alarmed at "
          "tau (count; weighted fraction of false episodes); true kept = true episodes at/above tau")
    print(R2.to_string(index=False, float_format=fmt))
    p = R2.iloc[0]
    print(f"PRE-STATED READING (mechanical, PRIMARY): delta {p.delta:.4f} [{p.CI_lo:.4f}, {p.CI_hi:.4f}] -> "
          f"\"{'C beats A' if p.delta > 0 and p.CI_lo > 0 else 'not confirmed'}\"")
    pool.shutdown()
    R1.to_csv(f"{T}/test1_ratios.csv", index=False); R2.to_csv(f"{T}/test2_stepB.csv", index=False)
    print(f"\nwall {time.time() - t00:.1f} s, workers {W}")
