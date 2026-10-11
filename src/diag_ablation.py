"""DIAGNOSTIC ABLATION (user, pre-declared diagnostic).  Dev 2010-2019 only; test HARPs never loaded.
Same SVM and the same 10 features as the gate.  One factor changed per run (D1-D5), then all together (D6).
Folds are held fixed from the Stage 2 baseline; HARPs that exist only in the +-68 deg variants are dealt into
folds by the same stratified seeded procedure, among themselves."""
import json
import numpy as np, pandas as pd
from joblib import Parallel, delayed
from sklearn.svm import SVC
from sklearn.metrics import roc_curve
import swpc

F = ["totusjh", "totpot", "totusjz", "absnjzh", "savncpp", "usflux", "area_acr", "meanpot", "r_value", "shrgt45"]
SVM = dict(kernel="rbf", C=4.0, gamma=0.075, tol=1e-8, class_weight={1: 2.0, 0: 1.0})
SEED, K, NP_BC = 20260921, 5, 5000 / 303            # B&C p.7: 303 positives, 5000 random negatives
split = pd.read_csv("frozen/split.csv")
TEST = set(split.loc[split["set"] == "test", "harpnum"])
BASE_FOLDS = {int(k): v for k, v in json.load(open("data/stage2/stage2_result.json"))["folds"].items()}
S = "scratch"


def load(path, primary_only=True):
    d = pd.read_csv(path, low_memory=False, parse_dates=["t_rec_utc"])
    d = d[(d["t_rec_utc"].dt.year <= 2019) & ~d["harpnum"].isin(TEST)]
    d = d.drop_duplicates(["harpnum", "t_rec_tai"])
    if primary_only:
        d = d[d["noaa_ar_count"] == 1]                               # primary subset throughout
    d = d[~d[F].isna().any(axis=1)]                                  # unscorable rows (user rule)
    assert not set(d["harpnum"]) & TEST
    return d.reset_index(drop=True)


_fold_cache = {}


def base_folds(seed):
    """Stage 2 fold procedure (3 HARP strata from K2 labels, shuffled per stratum, dealt round-robin) with a given
    seed.  seed == SEED reproduces the Stage 2 folds exactly (asserted)."""
    if seed not in _fold_cache:
        d = load("data/labelled_20100501_20250101.csv", primary_only=False)
        y, prim = d["flared_M1_next_24h"].to_numpy(), (d["noaa_ar_count"] == 1).to_numpy()
        ps, pa = set(d.loc[prim & (y == 1), "harpnum"]), set(d.loc[y == 1, "harpnum"])
        harps = np.sort(d["harpnum"].unique())
        st = {h: "positive_single" if h in ps else ("positive_multi_only" if h in pa else "negative") for h in harps}
        rng, out = np.random.RandomState(seed), {}
        for name in ["positive_single", "positive_multi_only", "negative"]:
            for i, h in enumerate(rng.permutation(np.sort([h for h in harps if st[h] == name]))):
                out[int(h)] = i % K
        if seed == SEED:
            assert out == BASE_FOLDS, "fold procedure does not reproduce Stage 2"
        _fold_cache[seed] = out
    return _fold_cache[seed]


def harp_folds(d, seed=SEED):
    """Baseline fold for known HARPs; unknown HARPs (only in +-68 variants) dealt stratified, seeded."""
    base = base_folds(seed)
    new = sorted(set(d["harpnum"]) - set(base))
    pos = set(d.loc[d["flared_M1_next_24h"] == 1, "harpnum"])
    rng, extra = np.random.RandomState(seed), {}
    for grp in [[h for h in new if h in pos], [h for h in new if h not in pos]]:
        for i, h in enumerate(rng.permutation(grp)):
            extra[h] = i % K
    return d["harpnum"].map({**base, **extra}).to_numpy()


def row_folds(n, seed=SEED):
    return np.random.RandomState(seed).permutation(n) % K           # random row-level split (D5)


