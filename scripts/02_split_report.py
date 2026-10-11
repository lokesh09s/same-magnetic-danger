"""Report the dataset under the FROZEN split (frozen/split.csv is read, never written).
Items 7-9 of decision K2: per set x subset table, the fallback rule, and the thinned training set."""
import hashlib
import pandas as pd

SPLIT = "frozen/split.csv"
print(f"{SPLIT} sha256 {hashlib.sha256(open(SPLIT, 'rb').read()).hexdigest()}")
lab = pd.read_csv("data/labelled_20100501_20250101.csv", low_memory=False)
lab = lab.merge(pd.read_csv(SPLIT), on="harpnum", how="inner")      # 2020-only HARPs drop out here
lab = lab[~lab["t_rec_utc"].str.startswith("2020")]                 # decision L: 2020 rows excluded
subsets = {"single": lambda d: d["noaa_ar_count"] == 1, "<=2": lambda d: d["noaa_ar_count"] <= 2,
           "all": lambda d: d["noaa_ar_count"] > 0}


def table(d, title, np_col=False):
    print(f"\n{title}")
    print("set    subset   rows      pos_rows  HARPs  pos_HARPs" + ("   N/P" if np_col else ""))
    for s in ["train", "val", "test"] if "set" in d else [None]:
        g0 = d if s is None else d[d["set"] == s]
        for name, f in subsets.items():
            g = g0[f(g0)]
            p = int(g["flared_M1_next_24h"].sum())
            extra = f"  {(len(g) - p) / p:5.1f}" if np_col and p else ""
            print(f"{s or 'dev':5s}  {name:6s}  {len(g):7d}  {p:8d}  {g['harpnum'].nunique():5d}  "
                  f"{g.loc[g['flared_M1_next_24h'] == 1, 'harpnum'].nunique():9d}{extra}")


table(lab, "7. per set x subset (hourly), 2022 INCLUDED -- sensitivity analysis only (decision L2)")
primary = lab[~lab["t_rec_utc"].str.startswith("2022")]            # decision L2: primary test = 2021, 2023, 2024
table(primary, "7b. per set x subset (hourly), PRIMARY -- 2022 excluded (decision L2)")

test = primary[primary["set"] == "test"]
n_single = test.loc[(test["noaa_ar_count"] == 1) & (test["flared_M1_next_24h"] == 1), "harpnum"].nunique()
print(f"\n8. fallback rule on the PRIMARY test: positive test HARPs, single-region = {n_single} -> "
      + ("single-region (>= 40)" if n_single >= 40 else "<= 2 regions (< 40)"))

dev = lab[lab["set"].isin(["train", "val"])]
th = dev[dev["t_rec_tai"].str[11:13].astype(int).isin([4, 10, 16, 22])].drop(columns="set")
print(f"\n9. thinned dev (TAI hours 4,10,16,22): {len(dev)} -> {len(th)} rows ({len(th) / len(dev):.1%})")
table(th, "   per subset", np_col=True)
