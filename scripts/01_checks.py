"""Sanity checks on a labelled SHARP file.  Usage: python checks.py [START END]"""
import sys, re
import numpy as np, pandas as pd
import flares, swpc

START = sys.argv[1] if len(sys.argv) > 1 else "2014-01-01"
END   = sys.argv[2] if len(sys.argv) > 2 else "2014-02-01"
TAG   = f"{START}_{END}".replace("-", "")
lab = pd.read_csv(f"data/labelled_{TAG}.csv", parse_dates=["t_rec_utc"])
raw = pd.read_csv(f"data/raw_sharp_{TAG}.csv")
print(f"labelled: data/labelled_{TAG}.csv  ({len(lab)} rows)   raw: {len(raw)} rows")

results = {}
def verdict(n, ok, why=""):
    results[n] = ok
    print(f"\n>>> CHECK {n}: {'PASS' if ok else '*** FAIL ***'} {why}")

# ---------------------------------------------------------------- CHECK 1
print("\n" + "=" * 70 + "\nCHECK 1  label correctness against a known X-class event")
fl, _ = swpc.fetch(lab["t_rec_utc"].min() - pd.Timedelta(hours=48),       # label source (decision A)
                   lab["t_rec_utc"].max() + pd.Timedelta(hours=24), verbose=False)
xf = fl[fl["goes_class"].str.startswith("X")].dropna(subset=["noaa_ar"]).sort_values("start")
print(xf.to_string(index=False))
# the first X flare with >= 1 labelled row in [t0-24h, t0) of a HARP containing its region -- the flare list is padded
# 48 h before the period, so the very first X flare can precede every labelled row (e.g. 2024-12-30 for a 2025 file)
def testable(ev):
    ar_, t0_ = int(ev["noaa_ar"]), ev["start"]
    hs = lab[lab["noaa_ars"].astype(str).str.split(",").apply(lambda L: str(ar_) in [x.strip() for x in L])]
    return ((hs["t_rec_utc"] >= t0_ - pd.Timedelta(hours=24)) & (hs["t_rec_utc"] < t0_)).any()
skipped = 0
for _, ev in xf.iterrows():
    if testable(ev):
        break
    skipped += 1
print(f"(skipped {skipped} earlier X flare(s) with no labelled row in their 24-h window)")
ar = int(ev["noaa_ar"]); t0 = ev["start"]
print(f"\nX flare: {ev['goes_class']} at {t0} UTC in NOAA {ar}")

has = lab[lab["noaa_ars"].astype(str).str.split(",").apply(lambda L: str(ar) in [x.strip() for x in L])]
harps = sorted(has["harpnum"].unique())
print(f"HARPNUM(s) containing NOAA {ar}: {harps}")
h = next(x for x in harps if ((lab["harpnum"] == x) & (lab["t_rec_utc"] >= t0 - pd.Timedelta(hours=24))
                                & (lab["t_rec_utc"] < t0)).any())
w = lab[(lab["harpnum"] == h) & (lab["t_rec_utc"] >= t0 - pd.Timedelta(hours=36))
                              & (lab["t_rec_utc"] <= t0 + pd.Timedelta(hours=6))]
w = w.sort_values("t_rec_utc")
print(f"\nHARP {h}, t0-36h .. t0+6h:")
for _, r in w.iterrows():
    dt = (r["t_rec_utc"] - t0).total_seconds() / 3600
    print(f"  {r['t_rec_utc']}  t0{dt:+6.1f}h   flared_M1_next_24h={r['flared_M1_next_24h']}")

# the X flare alone must make every row in [t0-24h, t0) positive
pre = w[(w["t_rec_utc"] >= t0 - pd.Timedelta(hours=24)) & (w["t_rec_utc"] < t0)]
early = w[w["t_rec_utc"] < t0 - pd.Timedelta(hours=24)]
ok1 = len(pre) > 0 and (pre["flared_M1_next_24h"] == 1).all()
print(f"\n  rows in [t0-24h, t0): {len(pre)}, all labelled 1 -> {ok1}")
print(f"  rows before t0-24h: {len(early)}, labelled 1: {int(early['flared_M1_next_24h'].sum())}"
      f"  (non-zero is fine only if other M1+ flares fall in their own windows)")
