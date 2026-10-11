"""COMBO-T (decisions.md 2026-09-27, 9a88d70): SECONDARY prospective model, fitted on dev 2010-2019 only (no 2021-2026 data read).
COMBO-T = Model C columns + log10 CV_box + prot12; L2 logistic C = 0.3, lbfgs; Step 6 settings otherwise. Usage: python combo_t.py freeze"""
import hashlib, json, os, sys, warnings
import numpy as np, pandas as pd
import joblib, swpc
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from stage4_models import LR, K
from phase_f import load_base, prep, tau_keep, op_stats, wlogloss, A_COLS, DEV_END
from euv_confirm_tests import log_r
from euv_heldout import fit_folds

warnings.filterwarnings("ignore")
ROOT = "data/combo_t"
COLS = A_COLS + ["logR", "log10_CV_box", "prot12"]
LR_T = dict(LR, C=0.3)                                            # only change from the Step 6 estimator
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def prot12(c, lo, hi):
    """1 if a region in noaa_ars had >= 1 flare of class C2.0+ (swpc.fetch: SWPC originals, K2 true scale, joinable events = the label
    join) starting in (t - 12 h, t); else 0. Same join code as euv_confirm_tests.log_r."""
    fl, _ = swpc.fetch(lo, hi, verbose=False)
    by = {int(a): np.sort(g.start.values) for a, g in fl[fl.flux >= 2e-6].groupby("noaa_ar")}
    out = []
    for e in c.itertuples():
        s = np.concatenate([by.get(int(a), np.array([], "datetime64[us]")) for a in str(e.noaa_ars).split(",") if a.strip().isdigit()])
        t = np.datetime64(e.t); out.append(int(((s > t - np.timedelta64(12, "h")) & (s < t)).any()))
    return np.array(out)


def fit_folds_t(c, cols):
    """= euv_heldout.fit_folds with LogisticRegression C = 0.3."""
    y, w, f = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.fold.to_numpy()
    p, ms = np.empty(len(c)), []
    for k in range(K):
        tr, te = f != k, f == k
        sc = StandardScaler().fit(c.loc[tr, cols])
        m = LogisticRegression(**LR_T).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]; ms.append((sc, m, cols))
    return ms, p


if __name__ == "__main__" and sys.argv[1:] == ["freeze"]:
    pd.set_option("display.width", 250)
    print("COMBO-T FREEZE (9a88d70) — dev 2010-2019 only; no 2021-2026 data read. SECONDARY prospective model; exploratory.")
    dv = load_base()
    c = prep(dv, dv.P & np.isfinite(dv.primary_CV_box) & (dv.primary_CV_box > 0))
    ex = pd.read_csv("data/euv_extra/dev_rows.csv")
    assert len(c) == 541 and (c.eid.to_numpy() == ex.eid.to_numpy()).all(), "dev set differs from the frozen euv_extra dev rows"
    c["logR"] = log_r(c, pd.Timestamp("2010-04-28"), DEV_END); c["log10_CV_box"] = np.log10(c.primary_CV_box)
    c["prot12"] = prot12(c, pd.Timestamp("2010-04-28"), DEV_END)
    assert (c.logR[c.prot12 == 1] < np.log1p(12)).all(), "prot12 = 1 without a C1+ start in (t-12h, t)"
    y, w = c.true_alarm.to_numpy(), c.weight.to_numpy()
    TX = json.load(open("data/euv_extra/thresholds.json"))
    _, pC = fit_folds(c, A_COLS + ["logR"])
    assert wlogloss(y, pC, w) == TX["C"]["dev_oof_logloss"] and tau_keep(pC, y, w) == TX["C"]["tau"], "Model C does not reproduce euv_extra"
    ms, p = fit_folds_t(c, COLS)
    tau = tau_keep(p, y, w); k = p >= tau; tk, fr, pr = op_stats(y, w, k)
    kC = pC >= TX["C"]["tau"]; tkC, frC, _ = op_stats(y, w, kC)
    out = dict(cols=COLS, estimator=LR_T, tau=tau, dev_oof_logloss=wlogloss(y, p, w), dev_oof_AUC=roc_auc_score(y, p, sample_weight=w),
               dev_oof_true_kept_w=tk, dev_oof_false_removed_w=fr, true_kept_n=f"{int((k & (y == 1)).sum())}/{int(y.sum())}",
               false_removed_n=f"{int((~k & (y == 0)).sum())}/{int((y == 0).sum())}")
    os.makedirs(f"{ROOT}/models", exist_ok=True); hashes = {}
    for f, (sc, mdl, cl) in enumerate(ms):
        fn = f"{ROOT}/models/COMBO_T_fold{f}.joblib"
        assert not os.path.exists(fn), f"{fn} exists; never overwrite"
        joblib.dump({"scaler": sc, "model": mdl, "cols": cl}, fn); hashes[fn] = H(fn)
    for fn, obj in [(f"{ROOT}/thresholds.json", out), (f"{ROOT}/dev_rows.csv", c[["eid", "harpnum", "t", "fold", "weight"] + COLS])]:
        assert not os.path.exists(fn), f"{fn} exists; never overwrite"
        json.dump(obj, open(fn, "w"), indent=1) if fn.endswith(".json") else obj.to_csv(fn, index=False)
        hashes[fn] = H(fn)
    json.dump(hashes, open(f"{ROOT}/model_hashes.json", "w"), indent=1)
    print(f"checks: dev set = the frozen euv_extra dev rows (541, same order); prot12 = 1 only where a C1+ started in (t-12h, t); "
          f"Model C (C = 1.0) reproduces euv_extra dev OOF log-loss and tau exactly")
    print(f"dev set: {len(c)} episodes (true {int(y.sum())}, false {int((y == 0).sum())}, HARPs {c.harpnum.nunique()}); "
          f"prot12 = 1 in {int(c.prot12.sum())} ({int(c.prot12[c.true_alarm == 1].sum())} true / {int(c.prot12[c.true_alarm == 0].sum())} false)")
    print(f"\nCOMBO-T cols {COLS}; LogisticRegression {LR_T}; Stage 4 folds, 1/n per HARP, training-fold StandardScaler")
    print(f"  dev OOF: LL {out['dev_oof_logloss']:.4f}, weighted AUC {out['dev_oof_AUC']:.4f}; tau (>= 88% weighted true kept) {tau:.10f}; "
          f"true kept {out['true_kept_n']} ({tk:.4f} w), false removed {out['false_removed_n']} ({fr:.4f} w)")
    print(f"  reference Model C (frozen euv_extra, dev OOF): LL {TX['C']['dev_oof_logloss']:.4f}, weighted AUC {roc_auc_score(y, pC, sample_weight=w):.4f}; "
          f"tau {TX['C']['tau']:.10f}; true kept {int((kC & (y == 1)).sum())}/{int(y.sum())} ({tkC:.4f} w), "
          f"false removed {int((~kC & (y == 0)).sum())}/{int((y == 0).sum())} ({frC:.4f} w)")
    co = pd.DataFrame([dict(fold=f, **{c_: b for c_, b in zip(COLS, m.coef_[0])}) for f, (_, m, _) in enumerate(ms)])
    print("  coefficients per fold (per 1 SD, training-fold StandardScaler):")
    print(co.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    for fn, h in hashes.items():
        print(f"  sha256 {h}  {fn}")
