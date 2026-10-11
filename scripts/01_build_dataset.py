"""Build a labelled SHARP dataset for flare forecasting (Bobra & Couvidat 2015 features).

Usage: python build_dataset.py [START] [END]     e.g. 2014-01-01 2014-02-01
Keyword queries only; no image segments.
"""
import sys, re, os
from datetime import datetime
import numpy as np, pandas as pd, drms
from astropy.time import Time
import astropy.units as u
import flares, swpc

if len(sys.argv) not in (1, 3):
    sys.exit("usage: python build_dataset.py [START END]   dates as YYYY-MM-DD, START inclusive, END exclusive")
START = sys.argv[1] if len(sys.argv) > 1 else "2014-01-01"
END   = sys.argv[2] if len(sys.argv) > 2 else "2014-02-01"
for d in (START, END):                                    # fail loudly on a typo'd date
    datetime.strptime(d, "%Y-%m-%d")
if START >= END:
    sys.exit(f"START ({START}) must be before END ({END})")
TAG   = f"{START}_{END}".replace("-", "")

# Flare label source. ONE switch for the whole range -- never per year (user, 2026-09-21).
#   swpc = SWPC original daily event reports (default)   hek = the old HEK/SWPC copy, kept for comparison
FLARE_SOURCE = os.environ.get("FLARE_SOURCE", "swpc")
assert FLARE_SOURCE in ("swpc", "hek"), FLARE_SOURCE
LABEL_DIR = "data" if FLARE_SOURCE == "swpc" else "data/labels_hek"
# DIAGNOSTIC ONLY (ablation): LON_LIMIT changes the longitude cut; DIAG_DIR sends every output elsewhere so the
# primary files can never be overwritten.  Defaults reproduce the primary pipeline exactly.
LON_LIMIT = float(os.environ.get("LON_LIMIT", "45"))
if os.environ.get("DIAG_DIR"):
    LABEL_DIR = os.environ["DIAG_DIR"]
assert LABEL_DIR != "data" or (LON_LIMIT == 45 and os.environ.get("FLARE_SCALE", "K2") == "K2"), \
    "diagnostic settings must write to DIAG_DIR"
os.makedirs(LABEL_DIR, exist_ok=True)


def jsoc(d):
    """YYYY-MM-DD -> JSOC date literal YYYY.MM.DD_TAI"""
    return d.replace("-", ".") + "_TAI"


# Confirmation set (user, frozen 2026-09-21): the FINAL chunk ends at 2026.08.16_23:00_TAI, inclusive.
# JSOC_END_OVERRIDE="2026-08-17|2026.08.16_23:00_TAI" replaces the query end only for the chunk whose END matches.
_ov = os.environ.get("JSOC_END_OVERRIDE", "")
JSOC_END = _ov.split("|")[1] if _ov and _ov.split("|")[0] == END else jsoc(END)


def banner():
    print("=" * 62)
    print(f"  argv          : {sys.argv[1:] or '(none -> defaults)'}")
    print(f"  START (CLI)   : {START}      END (CLI, exclusive): {END}")
    print(f"  START (JSOC)  : {jsoc(START)}   END (JSOC): {jsoc(END)}")
    print(f"  JSOC record set: hmi.sharp_cea_720s[][{jsoc(START)}-{JSOC_END}@1h]")
    print(f"  flare source  : {FLARE_SOURCE}   labels -> {LABEL_DIR}/")
    print("=" * 62)

FEATURES = ["USFLUX","TOTUSJH","TOTPOT","MEANSHR","R_VALUE","ABSNJZH","SAVNCPP","AREA_ACR"]
# decision O: Bobra & Couvidat (2015) keywords that exist in hmi.sharp_cea_720s (see fetch_extra.py)
EXTRA_COLS = ["TOTUSJZ","MEANPOT","SHRGT45","MEANGAM","MEANGBT","MEANGBZ","MEANGBH","MEANJZH","MEANJZD","MEANALP"]
KEYS = ["HARPNUM","T_REC","NOAA_ARS","NOAA_NUM","QUALITY","LAT_FWT","LON_FWT"] + FEATURES


def step(msg): print(f"\n=== {msg} ===")


# ---------------------------------------------------------------- STEP 1
banner()
step("STEP 1  SHARP keywords")
qs = f"hmi.sharp_cea_720s[][{jsoc(START)}-{JSOC_END}@1h]"
RAW = f"data/raw_sharp_{TAG}.csv"
if os.path.exists(RAW):
    # relabelling never re-downloads.  NOAA_ARS must stay a string: a month whose regions are
    # all single numbers would otherwise read back as float ("11944.0") and fail the digit test.
    raw = pd.read_csv(RAW, dtype={"NOAA_ARS": str, "T_REC": str})
    print(f"loaded cached {RAW}  (no JSOC query)")
else:
    print("query:", qs)
    raw = drms.Client().query(qs, key=",".join(KEYS))
    raw.to_csv(RAW, index=False)
    print(f"saved {RAW}")
print(f"SHARP rows retrieved: {len(raw)}")