def bc_samples(d, scale):
    """B&C p.7 sample definition: one positive per M1+ flare at exactly 24 h before its GOES peak; random quiet
    rows as negatives at N/P = 5000/303.  Positive row = the HARP's row within 30 min of peak - 24 h."""
    prev, swpc.FLARE_SCALE = swpc.FLARE_SCALE, scale                 # the flare list must match the label scale
    try:
        fl, _ = swpc.fetch(d["t_rec_utc"].min(), d["t_rec_utc"].max() + pd.Timedelta(hours=48), verbose=False)
    finally:
        swpc.FLARE_SCALE = prev
    n_k2_check = int((fl["flux"] >= 1e-5).sum())
    m1 = fl[(fl["flux"] >= 1e-5) & fl["peak"].notna()]
    d = d.sort_values("t_rec_utc")
    d["ars"] = d["noaa_ars"].astype(str).str.split(",").apply(lambda v: {int(x) for x in v if x.strip().isdigit()})
    pos_idx, missed = [], 0
    for _, f in m1.iterrows():
        tgt = f["peak"] - pd.Timedelta(hours=24)
        c = d[(d["t_rec_utc"] - tgt).abs() <= pd.Timedelta(minutes=30)]
        c = c[c["ars"].apply(lambda s: f["noaa_ar"] in s)]
        if len(c):
            pos_idx.append(c.index[0])
        else:
            missed += 1
    pos_idx = sorted(set(pos_idx))
    neg_pool = d.index[(d["flared_M1_next_24h"] == 0)].difference(pos_idx)
    n_neg = min(int(round(NP_BC * len(pos_idx))), len(neg_pool))
    neg_idx = np.random.RandomState(SEED).choice(neg_pool, n_neg, replace=False)
    out = d.loc[pos_idx + list(neg_idx)].drop(columns="ars").copy()
    out["flared_M1_next_24h"] = [1] * len(pos_idx) + [0] * n_neg      # positive = the flare-anchored sample
    info = f"[{scale}: {n_k2_check} M1+ flares in window] {len(pos_idx)} flare samples ({missed} M1+ flares with no matching single-region row), {n_neg} random negatives"
    return out.reset_index(drop=True), info


def run(d, folds, train_mask, thr_rule):
    y = d["flared_M1_next_24h"].to_numpy()
    X = d[F].to_numpy(float)

    def fit(f):
        tr = train_mask & (folds != f)
        med, sd = np.median(X[tr], axis=0), X[tr].std(axis=0)
        m = SVC(**SVM).fit((X[tr] - med) / sd, y[tr])
        te = folds == f
        return np.where(te)[0], m.decision_function((X[te] - med) / sd)
    s = np.empty(len(d))
    for idx, v in Parallel(n_jobs=3)(delayed(fit)(f) for f in range(K)):
        s[idx] = v
    if thr_rule == "zero":
        thr = 0.0
    else:
        fpr, tpr, th = roc_curve(y, s); thr = float(th[np.argmax(tpr - fpr)])
    a = s >= thr
    tpr = (a & (y == 1)).sum() / (y == 1).sum(); fpr = (a & (y == 0)).sum() / (y == 0).sum()
    return dict(TSS=tpr - fpr, TPR=tpr, FPR=fpr, threshold=thr, eval_rows=len(d), eval_pos=int(y.sum()),
                pos_HARPs=d.loc[y == 1, "harpnum"].nunique()), s


thin = lambda d: d["t_rec_tai"].str[11:13].astype(int).isin([4, 10, 16, 22]).to_numpy()


if __name__ == "__main__":
    rows = []

    # baseline + D1 (same scores, different threshold)
    base = load("data/labelled_20100501_20250101.csv")
    r, s = run(base, harp_folds(base), thin(base), "maxTSS"); rows.append(("baseline (Stage 2)", r))
    yb = base["flared_M1_next_24h"].to_numpy(); a = s >= 0.0
    tpr, fpr = (a & (yb == 1)).sum() / (yb == 1).sum(), (a & (yb == 0)).sum() / (yb == 0).sum()
    rows.append(("D1 threshold = decision value 0", {**r, "TSS": tpr - fpr, "TPR": tpr, "FPR": fpr, "threshold": 0.0}))

    d2 = load(f"{S}/labelled_K.csv")                                          # file 85b88518...
    rows.append(("D2 K labels (old scale)", run(d2, harp_folds(d2), thin(d2), "maxTSS")[0]))

    d3 = load("data/diag_K2_lon68/labelled_dev.csv")
    rows.append(("D3 longitude +-68 deg", run(d3, harp_folds(d3), thin(d3), "maxTSS")[0]))

    d4, info4 = bc_samples(base.copy(), "K2")
    r4 = run(d4, harp_folds(d4), np.ones(len(d4), bool), "maxTSS")[0]; rows.append(("D4 B&C samples (flare-24h + random neg, N/P 16.5)", r4))

    rows.append(("D5 random row-level split", run(base, row_folds(len(base)), thin(base), "maxTSS")[0]))

    d6src = load("data/diag_K_lon68/labelled_dev.csv")
    d6, info6 = bc_samples(d6src.copy(), "K")
    rows.append(("D6 all of D1-D5", run(d6, row_folds(len(d6)), np.ones(len(d6), bool), "zero")[0]))

    t = pd.DataFrame([{"run": n, **r} for n, r in rows])
    t.to_csv("data/diag/ablation.csv", index=False)
    print("D4 samples:", info4); print("D6 samples:", info6)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
