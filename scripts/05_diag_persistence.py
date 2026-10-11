"""READ-ONLY (decisions.md 2026-09-23): persistence baseline P vs the frozen gate, test 2021/2023/2024, single-region, K2.
P = 1 if an M1+ (K2 SWPC) from the same NOAA region(s) started in (t-24h, t]. Stage 5 units: hour = scorable rows;
region = one entry per HARP (alarm if any alarm hour, positive if any positive hour). HARP bootstrap 1,000, seed 20260921."""
import hashlib, json
import numpy as np, pandas as pd, joblib
import swpc

SPEC = json.load(open("frozen/frozen_spec.json")); H = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
assert H("frozen/frozen_spec.json").startswith("1d205068") and H(SPEC["data"]["labelled_file"]) == SPEC["data"]["labelled_sha256"]
F, THR = SPEC["gate"]["features"], SPEC["gate"]["threshold"]
split = pd.read_csv("frozen/split.csv")
lab = pd.read_csv(SPEC["data"]["labelled_file"], parse_dates=["t_rec_utc"], low_memory=False)
d = lab[lab.harpnum.isin(split.loc[split.set == "test", "harpnum"]) & lab.t_rec_utc.dt.year.isin([2021, 2023, 2024])
        & (lab.noaa_ar_count == 1)]
d = d[~d[F].isna().any(axis=1)].reset_index(drop=True)
X = d[F].to_numpy(float); dv = np.zeros(len(d))
for v in SPEC["gate"]["fold_models"].values():
    assert H(v["path"]) == v["sha256"]; g = joblib.load(v["path"]); dv += g["model"].decision_function((X - g["median"]) / g["sd"])
d["gate"] = dv / 5 >= THR

fl, _ = swpc.load(pd.Timestamp("2020-12-29"), pd.Timestamp("2025-01-01"))
m1 = fl[fl.flux >= 1e-5].dropna(subset=["noaa_ar"]); by = {int(a): np.sort(g.start.values) for a, g in m1.groupby("noaa_ar")}


def recent(row):
    t1 = np.datetime64(row.t_rec_utc); t0 = t1 - np.timedelta64(24, "h")
    for a in str(row.noaa_ars).split(","):
        s = by.get(int(a)) if a.strip().isdigit() else None
        if s is not None and ((s > t0) & (s <= t1)).any():
            return True
    return False


d["P"] = d.apply(recent, axis=1)
y, h = d.flared_M1_next_24h.to_numpy(), d.harpnum.to_numpy()


def cont(y, a):
    tp, fp, fn, tn = (int(x) for x in ((a & (y == 1)).sum(), (a & (y == 0)).sum(), (~a & (y == 1)).sum(), (~a & (y == 0)).sum()))
    tpr = tp / (tp + fn) if tp + fn else np.nan; fpr = fp / (fp + tn) if fp + tn else np.nan
    return dict(TP=tp, FP=fp, FN=fn, TN=tn, TSS=tpr - fpr, TPR=tpr, FPR=fpr,
                precision=tp / (tp + fp) if tp + fp else np.nan, FAR=fp / (tp + fp) if tp + fp else np.nan)


def boot(groups, stat):
    keys = np.array(list(groups)); rng = np.random.RandomState(20260921); v = []
    for _ in range(1000):
        x = stat(np.concatenate([groups[k] for k in rng.choice(keys, len(keys), replace=True)]))
        if np.isfinite(x): v.append(x)
    return np.percentile(v, [2.5, 97.5])


rows = []
grp = {k: np.where(h == k)[0] for k in np.unique(h)}
r = d.groupby("harpnum").agg(y=("flared_M1_next_24h", "max"), gate=("gate", "max"), P=("P", "max"))
ry = r.y.to_numpy(); rg = {i: np.array([i]) for i in range(len(r))}
for name in ["gate", "P"]:
    a = d[name].to_numpy(); m = cont(y, a); ci = boot(grp, lambda ix: cont(y[ix], a[ix])["TSS"])
    rows.append(dict(predictor=name, level="hour", **m, TSS_lo=ci[0], TSS_hi=ci[1]))
    ra = r[name].to_numpy().astype(bool); m = cont(ry, ra); ci = boot(rg, lambda ix: cont(ry[ix], ra[ix])["TSS"])
    rows.append(dict(predictor=name, level="region", **m, TSS_lo=ci[0], TSS_hi=ci[1]))
t = pd.DataFrame(rows)
g0 = t[(t.predictor == "gate") & (t.level == "hour")].iloc[0]
assert abs(g0.TSS - 0.546719) < 1e-5 and abs(g0.FAR - 0.702106) < 1e-5, "gate does not reproduce Stage 5"
t.to_csv("data/stage5/persistence_vs_gate.csv", index=False)
pd.set_option("display.width", 250); print(t.round(4).to_string(index=False))
z = d[~d.P]; mz = cont(z.flared_M1_next_24h.to_numpy(), z.gate.to_numpy())
print(f"\ngate on hours with P = 0 (n {len(z)}, positives {mz['TP'] + mz['FN']}): TPR {mz['TPR']:.4f}, precision {mz['precision']:.4f}; "
      f"TP {mz['TP']} FP {mz['FP']} FN {mz['FN']} TN {mz['TN']}")
o = d[d.P]; mo = cont(o.flared_M1_next_24h.to_numpy(), o.gate.to_numpy())
print(f"(for reference, hours with P = 1: n {len(o)}, TPR {mo['TPR']:.4f}, precision {mo['precision']:.4f})")
print(f"P = 1 hours: {int(d.P.sum())} of {len(d)}; history_incomplete rows in set: {int(d.history_incomplete.sum())}")
