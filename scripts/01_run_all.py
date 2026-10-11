"""Run build_dataset.py over a long range in monthly chunks, resumably, then summarise.

Usage: python run_all.py [START END]      default 2010-05-01 2025-01-01
A chunk is skipped if its labelled CSV already exists, so re-running resumes.
"""
import sys, subprocess, time, os
import numpy as np, pandas as pd
from chunks import months

START = sys.argv[1] if len(sys.argv) > 1 else "2010-05-01"
END   = sys.argv[2] if len(sys.argv) > 2 else "2025-01-01"
PY    = sys.executable


chunks = months(START, END)
print(f"{len(chunks)} monthly chunks from {START} to {END}\n")
for i, (a, b) in enumerate(chunks, 1):
    tag = f"{a}_{b}".replace("-", "")
    done = f"data/labelled_{tag}.csv"
    if os.path.exists(done):
        print(f"[{i}/{len(chunks)}] {a} -> {b}  SKIP (already on disk)")
        continue
    print(f"[{i}/{len(chunks)}] {a} -> {b}  running...", flush=True)
    for attempt in range(1, 6):        # JSOC/HEK time out occasionally; retry before giving up
        r = subprocess.run([PY, "scripts/01_build_dataset.py", a, b], capture_output=True, text=True)
        if r.returncode == 0:
            break
        transient = any(k in r.stderr for k in ("timed out", "TimeoutError", "URLError",
                        "ConnectionResetError", "RemoteDisconnected", "IncompleteRead",
                        "Connection aborted", "ProtocolError", "503", "502"))
        print(f"          attempt {attempt} failed ({'transient' if transient else 'hard error'})", flush=True)
        if not transient or attempt == 5:
            print(r.stdout[-2000:]); print(r.stderr[-2000:])
            sys.exit(f"chunk {a}..{b} FAILED -- fix and re-run, completed chunks will be skipped")
        time.sleep(60 * attempt)
    tail = [l for l in r.stdout.splitlines() if "SHARP rows retrieved" in l or "positives:" in l]
    print("          " + " | ".join(t.strip() for t in tail), flush=True)

# ------------------------------------------------------------------ concatenate
TAG = f"{START}_{END}".replace("-", "")
raw = pd.concat([pd.read_csv(f"data/raw_sharp_{a}_{b}.csv".replace("-", ""), low_memory=False)
                 for a, b in chunks], ignore_index=True)
lab = pd.concat([pd.read_csv(f"data/labelled_{a}_{b}.csv".replace("-", ""), parse_dates=["t_rec_utc"],
                             low_memory=False) for a, b in chunks], ignore_index=True)
# empty chunks (e.g. May 2016) make pandas fall back to an object column; re-parse explicitly
lab["t_rec_utc"] = pd.to_datetime(lab["t_rec_utc"])

# JSOC record-set ranges "A-B" include BOTH ends, so the 00:00 TAI record on the 1st of each month is in
# two adjacent chunks.  Drop the second copy -- after asserting the copies are identical in every column.
def dedup(df, key, name):
    dup = df.duplicated(key, keep=False)
    for _, g in df[dup].groupby(key):
        assert len(g.astype(str).drop_duplicates()) == 1, f"{name}: non-identical duplicates {g.iloc[0][key].tolist()}"
    n = int(df.duplicated(key).sum())
    print(f"{name}: dropped {n} month-boundary duplicate rows (identical copies)")
    return df.drop_duplicates(key).reset_index(drop=True)

raw = dedup(raw, ["HARPNUM", "T_REC"], "raw")
lab = dedup(lab, ["harpnum", "t_rec_tai"], "labelled")
raw.to_csv(f"data/raw_sharp_{TAG}.csv", index=False)
lab.to_csv(f"data/labelled_{TAG}.csv", index=False)
print(f"\nwrote data/raw_sharp_{TAG}.csv ({len(raw)}) and data/labelled_{TAG}.csv ({len(lab)})")

# ------------------------------------------------------------------ full summary
r = raw.copy(); r.columns = [c.lower() for c in r.columns]
feat = ["usflux", "totusjh", "totpot", "meanshr", "r_value", "absnjzh", "savncpp", "area_acr",
        "lat_fwt", "lon_fwt"]
