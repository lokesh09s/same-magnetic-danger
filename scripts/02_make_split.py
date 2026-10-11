"""HARP-level train / val / test split (decisions L, M, N -- user, 2026-09-21).

  2020               : excluded entirely (L)
  test               : every HARP with rows in 2021-2024 -- untouched until final evaluation
  train + val        : HARPs with rows in 2010-2019
  val                : 25% of the 2010-2019 HARPs, fixed seed, stratified at HARP level on
                       (positive in single-region rows | positive only in multi-region rows | negative)
                       so validation contains positive HARPs for the primary subset.
A HARP is assigned by the years of its rows. A HARP with rows in both 2010-2019 and 2021-2024 would
break the split, so it raises rather than being assigned silently.
"""
import hashlib
import numpy as np, pandas as pd

SEED = 20260921
VAL_FRAC = 0.25
LAB = "data/labelled_20100501_20250101.csv"
OUT = "frozen/split.csv"     # tracked in git; data/ is not

lab = pd.read_csv(LAB, parse_dates=["t_rec_utc"], low_memory=False)
lab["year"] = lab["t_rec_utc"].dt.year
n0 = len(lab)
lab = lab[lab["year"] != 2020]
print(f"rows: {n0} -> {len(lab)} after excluding 2020 (decision L, -{n0 - len(lab)})")

# ---- period of each HARP from its rows
period = lab.assign(p=np.where(lab["year"] <= 2019, "early", "late")).groupby("harpnum")["p"].unique()
both = period[period.apply(len) > 1]
assert both.empty, f"HARPs with rows in both 2010-2019 and 2021-2024: {list(both.index)}"
period = period.str[0]

# ---- stratify the early HARPs
early = lab[lab["harpnum"].isin(period[period == "early"].index)]
pos_single = early[(early["noaa_ar_count"] == 1) & (early["flared_M1_next_24h"] == 1)]["harpnum"].unique()
pos_any = early[early["flared_M1_next_24h"] == 1]["harpnum"].unique()
harps = np.sort(early["harpnum"].unique())
stratum = pd.Series("negative", index=harps)
stratum[np.isin(harps, pos_any)] = "positive_multi_only"
stratum[np.isin(harps, pos_single)] = "positive_single"

rng = np.random.RandomState(SEED)
val = []
for name in ["positive_single", "positive_multi_only", "negative"]:     # fixed order -> reproducible
    members = np.sort(stratum[stratum == name].index.values)
    k = int(round(VAL_FRAC * len(members)))
    val += list(rng.permutation(members)[:k])
    print(f"stratum {name:20s}: {len(members):4d} HARPs -> {k:3d} to val")

split = pd.Series("train", index=harps, name="set")
split[np.isin(harps, val)] = "val"
split = pd.concat([split, pd.Series("test", index=np.sort(period[period == "late"].index.values), name="set")])
split.index.name = "harpnum"

# ---- the invariant
assert split.index.is_unique, "a HARPNUM appears in more than one set"
assert set(split.index) == set(lab["harpnum"]), "split does not cover every HARP"
split.sort_index().to_csv(OUT)
digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
print(f"\nwrote {OUT}: {len(split)} HARPs  " + str(split.value_counts().to_dict()))
print(f"SHA-256 {digest}")
print("assert passed: no HARPNUM in more than one set; every HARP assigned")

# ---- per set x region subset
lab = lab.join(split, on="harpnum")
subsets = {"single": lab["noaa_ar_count"] == 1, "le2": lab["noaa_ar_count"] <= 2,
           "all": pd.Series(True, index=lab.index)}
print("\nset    subset   rows      pos_rows  HARPs  pos_HARPs  pos_rate")
for s in ["train", "val", "test"]:
    for name, m in subsets.items():
        g = lab[(lab["set"] == s) & m]
        pos = g[g["flared_M1_next_24h"] == 1]
        print(f"{s:5s}  {name:6s}  {len(g):7d}  {len(pos):8d}  {g['harpnum'].nunique():5d}  "
              f"{pos['harpnum'].nunique():9d}  {len(pos) / max(len(g), 1):7.2%}")