verdict(1, ok1, "" if ok1 else "the 24h window or the NOAA join is broken -- STOP, downstream data is worthless")

# ---------------------------------------------------------------- CHECK 2
print("\n" + "=" * 70 + "\nCHECK 2  feature sanity: USFLUX / TOTUSJH by label")
ok2 = True
for f in ["usflux", "totusjh"]:
    g = lab.groupby("flared_M1_next_24h")[f]
    print(f"\n{f}:")
    print(g.describe()[["count", "mean", "50%", "min", "max"]].to_string())
    med0, med1 = g.median()[0], g.median()[1]
    print(f"  median ratio positive/negative = {med1/med0:.2f}x")
    ok2 &= med1 > med0
verdict(2, ok2, "" if ok2 else "positives do not skew higher -- labelling is wrong")

# ---------------------------------------------------------------- CHECK 3
print("\n" + "=" * 70 + "\nCHECK 3  independent sample size")
n = lab.groupby("harpnum").size()
print(f"  total rows              : {len(lab)}")
print(f"  distinct HARPNUMs       : {lab['harpnum'].nunique()}")
print(f"  rows per HARPNUM        : mean {n.mean():.1f}  median {n.median():.0f}  min {n.min()}  max {n.max()}")
pos_h = lab.groupby("harpnum")["flared_M1_next_24h"].max()
print(f"  HARPNUMs with >=1 positive row: {int(pos_h.sum())} of {len(pos_h)}")
verdict(3, True, "(descriptive)")

# ---------------------------------------------------------------- CHECK 4
print("\n" + "=" * 70 + "\nCHECK 4  what are the missing-mapping rows?")
r = raw.copy(); r.columns = [c.lower() for c in r.columns]
r["usflux"] = pd.to_numeric(r["usflux"], errors="coerce")
miss = r["noaa_ars"].isna() | (r["noaa_ars"].astype(str).str.strip().isin(["", "nan", "MISSING"]))
print(f"  missing-mapping rows: {miss.sum()} / {len(r)} ({miss.mean():.1%})")
d = r.groupby(miss)["usflux"].describe()[["count", "mean", "50%", "max"]]
d.index = ["mapped", "missing"]
print(d.to_string())
mm, md = r.loc[miss, "usflux"].median(), r.loc[~miss, "usflux"].median()
big = (r.loc[miss, "usflux"] > md).mean()
print(f"  median USFLUX  missing {mm:.3e}  vs mapped {md:.3e}   ratio {mm/md:.3f}")
print(f"  fraction of missing-mapping rows above the mapped median: {big:.1%}")
ok4 = mm < md
verdict(4, ok4, "missing-mapping HARPs are systematically smaller" if ok4
        else "missing-mapping rows include large regions -- we are dropping real data, reconsider")

# ---------------------------------------------------------------- CHECK 5
print("\n" + "=" * 70 + "\nCHECK 5  per-year flare->HARP join coverage")
import os, join_report
if os.path.exists(join_report.OUT):
    jr = pd.read_csv(join_report.OUT)
    print(f"(using cached {join_report.OUT} -- delete it to recompute)")
else:
    jr = join_report.build(); jr.to_csv(join_report.OUT, index=False)
bad = join_report.show(jr)
ok5 = len(bad) == 0
verdict(5, ok5, "" if ok5 else
        f"years below the {join_report.THRESHOLD:.0%} usable-region threshold: {list(bad['year'])} "
        "-- their labels are false negatives, not quiet Sun")

print("\n" + "=" * 70)
print("SUMMARY: " + "  ".join(f"check{k}={'PASS' if v else 'FAIL'}" for k, v in results.items()))
sys.exit(0 if all(results.values()) else 1)
