"""STAGE 4 -- primary cohort models on DEV only (test years never loaded).  Implements the pre-registered details
(decisions.md, 'Stage 4 implementation details -- PRE-REGISTERED').
  A = gate score + n_C + n_M + n_X;  B = A + rel_slope_usflux + rel_slope_totusjh
  LogisticRegression L2, C = 1.0, no tuning; StandardScaler fitted on training folds; sample_weight = episode weight."""
import hashlib, json, os
import numpy as np, pandas as pd, joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

SEED, K, NBOOT = 20260921, 5, 1000
A_COLS = ["score", "n_C", "n_M", "n_X"]
B_COLS = A_COLS + ["rel_slope_usflux", "rel_slope_totusjh"]
LR = dict(penalty="l2", C=1.0, solver="lbfgs", max_iter=10000)
OUT = "data/stage4"

coh = pd.read_csv("data/stage3/cohort_dev.csv", parse_dates=["t"])
assert coh["t"].dt.year.max() <= 2019, "non-dev episode in cohort"
split = pd.read_csv("frozen/split.csv")
assert not set(coh["harpnum"]) & set(split.loc[split["set"] == "test", "harpnum"]), "test HARP in cohort"


def folds_for(c):
    """Pre-registered item 1: 2 HARP strata (>= 1 true episode / none), shuffled with SEED, dealt round-robin."""
    has_true = c.groupby("harpnum")["true_alarm"].max()
    rng, fold_of = np.random.RandomState(SEED), {}
    for flag in [1, 0]:
        for i, h in enumerate(rng.permutation(np.sort(has_true[has_true == flag].index.values))):
            fold_of[int(h)] = i % K
    return c["harpnum"].map(fold_of).to_numpy()


def wlogloss(y, p, w):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(np.sum(w * -(y * np.log(p) + (1 - y) * np.log(1 - p))) / np.sum(w))


def cv(c, cols, tag, save):
    y, w, folds = c["true_alarm"].to_numpy(), c["weight"].to_numpy(), folds_for(c)
    p = np.empty(len(c))
    for f in range(K):
        tr, te = folds != f, folds == f
        sc = StandardScaler().fit(c.loc[tr, cols])
        m = LogisticRegression(**LR).fit(sc.transform(c.loc[tr, cols]), y[tr], sample_weight=w[tr])
        p[te] = m.predict_proba(sc.transform(c.loc[te, cols]))[:, 1]
        if save:
            joblib.dump({"scaler": sc, "model": m, "cols": cols}, f"{OUT}/models/{tag}_fold{f}.joblib")
    return p, folds


def report(c, label, save=False):
    y, w, h = c["true_alarm"].to_numpy(), c["weight"].to_numpy(), c["harpnum"].to_numpy()
    pA, folds = cv(c, A_COLS, "A", save)
    pB, _ = cv(c, B_COLS, "B", save)
    rows = []
    for f in list(range(K)) + ["pooled"]:
        m = np.ones(len(c), bool) if f == "pooled" else folds == f
        rows.append({"fold": f, "episodes": int(m.sum()), "true": int(y[m].sum()), "HARPs": len(set(h[m])),
                     "true_HARPs": len(set(h[m & (y == 1)])), "weight_sum": w[m].sum(),
                     "logloss_A": wlogloss(y[m], pA[m], w[m]), "logloss_B": wlogloss(y[m], pB[m], w[m]),
                     "AUC_A": roc_auc_score(y[m], pA[m], sample_weight=w[m]) if 0 < y[m].sum() < m.sum() else np.nan,
                     "AUC_B": roc_auc_score(y[m], pB[m], sample_weight=w[m]) if 0 < y[m].sum() < m.sum() else np.nan})
    t = pd.DataFrame(rows); t["delta_A_minus_B"] = t["logloss_A"] - t["logloss_B"]
    harps = np.unique(h); idx_of = {x: np.where(h == x)[0] for x in harps}
    rng, d = np.random.RandomState(SEED), []
    for _ in range(NBOOT):
        ix = np.concatenate([idx_of[x] for x in rng.choice(harps, len(harps), replace=True)])
        d.append(wlogloss(y[ix], pA[ix], w[ix]) - wlogloss(y[ix], pB[ix], w[ix]))
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"\n{label}: {len(c)} episodes, {int(y.sum())} true, {len(harps)} HARPs "
          f"({len(set(h[y == 1]))} with a true episode); weighted true {np.sum(w * y):.2f} of {w.sum():.2f}")
    print(t.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"pooled log-loss(A) - log-loss(B) = {t.iloc[-1]['delta_A_minus_B']:.4f}, "
          f"HARP-bootstrap 95% CI [{lo:.4f}, {hi:.4f}] ({NBOOT} resamples)")
    return t, (lo, hi), pA, pB


