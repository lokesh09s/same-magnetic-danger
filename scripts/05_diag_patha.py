"""PATH A -- "phantom false alarms" (descriptive; NOT a test of the FINAL primary result; decisions.md 2026-09-22).
Frozen 10-feature gate, frozen threshold, primary subset (single-region). Three label sets on the same rows:
  HEK = archived HEK/SWPC labels, classes as reported (old operational scale to 2019, GOES-16 true scale 2020+)
  K   = SWPC originals, old operational scale (diagnostic file 85b88518...)
  K2  = SWPC originals, true scale (final, frozen)
Same-scale pairs: 2010-2019 HEK vs K; 2021-2024 HEK vs K2 (HEK carries GOES-16 fluxes as reported, as K2 does).
Scores: dev = frozen Stage 2 out-of-fold scores; test = mean of the 5 frozen fold models (as Stage 5).
Episodes: T1-T4 (cohort.py, unchanged) under K2; each episode relabelled at its t with HEK and K."""
import hashlib, json
import numpy as np, pandas as pd, joblib
import cohort, swpc

SPEC = json.load(open("frozen/frozen_spec.json"))
H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
assert H("frozen/frozen_spec.json").startswith("1d205068") and H("src/cohort.py") == SPEC["cohort"]["code_sha256"]
F, THR, SEED = SPEC["gate"]["features"], SPEC["gate"]["threshold"], 20260921
K = ["harpnum", "t_rec_tai"]
rd = lambda p, c: pd.read_csv(p, usecols=K + c, low_memory=False).drop_duplicates(K)   # month-boundary duplicates

k2 = pd.read_csv(SPEC["data"]["labelled_file"], parse_dates=["t_rec_utc"], low_memory=False)
lab = k2.merge(rd("data/labels_hek/labelled_hek_20100501_20250101.csv", ["flared_M1_next_24h"])
               .rename(columns={"flared_M1_next_24h": "y_HEK"}), on=K, how="inner", validate="one_to_one") \
        .merge(rd("data/diag/labelled_swpc_K.csv", ["flared_M1_next_24h"])
               .rename(columns={"flared_M1_next_24h": "y_K"}), on=K, how="inner", validate="one_to_one")
lab["y_K2"] = lab["flared_M1_next_24h"]
print(f"rows: K2 {len(k2)}; in all three label sets {len(lab)}")
split = pd.read_csv("frozen/split.csv")
dev_h, test_h = set(split.loc[split.set.isin(["train", "val"]), "harpnum"]), set(split.loc[split.set == "test", "harpnum"])

# ---------------------------------------------------------------- frozen gate scores, primary subset
oof = pd.read_csv("data/stage2/oof_scores_dev.csv", usecols=K + ["score"])
dev = lab[lab.harpnum.isin(dev_h) & (lab.noaa_ar_count == 1)].merge(oof, on=K, how="inner")
test = lab[lab.harpnum.isin(test_h) & (lab.noaa_ar_count == 1) & lab.t_rec_utc.dt.year.between(2021, 2024)].copy()
test = test[~test[F].isna().any(axis=1)].reset_index(drop=True)
X = test[F].to_numpy(float); dv = np.zeros(len(test))
for v in SPEC["gate"]["fold_models"].values():
    assert H(v["path"]) == v["sha256"]
    g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
test["score"] = dv / len(SPEC["gate"]["fold_models"])


def cont(y, a):
    tp, fn, fp, tn = (int(x) for x in ((a & (y == 1)).sum(), (~a & (y == 1)).sum(), (a & (y == 0)).sum(), (~a & (y == 0)).sum()))
    tpr = tp / (tp + fn) if tp + fn else np.nan; fpr = fp / (fp + tn) if fp + tn else np.nan
    return dict(TSS=tpr - fpr, FAR=fp / (tp + fp) if tp + fp else np.nan, precision=tp / (tp + fp) if tp + fp else np.nan,
                pos=tp + fn, n=tp + fn + fp + tn)


def boot(groups, stat, n=1000):
    keys = np.array(list(groups)); rng = np.random.RandomState(SEED); v = []
    for _ in range(n):
        x = stat(np.concatenate([groups[k] for k in rng.choice(keys, len(keys), replace=True)]))
        if np.isfinite(x):
            v.append(x)
    return np.percentile(v, [2.5, 97.5])


