"""STAGE 2 -- the gate: Bobra & Couvidat-style SVM on 10 of their 13 features (decisions Q, S, N2, K2).

Dev only: HARPs assigned train/val in frozen/split.csv, rows 2010-2019 (2020 excluded, decision L).
The test HARPs are never loaded -- asserted below.

  features   the 10 B&C Table-1 "Included" features available as SHARP keywords (decision Q)
  training   single-region rows (noaa_ar_count == 1, primary subset, decision M), thinned to
             TAI hours {4, 10, 16, 22} (decision S)
  scaling    B&C 2015 sec. 5: subtract each feature's median, divide by its standard deviation --
             fitted on each training fold only
  SVM        RBF, C = 4, gamma = 0.075, tol = 1e-8, class weights positive:negative = 2.0 : 1.0. No tuning.
  CV         5 folds, grouped by HARPNUM, stratified by 3 HARP strata computed from K2 labels
             (positive in single-region rows / positive only in multi-region rows / negative), seed 20260921
  scoring    every hourly dev row scored out-of-fold (by the model whose fold held its HARP out)
  threshold  max TSS on the pooled out-of-fold hourly scores of the primary subset; per-fold optima reported
Rows with a missing gate feature cannot be scored (no imputation): excluded and counted.
"""
import json, os, time, hashlib
import numpy as np, pandas as pd, joblib
from joblib import Parallel, delayed
from sklearn.svm import SVC
from sklearn.metrics import roc_curve

FEATURES = ["totusjh", "totpot", "totusjz", "absnjzh", "savncpp", "usflux", "area_acr", "meanpot", "r_value", "shrgt45"]
SEED, K, N_JOBS = 20260921, 5, 3
SVM = dict(kernel="rbf", C=4.0, gamma=0.075, tol=1e-8, class_weight={1: 2.0, 0: 1.0})
LIMIT_S = 3 * 3600
OUT = "data/stage2"

# ------------------------------------------------------------------ data: dev only
split = pd.read_csv("frozen/split.csv")
dev_harps = set(split.loc[split["set"].isin(["train", "val"]), "harpnum"])
lab = pd.read_csv("data/labelled_20100501_20250101.csv", low_memory=False)
lab = lab[lab["harpnum"].isin(dev_harps)]
lab = lab[lab["t_rec_utc"].str[:4].astype(int) <= 2019]                 # 2020 excluded (L); dev <= 2019
assert not set(lab["harpnum"]) & set(split.loc[split["set"] == "test", "harpnum"]), "test HARP loaded"
assert lab["t_rec_utc"].str[:4].astype(int).max() <= 2019, "row after 2019 loaded"
n_all = len(lab)
missing = lab[FEATURES].isna().any(axis=1)
print(f"dev hourly rows {n_all}; missing a gate feature: {int(missing.sum())} "
      f"(positives {int(lab.loc[missing, 'flared_M1_next_24h'].sum())}) -> unscorable, excluded")
lab = lab[~missing].reset_index(drop=True)
y = lab["flared_M1_next_24h"].to_numpy()
primary = (lab["noaa_ar_count"] == 1).to_numpy()

# ------------------------------------------------------------------ folds: stratified at HARP level
pos_single = set(lab.loc[primary & (y == 1), "harpnum"])
pos_any = set(lab.loc[y == 1, "harpnum"])
harps = np.sort(lab["harpnum"].unique())
stratum = {h: "positive_single" if h in pos_single else ("positive_multi_only" if h in pos_any else "negative")
           for h in harps}
rng = np.random.RandomState(SEED)
fold_of = {}
for name in ["positive_single", "positive_multi_only", "negative"]:        # fixed order -> reproducible
    members = rng.permutation(np.sort([h for h in harps if stratum[h] == name]))
    for i, h in enumerate(members):
        fold_of[h] = i % K                                                    # deal round-robin
lab["fold"] = lab["harpnum"].map(fold_of)
print("\nfolds (HARPs / positive-single HARPs):",
      {f: (int((pd.Series(fold_of) == f).sum()),
           int(sum(1 for h in pos_single if fold_of[h] == f))) for f in range(K)})
for f in range(K):                                                            # grouped: no HARP in two folds
    assert not set(lab.loc[lab["fold"] == f, "harpnum"]) & set(lab.loc[lab["fold"] != f, "harpnum"])

thin = lab["t_rec_tai"].str[11:13].astype(int).isin([4, 10, 16, 22]).to_numpy()
train_mask = primary & thin