# Decision O: the extra Bobra & Couvidat keywords, fetched separately for the same record set
# (fetch_extra.py).  Merged 1:1 on HARPNUM + T_REC; anything but an exact match stops the build.
EXTRA_FILE = f"data/raw_sharp_extra_{TAG}.csv"
if os.path.exists(EXTRA_FILE):
    ex = pd.read_csv(EXTRA_FILE, dtype={"T_REC": str})
    assert not ex.duplicated(["HARPNUM", "T_REC"]).any(), "duplicate HARPNUM+T_REC in extras"
    n_raw = len(raw)
    raw = raw.merge(ex, on=["HARPNUM", "T_REC"], how="left", validate="one_to_one", indicator=True)
    unmatched = int((raw["_merge"] != "both").sum())
    assert unmatched == 0 and len(ex) == n_raw, \
        f"extras do not match raw 1:1: raw {n_raw}, extras {len(ex)}, unmatched {unmatched}"
    raw = raw.drop(columns="_merge")
    print(f"merged {len(EXTRA_COLS)} extra keywords from {EXTRA_FILE}: 1:1, {n_raw} rows")
else:
    EXTRA_COLS = []
    print(f"(no {EXTRA_FILE}; extra keywords absent from this chunk's output)")

df = raw.copy()
df.columns = [x.lower() for x in df.columns]
df = df.rename(columns={"t_rec": "t_rec_tai"})