rows = []
for per, d in [("2010-2019 (dev, OOF scores)", dev), ("2021-2024 (test HARPs, frozen fold models)", test)]:
    h = d.harpnum.to_numpy(); a = d.score.to_numpy() >= THR
    grp = {x: np.where(h == x)[0] for x in np.unique(h)}
    for ls in ["HEK", "K", "K2"]:
        y = d[f"y_{ls}"].to_numpy()
        m = cont(y, a); ci = boot(grp, lambda ix: cont(y[ix], a[ix])["TSS"])
        rows.append(dict(period=per, labels=ls, level="hour", **m, TSS_lo=ci[0], TSS_hi=ci[1]))
        r = pd.DataFrame({"h": h, "y": y, "a": a}).groupby("h").max()
        ry, ra = r.y.to_numpy(), r.a.to_numpy(); rg = {i: np.array([i]) for i in range(len(r))}
        m = cont(ry, ra); ci = boot(rg, lambda ix: cont(ry[ix], ra[ix])["TSS"])
        rows.append(dict(period=per, labels=ls, level="region", **m, TSS_lo=ci[0], TSS_hi=ci[1]))
g = pd.DataFrame(rows); g.to_csv("data/diag/patha_gate.csv", index=False)
print(g.round(4).to_string(index=False))

# ---------------------------------------------------------------- episodes (T1-T4 under K2), relabelled at t
missing = swpc.label_missing_days()
c_dev = pd.read_csv("data/stage3/cohort_dev.csv", parse_dates=["t"])                      # frozen dev cohort (547)
full = k2[k2.harpnum.isin(set(test.harpnum))]
c_test, _, _ = cohort.build(test[["harpnum", "t_rec_utc", "score"]].merge(test.drop(columns="score"),
                            on=["harpnum", "t_rec_utc"]), full, THR, missing)
lab_t = lab.set_index(["harpnum", "t_rec_utc"])
ep = []
for per, c in [("2010-2019", c_dev), ("2021-2024", c_test)]:
    x = c[["harpnum", "t", "true_alarm"]].copy()
    ix = pd.MultiIndex.from_arrays([x.harpnum, x.t])
    for ls in ["HEK", "K", "K2"]:
        x[f"true_{ls}"] = lab_t[f"y_{ls}"].reindex(ix).to_numpy()
    assert (x.true_K2 == x.true_alarm).all(), "K2 relabel must reproduce the cohort's own labels"
    x["period"], x["year"] = per, x.t.dt.year
    ep.append(x)
ep = pd.concat(ep)
ep.to_csv("data/diag/patha_episodes.csv", index=False)
print(f"episodes with a label in all three sets: {ep[['true_HEK', 'true_K']].notna().all(axis=1).sum()} of {len(ep)}")


def phantom(a, b):
    """episodes FALSE under label set a but TRUE under b, per year, and as % of a's false alarms"""
    t = ep.dropna(subset=[f"true_{a}", f"true_{b}"]).groupby("year").apply(
        lambda d: pd.Series({"episodes": len(d), f"false_{a}": int((d[f"true_{a}"] == 0).sum()),
                             "phantom": int(((d[f"true_{a}"] == 0) & (d[f"true_{b}"] == 1)).sum()),
                             "reverse": int(((d[f"true_{a}"] == 1) & (d[f"true_{b}"] == 0)).sum())}), include_groups=False)
    t.loc["all"] = t.sum()
    t["phantom_pct_of_false"] = (100 * t.phantom / t[f"false_{a}"]).round(1)
    return t


for a, b, note in [("HEK", "K2", "HEK -> final (both causes)"),
                   ("HEK", "K", "same scale in 2010-2019 (region/catalogue only)"),
                   ("K", "K2", "scale change only (SWPC both)")]:
    t = phantom(a, b); t.to_csv(f"data/diag/patha_phantom_{a}_vs_{b}.csv")
    print(f"\n{a} false -> {b} true ({note}); 'reverse' = {a} true, {b} false")
    print(t.to_string())