if __name__ == "__main__":
    # ---------------------------------------------------------------- primary + sensitivity
    t_pri, ci_pri, pA, pB = report(coh, "PRIMARY cohort (T1-T4, all eligible episodes, region-weighted)", save=True)
    first = coh[coh["first_eligible"]].copy(); first["weight"] = 1.0
    t_sen, ci_sen, _, _ = report(first.reset_index(drop=True), "SENSITIVITY: first eligible episode per region")
    t_pri.to_csv(f"{OUT}/cv_primary.csv", index=False); t_sen.to_csv(f"{OUT}/cv_first_episode.csv", index=False)
    coh.assign(p_A=pA, p_B=pB, fold=folds_for(coh)).to_csv(f"{OUT}/oof_cohort_dev.csv", index=False)

    # ---------------------------------------------------------------- score-matched pairs (supporting)
    caliper = 0.2 * coh["score"].std(ddof=1)                             # pre-registered: from gate scores only
    rng = np.random.RandomState(SEED)
    tru = coh[coh["true_alarm"] == 1].iloc[rng.permutation((coh["true_alarm"] == 1).sum())]
    fal = coh[coh["true_alarm"] == 0].copy()
    used, pairs = set(), []
    for _, e in tru.iterrows():
        cand = fal[(fal["harpnum"] != e["harpnum"]) & ~fal.index.isin(used)]
        dist = (cand["score"] - e["score"]).abs()
        if len(dist) and dist.min() <= caliper:
            j = dist.idxmin(); used.add(j)
            pairs.append({"true_harp": e["harpnum"], "false_harp": fal.loc[j, "harpnum"],
                          "score_diff": e["score"] - fal.loc[j, "score"],
                          **{f"d_{s}": e[s] - fal.loc[j, s] for s in ["rel_slope_usflux", "rel_slope_totusjh"]}})
    pr = pd.DataFrame(pairs)
    pr.to_csv(f"{OUT}/matched_pairs_dev.csv", index=False)
    print(f"\nSCORE-MATCHED PAIRS: caliper {caliper:.4f} (0.2 x SD of gate score over {len(coh)} cohort episodes); "
          f"{len(pr)} pairs from {len(tru)} true episodes ({len(tru) - len(pr)} unmatched); "
          f"max |score diff| {pr['score_diff'].abs().max():.4f}; {pr['true_harp'].nunique()} true HARPs")
    g = {x: np.where(pr["true_harp"].to_numpy() == x)[0] for x in pr["true_harp"].unique()}
    keys = np.array(list(g))
    for s in ["rel_slope_usflux", "rel_slope_totusjh"]:
        v = pr[f"d_{s}"].to_numpy()
        bs = [v[np.concatenate([g[x] for x in rng.choice(keys, len(keys), replace=True)])].mean() for _ in range(NBOOT)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        print(f"  {s:18s} paired diff (true - false): mean {v.mean():.3e}  median {np.median(v):.3e}  "
              f"95% CI (mean, clustered by true HARP) [{lo:.3e}, {hi:.3e}]")

    # ---------------------------------------------------------------- delayed vs true (exploratory, descriptive)
    grp = np.where(coh["true_alarm"] == 1, "true", np.where(coh["delayed"] == 1, "delayed", "other false"))
    print("\nEXPLORATORY (descriptive only): weighted mean [median] by group")
    for name in ["true", "delayed", "other false"]:
        c = coh[grp == name]; w = c["weight"]
        cells = "  ".join(f"{s}: {np.average(c[s], weights=w):.3g} [{c[s].median():.3g}]"
                          for s in ["score", "n_C", "n_M", "n_X", "rel_slope_usflux", "rel_slope_totusjh"])
        print(f"  {name:11s} episodes {len(c):3d}  HARPs {c['harpnum'].nunique():3d}  weight {w.sum():6.2f}  {cells}")

    json.dump({"primary_ci": ci_pri, "first_episode_ci": ci_sen, "caliper": caliper}, open(f"{OUT}/stage4_result.json", "w"))
