"""POST-HOC incremental table (decisions.md 2026-10-05, "DRAFT FACT-CHECK, POST-HOC INCREMENTAL TABLE ..." item 2; decided by: user).
Frozen euv_extra models A, C, C_CV only (hash-verified, mean of the 5 fold models, no refitting, no new features) on
  - 2025-26: the 378 evaluable <= 2-region episodes of the filter re-test (euv_confirm_retest.evaluable), and
  - 2021/23/24 held-out test set: the 306 EUV-evaluable episodes (as posthoc_2026_09_28.load_all builds "test").
Step 1 reproduces the logged weighted log-loss and AUC to the printed 4 decimals (2025-26: euv_confirm_filter_retest.log, all three
models; test set: docs/posthoc_2026-09-28.md, Model C only; A and C_CV were never logged there). Stops on any mismatch.
Step 2 (POST-HOC, new): weighted PR-AUC (average precision) and weighted Brier score per model, with HARP-bootstrap 95% percentile CIs
(2,000 resamples, seed 0, phase_f.choices), and paired differences C - A and C_CV - C on the same resamples.
Weights 1/n per HARP; delayed episodes are false. Reads local files only (no download). Code written by Claude Code (AI).
Usage: python incremental_posthoc.py > incremental_posthoc.log"""
import glob, json, re, warnings
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from phase_f import wlogloss, choices, pct
from euv_confirm_tests import log_r
from euv_confirm_retest import load_models, evaluable, LABEL_FREE, pred

warnings.filterwarnings("ignore")
MODELS, NB, SEED = ["A", "C", "C_CV"], 2000, 0


def test_set():
    """= posthoc_2026_09_28.load_all, set "test" (only the columns models A, C, C_CV need)."""
    tc = pd.read_csv("data/stage5/cohort_test_primary.csv", parse_dates=["t"]); tc["eid"] = [f"{h}_{t:%Y%m%dT%H%M}" for h, t in zip(tc.harpnum, tc.t)]
    r = pd.DataFrame([json.load(open(p)) for p in glob.glob("data/euv_test/results/*.json")])[["eid", "primary_fill", "primary_CV_box"]]
    r[["primary_fill", "primary_CV_box"]] = r[["primary_fill", "primary_CV_box"]].apply(pd.to_numeric, errors="coerce")
    c = tc.drop(columns=["weight"]).merge(r, on="eid", how="left")
    c = c[(c.primary_fill >= 0.80) & np.isfinite(c.primary_CV_box) & (c.primary_CV_box > 0)].reset_index(drop=True); assert len(c) == 306
    c["log10_CV_box"] = np.log10(c.primary_CV_box); c["logR"] = log_r(c, pd.Timestamp("2020-12-29"), pd.Timestamp("2025-01-01"))
    c["weight"] = 1 / c.groupby("harpnum").harpnum.transform("size")
    return c


def logged():
    """The logged 4-decimal values to reproduce: {(set, model): (logloss, AUC, source)}."""
    out = {}
    for i, line in enumerate(open("euv_confirm_filter_retest.log", encoding="utf-8"), 1):
        m = re.match(r"\s+(A|C|C_CV) (\d\.\d{4}) .* (\d\.\d{4})\s+(\d\.\d{4})\s*$", line)
        if m:
            out[("2025-26", m.group(1))] = (m.group(4), m.group(3), f"euv_confirm_filter_retest.log:{i}")
    for i, line in enumerate(open("docs/posthoc_2026-09-28.md", encoding="utf-8"), 1):
        if line.startswith("| 2021/23/24 test (euv_test) | Model C | ") and line.count("|") == 12:
            f = [x.strip() for x in line.strip("|\n").split("|")]
            out[("test", "C")] = (f[10], f[8], f"docs/posthoc_2026-09-28.md:{i}")
    assert len([k for k in out if k[0] == "2025-26"]) == 3 and ("test", "C") in out, out
    return out


def metrics(y, p, w):
    if y.sum() == 0 or y.sum() == len(y):
        return np.nan, np.nan
    return average_precision_score(y, p, sample_weight=w), brier_score_loss(y, p, sample_weight=w)


if __name__ == "__main__":
    hs, TH, M = load_models()                                    # verifies every frozen file hash and thresholds.json
    _, _, conf = evaluable(LABEL_FREE + ["true_alarm"]); assert len(conf) == 378 and conf.harpnum.nunique() == 101
    SETS = {"2025-26": conf, "test": test_set()}
    LOG = logged()
    print("INCREMENTAL TABLE — POST-HOC (decided by: user, decisions.md 2026-10-05). Frozen euv_extra A, C, C_CV "
          f"({len(hs)} hashed files verified); mean of 5 fold models; no refitting; no new features.")
    print("weights 1/n per HARP; delayed = false; PR-AUC = weighted average precision; Brier = weighted mean (p - y)^2; "
          f"HARP bootstrap {NB:,} resamples, seed {SEED} (phase_f.choices), 95% percentile CI; differences paired on the same resamples.")
    ok = True
    for s, e in SETS.items():
        y, w, h = e.true_alarm.to_numpy(), e.weight.to_numpy(), e.harpnum.to_numpy()
        P = {m: pred(M[m], e) for m in MODELS}
        print(f"\nset {s}: n {len(e)} (true {int(y.sum())}, false {int((y == 0).sum())}), HARPs {len(np.unique(h))}")
        for m in MODELS:
            ll, auc = f"{wlogloss(y, P[m], w):.4f}", f"{roc_auc_score(y, P[m], sample_weight=w):.4f}"
            if (s, m) in LOG:
                want = LOG[(s, m)]; same = (ll, auc) == want[:2]; ok &= same
                print(f"REPRODUCED {s} {m}: logloss {ll} AUC {auc}; logged logloss {want[0]} AUC {want[1]} ({want[2]}); identical {same}")
            else:
                print(f"NOT PREVIOUSLY LOGGED {s} {m}: logloss {ll} AUC {auc} (POST-HOC)")
        assert ok, "logged log-loss/AUC not reproduced: STOP"
        groups = [np.where(h == v)[0] for v in np.unique(h)]
        pt = {m: metrics(y, P[m], w) for m in MODELS}
        B = []
        for row in choices(len(groups), NB, SEED):
            ix = np.concatenate([groups[j] for j in row])
            B.append([metrics(y[ix], P[m][ix], w[ix]) for m in MODELS])
        B = np.array(B, float)                                   # resamples x models x (PR-AUC, Brier)
        used = int(np.isfinite(B).all(axis=(1, 2)).sum())
        for i, m in enumerate(MODELS):
            (al, ah), (bl, bh) = pct(B[:, i, 0]), pct(B[:, i, 1])
            print(f"POST-HOC {s} {m}: PRAUC {pt[m][0]:.4f} [{al:.4f}, {ah:.4f}] Brier {pt[m][1]:.4f} [{bl:.4f}, {bh:.4f}] resamples_used {used}")
        for a, b in [("A", "C"), ("C", "C_CV")]:
            ia, ib = MODELS.index(a), MODELS.index(b)
            d = B[:, ib] - B[:, ia]
            (al, ah), (bl, bh) = pct(d[:, 0]), pct(d[:, 1])
            print(f"POST-HOC {s} {b}-{a}: dPRAUC {pt[b][0] - pt[a][0]:.4f} [{al:.4f}, {ah:.4f}] dBrier {pt[b][1] - pt[a][1]:.4f} [{bl:.4f}, {bh:.4f}] "
                  f"resamples_used {used}")
    print("\nAll logged values reproduced: True. Every PR-AUC / Brier number above is POST-HOC.")
