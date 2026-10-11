"""EXPLORATORY ROBUSTNESS CHECK (decisions.md 2026-09-26, 0043520): lnR4a = ln(R4a + 3) vs raw R4a. DEV 2010-2019 ONLY."""
import time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from sklearn.metrics import roc_auc_score
from euv_spatial import cv_fit
from phase_f import load_base, prep, boot_many, wlogloss, pct, A_COLS, W

if __name__ == "__main__":
    t00 = time.time(); pd.set_option("display.width", 250); fmt = lambda v: f"{v:.4f}"
    dv = load_base()
    assert (dv.R4a.dropna() >= -3).all() and (dv.R4a_nf.dropna() >= -3).all()
    dv["lnR4a"], dv["lnR4a_nf"] = np.log(dv.R4a + 3), np.log(dv.R4a_nf + 3)
    c1, c2 = prep(dv, dv.P & dv.R4a.notna()), prep(dv, dv.S & dv.R4a_nf.notna())
    P = {"A": cv_fit(c1, A_COLS), "A+R4a": cv_fit(c1, A_COLS + ["R4a"]), "A+lnR4a": cv_fit(c1, A_COLS + ["lnR4a"]),
         "A2": cv_fit(c2, A_COLS), "A+lnR4a_nf": cv_fit(c2, A_COLS + ["lnR4a_nf"])}
    specs = [("A vs A+R4a (check)", c1, "A", "A+R4a"), ("PRIMARY A vs A+lnR4a", c1, "A", "A+lnR4a"),
             ("paired A+R4a vs A+lnR4a", c1, "A+R4a", "A+lnR4a"), ("flare-excluded A vs A+ln(R4a_nf+3)", c2, "A2", "A+lnR4a_nf")]
    rows, jobs = [], {}
    for name, c, b, f in specs:
        y, w, h = c.true_alarm.to_numpy(), c.weight.to_numpy(), c.harpnum.to_numpy()
        groups = [np.where(h == v)[0] for v in np.unique(h)]
        rows.append(dict(test=name, n=len(c), true=int(y.sum()), false=int((y == 0).sum()), HARPs=len(groups),
                         logloss_base=wlogloss(y, P[b], w), logloss_full=wlogloss(y, P[f], w),
                         AUC_base=roc_auc_score(y, P[b], sample_weight=w), AUC_full=roc_auc_score(y, P[f], sample_weight=w)))
        rows[-1]["delta"] = rows[-1]["logloss_base"] - rows[-1]["logloss_full"]
        jobs[name] = ("dll", dict(y=y, w=w, pA=P[b], pE=P[f], groups=groups), 10000, 20260921)
    with ProcessPoolExecutor(W) as pool:
        B = boot_many(jobs, pool)
    for r in rows:
        r["CI_lo"], r["CI_hi"] = pct(B[r["test"]])
    T = pd.DataFrame(rows)
    px = pd.read_csv("data/euv_full/spatial/eval_compare.csv", float_precision="round_trip").set_index("candidate").loc["R4a"]
    ck = T.iloc[0]
    assert ck.delta == px.delta_A_minus_Aplus and ck.CI_lo == px.CI_lo and ck.CI_hi == px.CI_hi and ck.AUC_full == px.AUC_A_plus
    print("check: A vs A + R4a reproduces committed Phase X exactly")
    print("dev 2010-2019, internal 5-fold CV, EXPLORATORY; delta = LL(base) - LL(base + x) (paired row: LL(A+R4a) - LL(A+lnR4a), "
          "+ = log better); HARP bootstrap 10,000, seed 20260921 (same resamples on the 541 set)")
    print(T.to_string(index=False, float_format=fmt))
    p = T.set_index("test").loc["paired A+R4a vs A+lnR4a"]
    print(f"pre-stated reading (mechanical): paired difference {p.delta:+.4f} [{p.CI_lo:+.4f}, {p.CI_hi:+.4f}] -> "
          f"\"{'log matters' if p.CI_lo > 0 else 'raw vs log makes no clear difference'}\"")
    T.to_csv("data/euv_full/spatial/eval_lnr4a.csv", index=False)
    print(f"wall {time.time() - t00:.1f} s, workers {W}")