for c in feat + ["quality"]:
    r[c] = pd.to_numeric(r[c], errors="coerce")
miss = r["noaa_ars"].isna() | r["noaa_ars"].astype(str).str.strip().isin(["", "nan", "MISSING"])
nars = r["noaa_ars"].astype(str).str.count(",") + 1

print("\n" + "=" * 62 + f"\nFULL SUMMARY  {START} .. {END}\n" + "=" * 62)
print(f"raw SHARP rows retrieved : {len(r)}")
print("mapping status           :", {"missing": int(miss.sum()),
                                     "single": int((~miss & (nars == 1)).sum()),
                                     "multiple": int((~miss & (nars > 1)).sum())})
s1 = r[r["quality"] == 0]
s2 = s1[s1["lon_fwt"].abs() <= 45]
s3 = s2[~(s2["noaa_ars"].isna() | s2["noaa_ars"].astype(str).str.strip().isin(["", "nan", "MISSING"]))]
print(f"after QUALITY==0         : {len(s1)}")
print(f"after |LON_FWT|<=45      : {len(s2)}")
print(f"after mapping!=missing   : {len(s3)}   (labelled file: {len(lab)})")

npos = int(lab["flared_M1_next_24h"].sum())
print(f"positives                : {npos} / {len(lab)}  ({npos/len(lab):.2%})")

n = lab.groupby("harpnum").size()
print(f"distinct HARPNUMs        : {lab['harpnum'].nunique()}")
print(f"rows per HARPNUM         : mean {n.mean():.1f}  median {n.median():.0f}  min {n.min()}  max {n.max()}")
print(f"HARPNUMs with a positive : {int(lab.groupby('harpnum')['flared_M1_next_24h'].max().sum())}")

print("\nper-feature missingness (labelled file):")
for c in feat:
    print(f"  {c:9s} {pd.to_numeric(lab[c], errors='coerce').isna().mean()*100:6.2f}%")

print("\npositive rate per year:")
y = lab.groupby(lab["t_rec_utc"].dt.year)["flared_M1_next_24h"].agg(["size", "sum"])
y["rate"] = y["sum"] / y["size"]
for yr, row in y.iterrows():
    print(f"  {yr}  rows {int(row['size']):7d}  pos {int(row['sum']):6d}  {row['rate']:7.2%}")

# ------------------------------------------------------------------ region groups (decision B)
print("\nper year by region subset (primary = single; fallback = <=2; robustness = all)")
print("year   | single: rows   pos  posHARPs | <=2: rows   pos  posHARPs | all: rows   pos  posHARPs")
lab["year"] = lab["t_rec_utc"].dt.year
subsets = {"single": lab["noaa_ar_count"] == 1, "le2": lab["noaa_ar_count"] <= 2,
           "all": pd.Series(True, index=lab.index)}
for yr, g in lab.groupby("year"):
    cells = []
    for name, m in subsets.items():
        s = g[m.loc[g.index]]
        cells.append(f"{len(s):7d} {int(s['flared_M1_next_24h'].sum()):5d} "
                     f"{s.loc[s['flared_M1_next_24h'] == 1, 'harpnum'].nunique():8d}")
    print(f"{yr}   | " + " | ".join(cells))

# ------------------------------------------------------------------ missing-day rules (C, D)
if "history_incomplete" in lab:
    exc = []
    for a, b in chunks:
        f = f"data/excluded_missing_swpc_{a}_{b}.csv".replace("-", "")
        if os.path.exists(f):
            e = pd.read_csv(f, parse_dates=["t_rec_utc"])
            if len(e):
                exc.append(e)
    exc = pd.concat(exc) if exc else pd.DataFrame(columns=["harpnum", "t_rec_utc"])
    ey = exc["t_rec_utc"].dt.year.value_counts() if len(exc) else pd.Series(dtype=int)
    hy = lab.groupby("year")["history_incomplete"].sum()
    print("\nper year: rows EXCLUDED (label window hits a label-missing day) | rows history_incomplete (kept)")
    for yr in sorted(set(lab["year"]) | set(ey.index)):
        print(f"  {yr}   excluded {int(ey.get(yr, 0)):6d}   history_incomplete {int(hy.get(yr, 0)):6d}")