def fit_fold(f):
    t0 = time.time()
    tr = train_mask & (lab["fold"] != f).to_numpy()
    X = lab.loc[tr, FEATURES].to_numpy(float)
    med, sd = np.median(X, axis=0), X.std(axis=0)                             # B&C sec. 5, this fold only
    m = SVC(**SVM).fit((X - med) / sd, y[tr])
    te = (lab["fold"] == f).to_numpy()                                        # every hourly row of held-out HARPs
    s = m.decision_function((lab.loc[te, FEATURES].to_numpy(float) - med) / sd)
    joblib.dump({"model": m, "median": med, "sd": sd, "features": FEATURES}, f"{OUT}/models/fold{f}.joblib")
    return f, np.where(te)[0], s, int(tr.sum()), int(y[tr].sum()), len(m.support_), time.time() - t0


t0 = time.time()
res = Parallel(n_jobs=N_JOBS, timeout=LIMIT_S)(delayed(fit_fold)(f) for f in range(K))
elapsed = time.time() - t0
lab["score"] = np.nan
for f, idx, s, ntr, ptr, nsv, dt in res:
    lab.loc[idx, "score"] = s
    print(f"fold {f}: trained on {ntr} thinned single-region rows ({ptr} positive), "
          f"{nsv} support vectors, {dt:.1f} s")
print(f"total wall time {elapsed:.1f} s (limit {LIMIT_S/3600:.0f} h)")
assert lab["score"].notna().all()


# ------------------------------------------------------------------ metrics
def metrics(yt, alarm):
    tp = int((alarm & (yt == 1)).sum()); fn = int((~alarm & (yt == 1)).sum())
    fp = int((alarm & (yt == 0)).sum()); tn = int((~alarm & (yt == 0)).sum())
    tpr = tp / (tp + fn) if tp + fn else np.nan
    fpr = fp / (fp + tn) if fp + tn else np.nan
    far = fp / (tp + fp) if tp + fp else np.nan
    hss = 2 * (tp * tn - fn * fp) / ((tp + fn) * (fn + tn) + (tp + fp) * (fp + tn))
    return dict(TSS=tpr - fpr, HSS=hss, TPR=tpr, FPR=fpr, FAR=far, TP=tp, FP=fp, FN=fn, TN=tn)


def best_threshold(yt, s):
    fpr, tpr, thr = roc_curve(yt, s)
    i = int(np.argmax(tpr - fpr))
    return float(thr[i]), float(tpr[i] - fpr[i])


P = lab[primary]                                                              # primary subset, all hours
thr, tss_pooled = best_threshold(P["flared_M1_next_24h"], P["score"])
print(f"\npooled out-of-fold threshold (max TSS, primary subset, hourly): {thr:.6f}  (TSS {tss_pooled:.4f})")

rows = []
for f in list(range(K)) + ["pooled"]:
    g = P if f == "pooled" else P[P["fold"] == f]
    yt, s = g["flared_M1_next_24h"].to_numpy(), g["score"].to_numpy()
    own_thr, own_tss = best_threshold(yt, s)
    m = metrics(yt, s >= thr)
    rows.append({"fold": f, "rows": len(g), "pos_rows": int(yt.sum()), "HARPs": g["harpnum"].nunique(),
                 "pos_HARPs": g.loc[g["flared_M1_next_24h"] == 1, "harpnum"].nunique(),
                 **{k: m[k] for k in ["TSS", "HSS", "TPR", "FPR", "FAR"]},
                 "own_opt_threshold": own_thr, "TSS_at_own_opt": own_tss})
t = pd.DataFrame(rows)
print("\nprimary subset, hourly, at the pooled threshold (own-fold optimum shown for comparison):")
print(t.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

lab[["harpnum", "t_rec_tai", "t_rec_utc", "fold", "score", "noaa_ar_count", "flared_M1_next_24h"]] \
    .to_csv(f"{OUT}/oof_scores_dev.csv", index=False)
t.to_csv(f"{OUT}/stage2_metrics.csv", index=False)
json.dump({"threshold": thr, "pooled_tss": tss_pooled, "folds": {str(k): int(v) for k, v in fold_of.items()},
           "unscorable_rows": int(missing.sum()), "elapsed_s": elapsed},
          open(f"{OUT}/stage2_result.json", "w"), indent=1)
for f in range(K):
    print(f"fold{f}.joblib sha256 {hashlib.sha256(open(f'{OUT}/models/fold{f}.joblib','rb').read()).hexdigest()}")