# expected hours: each HARP's own on-disk span, at 1h spacing
exp = 0
for h, g in df.groupby("harpnum"):
    t = pd.to_datetime(g["t_rec_tai"].str.replace("_TAI", "", regex=False), format="%Y.%m.%d_%H:%M:%S")
    exp += int((t.max() - t.min()).total_seconds() // 3600) + 1
print(f"expected hourly records (per-HARP span): {exp}; present: {len(df)}; missing: {exp - len(df)}")

# ---------------------------------------------------------------- STEP 3 (times first, needed for the padded flare window)
step("STEP 3  time handling (TAI -> UTC)")
tai = Time([s.replace("_TAI", "").replace(".", "-", 2).replace("_", " ") for s in df["t_rec_tai"]], format="iso", scale="tai")
df["t_rec_utc"] = pd.to_datetime(tai.utc.isot)
print("example:", df["t_rec_tai"].iloc[0], "->", df["t_rec_utc"].iloc[0], "UTC")

# ---------------------------------------------------------------- STEP 2
step("STEP 2  flare catalogue (HEK / SWPC)")
lo = (df["t_rec_utc"].min() - pd.Timedelta(hours=48)).to_pydatetime()
hi = (df["t_rec_utc"].max() + pd.Timedelta(hours=24)).to_pydatetime()
print(f"padded window: {lo} .. {hi}")
if FLARE_SOURCE == "swpc":
    swpc.download_range(lo, hi)                   # no-op for days already cached
    fl, m1 = swpc.fetch(lo, hi)
else:
    fl, m1 = flares.fetch(lo, hi)

# ---------------------------------------------------------------- STEP 4
step("STEP 4  NOAA mapping")
def ars(s):
    if s is None or (isinstance(s, float) and np.isnan(s)) or str(s).strip() in ("", "MISSING", "nan"):
        return []
    return [int(x) for x in str(s).split(",") if x.strip().isdigit()]

df["_ars"] = df["noaa_ars"].apply(ars)
df["noaa_ar_count"] = df["_ars"].apply(len)
df["noaa_mapping_status"] = np.where(df["noaa_ar_count"] == 0, "missing",
                             np.where(df["noaa_ar_count"] == 1, "single", "multiple"))
print(df["noaa_mapping_status"].value_counts().to_dict())

# ---------------------------------------------------------------- STEP 6
step("STEP 6  filtering")
print(f"in: {len(df)}")
df = df[df["quality"].astype(int) == 0];              print(f"after QUALITY==0: {len(df)}")
df = df[df["lon_fwt"].abs() <= LON_LIMIT];            print(f"after |LON_FWT|<={LON_LIMIT:g}: {len(df)}")
nmiss = (df["noaa_mapping_status"] == "missing").sum()
df = df[df["noaa_mapping_status"] != "missing"];      print(f"after mapping!=missing: {len(df)}  (excluded {nmiss} missing-mapping rows)")

# ---------------------------------------------------------------- STEP 5
step("STEP 5  labels")
by_ar_m1 = {k: np.sort(v["start"].values) for k, v in m1.groupby("noaa_ar")}
by_ar_all = {k: v[["start", "cls"]].sort_values("start") for k, v in fl.groupby("noaa_ar")}

def label(row):
    t = row["t_rec_utc"]
    hi24 = t + pd.Timedelta(hours=24)
    lo48 = t - pd.Timedelta(hours=48)
    pos = 0
    prev = []
    for ar in row["_ars"]:
        s = by_ar_m1.get(ar)
        if s is not None and ((s > np.datetime64(t)) & (s <= np.datetime64(hi24))).any():
            pos = 1
        g = by_ar_all.get(ar)
        if g is not None:
            w = g[(g["start"] >= lo48) & (g["start"] < t)]
            prev.append(w)
    p = pd.concat(prev).drop_duplicates() if prev else pd.DataFrame(columns=["start", "cls"])
    return pd.Series([pos, len(p),
                      (p["cls"] == "C").sum(), (p["cls"] == "M").sum(), (p["cls"] == "X").sum()])

LABEL_COLS = ["flared_M1_next_24h", "n_flares_prev_48h", "n_C_prev_48h", "n_M_prev_48h", "n_X_prev_48h"]
if len(df):
    df[LABEL_COLS] = df.apply(label, axis=1)
else:
    # a chunk can be legitimately empty (e.g. May 2016: every record carries QUALITY bit 0x80)
    for c in LABEL_COLS:
        df[c] = pd.Series(dtype=int)
# region_group: the dataset is NOT filtered by region count; each analysis selects its subset.
#   primary = "1" (single region), fallback = "1"+"2", robustness = all  (user, 2026-09-21)
df["region_group"] = np.where(df["noaa_ar_count"] == 1, "1",
                      np.where(df["noaa_ar_count"] == 2, "2", "3+"))

if FLARE_SOURCE == "swpc":
    # A day with no SWPC report means "flares unknown", not "no flares". Any row whose label
    # window (t, t+24h] overlaps such a day has an unknown label and is excluded (user, 2026-09-21).
    # Overlap with day D = [D, D+1d):  t < D+1d  and  t+24h > D.
    unknown = pd.Series(False, index=df.index)
    for d in swpc.label_missing_days():          # 404 days + empty reports with GOES max >= M1
        D = pd.Timestamp(d)
        unknown |= (df["t_rec_utc"] < D + pd.Timedelta(days=1)) & \
                   (df["t_rec_utc"] + pd.Timedelta(hours=24) > D)
    # history_incomplete: the backward window (t-48h, t] overlaps a missing SWPC day, so the
    # n_*_prev_48h counts may be undercounted. Rows are KEPT (usable for gate training on SHARP
    # features only); the cohort analysis excludes them, since flare history is its mandatory
    # control (user, 2026-09-21).  Overlap of (t-48h, t] with [D, D+1d): t-48h < D+1d and t >= D.
    hist = pd.Series(False, index=df.index)
    for d in swpc.history_incomplete_days():     # 404 days + empty reports with GOES max >= C1
        D = pd.Timestamp(d)
        hist |= (df["t_rec_utc"] - pd.Timedelta(hours=48) < D + pd.Timedelta(days=1)) & \
                (df["t_rec_utc"] >= D)
    df["history_incomplete"] = hist
    df.loc[unknown, ["harpnum", "t_rec_utc"]].to_csv(f"{LABEL_DIR}/excluded_missing_swpc_{TAG}.csv", index=False)
    print(f"label window overlaps a label-missing day: {int(unknown.sum())} rows -> label unknown, excluded")
    df = df[~unknown]
    print(f"history_incomplete (prev-48h window overlaps a history-incomplete day): "
          f"{int(df['history_incomplete'].sum())} rows kept, flagged")
else:
    df["history_incomplete"] = False    # HEK comparison labels: missing-day rule not applied

npos = int(df["flared_M1_next_24h"].sum())
print(f"positives: {npos} / {len(df)}  ({npos/max(len(df),1):.2%})")
for g in ["1", "2", "3+"]:
    sub = df[df["region_group"] == g]
    print(f"  region_group {g:2s}: rows {len(sub):6d}  positives {int(sub['flared_M1_next_24h'].sum()):5d}"
          f"  positive HARPs {sub.loc[sub['flared_M1_next_24h'] == 1, 'harpnum'].nunique()}")

# ---------------------------------------------------------------- STEP 7
step("STEP 7  missing values")
feat = [f.lower() for f in FEATURES + EXTRA_COLS] + ["lat_fwt", "lon_fwt"]
for col in feat:
    df[col] = pd.to_numeric(df[col], errors="coerce")
# drms already returns JSOC MISSING as NaN for float keywords; to_numeric above catches the rest.
# ponytail: no magnitude-based sentinel mask -- USFLUX/TOTPOT are legitimately ~1e22.
for col in feat:
    print(f"  {col:9s} {df[col].isna().mean()*100:6.2f}% missing")

out = ["harpnum","t_rec_tai","t_rec_utc","noaa_ars","noaa_ar_count","noaa_mapping_status","region_group","history_incomplete",
       "usflux","totusjh","totpot","meanshr","r_value","absnjzh","savncpp","area_acr",
       "lat_fwt","lon_fwt","quality","flared_M1_next_24h","n_flares_prev_48h",
       "n_C_prev_48h","n_M_prev_48h","n_X_prev_48h"]
out += [c.lower() for c in EXTRA_COLS]
df[out].to_csv(f"{LABEL_DIR}/labelled_{TAG}.csv", index=False)
print(f"\nsaved {LABEL_DIR}/labelled_{TAG}.csv  ({len(df)} rows, flare source: {FLARE_SOURCE})")
